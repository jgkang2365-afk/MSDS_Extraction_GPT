import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "golden_regression.py"
SPEC = importlib.util.spec_from_file_location("golden_regression", MODULE_PATH)
golden = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = golden
SPEC.loader.exec_module(golden)


class GoldenRegressionTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "id": "x",
            "file": "x.pdf",
            "product_name": {"expected": "Product X", "allowed_variants": ["PRODUCT X"]},
            "components": [
                {"cas": "7732-18-5", "content_expected": "60~70%"},
                {"cas": "1310-73-2", "content_expected": "<1%"},
            ],
            "cas_missing_components": [],
            "excluded_cas_outside_section_3": [{"cas": "123-86-4"}],
        }

    def test_exact_result_passes(self):
        result = golden.compare_case(
            self.case,
            {"제품명": "Product X", "구성성분": "7732-18-5(60~70%); 1310-73-2(<1%)"},
        )
        self.assertTrue(result.passed, result.errors)

    def test_allowed_product_variant_passes(self):
        result = golden.compare_case(
            self.case,
            {"제품명": "PRODUCT X", "구성성분": "7732-18-5(60~70%); 1310-73-2(<1%)"},
        )
        self.assertTrue(result.passed, result.errors)

    def test_component_order_is_strict(self):
        result = golden.compare_case(
            self.case,
            {"제품명": "Product X", "구성성분": "1310-73-2(<1%); 7732-18-5(60~70%)"},
        )
        self.assertFalse(result.passed)
        self.assertIn("component rows mismatch", result.errors[0])

    def test_content_is_strict(self):
        result = golden.compare_case(
            self.case,
            {"제품명": "Product X", "구성성분": "7732-18-5(60-70%); 1310-73-2(<1%)"},
        )
        self.assertFalse(result.passed)

    def test_outside_section_cas_fails(self):
        result = golden.compare_case(
            self.case,
            {"제품명": "Product X", "구성성분": "7732-18-5(60~70%); 1310-73-2(<1%); 123-86-4(1%)"},
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("forbidden CAS" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
