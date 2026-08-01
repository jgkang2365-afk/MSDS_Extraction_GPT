import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from diagnostic_sharing import (
    DiagnosticShareError,
    assert_share_is_safe,
    build_share_package,
    default_user_review,
    latest_successful_share,
    publish_share_package,
    safe_export_name,
)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8")


class ReviewStateTests(unittest.TestCase):
    def test_failed_file_is_auto_selected_but_user_selection_is_separate(self):
        review = default_user_review({"status": "완전 실패"})
        self.assertTrue(review["auto_selected"])
        self.assertTrue(review["user_marked_error"])
        review["user_marked_error"] = False
        self.assertTrue(review["auto_selected"])
        self.assertFalse(review["user_marked_error"])

    def test_completed_file_starts_unselected_and_can_be_selected(self):
        review = default_user_review({"status": "completed"})
        self.assertFalse(review["auto_selected"])
        self.assertFalse(review["user_marked_error"])
        review["user_marked_error"] = True
        review["error_types"] = ["CAS 오류"]
        review["user_note"] = "원문과 다름"
        self.assertTrue(review["user_marked_error"])
        self.assertEqual(review["error_types"], ["CAS 오류"])

    def test_latest_successful_share_ignores_later_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "logs" / "diagnostic_share_history.jsonl"
            history.parent.mkdir(parents=True)
            history.write_text(
                '\n'.join((json.dumps({"push_status": "success", "branch_name": "diagnostics/run-1"}), json.dumps({"push_status": "failed"}))),
                encoding="utf-8",
            )
            self.assertEqual(latest_successful_share(tmp)["branch_name"], "diagnostics/run-1")


class PackageTests(unittest.TestCase):
    def _record(self, root, run_id="run-1", trace_id="trace-1", selected=True, status="completed"):
        source_pdf = Path(root) / f"{trace_id}.pdf"
        source_pdf.write_bytes(b"%PDF-1.4\noriginal-source-bytes\n%%EOF")
        source_dir = Path(root) / "logs" / "runs" / run_id / "files" / trace_id
        images_dir = source_dir / "images"
        images_dir.mkdir(parents=True)
        (images_dir / "section3_crop.png").write_bytes(b"diagnostic-image")
        (images_dir / "component_ai_input_1.png").write_bytes(b"excluded-ai-image")
        diagnostic = {
            "result": {"status": status, "제품명": "제품", "구성성분": "140-11-4(2.00%)"},
            "failures": [{"stage_id": "pairing", "details": {"reason": "CAS_CONTENT_PAIRING_FAILED"}}],
            "images": [
                {"path": "images/section3_crop.png"},
                {"path": "images/component_ai_input_1.png"},
            ],
            "context": {"file_path": r"C:\Users\someone\private\sample.pdf"},
            "raw_response": "should not be shared",
        }
        (source_dir / "diagnostic.json").write_text(json.dumps(diagnostic, ensure_ascii=False), encoding="utf-8")
        (source_dir / "diagnostic.md").write_text(r"source C:\Users\someone\private\sample.pdf", encoding="utf-8")
        return {
            "filename": "012_긴 파일명: FRESH?.pdf", "product_name": "제품",
            "full_path": str(source_pdf),
            "raw_content": "140-11-4(2.00%)", "status": status,
            "source_branch": "codex/source", "source_commit": "abc123",
            "diagnostics": {
                "run_id": run_id, "file_trace_id": trace_id,
                "diagnostic_json": str(source_dir / "diagnostic.json"),
                "diagnostic_markdown": str(source_dir / "diagnostic.md"),
                "diagnostic_images_dir": str(images_dir),
                "trace_context": {"mode": "FULL"},
            },
            "user_review": {
                "user_marked_error": selected, "auto_selected": status != "completed",
                "error_types": ["함유량 오류"], "user_note": "원문 2.00% 누락",
            },
        }

    def test_no_selection_does_not_create_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(DiagnosticShareError, "공유할 오류 파일"):
                build_share_package([self._record(tmp, selected=False)], tmp)
            self.assertFalse((Path(tmp) / "diagnostic_exports").exists())

    def test_only_selected_files_and_safe_representative_images_are_packaged(self):
        with tempfile.TemporaryDirectory() as tmp:
            selected = self._record(tmp, trace_id="selected", selected=True)
            ignored = self._record(tmp, trace_id="normal", selected=False)
            package, summary = build_share_package([selected, ignored], tmp)
            self.assertEqual(summary["selected_error_files"], 1)
            self.assertEqual(len(list((package / "files").iterdir())), 1)
            self.assertEqual(len(list(package.rglob("section3_crop.png"))), 1)
            self.assertFalse(list(package.rglob("*ai_input*")))
            shared_pdf = next(package.rglob("*.pdf"))
            self.assertEqual(shared_pdf.read_bytes(), Path(selected["full_path"]).read_bytes())
            self.assertEqual(summary["source_pdf_counts"]["FULL"], 1)
            self.assertTrue((package / "run_summary.md").exists())
            self.assertTrue((package / "run_summary.json").exists())
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["files"])
            shared_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in package.rglob("*.json"))
            self.assertNotIn(r"C:\Users\someone", shared_text)
            self.assertNotIn("should not be shared", shared_text)
            assert_share_is_safe(package)

    def test_missing_and_too_large_source_pdf_do_not_block_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = self._record(tmp, trace_id="missing")
            Path(missing["full_path"]).unlink()
            large = self._record(tmp, trace_id="large")
            with patch("diagnostic_sharing.SOURCE_PDF_HARD_LIMIT_BYTES", 8):
                package, summary = build_share_package([missing, large], tmp)
            self.assertEqual(summary["source_pdf_counts"]["PARTIAL_SOURCE_PDF_MISSING"], 1)
            self.assertEqual(summary["source_pdf_counts"]["TOO_LARGE"], 1)
            self.assertFalse(list(package.rglob("*.pdf")))

    def test_user_review_diagnosis_records_known_pairing_and_page_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = self._record(tmp, trace_id="sarafong")
            record["filename"] = "008_★msds_사라퐁.pdf"
            record["user_review"]["user_note"] = "1310-73-2(>3%) -->(<1%)"
            package, summary = build_share_package([record], tmp)
            diagnosis = summary["files"][0]["diagnosis"]
            self.assertEqual(diagnosis["reason_code"], "CLASSIFICATION_COLUMN_MISREAD_AS_CONCENTRATION")
            review = json.loads(next(package.rglob("user_review.json")).read_text(encoding="utf-8"))
            self.assertEqual(review["diagnosis"]["expected"], "<1%")

    def test_safe_name_preserves_readable_prefix_and_trace_suffix(self):
        value = safe_export_name('가:나/다*라?.pdf', 'abcdef123456')
        self.assertTrue(value.startswith("가_나_다_라"))
        self.assertTrue(value.endswith("__abcdef12"))


@unittest.skipUnless(shutil.which("git"), "git executable required")
class WorktreePublishTests(unittest.TestCase):
    def test_publish_keeps_dirty_source_tree_unchanged_and_pushes_new_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, bare = root / "repo", root / "remote.git"
            repo.mkdir()
            _git(repo, "init")
            _git(repo, "config", "user.email", "diagnostics@example.invalid")
            _git(repo, "config", "user.name", "Diagnostic Test")
            (repo / "tracked.txt").write_text("base", encoding="utf-8")
            (repo / "smu_cache.json").write_text("base-cache", encoding="utf-8")
            _git(repo, "add", "tracked.txt", "smu_cache.json")
            _git(repo, "commit", "-m", "base")
            source_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
            _git(root, "init", "--bare", str(bare))
            _git(repo, "remote", "add", "origin", str(bare))

            (repo / "smu_cache.json").write_text("user-change", encoding="utf-8")
            (repo / "config.json").write_text("user-config", encoding="utf-8")
            package = root / "package"
            package.mkdir()
            (package / "run_summary.md").write_text("safe", encoding="utf-8")
            (package / "run_summary.json").write_text("{}", encoding="utf-8")
            (package / "manifest.json").write_text("{}", encoding="utf-8")
            before = _git(repo, "status", "--porcelain=v1", "-z").stdout

            with patch("diagnostic_sharing.EXPECTED_REPOSITORY", ""):
                result = publish_share_package(repo, package, source_commit, "run-test")

            after = _git(repo, "status", "--porcelain=v1", "-z").stdout
            self.assertEqual(before, after)
            self.assertTrue(result["branch_name"].startswith("diagnostics/run-"))
            remote_heads = _git(repo, "ls-remote", "--heads", "origin", result["branch_name"]).stdout
            self.assertIn(result["commit_sha"], remote_heads)


if __name__ == "__main__":
    unittest.main()
