import json
import inspect
import sys
import tempfile
import types
import unittest
from pathlib import Path

from section_detector_v7 import SectionConfidence, SectionDetectorV7, SectionRange


# 번들 테스트 Python에는 운영 환경의 Google 인증 패키지가 없으므로
# 네트워크를 호출하지 않는 V7 계약 테스트에 필요한 import 표면만 제공한다.
google_stub = sys.modules.setdefault("google", types.ModuleType("google"))
oauth2_stub = sys.modules.setdefault("google.oauth2", types.ModuleType("google.oauth2"))
service_account_stub = sys.modules.setdefault(
    "google.oauth2.service_account", types.ModuleType("google.oauth2.service_account")
)
auth_stub = sys.modules.setdefault("google.auth", types.ModuleType("google.auth"))
transport_stub = sys.modules.setdefault("google.auth.transport", types.ModuleType("google.auth.transport"))
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


class SectionDetectorV7Tests(unittest.TestCase):
    def setUp(self):
        self.detector = SectionDetectorV7()

    def test_korean_section1_and_section2_boundary(self):
        text = """1. 화학제품과 회사에 관한 정보
가. 제품명: 에폭시 프라이머
공급자: 예시회사
2. 유해성·위험성
분류 수치 99"""
        found = self.detector.detect(text, 1)
        self.assertTrue(found.usable)
        self.assertEqual(found.confidence, SectionConfidence.HIGH)
        self.assertIn("에폭시 프라이머", self.detector.extract(text, found))
        self.assertNotIn("분류 수치", self.detector.extract(text, found))

    def test_english_section1_number_variants(self):
        for heading in (
            "SECTION 1 Identification of the substance or mixture and of the supplier",
            "I. Product and company identification",
            "제1항 제품 및 회사에 관한 정보",
        ):
            with self.subTest(heading=heading):
                text = f"{heading}\nProduct name: CLEAN-100\nSupplier: ACME\nSECTION 2 Hazards identification\nDanger"
                self.assertTrue(self.detector.detect(text, 1).usable)

    def test_section1_start_without_boundary_is_limited(self):
        text = "1. 화학제품과 회사에 관한 정보\n제품명: TEST\n회사: ACME\n" + ("본문 " * 1000)
        found = self.detector.detect(text, 1)
        self.assertTrue(found.usable)
        self.assertEqual(found.end_reason, "max_chars")
        self.assertLessEqual(found.end - found.start, 1800)

    def test_cas_line_is_not_mistaken_for_next_numbered_section(self):
        text = "항 3: 구성성분의 명칭 및 함유량\n성분 CAS 번호 함유량\n: 90-80-2\n함유량 99%\n항 4: 응급조치요령"
        found = self.detector.detect(text, 3)
        self.assertTrue(found.usable)
        self.assertIn("90-80-2", self.detector.extract(text, found))

    def test_korean_and_english_section3_boundaries(self):
        cases = (
            "3. 구성성분의 명칭 및 함유량\n성분명 CAS 번호 함유량\nWater 7732-18-5 50%\n4. 응급조치 요령\n전화 119",
            "SECTION III Composition / information on ingredients\nChemical name CAS No. Concentration\nWater 7732-18-5 50%\nSECTION 4 First-aid measures\nCall doctor",
        )
        for text in cases:
            with self.subTest(text=text[:20]):
                found = self.detector.detect(text, 3)
                scoped = self.detector.extract(text, found)
                self.assertTrue(found.usable)
                self.assertIn("7732-18-5", scoped)
                self.assertNotIn("Call doctor", scoped)
                self.assertNotIn("전화 119", scoped)

    def test_ocr_spacing_and_slash_damage(self):
        text = "SECTION 3 COMPOSITION/INFORMATIONONINGREDIENTS\nCASNo Concentration ChemicalName\n7732-18-5 90% Water\nSECTION 4 FIRST AID MEASURES"
        self.assertTrue(self.detector.detect(text, 3).usable)

    def test_weak_title_alone_is_not_section3(self):
        found = self.detector.detect("Ingredients\n향료에 대한 일반 설명과 날짜 2026-01-01", 3)
        self.assertFalse(found.usable)

    def test_weak_title_with_number_and_two_columns_is_accepted(self):
        text = "3. Ingredients\nChemical name CAS No. Concentration\nWater 7732-18-5 90%\n4. First aid measures"
        self.assertTrue(self.detector.detect(text, 3).usable)

    def test_toc_heading_is_rejected_in_favor_of_body(self):
        text = """목차
1. Identification 1
2. Hazards identification 2
3. Composition/information on ingredients 3
4. First-aid measures 4
5. Fire-fighting measures 5

SECTION 1 Identification of the substance or mixture and of the supplier
Product name: BODY PRODUCT
Supplier: ACME
SECTION 2 Hazards identification
본문"""
        found = self.detector.detect(text, 1)
        self.assertTrue(found.usable)
        self.assertGreater(found.start, text.index("SECTION 1" ) - 1)
        self.assertIn("BODY PRODUCT", self.detector.extract(text, found))

    def test_bilingual_duplicate_heading_produces_one_range(self):
        text = "3. 구성성분의 명칭 및 함유량 / Composition/information on ingredients\n성분명 CAS No. 함유량\nWater 7732-18-5 100%\n4. 응급조치 요령"
        found = self.detector.detect(text, 3)
        self.assertTrue(found.usable)
        self.assertEqual(self.detector.extract(text, found).count("7732-18-5"), 1)

    def test_detection_failure(self):
        self.assertEqual(self.detector.detect("일반 안내문", 3).confidence, SectionConfidence.FAILED)


class EngineV7ContractTests(unittest.TestCase):
    def test_invalid_or_missing_engine_version_defaults_to_v6(self):
        from msds_engine import load_engine_version

        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "config.json"
            config.write_text(json.dumps({"msds_engine_version": "unexpected"}), encoding="utf-8")
            self.assertEqual(load_engine_version(config), "v6")
            self.assertEqual(load_engine_version(Path(temp_dir) / "missing.json"), "v6")

    def test_v7_prompts_preserve_scope_hallucination_and_json_rules(self):
        from msds_engine_v7 import V7_COMPONENT_PROMPT_SUFFIX, V7_PRODUCT_PROMPT_SUFFIX

        self.assertIn("Section 1", V7_PRODUCT_PROMPT_SUFFIX)
        self.assertIn("추정", V7_PRODUCT_PROMPT_SUFFIX)
        self.assertIn("Section 3", V7_COMPONENT_PROMPT_SUFFIX)
        self.assertIn("같은 표 행", V7_COMPONENT_PROMPT_SUFFIX)
        self.assertIn("EC 번호", V7_COMPONENT_PROMPT_SUFFIX)
        self.assertIn("REACH", V7_COMPONENT_PROMPT_SUFFIX)
        self.assertIn("부등호", V7_COMPONENT_PROMPT_SUFFIX)
        self.assertIn("영업비밀", V7_COMPONENT_PROMPT_SUFFIX)
        self.assertIn("잔량", V7_COMPONENT_PROMPT_SUFFIX)
        self.assertIn("JSON", V7_COMPONENT_PROMPT_SUFFIX)

    def test_section3_filter_rejects_numbers_from_other_sections(self):
        from msds_engine_v7 import MSDSEngineV7

        engine = MSDSEngineV7.__new__(MSDSEngineV7)
        engine._v7_scope_enabled = True
        engine._v7_sections = {3: SectionRange(3, 0, 80, confidence=SectionConfidence.HIGH)}
        engine._v7_section3_text = "SECTION 3\nWater 7732-18-5 50%"
        values = [
            {"cas": "7732-18-5", "content": "50%"},
            {"cas": "64-17-5", "content": "100 ppm"},
        ]
        self.assertEqual(engine._filter_components_to_section3(values), values[:1])

    def test_comparison_uses_existing_results_without_api_calls(self):
        from msds_engine_v7 import compare_results

        compared = compare_results(
            {"제품명": "V6", "구성성분": "64-17-5(10~20%)"},
            {"제품명": "V7", "구성성분": "64-17-5(10~20%); 7732-18-5(Balance)"},
        )
        self.assertEqual(compared["v6_component_count"], 1)
        self.assertEqual(compared["v7_component_count"], 2)
        self.assertEqual(compared["v7_content"]["7732-18-5"], "Balance")

    def test_fallback_is_item_scoped_not_full_pipeline_restart(self):
        from msds_engine_v7 import MSDSEngineV7

        source = inspect.getsource(MSDSEngineV7.process_msds_pipeline)
        self.assertEqual(source.count("super().process_msds_pipeline"), 1)
        self.assertIn("_trigger_ai_extraction", source)
        self.assertIn("_run_v6_product_fallback", source)


if __name__ == "__main__":
    unittest.main()
