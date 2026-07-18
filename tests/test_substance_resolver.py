import unittest
from pathlib import Path

from dataset.index_loader import DatasetIndex, is_dataset_v2_enabled
from dataset.substance_resolver import SubstanceResolver


ROOT = Path(__file__).resolve().parents[1]


class SubstanceResolverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = DatasetIndex.from_directory(ROOT / "data/generated")
        cls.resolver = SubstanceResolver(cls.index)

    def test_feature_flag_defaults_off(self):
        self.assertFalse(is_dataset_v2_enabled({}))
        self.assertTrue(is_dataset_v2_enabled({"MSDS_DATASET_V2": "true"}))

    def test_same_cas_returns_only_two_selectable_variants(self):
        result = self.resolver.resolve("활석", "14807-96-6")
        self.assertTrue(result["requires_user_choice"])
        self.assertEqual(
            {"활석(석면불포함)", "소우프스톤(호흡성)"},
            {item["canonical_name"] for item in result["same_cas_candidates"]},
        )

    def test_welding_rule_requires_process_context(self):
        without_context = self.resolver.resolve("철", "7439-89-6")
        with_context = self.resolver.resolve(
            "철", "7439-89-6", {"process_name": "스테인리스 용접"}
        )
        self.assertNotIn(
            "산화철(분진, 흄)",
            {item["canonical_name"] for item in without_context["related_recommendations"]},
        )
        self.assertIn(
            "산화철(분진, 흄)",
            {item["canonical_name"] for item in with_context["related_recommendations"]},
        )

    def test_asbestos_relation_never_auto_confirms(self):
        result = self.resolver.resolve(
            "활석", "14807-96-6", {"asbestos_status": "unknown"}
        )
        asbestos = next(
            item for item in result["related_recommendations"]
            if item["canonical_name"] == "석면"
        )
        self.assertTrue(asbestos["requires_user_confirmation"])
        self.assertEqual("analytical_relation", asbestos["selection_source"])

    def test_rutile_returns_two_default_multiple_recommendations(self):
        result = self.resolver.resolve("금홍석", "1317-80-2")
        recommendations = {
            item["canonical_name"]: item for item in result["related_recommendations"]
        }
        self.assertEqual({"이산화티타늄", "기타광물성분진"}, set(recommendations))
        self.assertTrue(all(item["default_selected"] for item in recommendations.values()))
        self.assertTrue(all(item["allow_multiple"] for item in recommendations.values()))
        self.assertTrue(all(item["requires_user_confirmation"] for item in recommendations.values()))

    def test_crystalline_silica_relations_and_amorphous_default(self):
        for name, cas_no in (("크리스토발라이트", "14464-46-1"), ("트리디마이트", "15468-32-3")):
            result = self.resolver.resolve(name, cas_no)
            quartz = next(
                item for item in result["related_recommendations"]
                if item["canonical_name"] == "석영"
            )
            self.assertTrue(quartz["default_selected"])
            self.assertEqual("analytical_relation", quartz["selection_source"])
        amorphous = self.resolver.resolve("무정형 실리카", "7631-86-9")
        quartz = next(
            item for item in amorphous["related_recommendations"]
            if item["canonical_name"] == "석영"
        )
        self.assertFalse(quartz["default_selected"])

    def test_legacy_sort_codes_migrate_to_stable_ids(self):
        migrated = self.index.migrate_legacy_codes(["2D-11-031", "2D-11-032"])
        self.assertEqual(2, len(migrated))
        self.assertTrue(all(value.startswith("SP_") for value in migrated))


if __name__ == "__main__":
    unittest.main()
