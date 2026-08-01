import ast
import io
import hashlib
import json
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

# 번들 테스트 Python에는 운영 환경의 네트워크/PDF 인증 패키지가 없다.
# 이 테스트는 호출 구조만 검증하므로 import 시 필요한 표면만 최소 제공한다.
if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.post = lambda *_args, **_kwargs: None
    requests_stub.RequestException = Exception
    sys.modules["requests"] = requests_stub

try:
    import fitz
except ModuleNotFoundError:
    fitz_stub = types.ModuleType("fitz")

    class _FitzMatrix:
        def __init__(self, x, y):
            self.a = x
            self.d = y

    class _FitzRect:
        def __init__(self, x0, y0, x1, y1):
            self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

        @property
        def width(self):
            return self.x1 - self.x0

        @property
        def height(self):
            return self.y1 - self.y0

    fitz_stub.Matrix = _FitzMatrix
    fitz_stub.Rect = _FitzRect
    fitz_stub.open = lambda *_args, **_kwargs: None
    sys.modules["fitz"] = fitz_stub

google_stub = sys.modules.setdefault("google", types.ModuleType("google"))
oauth2_stub = sys.modules.setdefault("google.oauth2", types.ModuleType("google.oauth2"))
service_account_stub = sys.modules.setdefault(
    "google.oauth2.service_account", types.ModuleType("google.oauth2.service_account")
)
auth_stub = sys.modules.setdefault("google.auth", types.ModuleType("google.auth"))
transport_stub = sys.modules.setdefault(
    "google.auth.transport", types.ModuleType("google.auth.transport")
)
transport_requests_stub = sys.modules.setdefault(
    "google.auth.transport.requests", types.ModuleType("google.auth.transport.requests")
)
google_stub.oauth2 = oauth2_stub
google_stub.auth = auth_stub
oauth2_stub.service_account = service_account_stub
auth_stub.transport = transport_stub
transport_stub.requests = transport_requests_stub

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda **_kwargs: None
    sys.modules["dotenv"] = dotenv_stub

import msds_engine_v6 as engine_module
import remote_ocr_client as remote_module


class _Rect:
    def __init__(self, width=600.0, height=800.0):
        self.width = width
        self.height = height


class _Pixmap:
    def __init__(self, width, height, page_marker):
        self.w = max(1, int(round(width)))
        self.h = max(1, int(round(height)))
        self.n = 3
        self._array = np.full((self.h, self.w, self.n), page_marker, dtype=np.uint8)
        self.samples = self._array.tobytes()

    def tobytes(self, _format):
        buffer = io.BytesIO()
        Image.fromarray(self._array, mode="RGB").save(buffer, format="PNG")
        return buffer.getvalue()


class _Page:
    def __init__(self, index, render_log):
        self.index = index
        self.rect = _Rect()
        self.render_log = render_log

    def get_text(self, *_args, **_kwargs):
        return ""

    def get_pixmap(self, matrix, clip=None):
        scale = float(matrix.a)
        width = clip.width if clip is not None else self.rect.width
        height = clip.height if clip is not None else self.rect.height
        self.render_log.append(
            {
                "page_index": self.index,
                "scale": scale,
                "clip": None if clip is None else [clip.x0, clip.y0, clip.x1, clip.y1],
            }
        )
        return _Pixmap(width * scale, height * scale, self.index + 1)


class _Document:
    def __init__(self, pages):
        self.pages = pages

    def __len__(self):
        return len(self.pages)

    def __iter__(self):
        return iter(self.pages)

    def __getitem__(self, index):
        return self.pages[index]

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _ocr_line(text, x0, y0, x1, y1):
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]], (text, 0.99)]


class _ReconOCR:
    def __init__(self, with_content=True):
        self.calls = 0
        self.with_content = with_content

    def ocr(self, image, cls=False):
        self.calls += 1
        marker = int(image[0, 0, 0])
        if marker == 1:
            return [[
                _ocr_line("1. 화학제품과 회사에 관한 정보", 30, 30, 500, 60),
                _ocr_line("제품명 Test Product", 30, 75, 420, 105),
                _ocr_line("2. 유해성 위험성", 30, 210, 360, 240),
            ]]
        return [[
            # x=600px는 페이지 왼쪽 33% 밖이다. 전체 폭 정찰 좌표를 써야 찾을 수 있다.
            _ocr_line("3. 구성성분의 명칭 및 함유량", 600, 150, 870, 180),
            _ocr_line(
                "에탄올 64-17-5 50%" if self.with_content else "에탄올 64-17-5",
                60, 260, 700, 300,
            ),
            _ocr_line("4. 응급조치 요령", 600, 600, 850, 630),
        ]]


class _AdaptiveReconOCR:
    def __init__(self, low_scale_succeeds):
        self.low_scale_succeeds = low_scale_succeeds
        self.calls = 0

    def ocr(self, image, cls=False):
        self.calls += 1
        is_low_scale = image.shape[1] <= 600
        if is_low_scale and not self.low_scale_succeeds:
            return [[_ocr_line("LOW_ONLY 판독 불충분", 30, 30, 300, 60)]]
        return [[
            _ocr_line("3. 구성성분의 명칭 및 함유량", 30, 120, 500, 150),
            _ocr_line("에탄올 64-17-5 50%", 30, 220, 500, 250),
            _ocr_line("4. 응급조치 요령", 30, 500, 420, 530),
        ]]


def _adaptive_evaluator(lines, _engine):
    text = "\n".join(line.get("text", "") for line in lines)
    accepted = "구성성분" in text and "64-17-5" in text
    return {
        "score": 80.0 if accepted else 10.0,
        "accepted": accepted,
        "features": {"test_heading": accepted},
    }


class _PPResult:
    html = {"table": "<table><tr><td>64-17-5</td><td>50%</td></tr></table>" + ("x" * 120)}
    markdown = {}


class _PPStructure:
    def __init__(self):
        self.calls = 0
        self.last_shape = None

    def predict(self, image, **_kwargs):
        self.calls += 1
        self.last_shape = image.shape
        return [_PPResult()]


class _RemoteClient:
    def __init__(self, enabled, result="64-17-5 50%", error=None):
        self.enabled = enabled
        self.result = result
        self.error = error
        self.calls = 0

    def extract_png(self, _image_bytes):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class ImageOCRReuseTests(unittest.TestCase):
    def _run_adaptive_recon(self, low_scale_succeeds):
        render_log = []
        document = _Document([_Page(0, render_log)])
        recon_ocr = _AdaptiveReconOCR(low_scale_succeeds)
        engine = engine_module.MSDSEngineV6(
            recon_attempt_scales=(1.0, 1.5),
            recon_confidence_evaluator=_adaptive_evaluator,
        )
        with patch.object(engine_module.fitz, "open", return_value=document), patch.object(
            engine_module, "get_ocr_engine", return_value=recon_ocr
        ):
            result = engine.extract_section3_images("scan.pdf")
        return engine, recon_ocr, render_log, result

    def test_production_recon_default_remains_fixed_1_5(self):
        engine = engine_module.MSDSEngineV6()
        self.assertEqual(engine._recon_attempt_scales, (1.5,))
        self.assertIsNone(engine._recon_confidence_evaluator)

    def test_adaptive_recon_low_scale_success_skips_1_5_retry(self):
        engine, recon_ocr, render_log, (_images, _text, pages, recon_data) = (
            self._run_adaptive_recon(low_scale_succeeds=True)
        )
        self.assertEqual(recon_ocr.calls, 1)
        self.assertEqual([item["scale"] for item in render_log], [1.0])
        self.assertEqual(pages, [0])
        self.assertEqual(recon_data["pages"][0]["render_scale"], 1.0)
        self.assertEqual(len(engine._recon_attempt_metrics), 1)

    def test_adaptive_recon_retry_uses_only_higher_confidence_result(self):
        engine, recon_ocr, render_log, (_images, _text, pages, recon_data) = (
            self._run_adaptive_recon(low_scale_succeeds=False)
        )
        self.assertEqual(recon_ocr.calls, 2)
        self.assertEqual([item["scale"] for item in render_log], [1.0, 1.5])
        self.assertEqual(pages, [0])
        self.assertEqual(recon_data["pages"][0]["render_scale"], 1.5)
        self.assertNotIn("LOW_ONLY", recon_data["pages"][0]["text"])
        self.assertEqual(len(engine._recon_attempt_metrics), 2)

    def test_remote_ocr_setting_defaults_false_and_can_be_enabled_from_config(self):
        self.assertFalse(remote_module.USE_REMOTE_OCR)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            remote_module.os.environ, {}, clear=True
        ):
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            self.assertFalse(remote_module.load_remote_ocr_enabled(config_path))
            config_path.write_text('{"USE_REMOTE_OCR": true}', encoding="utf-8")
            self.assertTrue(remote_module.load_remote_ocr_enabled(config_path))

    def test_golden_master_has_no_automatic_race_writer(self):
        repo_root = Path(__file__).resolve().parents[1]
        race_source = (repo_root / "run_production_race.py").read_text(encoding="utf-8")
        gui_source = (repo_root / "smu_gui.py").read_text(encoding="utf-8")

        self.assertNotIn('open(golden_file, "w"', race_source)
        self.assertIn('os.environ["ANTIGRAVITY_GOLDEN_VALIDATION"] = "1"', race_source)

        registration = gui_source.split("def check_and_register_golden_master", 1)[1].split(
            "def perform_standard_save", 1
        )[0]
        approval_index = registration.index("if reply == QMessageBox.Yes:")
        write_index = registration.index('open(golden_path, "w"')
        self.assertLess(approval_index, write_index)

    def test_extraction_start_preserves_existing_cache(self):
        repo_root = Path(__file__).resolve().parents[1]
        gui_source = (repo_root / "smu_gui.py").read_text(encoding="utf-8")
        run_extraction = gui_source.split("def run_extraction(self):", 1)[1].split(
            "def add_result_to_table", 1
        )[0]

        self.assertNotIn('os.remove(cache_path)', run_extraction)
        self.assertNotIn('self.cache.clear()', run_extraction)
        self.assertNotIn('self.save_cache()', run_extraction)

    def test_pdf_list_changes_are_saved_immediately(self):
        repo_root = Path(__file__).resolve().parents[1]
        gui_source = (repo_root / "smu_gui.py").read_text(encoding="utf-8")

        for start_name, end_name in [
            ("def load_pdfs(self):", "def load_pdf_folder"),
            ("def load_pdf_folder(self):", "def on_files_dropped"),
            ("def on_files_dropped(self, paths):", "def update_file_count_display"),
            ("def batch_rename_files(self):", "def is_file_locked"),
        ]:
            method_source = gui_source.split(start_name, 1)[1].split(end_name, 1)[0]
            self.assertIn("self.save_config()", method_source)

    def test_cache_save_is_atomic_and_keeps_previous_backup(self):
        repo_root = Path(__file__).resolve().parents[1]
        gui_source = (repo_root / "smu_gui.py").read_text(encoding="utf-8")
        save_cache = gui_source.split("def save_cache(self):", 1)[1].split(
            "def update_cache", 1
        )[0]
        load_cache = gui_source.split("def load_cache(self):", 1)[1].split(
            "def save_cache", 1
        )[0]

        self.assertIn('temp_path = f"{cache_path}.tmp"', save_cache)
        self.assertIn("os.replace(temp_path, cache_path)", save_cache)
        self.assertIn("shutil.copy2(cache_path, backup_path)", save_cache)
        self.assertIn('"smu_cache.json.bak"', load_cache)

    def test_excel_mapping_can_save_gui_sequence_display(self):
        repo_root = Path(__file__).resolve().parents[1]
        gui_source = (repo_root / "smu_gui.py").read_text(encoding="utf-8")
        standard_save = gui_source.split("def perform_standard_save(self):", 1)[1].split(
            "def global_exception_handler", 1
        )[0]

        self.assertIn('"GUI 순번(신호등+번호)"', gui_source)
        self.assertIn(
            '"sequence_display": self.table.item(start_row, 0).text().strip()',
            standard_save,
        )
        self.assertIn(
            'elif key == "GUI 순번(신호등+번호)": val = sequence_display_val',
            standard_save,
        )
        self.assertIn(
            'elif key == "GUI 순번(신호등+번호)": val = td.get("sequence_display")',
            standard_save,
        )

    def test_excel_traffic_display_uses_colored_plain_circle(self):
        repo_root = Path(__file__).resolve().parents[1]
        gui_tree = ast.parse(
            (repo_root / "smu_gui.py").read_text(encoding="utf-8")
        )
        selected_nodes = []
        for node in gui_tree.body:
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id == "EXCEL_TRAFFIC_COLORS"
                    for target in node.targets
                )
            ) or (
                isinstance(node, ast.FunctionDef)
                and node.name == "format_excel_traffic_display"
            ):
                selected_nodes.append(node)
        namespace = {}
        exec(
            compile(
                ast.Module(body=selected_nodes, type_ignores=[]),
                filename="smu_gui.py",
                mode="exec",
            ),
            namespace,
        )
        formatter = namespace["format_excel_traffic_display"]

        self.assertEqual(
            formatter("🟢 201"),
            ("● 201", 0x50B000),
        )
        self.assertEqual(
            formatter("🔴 빨강"),
            ("● 빨강", 0x0000FF),
        )

    def test_excel_traffic_color_has_whole_cell_fallback(self):
        gui_source = (
            Path(__file__).resolve().parents[1] / "smu_gui.py"
        ).read_text(encoding="utf-8")
        writer_source = gui_source.split(
            "def write_excel_mapped_value", 1
        )[1].split("class ExtractionWorker", 1)[0]

        self.assertIn("cell.Characters(Start=1, Length=1)", writer_source)
        self.assertIn("except Exception:", writer_source)
        self.assertIn("cell.Font.Color = traffic_color", writer_source)

    def test_validation_worker_reports_kosha_cache_and_budget_metrics(self):
        repo_root = Path(__file__).resolve().parents[1]
        gui_source = (repo_root / "smu_gui.py").read_text(encoding="utf-8")
        worker_source = gui_source.split("class ValidationWorker", 1)[1].split(
            "class ModernMappingPanel", 1
        )[0]

        self.assertIn("except KoshaRequestBudgetExceeded as e:", worker_source)
        self.assertIn("공단 API 호출 요약", worker_source)
        self.assertIn('end_metrics["persistent_cache_hits"]', worker_source)

    def test_golden_validation_bypasses_result_cache_without_rewriting_it(self):
        engine = engine_module.MSDSEngineV6()
        fresh_result = {"제품명": "Fresh", "구성성분": "64-17-5(50%)"}

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pdf_path = temp_path / "sample.pdf"
            pdf_path.write_bytes(b"golden-regression-input")
            file_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            registry_path = temp_path / "msds_cache_registry.json"
            cached_registry = {
                file_hash: {
                    "engine_version": engine_module.VERSION,
                    "result": {"제품명": "Stale", "구성성분": ""},
                }
            }
            registry_path.write_text(
                json.dumps(cached_registry, ensure_ascii=False), encoding="utf-8"
            )

            with patch.object(
                engine_module, "__file__", str(temp_path / "msds_engine_v6.py")
            ), patch.object(
                engine, "_process_msds_pipeline_impl", return_value=fresh_result
            ) as actual_pipeline:
                result = engine.process_msds_pipeline(
                    str(pdf_path), bypass_cache=True
                )

            self.assertEqual(result, fresh_result)
            actual_pipeline.assert_called_once()
            self.assertEqual(
                json.loads(registry_path.read_text(encoding="utf-8")), cached_registry
            )

    def test_error_isolation_result_is_not_cached(self):
        engine = engine_module.MSDSEngineV6()
        isolated_result = {
            "제품명": "Failed",
            "구성성분": "",
            "교정_사유": "추출 실패 격리수거: 유효한 성분 데이터가 존재하지 않음",
            "used_engine": "error_isolation",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pdf_path = temp_path / "failed.pdf"
            pdf_path.write_bytes(b"failed-extraction")
            registry_path = temp_path / "msds_cache_registry.json"

            with patch.object(
                engine_module, "__file__", str(temp_path / "msds_engine_v6.py")
            ), patch.object(
                engine, "_process_msds_pipeline_impl", return_value=isolated_result
            ):
                result = engine.process_msds_pipeline(str(pdf_path))

            self.assertEqual(result, isolated_result)
            self.assertFalse(registry_path.exists())

    def test_scan_pipeline_propagates_error_isolation_package(self):
        engine = engine_module.MSDSEngineV6()
        isolated_result = {
            "제품명": "금속광택제튜브타입",
            "구성성분": "",
            "교정_사유": "추출 실패 격리수거: 외부 AI 호출 실패 또는 정제 에러",
            "used_engine": "error_isolation",
        }

        with patch.object(engine_module, "get_ocr_engine", return_value=object()), patch.object(
            engine, "run_flexible_sandwich_pipeline", return_value={"data": "", "raw_data": ""}
        ), patch.object(engine, "_trigger_ai_extraction", return_value=isolated_result):
            result = engine._process_scan_pdf_v6(
                pdf_path="failed.pdf",
                image_list=[{"data": "image", "mimeType": "image/png"}],
                product_name="금속광택제튜브타입",
            )

        self.assertIs(result, isolated_result)

    def test_section3_detection_retries_with_sorted_normalized_blocks(self):
        class _BrokenReadingOrderPage:
            def get_text(self, mode):
                if mode == "text":
                    return "명칭\n및\n함유량\n3.\n구성\n성분"
                if mode == "blocks":
                    return [
                        (0, 0, 100, 20, "3. 구성성분의 명칭 및 함유량"),
                        (0, 30, 100, 50, "64-17-5 50%"),
                    ]
                raise AssertionError(mode)

        engine = engine_module.MSDSEngineV6()
        pages = engine.find_section3_pages(_Document([_BrokenReadingOrderPage()]))

        self.assertEqual(pages, [0])

    def test_recon_honors_cancel_request_before_followup_processing(self):
        engine, document, recon_ocr, _render_log = self._fixture()

        with patch.object(engine_module.fitz, "open", return_value=document), patch.object(
            engine_module, "get_ocr_engine", return_value=recon_ocr
        ):
            with self.assertRaisesRegex(InterruptedError, "사용자 중지 요청"):
                engine.extract_section3_images(
                    "scan.pdf",
                    cancel_check=lambda: recon_ocr.calls >= 1,
                )

        self.assertEqual(recon_ocr.calls, 1)

    def test_pipeline_does_not_convert_cancel_request_to_error_isolation(self):
        engine = engine_module.MSDSEngineV6()

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "cancelled.pdf"
            pdf_path.write_bytes(b"cancelled-extraction")
            with patch.object(
                engine,
                "_process_msds_pipeline_impl",
                side_effect=InterruptedError("사용자 중지 요청"),
            ):
                with self.assertRaisesRegex(InterruptedError, "사용자 중지 요청"):
                    engine.process_msds_pipeline(
                        str(pdf_path),
                        cancel_check=lambda: False,
                    )

    def test_image_pipeline_logs_elapsed_paddle_and_ppstructure_comparison(self):
        engine = engine_module.MSDSEngineV6()
        logs = []

        def fake_pipeline(_pdf_path, log_func=None):
            engine._image_pipeline_active = True
            return {"제품명": "Test", "구성성분": "64-17-5(50%)", "교정_사유": "정상"}

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "scan.pdf"
            pdf_path.write_bytes(b"image-pipeline")
            with patch.object(engine, "_process_msds_pipeline_impl", side_effect=fake_pipeline), patch.object(
                engine_module.time, "perf_counter", side_effect=[10.0, 12.5]
            ):
                engine.process_msds_pipeline(
                    str(pdf_path), log_func=logs.append, bypass_cache=True
                )

        comparison_log = next(log for log in logs if "[이미지 PDF 처리 비교]" in log)
        self.assertIn("전체시간=2.50초", comparison_log)
        self.assertIn("Paddle=0회", comparison_log)
        self.assertIn("PPStructure=미사용(0회)", comparison_log)

    def test_paddleocr3_result_is_normalized_with_pdf_coordinates(self):
        engine = engine_module.MSDSEngineV6()
        raw_result = [
            {
                "rec_texts": ["3. 구성성분의 명칭 및 함유량"],
                "rec_scores": np.array([0.98], dtype=np.float32),
                "rec_polys": np.array(
                    [[[30, 150], [450, 150], [450, 195], [30, 195]]],
                    dtype=np.int32,
                ),
            }
        ]

        lines = engine._normalize_recon_ocr_lines(raw_result, scale=1.5)

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["text"], "3. 구성성분의 명칭 및 함유량")
        self.assertEqual(lines[0]["bbox_pdf"][1], 100.0)
        self.assertEqual(lines[0]["bbox_pdf"][3], 130.0)

    def _fixture(self, with_content=True):
        render_log = []
        pages = [_Page(0, render_log), _Page(1, render_log)]
        document = _Document(pages)
        recon_ocr = _ReconOCR(with_content=with_content)
        engine = engine_module.MSDSEngineV6()
        return engine, document, recon_ocr, render_log

    def _extract_two_page_scan(self, with_content=True):
        engine, document, recon_ocr, render_log = self._fixture(with_content=with_content)
        with patch.object(engine_module.fitz, "open", return_value=document), patch.object(
            engine_module, "get_ocr_engine", return_value=recon_ocr
        ):
            images, section_text, pages, recon_data = engine.extract_section3_images("scan.pdf")
        return engine, document, recon_ocr, render_log, images, section_text, pages, recon_data

    def test_valid_recon_components_skip_crop_and_all_followup_ocr(self):
        (
            engine,
            document,
            recon_ocr,
            render_log,
            images,
            section_text,
            pages,
            recon_data,
        ) = self._extract_two_page_scan()

        self.assertEqual(recon_ocr.calls, 2)
        self.assertEqual(pages, [1])
        self.assertIn("64-17-5", section_text)
        self.assertTrue(recon_data["direct_integrity_passed"])
        self.assertIsNone(recon_data["section_crop"])
        self.assertEqual(images, [])

        with patch.object(engine_module.fitz, "open", return_value=document), patch.object(
            engine_module, "get_paddle_structure_engine", side_effect=AssertionError("제품명 PPStructure 재호출")
        ), patch.object(engine_module.os.path, "exists", return_value=True):
            product_text = engine.extract_section_1(
                "scanned", "scan.pdf", recon_data=recon_data
            )
        self.assertIn("Test Product", product_text)

        self.assertEqual(len(engine._paddle_call_metrics), 2)
        self.assertEqual([entry["scale"] for entry in render_log], [1.5, 1.5])
        print("호출 비교(정찰 직접 채택): 변경 전 정찰+재단 OCR -> 변경 후 정찰 2회, 재단 OCR 0회")

    def test_every_paddle_call_logs_page_size_purpose_and_elapsed_time(self):
        engine = engine_module.MSDSEngineV6()
        recon_ocr = _ReconOCR()
        image = np.ones((120, 200, 3), dtype=np.uint8)
        logs = []

        engine._run_paddle_call(
            recon_ocr,
            "ocr",
            image,
            "계측 검증",
            0,
            log_func=logs.append,
            cls=False,
        )

        self.assertEqual(len(logs), 2)
        self.assertIn("페이지 1", logs[0])
        self.assertIn("200x120px", logs[0])
        self.assertIn("목적: 계측 검증", logs[0])
        self.assertIn("소요시간:", logs[1])

    def test_remote_disabled_never_calls_client_and_logs_only_once(self):
        (
            engine,
            _document,
            _recon_ocr,
            _render_log,
            _images,
            _section_text,
            _pages,
            recon_data,
        ) = self._extract_two_page_scan(with_content=False)
        disabled_client = _RemoteClient(enabled=False)
        engine.remote_ocr_client = disabled_client
        logs = []
        remote_module._reset_disabled_log_for_tests()

        with patch.object(
            engine_module, "get_paddle_structure_engine", side_effect=AssertionError("PPStructure 신규/재사용 호출 금지")
        ):
            results = [
                engine.run_flexible_sandwich_pipeline(
                    "scan.pdf",
                    None,
                    log_func=logs.append,
                    target_page_idx=1,
                    recon_data=recon_data,
                    pre_rendered_crop=recon_data["section_crop"],
                )
                for _ in range(2)
            ]

        self.assertTrue(all(result["status"] == "FALLBACK" for result in results))
        self.assertTrue(all(result["fallback_reason"] == "remote_disabled" for result in results))
        self.assertEqual(disabled_client.calls, 0)
        self.assertEqual(engine._ppstructure_usage_count, 0)
        self.assertEqual(len(engine._paddle_call_metrics), 2)
        self.assertEqual(sum("[원격 OCR 비활성]" in log for log in logs), 1)

    def test_remote_failure_skips_even_loaded_ppstructure_and_hands_off_to_ai(self):
        engine, _document, _ocr, _render, _images, _text, _pages, recon_data = (
            self._extract_two_page_scan(with_content=False)
        )
        ppstructure = _PPStructure()
        remote_client = _RemoteClient(
            enabled=True,
            error=remote_module.RemoteOCRError("offline"),
        )
        engine.remote_ocr_client = remote_client

        with patch.object(engine_module, "_PADDLE_STRUCTURE_ENGINE", ppstructure), patch.object(
            engine_module, "get_paddle_structure_engine", side_effect=AssertionError("PPStructure 신규/재사용 호출 금지")
        ):
            result = engine.run_flexible_sandwich_pipeline(
                "scan.pdf", None, target_page_idx=1,
                recon_data=recon_data, pre_rendered_crop=recon_data["section_crop"],
            )

        self.assertEqual(result["fallback_reason"], "remote_failure")
        self.assertEqual(remote_client.calls, 1)
        self.assertEqual(ppstructure.calls, 0)
        self.assertEqual(engine._ppstructure_usage_count, 0)

    def test_loaded_ppstructure_runs_only_for_clear_table_row_matching_failure(self):
        engine, _document, _ocr, _render, _images, _text, _pages, recon_data = (
            self._extract_two_page_scan(with_content=False)
        )
        recon_data["section_crop"]["table_structure_likely"] = True
        ppstructure = _PPStructure()
        remote_client = _RemoteClient(enabled=True)
        engine.remote_ocr_client = remote_client

        with patch.object(engine_module, "_PADDLE_STRUCTURE_ENGINE", ppstructure), patch.object(
            engine, "verify_integrity_of_local_data", side_effect=[(False, "행 매칭 실패"), (True, "")]
        ):
            result = engine.run_flexible_sandwich_pipeline(
                "scan.pdf",
                None,
                target_page_idx=1,
                recon_data=recon_data,
                pre_rendered_crop=recon_data["section_crop"],
            )

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(remote_client.calls, 1)
        self.assertEqual(ppstructure.calls, 1)
        self.assertEqual(engine._ppstructure_usage_count, 1)
        self.assertEqual(len(engine._paddle_call_metrics), 3)

    def test_trigger_ai_reuses_precomputed_sandwich_result(self):
        engine, _document, _recon_ocr, _render_log, images, section_text, pages, recon_data = (
            self._extract_two_page_scan(with_content=False)
        )
        precomputed = {
            "status": "SUCCESS",
            "data": "64-17-5 50%",
            "raw_data": "64-17-5 50%",
            "image": recon_data["section_crop"]["bytes"],
            "image_item": recon_data["section_crop"]["image_item"],
            "page_index": 1,
        }
        components = [{"cas": "64-17-5", "content": "50%", "name": "에탄올"}]

        with patch.object(engine_module.time, "sleep", return_value=None), patch.object(
            engine, "run_flexible_sandwich_pipeline", side_effect=AssertionError("샌드위치 재실행")
        ), patch.object(engine, "scan_self_diagnosis", return_value=(True, components, {})), patch.object(
            engine, "final_quality_control", return_value=(components, False)
        ), patch.object(engine, "verify_cas_number", return_value=True):
            result = engine._trigger_ai_extraction(
                "scan.pdf",
                image_list=images,
                hybrid_pn="Test Product",
                doc_type="스캔본",
                recon_data=recon_data,
                precomputed_sandwich=precomputed,
            )

        self.assertIn("64-17-5", result["구성성분"])
        self.assertEqual(pages, [1])
        self.assertIn("64-17-5", section_text)

    def test_scan_pipeline_keeps_components_from_ai_result_package(self):
        engine = engine_module.MSDSEngineV6()
        recon_data = {
            "section_crop": {
                "image_item": {"mimeType": "image/png", "data": "cached-crop"},
                "bytes": b"cached-crop",
            }
        }
        ai_package = {
            "구성성분": "64742-54-7(>97%); 68649-42-3(<2%)",
            "제품명": "Super Way Lube 32",
            "신호등": "🟢",
        }

        with patch.object(
            engine,
            "run_flexible_sandwich_pipeline",
            return_value={"status": "FALLBACK", "data": "", "raw_data": ""},
        ), patch.object(engine, "_trigger_ai_extraction", return_value=ai_package):
            components = engine._process_scan_pdf_v6(
                "scan.pdf",
                image_list=[],
                product_name="Super Way Lube 32",
                recon_data=recon_data,
            )

        self.assertEqual(
            [(item["cas"], item["content"]) for item in components],
            [("64742-54-7", ">97%"), ("68649-42-3", "<2%")],
        )


class ProductNameGuardTests(unittest.TestCase):
    def test_explicit_english_product_label_wins(self):
        section_text = (
            "1. Supplier and product\n"
            "1.1. Name of product TEA TREE-857W\n"
            "1.2 Relevant identified uses\n"
        )

        self.assertEqual(
            engine_module.extract_labeled_product_name(section_text),
            "TEA TREE-857W",
        )

    def test_lettered_english_product_label_is_supported(self):
        section_text = (
            "1. CHEMICAL PRODUCT AND COMPANY IDENTIFICATION\n"
            "a. Product name : MICONOL C2M(H)\n"
            "b. Recommended use : Cosmetic\n"
        )

        self.assertEqual(
            engine_module.extract_labeled_product_name(section_text),
            "MICONOL C2M(H)",
        )

    def test_parenthesized_filename_alias_cannot_replace_document_product(self):
        section_text = (
            "1. Supplier and product\n"
            "1.1. Name of product Frag-39069\n"
            "1.2 Relevant identified uses of the substance\n"
        )

        self.assertEqual(
            engine_module.extract_labeled_product_name(section_text),
            "Frag-39069",
        )

    def test_product_name_pipeline_never_uses_filename_fallback(self):
        repo_root = Path(__file__).resolve().parents[1]
        engine_source = (repo_root / "msds_engine_v6.py").read_text(encoding="utf-8")

        self.assertNotIn("file_pn_hint", engine_source)
        self.assertNotIn("clean_filename_product_hint", engine_source)
        self.assertNotIn("파일명 기반 청정 상표", engine_source)

    def test_error_isolation_does_not_promote_filename_to_product_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_pdf = Path(tmp_dir) / "296_R002640 MICONOL C2M(H).pdf"
            result = engine_module.MSDSEngineV6()._get_graceful_error_dict(
                str(fake_pdf),
                "test isolation",
            )

        self.assertEqual(result["제품명"], "")


class BulkExtractionResponsivenessTests(unittest.TestCase):
    def test_legacy_raw_content_is_restored_for_table_rendering(self):
        repo_root = Path(__file__).resolve().parents[1]
        gui_source = (repo_root / "smu_gui.py").read_text(encoding="utf-8")
        gui_tree = ast.parse(gui_source)
        function_node = next(
            node
            for node in gui_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "parse_cached_raw_components"
        )
        namespace = {"re": re}
        exec(
            compile(
                ast.Module(body=[function_node], type_ignores=[]),
                filename="smu_gui.py",
                mode="exec",
            ),
            namespace,
        )

        components = namespace["parse_cached_raw_components"](
            "90170-45-9(25~35%); 7732-18-5(65~75%)"
        )

        self.assertEqual(
            [(item["cas"], item["content"]) for item in components],
            [
                ("90170-45-9", "25~35%"),
                ("7732-18-5", "65~75%"),
            ],
        )

    def test_cache_without_manual_edits_is_not_forced_to_reextract(self):
        repo_root = Path(__file__).resolve().parents[1]
        gui_source = (repo_root / "smu_gui.py").read_text(encoding="utf-8")

        self.assertIn("elif manual and (", gui_source)
        self.assertNotIn(
            'elif manual.get("product_name") == "" or manual.get("raw_content") == "":',
            gui_source,
        )

    def test_each_result_only_resizes_its_own_row(self):
        repo_root = Path(__file__).resolve().parents[1]
        gui_source = (repo_root / "smu_gui.py").read_text(encoding="utf-8")
        add_result_source = gui_source.split(
            "    def add_result_to_table", 1
        )[1].split("    def run_validation", 1)[0]

        self.assertIn("self.table.resizeRowToContents(row)", add_result_source)
        self.assertNotIn("self._safe_resize_rows()", add_result_source)
        self.assertNotIn("self.table.sortItems", add_result_source)

    def test_selective_extraction_uses_cache_hashes_not_visible_rows(self):
        repo_root = Path(__file__).resolve().parents[1]
        gui_source = (repo_root / "smu_gui.py").read_text(encoding="utf-8")
        run_source = gui_source.split(
            "    def run_extraction", 1
        )[1].split("    def add_result_to_table", 1)[0]

        self.assertIn("cached_data = self.cache.get(f_hash)", run_source)
        self.assertIn("cached_data.get(\"engine_version\") == engine.VERSION", run_source)
        self.assertNotIn("if self.table.rowCount() > 0:", run_source)

    def test_pdf_engine_is_process_isolated_and_time_limited(self):
        repo_root = Path(__file__).resolve().parents[1]
        core_source = (repo_root / "msds_core.py").read_text(encoding="utf-8")
        batch_source = (repo_root / "batch_pipeline.py").read_text(encoding="utf-8")

        self.assertIn('multiprocessing.get_context("spawn")', core_source)
        self.assertIn('"MSDS_FILE_TIMEOUT_SECONDS"', batch_source)
        self.assertIn('"MSDS_TEXT_FILE_TIMEOUT_SECONDS"', batch_source)
        self.assertIn("process.terminate()", core_source)


class AICallMetricsTests(unittest.TestCase):
    @staticmethod
    def _response(text):
        return {"candidates": [{"content": {"parts": [{"text": text}]}}]}

    def test_each_ai_response_tracks_its_own_harvest_and_final_application(self):
        engine = engine_module.MSDSEngineV6()
        responses = [
            self._response("Unused AI Product"),
            self._response('{"components":[{"cas":"64-17-5","content":"50%"}]}'),
        ]

        def fake_pipeline(_path, log_func=None):
            engine.call_llm_router({}, purpose="product_name")
            engine.call_llm_router({}, purpose="component_extraction")
            return {"제품명": "Local Product", "구성성분": "64-17-5(50%)", "교정_사유": "정상"}

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "metrics.pdf"
            pdf_path.write_bytes(b"metrics")
            with patch.object(engine, "call_deepseek_with_retry", side_effect=responses), patch.object(
                engine, "_process_msds_pipeline_impl", side_effect=fake_pipeline
            ):
                result = engine.process_msds_pipeline(str(pdf_path), bypass_cache=True)

        metrics = result["metrics"]["ai"]
        self.assertEqual(len(metrics), 2)
        self.assertTrue(metrics[0]["response_received"])
        self.assertTrue(metrics[0]["product_name_harvested"])
        self.assertFalse(metrics[0]["final_result_applied"])
        self.assertEqual(metrics[0]["discard_reason"], "NOT_APPLIED_TO_FINAL_RESULT")
        self.assertFalse(metrics[1]["product_name_harvested"])
        self.assertTrue(metrics[1]["cas_harvested"])
        self.assertTrue(metrics[1]["content_harvested"])
        self.assertEqual(metrics[1]["applied_fields"], ["cas", "content"])
        self.assertTrue(metrics[1]["final_result_applied"])

    def test_empty_synthetic_response_is_not_counted_as_received(self):
        engine = engine_module.MSDSEngineV6()
        with patch.object(engine, "call_deepseek_with_retry", return_value=self._response("")):
            engine.call_llm_router({}, purpose="product_name")

        metric = engine._ai_call_metrics[0]
        self.assertFalse(metric["response_received"])
        self.assertFalse(metric["product_name_harvested"])
        self.assertEqual(metric["discard_reason"], "NO_RESPONSE")

    def test_content_is_applied_only_when_the_final_cas_content_pair_matches(self):
        engine = engine_module.MSDSEngineV6()

        def fake_pipeline(_path, log_func=None):
            engine.call_llm_router({}, purpose="component_extraction")
            return {"제품명": "P", "구성성분": "64-17-5(70%)", "교정_사유": "정상"}

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "content-mismatch.pdf"
            pdf_path.write_bytes(b"metrics")
            with patch.object(
                engine,
                "call_deepseek_with_retry",
                return_value=self._response('{"components":[{"cas":"64-17-5","content":"50%"}]}'),
            ), patch.object(engine, "_process_msds_pipeline_impl", side_effect=fake_pipeline):
                result = engine.process_msds_pipeline(str(pdf_path), bypass_cache=True)

        metric = result["metrics"]["ai"][0]
        self.assertEqual(metric["applied_fields"], ["cas"])
        self.assertTrue(metric["final_result_applied"])

    def test_failover_records_failed_and_received_calls_separately(self):
        engine = engine_module.MSDSEngineV6()
        with patch.object(engine, "call_deepseek_with_retry", side_effect=RuntimeError("offline")), patch.object(
            engine, "call_vertex_gemini_with_retry", return_value=self._response("Vertex Product")
        ):
            engine.call_llm_router({}, purpose="product_name")

        self.assertEqual(len(engine._ai_call_metrics), 2)
        self.assertFalse(engine._ai_call_metrics[0]["response_received"])
        self.assertTrue(engine._ai_call_metrics[0]["discard_reason"].startswith("CALL_ERROR:"))
        self.assertTrue(engine._ai_call_metrics[1]["response_received"])


class SectionTablePairingRegressionTests(unittest.TestCase):
    def test_classification_number_list_is_not_a_concentration(self):
        engine = engine_module.MSDSEngineV6()
        self.assertTrue(engine._is_classification_number_list("1, 2, 3"))
        for valid in ("<1", "〈1", ">3", "1~3", "1-3", "1 to 3"):
            self.assertFalse(engine._is_classification_number_list(valid))
        self.assertEqual(engine._normalize_single_content("〈 1"), "<1%")

    def test_html_parser_uses_named_content_column_not_classification_column(self):
        engine = engine_module.MSDSEngineV6()
        html = """
        <table><tr><td>CAS No.</td><td>구분</td><td>함유량(%)</td></tr>
        <tr><td>1310-73-2</td><td>1, 2, 3</td><td>&lt; 1</td></tr></table>
        """
        result = engine.parse_html_table_to_components(html)
        self.assertEqual(result[0]["cas_no"], "1310-73-2")
        self.assertEqual(result[0]["content"], "<1%")

    def test_component_target_pages_stops_before_section_four(self):
        engine = engine_module.MSDSEngineV6()
        pages = [
            unittest.mock.Mock(), unittest.mock.Mock(), unittest.mock.Mock(), unittest.mock.Mock(), unittest.mock.Mock()
        ]
        for index, page in enumerate(pages):
            page.number = index
            page.get_text.side_effect = lambda mode, i=index: (
                [(0, 0, 1, 1, "4. 응급조치 요령" if i == 3 else "성분 표 계속")]
                if mode == "blocks" else []
            )
        document = _Document(pages)
        with patch.object(engine_module.fitz, "open", return_value=document):
            self.assertEqual(engine._component_target_pages("pikal.pdf", 2), [2, 3])

    @unittest.skipUnless(hasattr(fitz, "Document"), "PyMuPDF required")
    def test_actual_sarafong_and_pikal_pages_preserve_expected_evidence(self):
        test_root = Path(__file__).resolve().parents[1] / "TEST_File"
        sarafong = next(test_root.glob("008_*.pdf"), None)
        pikal = next(test_root.glob("051_*.pdf"), None)
        if not sarafong or not pikal:
            self.skipTest("actual regression PDFs not available")
        engine = engine_module.MSDSEngineV6()
        with fitz.open(sarafong) as document:
            components = engine.extract_table_by_density_clustering(document[1])
        pairing = {item["cas_no"]: item["content"] for item in components}
        self.assertEqual(pairing["1310-73-2"], "<1%")
        self.assertNotEqual(pairing["1310-73-2"], ">3%")

        rendered = engine._render_component_pages(str(pikal), [2, 3])
        self.assertEqual([item["page_index"] for item in rendered], [2, 3])
        self.assertTrue(all(item["data"] for item in rendered))
        self.assertEqual(engine_module._romanize_hangul_token("피칼"), "pikal")


if __name__ == "__main__":
    unittest.main()
