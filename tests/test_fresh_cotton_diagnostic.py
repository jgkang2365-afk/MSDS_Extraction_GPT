import json
import os
import tempfile
import unittest
from pathlib import Path

from diagnostic_trace import activate_trace, create_trace_context, finalize_trace
try:
    import fitz  # noqa: F401
    from msds_engine_v6 import MSDSEngineV6
except ImportError:
    fitz = None
    MSDSEngineV6 = None


def _fixture_path():
    configured = os.getenv("MSDS_FRESH_COTTON_TEST_PDF")
    if configured:
        return Path(configured)
    return Path.home() / "Desktop" / "노디너리" / "MSDS" / "012_R000120 향)FRESH COTTON HYPO NATCO 1805663.pdf"


class FreshCottonDiagnosticRegressionTests(unittest.TestCase):
    def test_real_pdf_records_raw_unicode_and_current_rejection_without_external_calls(self):
        if fitz is None or MSDSEngineV6 is None:
            self.skipTest("PyMuPDF 또는 운영 엔진 의존성이 이 테스트 런타임에 없음")
        pdf_path = _fixture_path()
        if not pdf_path.exists():
            self.skipTest("FRESH COTTON 운영 회귀 PDF가 이 환경에 없음")

        engine = MSDSEngineV6.__new__(MSDSEngineV6)
        engine._diagnostic_candidate_ids = {}
        engine._diagnostic_last_candidate_ids = []

        with tempfile.TemporaryDirectory() as tmp:
            context = create_trace_context(
                {"file_path": str(pdf_path)},
                run_id="fresh-cotton",
                file_trace_id="real-pdf",
                mode="FULL",
                base_dir=tmp,
            )
            with activate_trace(context):
                images, section3_text, pages, recon_data = engine.extract_section3_images(str(pdf_path))
                self.assertIsNone(recon_data)
                self.assertIn(1, pages, "3항 원문이 존재하는 PDF 표시 2페이지가 선택되어야 함")
                self.assertIn("140−11−4", section3_text)
                self.assertIn("2,00%", section3_text)
                self.assertTrue(images)

                # 현재 추출 규칙을 고치지 않고, 원시 후보가 ASCII CAS 형식 검사에서
                # 탈락하는 사실만 진단 계층이 증명하는지 확인한다.
                self.assertEqual(
                    engine.refine_msds_components_strict(
                        [{"name": "benzyl acetate", "cas": "140−11−4", "content": "2,00%", "page": 2, "engine": "PyMuPDF"}]
                    ),
                    [],
                )
                diagnostic_path = finalize_trace(
                    context,
                    {
                        "status": "failed",
                        "document_type": "text",
                        "제품명": "FRESH COTTON HYPO% NATCO 1805663",
                        "구성성분": "",
                        "error_code": "CAS_CONTENT_PAIRING_FAILED",
                    },
                )

            diagnostic = json.loads(Path(diagnostic_path).read_text(encoding="utf-8"))
            events = [json.loads(line) for line in (Path(tmp) / "fresh-cotton" / "files" / "real-pdf" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            raw_event = next(item for item in events if item["event_type"] == "section3.text_source_result")
            self.assertEqual(raw_event["details"]["page_numbers"], [index + 1 for index in pages])
            self.assertIn("140−11−4", raw_event["details"]["raw_text"])
            self.assertIn("2,00%", raw_event["details"]["raw_text"])
            self.assertEqual(diagnostic["rejections"][0]["details"]["reason"], "INVALID_CAS_FORMAT")
            report = (Path(tmp) / "fresh-cotton" / "files" / "real-pdf" / "diagnostic.md").read_text(encoding="utf-8")
            self.assertIn("직접 실패 원인", report)
            self.assertIn("INVALID_CAS_FORMAT", report)


if __name__ == "__main__":
    unittest.main()
