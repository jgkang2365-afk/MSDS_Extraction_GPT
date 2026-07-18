import unittest

from dataset.index_validator import validate_dataset


class IndexValidatorTest(unittest.TestCase):
    def test_duplicate_ids_and_active_held_rule_fail(self):
        profile = {
            "profile_id": "P1", "cas_no": "7440-50-8", "cas_no_raw": "7440-50-8",
            "active": True, "selectable": True, "source_version": "msds_index_V24",
        }
        rule = {
            "rule_id": "R1", "source_profile_id": "P1", "target_profile_id": "P1",
            "active": True, "final_decision": "보류", "review_status": "REVIEW_REQUIRED",
        }
        report = validate_dataset(
            [profile, dict(profile)], [], [rule], expected_source_master_rows=2
        )
        codes = {item.code for item in report.errors}
        self.assertIn("DUPLICATE_PROFILE_ID", codes)
        self.assertIn("HELD_RULE_ACTIVE", codes)
        self.assertIn("REVIEW_RULE_ACTIVE", codes)

    def test_raw_cas_cannot_be_runtime_key(self):
        report = validate_dataset([
            {"profile_id": "P1", "cas_no": "14808-60-7 등", "cas_no_raw": "14808-60-7 등",
             "active": True, "source_version": "msds_index_V24"}
        ], [], [], expected_source_master_rows=1)
        self.assertFalse(report.is_valid)


if __name__ == "__main__":
    unittest.main()
