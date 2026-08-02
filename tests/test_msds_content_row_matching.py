import hashlib
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import msds_engine_v6 as engine_module


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_FILE_DIR = REPO_ROOT / "TEST_File"
CACHE_PATH = REPO_ROOT / "msds_cache_registry.json"


class _FakePage:
    def __init__(self, lines):
        self._words = []
        self._blocks = []
        for block_no, (y, texts) in enumerate(lines):
            x = 20.0
            line_words = []
            for word_no, text in enumerate(texts):
                width = max(12.0, len(text) * 6.0)
                word = (x, y, x + width, y + 10.0, text, block_no, 0, word_no)
                self._words.append(word)
                line_words.append(text)
                x += width + 12.0
            self._blocks.append((20.0, y, x, y + 10.0, " ".join(line_words), block_no, 0))

    def get_text(self, kind):
        if kind == "words":
            return list(self._words)
        if kind == "blocks":
            return list(self._blocks)
        raise AssertionError(f"unexpected text kind: {kind}")


def _cache_sha256():
    return hashlib.sha256(CACHE_PATH.read_bytes()).hexdigest()


class ContentRowMatchingUnitTests(unittest.TestCase):
    def setUp(self):
        self.engine = engine_module.MSDSEngineV6(use_remote_ocr=False)

    def test_korean_comparator_normalization_preserves_meaning(self):
        cases = {
            "2 미만": "<2%",
            "2 이하": "≤2%",
            "2 이상": "≥2%",
            "2 초과": ">2%",
            "99.5<": ">99.5%",
            "99.5>": "<99.5%",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self.engine._normalize_single_content(raw), expected)

    def test_percentless_korean_comparator_is_accepted_in_same_row(self):
        cases = {
            "미만": "<2%",
            "이하": "≤2%",
            "이상": "≥2%",
            "초과": ">2%",
        }
        for suffix, expected in cases.items():
            with self.subTest(suffix=suffix):
                page = _FakePage(
                    [
                        (100.0, ["3.", "구성성분의", "명칭", "및", "함유량"]),
                        (140.0, ["Test", "64-17-5", "2", suffix]),
                        (200.0, ["4.", "응급조치요령"]),
                    ]
                )
                components, _ = self.engine.extract_from_text_regex(page)
                self.assertEqual(components[0]["content"], expected)

    def test_section4_and_footer_page_number_are_not_content(self):
        page = _FakePage(
            [
                (100.0, ["항", "3:", "구성성분의", "명칭", "및", "함유량"]),
                (140.0, ["Test", "64-17-5"]),
                (180.0, ["항", "4:", "응급조치요령"]),
                (700.0, ["Sigma-", "쪽", "2", "/", "10"]),
            ]
        )
        components, _ = self.engine.extract_from_text_regex(page)
        self.assertEqual(components[0]["content"], "미기재%")

    def test_independent_adjacent_row_does_not_inherit_previous_content(self):
        page = _FakePage(
            [
                (100.0, ["3.", "구성성분의", "명칭", "및", "함유량", "CAS번호"]),
                (140.0, ["First", "64-17-5", "1", "-", "5"]),
                (160.0, ["Second", "67-64-1"]),
                (200.0, ["4.", "응급조치요령"]),
            ]
        )
        components, _ = self.engine.extract_from_text_regex(page)
        by_cas = {item["cas"]: item["content"] for item in components}
        self.assertEqual(by_cas["64-17-5"], "1~5%")
        self.assertEqual(by_cas["67-64-1"], "미기재%")

    def test_note_and_revision_noise_keep_cas_without_content(self):
        cases = {
            "note": ["Test", "64-17-5", "50%", "Note"],
            "revision": ["Rev.03", "Test", "64-17-5", "50%"],
        }
        for label, row in cases.items():
            with self.subTest(label=label):
                page = _FakePage([
                    (100.0, ["3.", "구성성분의", "명칭", "및", "함유량"]),
                    (140.0, row),
                    (200.0, ["4.", "응급조치요령"]),
                ])
                components, _ = self.engine.extract_from_text_regex(page)
                self.assertEqual(len(components), 1)
                self.assertEqual(components[0]["cas"], "64-17-5")
                self.assertEqual(components[0]["content"], "미기재%")

        english_page = _FakePage(
            [
                (100.0, ["SECTION", "3:", "Composition"]),
                (140.0, ["Test", "64-17-5", "50%", "Note"]),
                (200.0, ["SECTION", "4:", "First", "Aid"]),
            ]
        )
        components, _ = self.engine.extract_from_text_regex(english_page)
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["cas"], "64-17-5")
        self.assertEqual(components[0]["content"], "미기재%")

    def test_normal_percent_candidate_remains_available(self):
        page = _FakePage([
            (100.0, ["3.", "구성성분의", "명칭", "및", "함유량"]),
            (140.0, ["Test", "64-17-5", "50%"]),
            (200.0, ["4.", "응급조치요령"]),
        ])
        components, _ = self.engine.extract_from_text_regex(page)
        self.assertEqual(components[0]["content"], "50%")

    def test_long_numbered_iupac_name_does_not_backtrack(self):
        page = _FakePage(
            [
                (
                    100.0,
                    [
                        "3.",
                        "COMPOSITION",
                        "CAS",
                        "NO.",
                        "CONTENTS(%)",
                    ],
                ),
                (
                    140.0,
                    [
                        "Imidazolium",
                        "compounds,",
                        "1-[2-(carboxymethoxy)ethyl]-1-(carboxymethyl)-"
                        "4,5-dihydro-2-norcoco",
                        "68650-39-5",
                        "30",
                        "-",
                        "40",
                    ],
                ),
                (200.0, ["4.", "FIRST", "AID", "MEASURES"]),
            ]
        )

        started = time.perf_counter()
        components, _ = self.engine.extract_from_text_regex(page)
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.5)
        self.assertEqual(
            [(item["cas"], item["content"]) for item in components],
            [("68650-39-5", "30~40%")],
        )

    def test_visual_grid_layout_variants_keep_same_row_evidence(self):
        cases = {
            "separate_boxes_same_visual_row": ([(100.0, ["3.", "구성성분의", "명칭", "및", "함유량"]), (140.0, ["Test", "64-17-5", "50%"]), (200.0, ["4.", "응급조치요령"])], "50%"),
            "two_line_ingredient_name": ([(100.0, ["3.", "구성성분의", "명칭", "및", "함유량"]), (120.0, ["Long", "Chemical", "Name"]), (130.0, ["Continuation", "Name"]), (150.0, ["64-17-5", "50%"]), (200.0, ["4.", "응급조치요령"])], "50%"),
            "content_split_across_boxes": ([(100.0, ["3.", "구성성분의", "명칭", "및", "함유량"]), (140.0, ["Test", "64-17-5", "1", "-", "5"]), (200.0, ["4.", "응급조치요령"])], "1~5%"),
        }
        for label, (lines, expected) in cases.items():
            with self.subTest(label=label):
                components, _ = self.engine.extract_from_text_regex(_FakePage(lines))
                self.assertEqual(components[0]["content"], expected)

    def test_vertical_card_layout_uses_field_context(self):
        page = _FakePage([
            (100.0, ["3.", "구성성분의", "명칭", "및", "함유량"]),
            (130.0, ["성분", "Ethanol"]), (150.0, ["CAS", "번호"]),
            (170.0, ["64-17-5"]), (190.0, ["함유량"]), (210.0, ["50%"]),
            (260.0, ["4.", "응급조치요령"]),
        ])
        components, _ = self.engine.extract_from_text_regex(page)
        self.assertEqual(components[0]["content"], "50%")

    def test_multiple_cas_in_one_row_share_only_explicit_row_content(self):
        page = _FakePage([
            (100.0, ["3.", "구성성분의", "명칭", "및", "함유량"]),
            (140.0, ["Blend", "64-17-5", "67-64-1", "50%"]),
            (200.0, ["4.", "응급조치요령"]),
        ])
        components, _ = self.engine.extract_from_text_regex(page)
        by_cas = {item["cas"]: item["content"] for item in components}
        self.assertEqual(by_cas, {"64-17-5": "50%", "67-64-1": "50%"})

    def test_html_cells_and_rowspan_use_only_same_tr_evidence(self):
        same_row_html = """<table><tr><td>Name</td><td>64-17-5</td><td>50%</td></tr></table>"""
        same_row = self.engine.parse_html_table_to_components(same_row_html)
        self.assertEqual([(item["cas"], item["content"]) for item in same_row], [("64-17-5", "50%")])
        rowspan_html = """<table><tr><td rowspan="2">50%</td><td>First</td><td>64-17-5</td></tr><tr><td>Second</td><td>67-64-1</td></tr></table>"""
        rowspan = self.engine.parse_html_table_to_components(rowspan_html)
        self.assertEqual([(item["cas"], item["content"]) for item in rowspan], [("64-17-5", "50%"), ("67-64-1", "미기재%")])

    def test_identifier_and_outside_field_numbers_are_not_content(self):
        cases = {
            "ec_identifier": ["Test", "64-17-5", "EC", "202-016-5"],
            "outside_field_number": ["Test", "64-17-5"],
        }
        for label, cas_row in cases.items():
            with self.subTest(label=label):
                lines = [(100.0, ["3.", "구성성분의", "명칭", "및", "함유량"]), (140.0, cas_row)]
                if label == "outside_field_number":
                    lines.append((160.0, ["Reference", "50"]))
                lines.append((220.0, ["4.", "응급조치요령"]))
                components, _ = self.engine.extract_from_text_regex(_FakePage(lines))
                self.assertEqual(components[0]["content"], "미기재%")

class ContentRowMatchingRealPdfTests(unittest.TestCase):
    def _run_cache_free(self, prefix):
        pdf_path = next(TEST_FILE_DIR.glob(f"{prefix}*.pdf"))
        before_cache = _cache_sha256()
        ai_calls = []
        ocr_calls = []
        ppstructure_calls = []
        engine = engine_module.MSDSEngineV6(use_remote_ocr=False)

        def fake_ai(payload, **kwargs):
            ai_calls.append(
                {
                    "has_images": "inlineData" in str(payload),
                    "model": kwargs.get("model"),
                    "is_scanned_strict": kwargs.get("is_scanned_strict"),
                }
            )
            return {
                "candidates": [{"content": {"parts": [{"text": ""}]}}],
                "actual_engine_label": "diagnostic-blocked",
            }

        def fail_ocr(*args, **kwargs):
            ocr_calls.append((args, kwargs))
            raise AssertionError("digital fixture must not call OCR")

        def fail_ppstructure(*args, **kwargs):
            ppstructure_calls.append((args, kwargs))
            raise AssertionError("digital fixture must not call PPStructure")

        engine.call_llm_router = fake_ai
        with (
            patch.object(engine_module, "get_ocr_engine", side_effect=fail_ocr),
            patch.object(
                engine_module,
                "get_paddle_structure_engine",
                side_effect=fail_ppstructure,
            ),
        ):
            result = engine.process_msds_pipeline(
                str(pdf_path),
                log_func=None,
                bypass_cache=True,
            )

        self.assertEqual(_cache_sha256(), before_cache)
        self.assertEqual(result["doc_type"], "디지털")
        self.assertEqual(ocr_calls, [])
        self.assertEqual(ppstructure_calls, [])
        self.assertEqual(engine._paddle_call_metrics, [])
        self.assertFalse(engine.remote_ocr_client.enabled)
        self.assertLessEqual(len(ai_calls), 1)
        self.assertTrue(all(not call["has_images"] for call in ai_calls))
        return result

    def test_027_does_not_use_footer_page_number_as_content(self):
        result = self._run_cache_free("027_")
        self.assertEqual(result["구성성분"], "90-80-2(미기재%)")

    def test_050_extracts_less_than_two_without_previous_row_inheritance(self):
        if not any(TEST_FILE_DIR.glob("050_*.pdf")):
            self.skipTest("승인 회귀 세트가 001~049로 정리되어 050 PDF가 없습니다")
        result = self._run_cache_free("050_")
        components = result["구성성분"].split("; ")
        self.assertEqual(len(components), 13)
        self.assertIn("13463-67-7(1~5%)", components)
        self.assertIn("1330-20-7(<2%)", components)
        self.assertNotIn("1330-20-7(1~5%)", components)


if __name__ == "__main__":
    unittest.main()
