import unittest
from pathlib import Path

from dataset.review_decision_loader import DEFAULT_REVIEW_WORKBOOK, load_review_decisions


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data/review/2026-07-18_msds_index_review/MSDS_측정인자_1차검토표_최종수정.xlsx"


class ReviewDecisionLoaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = load_review_decisions(REVIEW)

    def test_all_approved_rows_are_loaded(self):
        self.assertEqual(27, len(self.result.same_cas_decisions))
        self.assertEqual(16, len(self.result.cross_cas_decisions))
        self.assertEqual(43, self.result.decision_count)

    def test_only_versioned_review_path_is_used(self):
        self.assertEqual(
            Path("data/review/2026-07-18_msds_index_review/MSDS_측정인자_1차검토표_최종수정.xlsx"),
            DEFAULT_REVIEW_WORKBOOK,
        )
        for name in (
            "same_cas_candidates.csv", "cross_cas_relation_candidates.csv",
            "gui_hardcoding_inventory.csv", "source_column_mapping.csv",
        ):
            self.assertFalse((ROOT / "data/review" / name).exists())

    def test_amendments_and_incomplete_policy_are_preserved(self):
        decisions = {item["candidate_id"]: item for item in self.result.cross_cas_decisions}
        self.assertEqual("바륨 및 그 가용성화합물", decisions["XCAS-012"]["target_name"])
        self.assertEqual("은(가용성)", decisions["XCAS-013"]["target_name"])
        self.assertIsNone(decisions["XCAS-007"]["allow_multiple"])
        self.assertEqual("보류", decisions["XCAS-014"]["final_decision"])


if __name__ == "__main__":
    unittest.main()
