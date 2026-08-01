import json
import tempfile
import unittest
from pathlib import Path

from diagnostic_trace import activate_trace, create_trace_context
from msds_utils_v3 import (
    is_valid_cas,
    normalize_cas_candidate,
    normalize_cas_separators_in_text,
    normalize_decimal_comma_content,
)


class CasNormalizationTests(unittest.TestCase):
    def test_supported_unicode_dashes_normalize_to_ascii(self):
        for raw in (
            "140-11-4", "140−11−4", "140‐11‐4", "140‑11‑4",
            "140‒11‒4", "140–11–4", "140—11—4", "140―11―4",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_cas_candidate(raw), "140-11-4")
                self.assertTrue(is_valid_cas(raw))

    def test_non_cas_values_are_not_promoted(self):
        for raw in (
            "140-11-5", "205-399-7", "01-2119638272-42-xxxx",
            "12/01/2024", "2024-01-12",
        ):
            with self.subTest(raw=raw):
                self.assertFalse(is_valid_cas(raw))

    def test_text_normalization_only_changes_cas_shaped_tokens(self):
        source = "CAS 140−11−4 / date 2024−01−12 / range 10−20"
        result = normalize_cas_separators_in_text(source)
        self.assertIn("CAS 140-11-4", result)
        self.assertIn("date 2024−01−12", result)
        self.assertIn("range 10−20", result)


class DecimalCommaNormalizationTests(unittest.TestCase):
    def test_percent_concentrations_are_normalized(self):
        expected = {
            "2,00%": "2.00%",
            "0,1%": "0.1%",
            "0,1-1,0%": "0.1-1.0%",
            "0,1 ~ 1,0 %": "0.1 ~ 1.0 %",
            "<0,5%": "<0.5%",
            "≥ 1,25%": "≥ 1.25%",
        }
        for raw, normalized in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_decimal_comma_content(raw), normalized)

    def test_non_percent_comma_values_are_unchanged(self):
        for raw in (
            "1,000 ppm", "10,000 mg/kg", "1,000", "2024, 2025",
            "CAS 140-11-4, EC 205-399-7",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_decimal_comma_content(raw), raw)

    def test_transform_events_preserve_before_and_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = create_trace_context(
                run_id="normalization", file_trace_id="file", mode="FULL", base_dir=tmp
            )
            with activate_trace(context):
                normalize_cas_candidate("140−11−4")
                normalize_decimal_comma_content("2,00%")
            events_path = Path(tmp) / "normalization" / "files" / "file" / "events.jsonl"
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
            transforms = [item["details"] for item in events if item["event_type"] == "candidate_transform"]
            self.assertIn(
                {"field": "cas", "before": "140−11−4", "after": "140-11-4", "transform": "unicode_dash_normalization", "module": "msds_utils_v3"},
                transforms,
            )
            self.assertIn(
                {"field": "content", "before": "2,00%", "after": "2.00%", "transform": "decimal_comma_normalization", "module": "msds_utils_v3"},
                transforms,
            )


if __name__ == "__main__":
    unittest.main()
