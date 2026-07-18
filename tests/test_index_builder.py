import json
import tempfile
import unittest
from pathlib import Path

from dataset.index_builder import build_dataset


ROOT = Path(__file__).resolve().parents[1]


class IndexBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.output = Path(cls.tempdir.name)
        cls.result = build_dataset(ROOT, output_dir=cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def test_counts_and_validation(self):
        self.assertEqual(297, self.result["manifest"]["master_profile_count"])
        self.assertEqual(305, len(self.result["profiles"]))
        self.assertEqual(0, len(self.result["validation_report"].errors))
        self.assertEqual(15, len(self.result["rules"]))
        self.assertEqual(12, sum(bool(item["active"]) for item in self.result["rules"]))

    def test_talc_and_soapstone_are_two_selectable_variants(self):
        candidates = [
            item for item in self.result["profiles"]
            if item.get("cas_no") == "14807-96-6" and item.get("selectable")
        ]
        self.assertEqual(
            {"활석(석면불포함)", "소우프스톤(호흡성)"},
            {item["canonical_name"] for item in candidates},
        )

    def test_held_excluded_and_incomplete_rows_are_safe(self):
        rules = {item["source_review_id"]: item for item in self.result["rules"]}
        self.assertNotIn("XCAS-004", rules)
        for candidate_id in ("XCAS-007", "XCAS-008", "XCAS-014"):
            self.assertFalse(rules[candidate_id]["active"])
            self.assertEqual("REVIEW_REQUIRED", rules[candidate_id]["review_status"])

    def test_generated_json_round_trips(self):
        for name in (
            "substance_profiles.json",
            "substance_relations.json",
            "recommendation_rules.json",
            "dataset_manifest.json",
        ):
            with (self.output / name).open(encoding="utf-8") as stream:
                self.assertIsNotNone(json.load(stream))

    def test_rebuild_preserves_profile_ids(self):
        before = {item["source_row_id"]: item["profile_id"] for item in self.result["profiles"]}
        rebuilt = build_dataset(ROOT, output_dir=self.output)
        after = {item["source_row_id"]: item["profile_id"] for item in rebuilt["profiles"]}
        self.assertEqual(before, after)

    def test_casless_mineral_dust_has_stable_profile_id(self):
        profile = next(
            item for item in self.result["profiles"]
            if item["canonical_name"] == "기타광물성분진"
        )
        self.assertFalse(profile["cas_no"])
        self.assertTrue(profile["profile_id"].startswith("SP_"))


if __name__ == "__main__":
    unittest.main()
