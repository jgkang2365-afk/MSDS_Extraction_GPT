import unittest
from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "smu_gui.py").read_text(encoding="utf-8")


class DiagnosticGuiContractTests(unittest.TestCase):
    def test_review_columns_and_explicit_share_controls_exist(self):
        for label in ("분석 요청", "오류 유형", "사용자 메모", "공유 상태"):
            self.assertIn(f'"{label}"', SOURCE)
        for action in ("선택 오류 GitHub 공유", "최근 공유 브랜치 복사", "실행 요약 열기", "공유 폴더 열기"):
            self.assertIn(action, SOURCE)

    def test_checkbox_updates_cache_without_starting_git(self):
        method = SOURCE.split("def _set_review_selected", 1)[1].split("def _set_review_error_type", 1)[0]
        self.assertIn('review["user_marked_error"]', method)
        self.assertIn("self.save_cache()", method)
        self.assertNotIn("publish_share_package", method)

    def test_git_publish_runs_in_background_worker(self):
        worker = SOURCE.split("class DiagnosticShareWorker", 1)[1].split("class SMUGUI", 1)[0]
        self.assertIn("publish_share_package", worker)
        self.assertIn('self.progress.emit("푸시 중")', worker)


if __name__ == "__main__":
    unittest.main()
