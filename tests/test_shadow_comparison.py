import inspect
import json
import os
import pickle
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from batch_pipeline import BatchRunLogger
from shadow_comparison import (
    build_shadow_comparison,
    compare_engine_results,
    comparison_rows,
    comparison_summary,
    export_comparison_report,
    failed_comparison,
    parse_components,
)
from result_safety import (
    RuntimeExtractionResult,
    detach_shadow_context,
    encapsulate_runtime_result,
    public_result,
)


ROOT = Path(__file__).resolve().parents[1]


def shared_text(cas="64-17-5", content="10 ~ 20%"):
    return [
        "1. 화학제품과 회사에 관한 정보\n제품명: TEST PRODUCT\n공급자: ACME\n2. 유해성·위험성\n",
        f"3. 구성성분의 명칭 및 함유량\n성분명 CAS 번호 함유량\nEthanol {cas} {content}\n4. 응급조치 요령\n",
    ]


class ComparisonCalculationTests(unittest.TestCase):
    def compare(self, v6, v7, **kwargs):
        return compare_engine_results("sample.pdf", "C:/sample.pdf", v6, v7, **kwargs)

    def test_product_name_same_ignores_simple_notation(self):
        result = self.compare({"제품명": "ＡＢＣ - 100", "구성성분": ""}, {"제품명": "abc100", "구성성분": ""})
        self.assertFalse(result.product_name_different)
        self.assertEqual(result.auto_judgment, "SAME")

    def test_product_name_difference_preserves_originals(self):
        result = self.compare({"제품명": "V6 원문"}, {"제품명": "V7 원문"})
        self.assertTrue(result.product_name_different)
        self.assertEqual((result.v6_product_name, result.v7_product_name), ("V6 원문", "V7 원문"))

    def test_v7_cas_addition(self):
        result = self.compare({"구성성분": "64-17-5(10%)"}, {"구성성분": "64-17-5(10%); 67-64-1(5%)"})
        self.assertEqual([item.cas for item in result.added_in_v7], ["67-64-1"])

    def test_v7_cas_removal(self):
        result = self.compare({"구성성분": "64-17-5(10%); 67-64-1(5%)"}, {"구성성분": "64-17-5(10%)"})
        self.assertEqual([item.cas for item in result.removed_in_v7], ["67-64-1"])

    def test_content_change_preserves_range_symbols(self):
        result = self.compare({"구성성분": "64-17-5(>=10 - <20%)"}, {"구성성분": "64-17-5(≤5%)"})
        self.assertEqual(result.changed_in_v7[0].v6_content, ">=10 - <20%")
        self.assertEqual(result.changed_in_v7[0].v7_content, "≤5%")
        self.assertIn("함유량 변경", result.changed_in_v7[0].status)

    def test_component_name_change(self):
        result = self.compare(
            {"components": [{"cas": "64-17-5", "name": "에탄올", "content": "10%"}]},
            {"components": [{"cas": "64-17-5", "name": "Ethanol", "content": "10%"}]},
        )
        self.assertIn("성분명 변경", result.changed_in_v7[0].status)

    def test_trade_secret_and_balance_are_not_normalized_away(self):
        parsed = parse_components({"구성성분": "64-17-5(Trade secret); 7732-18-5(Balance); 67-64-1(잔량)"})
        self.assertEqual([item["content"] for item in parsed], ["Trade secret", "Balance", "잔량"])

    def test_casless_difference_requires_manual_review(self):
        result = self.compare({"components": [{"name": "향료", "content": "영업비밀"}]}, {"components": []})
        self.assertEqual(result.auto_judgment, "MANUAL_REVIEW_REQUIRED")


class ShadowReuseTests(unittest.TestCase):
    def test_full_comparison_uses_shared_page_text(self):
        v6 = {"제품명": "TEST PRODUCT", "구성성분": "64-17-5(10 ~ 20%)", "metrics": {}, "doc_type": "디지털"}
        result = build_shadow_comparison("C:/sample.pdf", v6, {"page_texts": shared_text()})
        self.assertEqual(result.comparison_completeness, "FULL")
        self.assertEqual(result.duplicate_ocr_calls, 0)
        self.assertEqual(result.duplicate_ai_calls, 0)

    def test_ai_path_is_partial_without_duplicate_call(self):
        v6 = {"제품명": "TEST PRODUCT", "구성성분": "64-17-5(10%)", "metrics": {"ai_text_calls": 1}}
        result = build_shadow_comparison("C:/sample.pdf", v6, {"page_texts": shared_text(content="10%")})
        self.assertEqual(result.comparison_completeness, "PARTIAL_AI_PATH")
        self.assertEqual(result.auto_judgment, "PARTIAL_COMPARISON")
        self.assertEqual(result.duplicate_ai_calls, 0)

    def test_ocr_path_is_partial_without_duplicate_call(self):
        v6 = {"제품명": "P", "구성성분": "64-17-5(10%)", "metrics": {}, "doc_type": "스캔본"}
        result = build_shadow_comparison("C:/scan.pdf", v6, {"section3_text": "64-17-5 10%", "ocr_reused": True})
        self.assertEqual(result.comparison_completeness, "PARTIAL_OCR_PATH")
        self.assertEqual(result.duplicate_ocr_calls, 0)

    def test_outside_section3_candidate_is_improvement_candidate(self):
        v6 = {"제품명": "TEST PRODUCT", "구성성분": "64-17-5(10%); 67-64-1(5%)", "metrics": {}}
        result = build_shadow_comparison("C:/sample.pdf", v6, {"page_texts": shared_text()})
        self.assertEqual(result.auto_judgment, "V7_IMPROVEMENT_CANDIDATE")
        self.assertEqual(result.removed_in_v7[0].reason_code, "OUTSIDE_SECTION_3")

    def test_max_chars_removal_is_v7_error_candidate(self):
        page = "3. 구성성분의 명칭 및 함유량\n성분명 CAS 번호 함유량\n" + ("설명 " * 3000) + "Ethanol 64-17-5 10%"
        v6 = {"제품명": "P", "구성성분": "64-17-5(10%)", "metrics": {}}
        result = build_shadow_comparison("C:/long.pdf", v6, {"page_texts": [page]})
        self.assertEqual(result.section_3_meta["end_reason"], "max_chars")
        self.assertEqual(result.auto_judgment, "V7_ERROR_CANDIDATE")

    def test_comparison_failure_object_keeps_v6_saved_flag(self):
        result = failed_comparison("C:/bad.pdf", ValueError("boom"))
        self.assertEqual(result.comparison_completeness, "COMPARISON_FAILED")
        self.assertTrue(result.v6_result_saved)
        self.assertIn("ValueError", result.error)

    def test_shadow_function_has_no_pdf_ocr_or_ai_calls(self):
        source = inspect.getsource(build_shadow_comparison)
        for forbidden in ("fitz.open", "extract_section3_images", "call_llm", "PaddleOCR", "process_pdf"):
            self.assertNotIn(forbidden, source)

    def test_v6_context_reuses_existing_document_iteration(self):
        source = (ROOT / "msds_engine_v6.py").read_text(encoding="utf-8")
        self.assertIn("page_texts = [self._get_sorted_and_normalized_text(page) for page in doc]", source)
        self.assertIn("RuntimeExtractionResult(", source)

    def test_runtime_context_is_not_part_of_serialized_result(self):
        result = RuntimeExtractionResult(
            {"제품명": "P", "구성성분": "64-17-5(10%)"},
            shadow_context={"page_texts": shared_text(content="10%")},
        )
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("_shadow_context", serialized)
        self.assertNotIn("page_texts", serialized)

        result, context = detach_shadow_context(result)
        comparison = build_shadow_comparison("C:/sample.pdf", result, context)
        self.assertEqual(comparison.comparison_completeness, "FULL")
        self.assertEqual(comparison.duplicate_ocr_calls, 0)
        self.assertEqual(comparison.duplicate_ai_calls, 0)

    def test_embedded_context_is_detached_at_process_boundary(self):
        result = encapsulate_runtime_result({
            "제품명": "P",
            "_shadow_context": {"section3_text": "64-17-5 10%"},
        })
        self.assertNotIn("_shadow_context", result)
        result, context = detach_shadow_context(result)
        self.assertEqual(context["section3_text"], "64-17-5 10%")

    def test_runtime_context_survives_process_serialization_without_mapping_key(self):
        original = RuntimeExtractionResult(
            {"제품명": "P"},
            shadow_context={"section3_text": "64-17-5 10%"},
        )
        restored = pickle.loads(pickle.dumps(original))
        self.assertNotIn("_shadow_context", restored)
        restored, context = detach_shadow_context(restored)
        self.assertEqual(context["section3_text"], "64-17-5 10%")

    def test_public_result_removes_nested_context_from_cache_and_user_output(self):
        unsafe = {
            "result": {"제품명": "P", "_shadow_context": {"raw": "secret"}},
            "items": [{"_shadow_context": {"page_texts": ["raw"]}}],
        }
        safe = public_result(unsafe)
        encoded = json.dumps(safe, ensure_ascii=False)
        self.assertNotIn("_shadow_context", encoded)
        self.assertNotIn("page_texts", encoded)


class SharedOutputTests(unittest.TestCase):
    def setUp(self):
        self.same = compare_engine_results("same.pdf", "C:/same.pdf", {"제품명": "P", "구성성분": "64-17-5(10%)"}, {"제품명": "P", "구성성분": "64-17-5(10%)"}).to_dict()
        self.diff = compare_engine_results("diff.pdf", "C:/diff.pdf", {"제품명": "P", "구성성분": "64-17-5(10%); 67-64-1(Balance)"}, {"제품명": "P", "구성성분": "64-17-5(20%)"}).to_dict()

    def test_default_gui_rows_exclude_same(self):
        self.assertEqual([row["file_name"] for row in comparison_rows([self.same, self.diff])], ["diff.pdf"])

    def test_filters_cover_add_remove_content_and_judgment(self):
        self.assertEqual(len(comparison_rows([self.diff], "CAS 제거")), 1)
        self.assertEqual(len(comparison_rows([self.diff], "함유량 변경")), 1)
        self.diff["auto_judgment"] = "V7_ERROR_CANDIDATE"
        self.assertEqual(len(comparison_rows([self.diff], "V7 오류 가능")), 1)

    def test_summary_counts_common_objects(self):
        summary = comparison_summary([self.same, self.diff])
        self.assertEqual((summary["total_documents"], summary["same"], summary["different"]), (2, 1, 1))
        self.assertEqual((summary["duplicate_ocr_calls"], summary["duplicate_ai_calls"]), (0, 0))

    def test_logger_writes_diff_partial_failed_and_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = BatchRunLogger(base_dir=tmp, run_id="comparison")
            logger.record_engine_comparison(self.diff)
            partial = dict(self.diff, comparison_completeness="PARTIAL_AI_PATH")
            logger.record_engine_comparison(partial)
            failed = failed_comparison("C:/failed.pdf", RuntimeError("fail")).to_dict()
            logger.record_engine_comparison(failed)
            logger.record_comparison_summary(comparison_summary([self.diff, partial, failed]), "report.xlsx")
            text = logger.error_summary_path.read_text(encoding="utf-8")
            for marker in ("[V6_V7_COMPARISON_DIFF]", "[V6_V7_COMPARISON_PARTIAL]", "[V6_V7_COMPARISON_FAILED]", "[V6_V7_COMPARISON_SUMMARY]"):
                self.assertIn(marker, text)
            json_lines = [line for line in text.splitlines() if line.startswith("{")]
            self.assertTrue(json_lines)
            for line in json_lines:
                json.loads(line)
            self.assertIn("file_path: C:/diff.pdf", text)
            self.assertIn("[SECTION_1]", text)

    def test_report_has_four_required_sheets_and_shared_values(self):
        node = Path(r"C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
        if not node.exists():
            self.skipTest("bundled artifact-tool runtime unavailable")
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"CODEX_BUNDLED_NODE": str(node)}):
            output = Path(tmp) / "comparison.xlsx"
            export_comparison_report([self.diff], str(output))
            workbook = openpyxl.load_workbook(output, read_only=True, data_only=True)
            self.assertEqual(workbook.sheetnames, ["요약", "문서별 비교", "성분 상세 비교", "부분 비교·실패"])
            document_values = list(workbook["문서별 비교"].values)
            self.assertIn("diff.pdf", document_values[1])
            self.assertIn("Balance", [value for row in workbook["성분 상세 비교"].values for value in row])
            workbook.close()

    def test_gui_and_worker_failure_isolation_contract(self):
        source = (ROOT / "smu_gui.py").read_text(encoding="utf-8")
        worker = source.split("class ExtractionWorker", 1)[1].split("class ValidationWorker", 1)[0]
        extraction_path = worker.split("ext_res = self.core.extract_from_pdf", 1)[1]
        self.assertLess(extraction_path.index("detach_shadow_context(ext_res)"), extraction_path.index("record_final_candidate"))
        self.assertLess(extraction_path.index("detach_shadow_context(ext_res)"), extraction_path.index("cache_update_signal.emit"))
        self.assertLess(worker.index("self.result_signal.emit(res_data)"), worker.index("build_shadow_comparison"))
        self.assertIn("COMPARISON_REPORT_FAILED", worker)
        self.assertIn("comparison_dialog_exc", source)
        self.assertIn("ShadowComparisonDetailDialog", source)

    def test_operational_core_is_pinned_to_v6(self):
        core_source = (ROOT / "msds_core.py").read_text(encoding="utf-8")
        gui_source = (ROOT / "smu_gui.py").read_text(encoding="utf-8")
        self.assertIn("import msds_engine_v6 as msds_engine", core_source)
        self.assertIn("import msds_engine_v6 as engine", gui_source)
        self.assertNotIn("V6/V7 라디오", gui_source)


if __name__ == "__main__":
    unittest.main()
