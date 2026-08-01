import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import batch_pipeline
from batch_pipeline import (
    BatchRunLogger,
    build_partial_timeout_result,
    classify_and_order,
    normalize_product_name,
    timeout_for_document,
    verify_product_name,
)


class TimeoutPolicyTests(unittest.TestCase):
    def test_document_specific_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(timeout_for_document("text"), 180)
            self.assertEqual(timeout_for_document("mixed"), 240)
            self.assertEqual(timeout_for_document("image"), 360)

    def test_legacy_environment_is_compatible(self):
        with patch.dict(os.environ, {"MSDS_FILE_TIMEOUT_SECONDS": "77"}, clear=True):
            self.assertEqual(timeout_for_document("text"), 77)
            self.assertEqual(timeout_for_document("mixed"), 77)
            self.assertEqual(timeout_for_document("image"), 77)

    def test_specific_environment_has_priority(self):
        env = {"MSDS_FILE_TIMEOUT_SECONDS": "77", "MSDS_IMAGE_FILE_TIMEOUT_SECONDS": "99"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(timeout_for_document("image"), 99)


class PartialCheckpointTests(unittest.TestCase):
    def test_product_name_checkpoint_is_preserved(self):
        result = build_partial_timeout_result(
            {"stage": "product_name_complete", "product_name": "AI Product", "next_stage": "section3_recon"},
            360,
            "timeout",
        )
        self.assertEqual(result["status"], "partial_timeout")
        self.assertEqual(result["제품명"], "AI Product")
        self.assertEqual(result["last_completed_stage"], "product_name_complete")

    def test_cas_partial_result_is_preserved(self):
        result = build_partial_timeout_result(
            {"stage": "cas_content_matching_complete", "product_name": "P", "구성성분": "64-17-5(50%)", "content_matching_complete": True},
            240,
            "timeout",
        )
        self.assertEqual(result["구성성분"], "64-17-5(50%)")
        self.assertEqual(result["error_code"], "PARTIAL_TIMEOUT")

    def test_cas_candidates_are_not_promoted_to_unlisted_content(self):
        result = build_partial_timeout_result(
            {
                "stage": "cas_candidates_complete",
                "product_name": "P",
                "cas_candidates": ["64-17-5", "67-64-1"],
                "content_matching_complete": False,
            },
            360,
            "timeout",
        )
        self.assertEqual(result["cas_candidates"], ["64-17-5", "67-64-1"])
        self.assertEqual(result["구성성분"], "")
        self.assertEqual(result["함유량"], "")
        self.assertFalse(result["content_matching_complete"])
        self.assertFalse(result["validation_eligible"])

    def test_empty_checkpoint_is_distinguishable_from_partial(self):
        result = build_partial_timeout_result({}, 180, "timeout")
        self.assertFalse(result["제품명"] or result["구성성분"])


class ProductVerificationTests(unittest.TestCase):
    def test_normalization_handles_width_spaces_hyphens_and_parentheses(self):
        self.assertEqual(normalize_product_name("ＡＢＣ - (123)"), normalize_product_name("abc123"))

    def test_ai_and_local_match(self):
        self.assertEqual(verify_product_name("MICONOL C2M(H)", "miconol-c2m h"), ("match", "verified"))

    def test_ai_and_local_mismatch(self):
        self.assertEqual(verify_product_name("Imagined Product", "Real Product"), ("mismatch", "review"))

    def test_filename_is_not_a_product_name_input(self):
        source = (Path(__file__).resolve().parents[1] / "msds_engine_v6.py").read_text(encoding="utf-8")
        self.assertNotIn("file_pn_hint", source)
        self.assertNotIn("clean_filename_product_hint", source)


class ClassificationAndQueueTests(unittest.TestCase):
    def test_text_documents_are_ordered_before_ocr_documents(self):
        types = {"image.pdf": "image", "mixed.pdf": "mixed", "text.pdf": "text"}
        with patch.object(batch_pipeline, "classify_document", side_effect=lambda path: {"document_type": types[path], "page_count": 1}):
            ordered = classify_and_order(["image.pdf", "mixed.pdf", "text.pdf"])
        self.assertEqual([item["document_type"] for item in ordered], ["text", "mixed", "image"])

    def test_ocr_parallel_limit_is_one(self):
        source = (Path(__file__).resolve().parents[1] / "msds_core.py").read_text(encoding="utf-8")
        self.assertIn("threading.Semaphore(1)", source)
        self.assertIn('document_type == "image"', source)


class StructuredLoggingTests(unittest.TestCase):
    def test_jsonl_and_summary_are_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "sample.pdf"
            self.assertFalse(pdf.exists())
            logger = BatchRunLogger(base_dir=Path(tmp) / "logs", run_id="test-run")
            info = {"path": str(pdf), "document_type": "text", "page_count": 1}
            result = {"status": "completed", "제품명": "P", "구성성분": "64-17-5(50%)", "metrics": {"ai_text_calls": 1, "ai_harvest_success": 1}}
            logger.record_file(info, result, 0.1, 180, "hash")
            summary = logger.finalize()
            events = [json.loads(line) for line in logger.events_path.read_text(encoding="utf-8").splitlines()]
            event = next(item for item in events if item.get("stage") == "file_complete")
            self.assertEqual(event["document_type"], "text")
            self.assertEqual(summary["ai_text_calls"], 1)
            self.assertTrue(logger.summary_path.exists())

    def test_file_trace_id_is_stable_and_artifacts_are_linked(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = BatchRunLogger(base_dir=Path(tmp) / "logs", run_id="trace-run", diagnostic_mode="FULL")
            info = {"path": str(Path(tmp) / "sample.pdf"), "document_type": "image", "page_count": 1}
            first = logger.file_trace_context(info, "same-hash")
            second = logger.file_trace_context(info, "same-hash")
            self.assertEqual(first.file_trace_id, second.file_trace_id)
            result = {"status": "partial_timeout", "제품명": "P", "구성성분": "", "error_code": "PARTIAL_TIMEOUT"}
            paths = logger.record_file(info, result, 0.1, 360, "same-hash", first)
            self.assertEqual(result["diagnostics"]["file_trace_id"], first.file_trace_id)
            self.assertTrue(Path(paths["diagnostic_json"]).exists())

    def test_diagnostics_redact_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = BatchRunLogger(base_dir=Path(tmp) / "logs", run_id="redact-run", diagnostic_mode="FULL")
            info = {"path": str(Path(tmp) / "sample.pdf"), "document_type": "text", "page_count": 1}
            context = logger.file_trace_context(info, "hash")
            logger._trace_event(context, "test_secret", authorization="Bearer definitely-not-for-log")
            paths = logger.record_file(info, {"status": "completed"}, 0.1, 180, "hash", context)
            payload = Path(paths["diagnostic_json"]).read_text(encoding="utf-8")
            self.assertNotIn("definitely-not-for-log", payload)

    def test_gui_uses_batched_log_and_table_queues(self):
        source = (Path(__file__).resolve().parents[1] / "smu_gui.py").read_text(encoding="utf-8")
        self.assertIn("_pending_gui_logs", source)
        self.assertIn("setMaximumBlockCount(3000)", source)
        self.assertIn("_pending_table_results", source)
        self.assertIn("setInterval(250)", source)
        flush_source = source.split("    def _flush_gui_logs", 1)[1].split("    def log", 1)[0]
        self.assertIn("cursor.insertText", flush_source)
        self.assertNotIn("cursor.insertHtml", flush_source)
        self.assertIn('cached_result.get("validation_eligible") is False', source)

    def test_gui_diagnostic_actions_keep_table_contract(self):
        source = (Path(__file__).resolve().parents[1] / "smu_gui.py").read_text(encoding="utf-8")
        self.assertIn('"진단 보고서 열기"', source)
        self.assertIn('"진단 이미지 폴더 열기"', source)
        self.assertIn('"진단 JSON 복사"', source)
        self.assertIn("QDesktopServices.openUrl(QUrl.fromLocalFile(path))", source)
        self.assertIn("QApplication.clipboard().setText", source)
        self.assertIn('"diagnostic_candidate_source"', source)


if __name__ == "__main__":
    unittest.main()
