import copy
import hashlib
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import run_production_race as race

from diagnostic_sharing import _user_review_diagnosis
from msds_validation import (
    PageMapValidationError,
    normalize_page_indexes,
    validate_component_image_page_map,
)
from run_production_race import (
    GoldenValidationError,
    build_inventory,
    load_cases,
    normalize_content,
    normalize_product_name_for_golden,
    parse_components_with_source,
    select_cases,
)
from result_safety import RuntimeExtractionResult
from tools.classify_golden_cases import DEFAULT_OUTPUT_DIR, classify_pdf, load_taxonomy, validate_tags
from tools.update_golden import GoldenUpdateError, apply_approved_candidate, update_golden_file


ROOT = Path(__file__).resolve().parents[1]


class GeneralizedDiagnosisTests(unittest.TestCase):
    def _diagnose(self, filename="unrelated.pdf", evidence=True, cas="140-11-4"):
        diagnostic = {}
        if evidence:
            diagnostic = {"trace": {
                "source_column_role": "classification", "selected_value": "1,2,3",
                "same_row_candidates": [{"source_column_role": "content", "value": "0.5%"}],
            }}
        review = {
            "error_types": ["함유량 오류"],
            "component_corrections": [{"cas": cas, "actual": "3%", "expected": "0.5%"}],
        }
        return _user_review_diagnosis({"filename": filename}, diagnostic, review)

    def test_structure_without_special_filename_creates_reason(self):
        self.assertEqual(self._diagnose()["reason_code"], "CLASSIFICATION_COLUMN_MISREAD_AS_CONCENTRATION")

    def test_special_filename_without_structure_does_not_create_reason(self):
        diagnosis = self._diagnose("008_★msds_사라퐁.pdf", evidence=False)
        self.assertEqual(diagnosis["reason_code"], "USER_REPORTED_RESULT_MISMATCH")

    def test_other_cas_and_values_use_same_rule(self):
        diagnosis = self._diagnose(cas="64-17-5")
        self.assertEqual(diagnosis["component_corrections"][0]["cas"], "64-17-5")

    def test_operating_files_do_not_contain_forbidden_case_values(self):
        files = [
            "msds_engine_v6.py", "msds_engine_v7.py", "msds_core.py", "batch_pipeline.py",
            "diagnostic_sharing.py", "smu_gui.py", "section_detector_v7.py",
        ]
        forbidden = ["사라퐁", "피칼", "1310-73-2", "7732-18-5", "008_★msds_사라퐁", "051_★금속광택제"]
        found = {name: value for name in files for value in forbidden if value in (ROOT / name).read_text(encoding="utf-8")}
        self.assertEqual(found, {})


class ClassificationArtifactBoundaryTests(unittest.TestCase):
    def test_generated_review_defaults_outside_managed_golden_directory(self):
        self.assertEqual(DEFAULT_OUTPUT_DIR, ROOT / "artifacts" / "golden_classification")
        self.assertNotEqual(DEFAULT_OUTPUT_DIR.parent, ROOT / "golden")


class V6CompatibilityTests(unittest.TestCase):
    def test_public_process_pdf_signature_is_preserved(self):
        import msds_engine_v6
        self.assertEqual(
            list(inspect.signature(msds_engine_v6.process_pdf).parameters),
            ["pdf_path", "log_func", "bypass_cache", "cancel_check", "checkpoint_func"],
        )
        self.assertIs(msds_engine_v6.analyze_msds, msds_engine_v6.process_pdf)

    def test_paid_ai_guard_prevents_provider_calls(self):
        import msds_engine_v6
        engine = msds_engine_v6.MSDSEngineV6()
        with patch.dict(os.environ, {"ANTIGRAVITY_DISABLE_PAID_AI": "1"}), patch.object(
            engine, "_invoke_ai_provider", side_effect=AssertionError("provider called")
        ):
            self.assertIsNone(engine.call_llm_router({"contents": [{"parts": [{"text": "generic"}]}]}))


class PageMapTests(unittest.TestCase):
    def test_dict_map_and_order_preserving_deduplication(self):
        self.assertEqual(normalize_page_indexes([{"page_index": 2}, {"page_index": 3}, {"page_index": 2}]), [2, 3])

    def test_single_target(self):
        result = validate_component_image_page_map({"target_page_index": 2, "source_page_indexes": [2]})
        self.assertEqual(result["target_page_indexes"], [2])

    def test_multiple_targets(self):
        result = validate_component_image_page_map({"target_page_indexes": [2, 3], "image_page_map": [{"image_index": 0, "page_index": 2}, {"image_index": 1, "page_index": 3}], "image_count": 2})
        self.assertEqual(result["image_page_indexes"], [2, 3])

    def test_image_count_mismatch(self):
        with self.assertRaisesRegex(PageMapValidationError, "이미지 수") as caught:
            validate_component_image_page_map({"image_page_map": [{"page_index": 2}], "image_count": 2})
        self.assertEqual(caught.exception.error_code, "COMPONENT_IMAGE_COUNT_MISMATCH")

    def test_source_and_map_contradiction(self):
        with self.assertRaises(PageMapValidationError) as caught:
            validate_component_image_page_map({"source_page_indexes": [2], "image_page_map": [{"page_index": 3}]})
        self.assertEqual(caught.exception.error_code, "COMPONENT_IMAGE_PAGE_MAP_INVALID")

    def test_invalid_indexes(self):
        for value in (-1, "2", True, 4):
            with self.subTest(value=value), self.assertRaises(PageMapValidationError):
                normalize_page_indexes(value, page_count=4)

    def test_target_must_be_in_source(self):
        with self.assertRaises(PageMapValidationError) as caught:
            validate_component_image_page_map({"target_page_indexes": [2, 3], "source_page_indexes": [2]})
        self.assertEqual(caught.exception.error_code, "COMPONENT_IMAGE_PAGE_MISMATCH")


class ClassificationTests(unittest.TestCase):
    taxonomy = load_taxonomy()

    def _pdf(self, root, pages):
        path = Path(root) / "sample.pdf"
        document = fitz.open()
        for text in pages:
            page = document.new_page()
            if text:
                page.insert_textbox(fitz.Rect(40, 40, 550, 800), text, fontsize=9)
        document.save(path)
        document.close()
        return path

    def _case(self, contents=None):
        return {"product_name": {"expected": "generic cleaner"}, "components": [{"content_expected": value} for value in (contents or ["10%"])]}

    def test_digital_and_content_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = "1. 화학제품과 회사에 관한 정보\n" + "제품 정보 " * 20 + "\n3. 구성성분의 명칭 및 함유량\nCAS No 함유량 화학물질명\n" + "64-17-5 10% " * 12
            result = classify_pdf(self._pdf(tmp, [text]), self._case(["<1%", "10~20%"]), self.taxonomy)
            self.assertIn("digital", result["tags"]["document"])
            self.assertIn("content-less-than", result["tags"]["content"])
            self.assertIn("content-range", result["tags"]["content"])

    def test_scanned_is_low_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = classify_pdf(self._pdf(tmp, [""]), self._case(), self.taxonomy)
            self.assertIn("scanned", result["tags"]["document"])
            self.assertEqual(result["classification"]["confidence"], "LOW")
            self.assertTrue(result["classification"]["needs_review"])

    def test_mixed_and_late_multipage_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            intro = "SECTION 1. IDENTIFICATION\n" + "product information " * 15
            section = "SECTION 3. COMPOSITION INGREDIENTS\n" + "CAS content chemical name " * 10
            result = classify_pdf(self._pdf(tmp, [intro, "", section, "continued table " * 15]), self._case(), self.taxonomy)
            self.assertIn("mixed", result["tags"]["document"])
            self.assertIn("section3-late-page", result["tags"]["section"])
            self.assertIn("section3-multipage", result["tags"]["section"])

    def test_secret_and_balance_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = classify_pdf(self._pdf(tmp, [""]), self._case(["영업비밀", "Balance"]), self.taxonomy)
            self.assertIn("content-text-secret", result["tags"]["content"])
            self.assertIn("content-balance", result["tags"]["content"])

    def test_taxonomy_rejects_unknown_tag(self):
        tags = {key: [] for key in ("document", "section", "layout", "content", "failure_modes", "product")}
        tags["layout"] = ["unknown-layout"]
        with self.assertRaisesRegex(ValueError, "taxonomy 외 태그"):
            validate_tags(tags, self.taxonomy)


class SelectionAndSafetyTests(unittest.TestCase):
    def setUp(self):
        self.cases = [
            {"id": "001", "regression_tier": "core", "tags": {"content": ["content-range"], "failure_modes": ["cas-content-pairing"]}},
            {"id": "002", "regression_tier": "full", "tags": {"layout": ["table-image"], "content": ["content-less-than"], "failure_modes": []}},
            {"id": "003", "regression_tier": "core", "tags": {"layout": ["table-image"], "content": ["content-range"], "failure_modes": []}},
        ]

    def test_ids(self):
        self.assertEqual([c["id"] for c in select_cases(self.cases, ids={"002"})], ["002"])

    def test_tag_or(self):
        self.assertEqual(len(select_cases(self.cases, tags=["content-less-than", "content-range"])), 3)

    def test_tag_and(self):
        selected = select_cases(self.cases, tags=["table-image", "content-range"], match_all=True)
        self.assertEqual([c["id"] for c in selected], ["003"])

    def test_failure_mode(self):
        self.assertEqual([c["id"] for c in select_cases(self.cases, failure_modes=["cas-content-pairing"])], ["001"])

    def test_tier_and_all(self):
        self.assertEqual(len(select_cases(self.cases, tier="core")), 2)
        self.assertEqual(len(select_cases(self.cases, select_all=True)), 3)

    def test_zero_selection(self):
        self.assertEqual(select_cases(self.cases, ids={"999"}), [])

    def test_missing_golden_fails(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(GoldenValidationError) as caught:
            load_cases(Path(tmp) / "missing.json", Path(tmp))
        self.assertEqual(caught.exception.code, "GOLDEN_FILE_MISSING")

    def test_filename_mismatch_is_reported_without_hash_remap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_dir = root / "pdfs"
            pdf_dir.mkdir()
            pdf = pdf_dir / "002_different.pdf"
            pdf.write_bytes(b"pdf")
            golden = root / "golden.json"
            golden.write_text(json.dumps({"cases": [{"id": "001", "file": "001_expected.pdf", "source_sha256": hashlib.sha256(b"pdf").hexdigest()}]}), encoding="utf-8")
            _, warnings = load_cases(golden, pdf_dir)
            self.assertTrue(any(value.startswith("GOLDEN_PDF_MISSING") for value in warnings))
            self.assertTrue(any(value.startswith("PDF_NOT_REGISTERED") for value in warnings))

    def test_selected_hash_mismatch_fails_before_extraction(self):
        with self.assertRaises(GoldenValidationError) as caught:
            race.run_case({"id": "001", "source_sha256": "expected", "_hash_mismatch": "actual", "_pdf_path": "unused.pdf"})
        self.assertEqual(caught.exception.code, "GOLDEN_SOURCE_HASH_MISMATCH")

    def test_content_operator_direction_is_preserved(self):
        self.assertEqual(normalize_content("10 ～ 20 %"), normalize_content("10 - 20%"))
        self.assertNotEqual(normalize_content("<1%"), normalize_content(">1%"))
        self.assertNotEqual(normalize_content("≤1%"), normalize_content("≥1%"))


class GoldenComparisonTests(unittest.TestCase):
    def _case(self, name="Product", components=None, **extra):
        return {
            "product_name": {"expected": name, "allowed_variants": []},
            "components": components if components is not None else [
                {"cas": "64-17-5", "content_expected": "10%"}
            ],
            **extra,
        }

    def _result(self, name="Product", components=None):
        return {
            "제품명": name,
            "components": components if components is not None else [
                {"cas": "64-17-5", "content": "10%"}
            ],
        }

    def _reason_codes(self, case, result):
        return [item.get("reason_code") for item in race.compare_case(case, result)]

    def test_expected_components_exactly_match(self):
        self.assertEqual(race.compare_case(self._case(), self._result()), [])

    def test_missing_expected_cas_fails(self):
        codes = self._reason_codes(self._case(), self._result(components=[]))
        self.assertEqual(codes, ["GOLDEN_MISSING_CAS"])

    def test_unexpected_actual_cas_fails(self):
        result = self._result(components=[
            {"cas": "64-17-5", "content": "10%"},
            {"cas": "67-64-1", "content": "90%"},
        ])
        codes = self._reason_codes(self._case(), result)
        self.assertIn("GOLDEN_UNEXPECTED_CAS", codes)

    def test_component_content_mismatch_fails(self):
        result = self._result(components=[{"cas": "64-17-5", "content": "20%"}])
        codes = self._reason_codes(self._case(), result)
        self.assertEqual(codes, ["GOLDEN_CONTENT_MISMATCH"])

    def test_duplicate_cas_with_different_values_fails(self):
        result = self._result(components=[
            {"cas": "64-17-5", "content": "10%"},
            {"cas": "64-17-5", "content": "20%"},
        ])
        differences = race.compare_case(self._case(), result)
        duplicate = next(item for item in differences if item.get("reason_code") == "GOLDEN_DUPLICATE_CAS")
        self.assertEqual(duplicate["actual_values"], ["10%", "20%"])

    def test_duplicate_cas_with_same_value_is_reported(self):
        result = self._result(components=[
            {"cas": "64-17-5", "content": "10%"},
            {"cas": "64-17-5", "content": "10%"},
        ])
        self.assertIn("GOLDEN_DUPLICATE_CAS", self._reason_codes(self._case(), result))

    def test_zero_actual_components_reports_all_missing(self):
        case = self._case(components=[
            {"cas": "64-17-5", "content_expected": "10%"},
            {"cas": "67-64-1", "content_expected": "20%"},
        ])
        codes = self._reason_codes(case, self._result(components=[]))
        self.assertEqual(codes.count("GOLDEN_MISSING_CAS"), 2)

    def test_review_only_case_skips_answer_comparison(self):
        case = self._case(components=[], _review_only=True)
        result = self._result(components=[{"cas": "67-64-1", "content": "90%"}])
        self.assertEqual(race.compare_case(case, result), [])

    def test_review_only_is_not_inferred_from_empty_golden_components(self):
        case = self._case(components=[])
        result = self._result(components=[{"cas": "67-64-1", "content": "90%"}])
        self.assertIn("GOLDEN_UNEXPECTED_CAS", self._reason_codes(case, result))

    def test_content_operator_direction_remains_distinct(self):
        case = self._case(components=[{"cas": "64-17-5", "content_expected": "<1%"}])
        result = self._result(components=[{"cas": "64-17-5", "content": ">1%"}])
        self.assertIn("GOLDEN_CONTENT_MISMATCH", self._reason_codes(case, result))

    def test_content_range_symbols_remain_equivalent(self):
        case = self._case(components=[{"cas": "64-17-5", "content_expected": "10 ～ 20 %"}])
        result = self._result(components=[{"cas": "64-17-5", "content": "10 - 20%"}])
        self.assertEqual(race.compare_case(case, result), [])

    def test_product_spacing_and_delimiters_match(self):
        self.assertEqual(
            normalize_product_name_for_golden("MICONOL C2M(H)"),
            normalize_product_name_for_golden("MICONOL-C2M (H)"),
        )

    def test_product_trademark_notation_matches(self):
        self.assertEqual(
            normalize_product_name_for_golden("PRODUCT NAME™"),
            normalize_product_name_for_golden("Product Name TM"),
        )

    def test_product_underscore_and_hyphen_match(self):
        self.assertEqual(
            normalize_product_name_for_golden("ABC_123"),
            normalize_product_name_for_golden("ABC-123"),
        )

    def test_korean_product_spacing_matches(self):
        self.assertEqual(
            normalize_product_name_for_golden("가나다 제품"),
            normalize_product_name_for_golden("가나다제품"),
        )

    def test_allowed_product_variant_is_normalized_for_comparison(self):
        case = self._case(name="MICONOL-C2M", components=[])
        case["product_name"]["allowed_variants"] = ["MICONOL-C2M (H)"]
        result = self._result(name="MICONOL C2M(H)", components=[])
        self.assertEqual(race.compare_case(case, result), [])

    def test_different_model_number_fails(self):
        case = self._case(name="MICONOL C2M(H)", components=[])
        result = self._result(name="MICONOL C3M(H)", components=[])
        self.assertIn("GOLDEN_PRODUCT_NAME_MISMATCH", self._reason_codes(case, result))

    def test_different_korean_product_fails(self):
        case = self._case(name="금속광택제", components=[])
        result = self._result(name="금속세정제", components=[])
        self.assertIn("GOLDEN_PRODUCT_NAME_MISMATCH", self._reason_codes(case, result))

    def test_extra_digit_fails(self):
        case = self._case(name="ABC-100", components=[])
        result = self._result(name="ABC-1000", components=[])
        self.assertIn("GOLDEN_PRODUCT_NAME_MISMATCH", self._reason_codes(case, result))

    def test_company_prefix_does_not_hide_different_product(self):
        case = self._case(name="회사명 제품A", components=[])
        result = self._result(name="회사명 제품B", components=[])
        self.assertIn("GOLDEN_PRODUCT_NAME_MISMATCH", self._reason_codes(case, result))


class FinalInventoryTests(unittest.TestCase):
    def _write_golden(self, root, cases):
        path = Path(root) / "golden.json"
        path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
        return path

    def test_registered_pdf_matches_id_filename_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdfs"
            pdf_dir.mkdir()
            pdf = pdf_dir / "001_sample.pdf"
            pdf.write_bytes(b"one")
            golden = self._write_golden(tmp, [{
                "id": "001", "file": pdf.name,
                "source_sha256": hashlib.sha256(b"one").hexdigest(),
            }])
            cases, warnings, summary = build_inventory(golden, pdf_dir)
            self.assertEqual(warnings, [])
            self.assertTrue(cases[0]["_registered_match"])
            self.assertEqual(summary["matched_case_count"], 1)

    def test_alias_match_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdfs"
            pdf_dir.mkdir()
            pdf = pdf_dir / "001_actual.pdf"
            pdf.write_bytes(b"one")
            golden = self._write_golden(tmp, [{
                "id": "001", "file": "001_old.pdf", "aliases": [pdf.name],
                "source_sha256": hashlib.sha256(b"one").hexdigest(),
            }])
            _, warnings, summary = build_inventory(golden, pdf_dir)
            self.assertEqual(warnings, [])
            self.assertEqual(summary["alias_match_count"], 1)

    def test_missing_golden_pdf_is_not_selected_for_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdfs"
            pdf_dir.mkdir()
            golden = self._write_golden(tmp, [{
                "id": "001", "file": "001_missing.pdf", "source_sha256": "a" * 64,
            }])
            cases, warnings, _ = build_inventory(golden, pdf_dir)
            self.assertTrue(any(item.startswith("GOLDEN_PDF_MISSING") for item in warnings))
            self.assertEqual(select_cases(cases, select_all=True), [])

    def test_registered_only_excludes_unregistered_and_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdfs"
            pdf_dir.mkdir()
            good = pdf_dir / "001_good.pdf"
            bad = pdf_dir / "002_bad.pdf"
            extra = pdf_dir / "003_extra.pdf"
            good.write_bytes(b"good")
            bad.write_bytes(b"bad")
            extra.write_bytes(b"extra")
            golden = self._write_golden(tmp, [
                {"id": "001", "file": good.name, "source_sha256": hashlib.sha256(b"good").hexdigest()},
                {"id": "002", "file": bad.name, "source_sha256": "b" * 64},
            ])
            cases, _, _ = build_inventory(golden, pdf_dir)
            selected = select_cases(cases, select_all=True, registered_only=True)
            self.assertEqual([case["id"] for case in selected], ["001"])

    def test_duplicate_physical_sha_is_selected_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdfs"
            pdf_dir.mkdir()
            first = pdf_dir / "001_a.pdf"
            second = pdf_dir / "002_b.pdf"
            first.write_bytes(b"same")
            second.write_bytes(b"same")
            digest = hashlib.sha256(b"same").hexdigest()
            golden = self._write_golden(tmp, [
                {"id": "001", "file": first.name, "source_sha256": digest},
                {"id": "002", "file": second.name, "source_sha256": digest},
            ])
            cases, warnings, _ = build_inventory(golden, pdf_dir)
            self.assertTrue(any(item.startswith("DUPLICATE_PHYSICAL_PDF") for item in warnings))
            self.assertEqual(len(select_cases(cases, select_all=True)), 1)

    def test_filename_mismatch_has_dedicated_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = Path(tmp) / "pdfs"
            pdf_dir.mkdir()
            (pdf_dir / "001_actual.pdf").write_bytes(b"one")
            golden = self._write_golden(tmp, [{
                "id": "001", "file": "001_expected.pdf",
                "source_sha256": hashlib.sha256(b"one").hexdigest(),
            }])
            _, warnings, _ = build_inventory(golden, pdf_dir)
            self.assertTrue(any(item.startswith("GOLDEN_FILENAME_MISMATCH") for item in warnings))


class ComponentSourceSelectionTests(unittest.TestCase):
    def test_empty_components_falls_through_to_component_string(self):
        parsed, source = parse_components_with_source({
            "components": [], "함유량": [], "구성성분": "64-17-5(10%)",
        })
        self.assertEqual(parsed, {"64-17-5": ["10%"]})
        self.assertEqual(source, "구성성분")

    def test_empty_content_list_falls_through_to_component_list(self):
        parsed, source = parse_components_with_source({
            "함유량": [], "구성성분": [{"cas": "64-17-5", "content": "10%"}],
        })
        self.assertEqual(parsed, {"64-17-5": ["10%"]})
        self.assertEqual(source, "구성성분")

    def test_first_valid_structured_field_wins_without_merging(self):
        parsed, source = parse_components_with_source({
            "components": [{"cas": "64-17-5", "content": "10%"}],
            "함유량": [{"cas": "67-64-1", "content": "20%"}],
        })
        self.assertEqual(parsed, {"64-17-5": ["10%"]})
        self.assertEqual(source, "components")

    def test_duplicate_rows_in_selected_field_are_preserved(self):
        parsed, source = parse_components_with_source({"components": [
            {"cas": "64-17-5", "content": "10%"},
            {"cas": "64-17-5", "content": "20%"},
        ]})
        self.assertEqual(parsed["64-17-5"], ["10%", "20%"])
        self.assertEqual(source, "components")


class ProductNameRegressionModeTests(unittest.TestCase):
    def _case(self):
        return {
            "id": "001", "file": "001.pdf", "_pdf_path": "001.pdf",
            "source_sha256": "a" * 64,
            "product_name": {"expected": "Expected", "allowed_variants": []},
            "components": [{"cas": "64-17-5", "content_expected": "10%"}],
        }

    def _result(self, product, *, calls=1, evidence="Section 1 product evidence"):
        return RuntimeExtractionResult({
            "제품명": product,
            "components": [{"cas": "64-17-5", "content": "10%"}],
            "metrics": {"ai": [
                {"purpose": "product_name", "provider": "vertex"} for _ in range(calls)
            ]},
        }, shadow_context={
            "product_name_evidence_text": evidence,
            "product_name_evidence_page": 0,
        })

    def test_no_paid_ai_skips_product_comparison_and_records_unverified(self):
        seen = []
        def process_pdf(*args, **kwargs):
            seen.append(os.environ.get("ANTIGRAVITY_DISABLE_PAID_AI"))
            return self._result("Different", calls=0)
        run = race.run_case(self._case(), process_pdf_func=process_pdf)
        self.assertEqual(run["product_name_status"], "product_name_not_verified_ai_disabled")
        self.assertNotIn("GOLDEN_PRODUCT_NAME_MISMATCH", [d.get("reason_code") for d in run["differences"]])
        self.assertEqual(seen, ["1"])

    def test_with_product_ai_compares_product_and_uses_product_only_guard(self):
        seen = []
        def process_pdf(*args, **kwargs):
            seen.append((os.environ.get("ANTIGRAVITY_DISABLE_PAID_AI"), os.environ.get("ANTIGRAVITY_PRODUCT_NAME_AI_ONLY")))
            return self._result("Different")
        run = race.run_case(self._case(), with_product_ai=True, process_pdf_func=process_pdf)
        self.assertEqual(run["product_name_status"], "product_name_mismatch")
        self.assertEqual(seen, [(None, "1")])
        self.assertEqual(run["ai_component_calls"], 0)

    def test_baseline_rechecks_only_mismatch_and_second_match_is_unstable(self):
        results = iter([self._result("Different"), self._result("Expected")])
        run = race.run_case(
            self._case(), with_product_ai=True, product_name_baseline=True,
            process_pdf_func=lambda *args, **kwargs: next(results),
        )
        self.assertEqual(run["product_name_status"], "product_name_unstable_warning")
        self.assertEqual(run["ai_product_name_calls"], 2)

    def test_baseline_matching_first_result_is_not_repeated(self):
        calls = []
        def process_pdf(*args, **kwargs):
            calls.append(1)
            return self._result("Expected")
        run = race.run_case(
            self._case(), with_product_ai=True, product_name_baseline=True,
            process_pdf_func=process_pdf,
        )
        self.assertEqual(run["product_name_status"], "product_name_complete")
        self.assertEqual(len(calls), 1)

    def test_second_mismatch_remains_mismatch(self):
        results = iter([self._result("Wrong A"), self._result("Wrong B")])
        run = race.run_case(
            self._case(), with_product_ai=True, product_name_baseline=True,
            process_pdf_func=lambda *args, **kwargs: next(results),
        )
        self.assertEqual(run["product_name_status"], "product_name_mismatch")
        self.assertEqual(run["ai_product_name_calls"], 2)

    def test_missing_evidence_is_structural_failure(self):
        result = RuntimeExtractionResult({
            "제품명": "Expected", "components": [{"cas": "64-17-5", "content": "10%"}],
        })
        run = race.run_case(self._case(), process_pdf_func=lambda *args, **kwargs: result)
        self.assertEqual(run["product_name_status"], "product_name_evidence_missing")
        self.assertEqual(run["status"], "extraction_failed")
        self.assertIn("PRODUCT_NAME_EVIDENCE_MISSING", [d.get("reason_code") for d in run["differences"]])

    def test_component_source_field_is_reported(self):
        run = race.run_case(
            self._case(), process_pdf_func=lambda *args, **kwargs: self._result("Expected", calls=0),
        )
        self.assertEqual(run["component_source_field"], "components")


class ProductOnlyAIGuardTests(unittest.TestCase):
    def test_product_only_mode_blocks_component_provider(self):
        import msds_engine_v6
        engine = msds_engine_v6.MSDSEngineV6()
        with patch.dict(os.environ, {"ANTIGRAVITY_PRODUCT_NAME_AI_ONLY": "1"}, clear=False), patch.object(
            engine, "_invoke_ai_provider", side_effect=AssertionError("provider called")
        ):
            self.assertIsNone(engine.call_llm_router(
                {"contents": [{"parts": [{"text": "components"}]}]}, purpose="component_extraction",
            ))

    def test_operating_engine_has_no_case_override_registry(self):
        source = (ROOT / "msds_engine_v6.py").read_text(encoding="utf-8")
        self.assertNotIn("EXCEPTION_REGISTRY", source)
        self.assertNotIn("골든 마스터 정합을 위한 제품명 강제 보정", source)

    def test_cli_defaults_to_no_product_ai(self):
        args = race.build_parser().parse_args(["--all"])
        self.assertFalse(args.with_product_ai)

    def test_baseline_requires_explicit_product_ai(self):
        self.assertEqual(race.main(["--all", "--product-name-baseline"]), 1)

    def test_baseline_artifacts_do_not_store_environment_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(race, "BASELINE_OUTPUT_DIR", Path(tmp)), patch.dict(
            os.environ, {"DEEPSEEK_API_KEY": "secret-value"}, clear=False,
        ):
            selected = [{
                "id": "001", "file": "001.pdf",
                "product_name": {"expected": "Expected"},
            }]
            results = [{
                "product_name_status": "product_name_complete",
                "ai_first_result": "Expected", "ai_second_result": "",
                "product_name_evidence_text": "Section 1 evidence",
                "product_name_evidence_page": 0,
                "result": {"metrics": {"ai": [{"purpose": "product_name", "provider": "vertex"}]}},
            }]
            json_path, csv_path = race.write_product_name_baseline(selected, results)
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertNotIn("secret-value", json_path.read_text(encoding="utf-8"))
            self.assertNotIn("secret-value", csv_path.read_text(encoding="utf-8-sig"))


class GoldenUpdateTests(unittest.TestCase):
    def _fixtures(self, root):
        root = Path(root)
        pdf_dir = root / "pdfs"
        pdf_dir.mkdir()
        pdf = pdf_dir / "001_sample.pdf"
        pdf.write_bytes(b"source")
        digest = hashlib.sha256(b"source").hexdigest()
        golden = {"cases": [{"id": "001", "file": pdf.name, "source_sha256": digest, "product_name": {"expected": "old"}, "components": []}, {"id": "002", "file": "other.pdf", "source_sha256": "x", "product_name": {"expected": "keep"}, "components": []}]}
        candidate = {"cases": [{"id": "001", "file": pdf.name, "pdf_sha256": digest, "approved": True, "user_expected": {"product_name": {"expected": "new"}}}]}
        return pdf_dir, golden, candidate

    def test_unapproved_candidate_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir, golden, candidate = self._fixtures(tmp)
            candidate["cases"][0]["approved"] = False
            with self.assertRaisesRegex(GoldenUpdateError, "APPROVAL"):
                apply_approved_candidate(golden, candidate, {"001"}, pdf_dir)

    def test_only_selected_case_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir, golden, candidate = self._fixtures(tmp)
            before_other = copy.deepcopy(golden["cases"][1])
            updated = apply_approved_candidate(golden, candidate, {"001"}, pdf_dir)
            self.assertEqual(updated["cases"][0]["product_name"]["expected"], "new")
            self.assertEqual(updated["cases"][1], before_other)

    def test_hash_mismatch_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir, golden, candidate = self._fixtures(tmp)
            candidate["cases"][0]["pdf_sha256"] = "bad"
            with self.assertRaisesRegex(GoldenUpdateError, "HASH_MISMATCH"):
                apply_approved_candidate(golden, candidate, {"001"}, pdf_dir)

    def test_full_regression_failure_restores_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_dir, golden, candidate = self._fixtures(root)
            golden_path = root / "golden.json"
            candidate_path = root / "candidate.json"
            golden_path.write_text(json.dumps(golden), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            original = golden_path.read_bytes()
            calls = []
            def runner(command, **kwargs):
                calls.append(command)
                return SimpleNamespace(returncode=1 if "--all" in command else 0)
            with self.assertRaisesRegex(GoldenUpdateError, "full"):
                update_golden_file(candidate_path, golden_path, {"001"}, pdf_dir, runner=runner)
            self.assertEqual(golden_path.read_bytes(), original)
            self.assertEqual(len(calls), 3)

    def test_candidate_generation_does_not_modify_golden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            golden = root / "golden.json"
            golden.write_text('{"cases": []}', encoding="utf-8")
            before = golden.read_bytes()
            original_root = race.ROOT
            try:
                race.ROOT = root
                candidate = race.write_candidate(
                    [{"id": "001", "file": "sample.pdf", "source_sha256": "hash", "components": [], "product_name": {}, "tags": {}}],
                    [{"result": {"제품명": "current"}, "differences": []}],
                )
            finally:
                race.ROOT = original_root
            self.assertTrue(candidate.exists())
            self.assertEqual(golden.read_bytes(), before)
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            self.assertFalse(payload["cases"][0]["approved"])


if __name__ == "__main__":
    unittest.main()
