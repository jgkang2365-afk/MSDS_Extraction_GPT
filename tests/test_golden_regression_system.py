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
    load_cases,
    normalize_content,
    select_cases,
)
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
