import unittest
from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "smu_gui.py").read_text(encoding="utf-8")


class DiagnosticGuiContractTests(unittest.TestCase):
    def test_review_columns_and_explicit_share_controls_exist(self):
        for label in ("분석 요청", "오류 유형", "사용자 메모", "공유 상태"):
            self.assertIn(f'"{label}"', SOURCE)
        for action in ("선택 오류 GitHub 공유", "최근 공유 브랜치 복사", "실행 요약 열기", "공유 폴더 열기"):
            self.assertIn(action, SOURCE)

    def test_review_columns_are_moved_next_to_number_column(self):
        setup = SOURCE.split("enumerate(REVIEW_COLUMN_INDICES)", 1)[1].split("# [V8.6]", 1)[0]
        for constant in ("COL_IDX_REVIEW_REQUEST", "COL_IDX_ERROR_TYPE", "COL_IDX_USER_NOTE", "COL_IDX_SHARE_STATUS"):
            self.assertIn(constant, SOURCE.split("REVIEW_COLUMN_INDICES =", 1)[1].split("class MultiSelectErrorCombo", 1)[0])
        self.assertIn("header_table.moveSection", setup)

    def test_review_columns_can_be_collapsed_as_a_group(self):
        method = SOURCE.split("def toggle_review_columns", 1)[1].split("def _set_review_note", 1)[0]
        self.assertIn("for column in REVIEW_COLUMN_INDICES", method)
        self.assertIn("setColumnHidden", method)
        self.assertIn("오류 입력 펼치기", method)

    def test_error_type_combo_supports_multiple_checked_values(self):
        widget = SOURCE.split("class MultiSelectErrorCombo", 1)[1].split("def natural_sort_key", 1)[0]
        self.assertIn("Qt.ItemIsUserCheckable", widget)
        self.assertIn("def checkedItems", widget)
        self.assertIn("selectionChanged.emit(self.checkedItems())", widget)

    def test_checkbox_updates_cache_without_starting_git(self):
        method = SOURCE.split("def _set_review_selected", 1)[1].split("def _set_review_error_types", 1)[0]
        self.assertIn('review["user_marked_error"]', method)
        self.assertIn("self.save_cache()", method)
        self.assertNotIn("publish_share_package", method)

    def test_git_publish_runs_in_background_worker(self):
        worker = SOURCE.split("class DiagnosticShareWorker", 1)[1].split("class SMUGUI", 1)[0]
        self.assertIn("publish_share_package", worker)
        self.assertIn('self.progress.emit("푸시 중")', worker)


if __name__ == "__main__":
    unittest.main()
