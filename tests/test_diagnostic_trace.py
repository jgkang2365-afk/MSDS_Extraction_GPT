import json
import os
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from diagnostic_trace import (
    DiagnosticMode,
    activate_trace,
    cleanup_retention,
    create_trace_context,
    diagnostic_mode,
    finalize_trace,
    get_tracer,
    redact,
    retention_settings,
)


class DiagnosticModeTests(unittest.TestCase):
    def test_default_and_environment_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(diagnostic_mode(), DiagnosticMode.SUMMARY)
        with patch.dict(os.environ, {"MSDS_DIAGNOSTIC_MODE": "full"}, clear=True):
            self.assertEqual(diagnostic_mode(), DiagnosticMode.FULL)

    def test_invalid_mode_falls_back_to_summary(self):
        with patch.dict(os.environ, {"MSDS_DIAGNOSTIC_MODE": "invalid"}, clear=True):
            self.assertEqual(diagnostic_mode(), DiagnosticMode.SUMMARY)

    def test_optional_config_provides_mode_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text('{"diagnostic":{"mode":"OFF","retention":{"retention_days":3,"max_runs":5}}}', encoding="utf-8")
            self.assertEqual(diagnostic_mode(config), DiagnosticMode.OFF)
            self.assertEqual(retention_settings(config), {"retention_days": 3, "max_runs": 5, "max_total_mb": None})


class TraceTests(unittest.TestCase):
    def test_common_ids_stage_and_lineage_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = create_trace_context("input.pdf", run_id="run", file_trace_id="file", mode="FULL", base_dir=tmp)
            with activate_trace(context) as tracer:
                with tracer.stage("parse"):
                    source = tracer.candidate({"text": "raw"}, candidate_id="c1")
                    self.assertEqual(tracer.transform(source, {"text": "normalized"}), "c1")
                    tracer.candidate({"text": "derived"}, candidate_id="c2", derived_from="c1")
                    tracer.reject("c2", "low confidence")
                    tracer.merge(["c1", "c2"], "c1")
                    tracer.override("c1", "human review")
                tracer.skip("optional_remote", "not configured")
                with self.assertRaises(RuntimeError):
                    with tracer.stage("fault"):
                        raise RuntimeError("expected")
                diagnostic = finalize_trace(context, {"status": "ok"})
            self.assertIsNotNone(diagnostic)
            trace_dir = Path(tmp) / "run" / "files" / "file"
            events = [json.loads(line) for line in (trace_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(all(e["run_id"] == "run" and e["file_trace_id"] == "file" for e in events))
            self.assertTrue(all("timestamp" in e and "elapsed_ms" in e for e in events))
            self.assertTrue(all(e["event_type"] == e["event"] for e in events))
            self.assertEqual(next(e for e in events if e["event"] == "candidate_transform")["candidate_id"], "c1")
            self.assertTrue({"candidate_merged", "candidate_override", "stage_skip", "stage_error"}.issubset({e["event"] for e in events}))
            report = json.loads(Path(diagnostic).read_text(encoding="utf-8"))
            self.assertEqual(next(x for x in report["candidates"] if x["candidate_id"] == "c2")["derived_from"], "c1")
            self.assertIn("stage_error", (trace_dir / "diagnostic.md").read_text(encoding="utf-8"))

    def test_context_is_serializable_and_activation_is_scoped(self):
        context = create_trace_context(run_id="run", file_trace_id="file", mode="OFF")
        restored = type(context).from_dict(context.to_dict())
        self.assertEqual(restored, context)
        self.assertIsNone(get_tracer().event("outside"))
        with activate_trace(restored) as tracer:
            self.assertIs(get_tracer(), tracer)
        self.assertIsNone(get_tracer().event("outside-again"))
        with activate_trace(None) as tracer:
            self.assertIsNone(tracer.event("null-context"))

    def test_off_creates_no_diagnostic_output_and_failures_are_soft(self):
        with tempfile.TemporaryDirectory() as tmp:
            off = create_trace_context(run_id="run", file_trace_id="off", mode="OFF", base_dir=tmp)
            with activate_trace(off) as tracer:
                tracer.event("anything")
                self.assertIsNone(tracer.finalize())
            self.assertFalse((Path(tmp) / "run").exists())
            context = create_trace_context(run_id="run", file_trace_id="soft", mode="FULL", base_dir=tmp)
            with activate_trace(context) as tracer:
                tracer._events_path = Path(tmp) / "missing" / "events.jsonl"
                self.assertIsNone(tracer.event("will_not_raise"))


class SecurityAndOutputTests(unittest.TestCase):
    def test_redaction_handles_authorization_secrets_and_base64(self):
        value = redact({"api_key": "abc", "Authorization": "Bearer live-token", "payload": "A" * 100,
                        "nested": {"private_key": "-----BEGIN PRIVATE KEY-----x-----END PRIVATE KEY-----"}})
        self.assertEqual(value["api_key"], "[REDACTED]")
        self.assertEqual(value["Authorization"], "[REDACTED]")
        self.assertEqual(value["payload"], "[REDACTED BASE64]")
        self.assertEqual(value["nested"]["private_key"], "[REDACTED]")

    def test_summary_only_saves_critical_image_and_reports(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is optional")
        with tempfile.TemporaryDirectory() as tmp:
            context = create_trace_context(run_id="run", file_trace_id="file", mode="SUMMARY", base_dir=tmp)
            with activate_trace(context) as tracer:
                canvas = Image.new("RGB", (30, 30), "white")
                ordinary = tracer.image(canvas, name="ordinary")
                self.assertTrue(ordinary.exists())
                saved = tracer.image(canvas, name="critical", critical=True, candidate_boxes={"c1": (1, 1, 10, 10)},
                                     table_lines=[(0, 15, 29, 15)])
                self.assertTrue(saved.exists())
                intermediate = tracer.image(canvas, name="intermediate", critical=True, intermediate=True)
                self.assertTrue(intermediate.exists())
                diagnostic = tracer.finalize({"status": "ok"})
            self.assertTrue(Path(diagnostic).exists())
            self.assertTrue((Path(tmp) / "run" / "files" / "file" / "diagnostic.md").exists())
            self.assertFalse(ordinary.exists())
            self.assertFalse(intermediate.exists())

    def test_parent_finalizer_reconstructs_child_journal_and_stage_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = create_trace_context(run_id="run", file_trace_id="shared", mode="FULL", base_dir=tmp)
            with activate_trace(context) as parent:
                parent.candidate("parent", candidate_id="candidate-001")
            # This simulates a process deserializing context and opening a
            # separate tracer instance against the same per-file JSONL journal.
            with activate_trace(context.to_dict()) as child:
                child.candidate("child", candidate_id="candidate-002", derived_from="candidate-001")
                child.stage_result("engine", status="partial", output_summary={"engine": "ocr"}, candidate_count=2)
                child.finalize({"child": "complete"})
            with activate_trace(context) as parent:
                diagnostic = parent.finalize({"parent": "complete"})
            payload = json.loads(Path(diagnostic).read_text(encoding="utf-8"))
            self.assertEqual({x["candidate_id"] for x in payload["candidates"]}, {"candidate-001", "candidate-002"})
            stage = next(x for x in payload["stages"] if x["event_type"] == "stage_result")
            self.assertEqual(stage["details"]["status"], "partial")
            self.assertEqual(payload["result"], {"parent": "complete"})

    def test_same_tracer_concurrent_events_remain_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = create_trace_context(run_id="run", file_trace_id="threaded", mode="FULL", base_dir=tmp)
            with activate_trace(context) as tracer:
                threads = [threading.Thread(target=lambda n=i: tracer.event("parallel", worker=n)) for i in range(12)]
                for item in threads:
                    item.start()
                for item in threads:
                    item.join()
                tracer.finalize({"status": "ok"})
            events = (Path(tmp) / "run" / "files" / "threaded" / "events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(sum(json.loads(line)["event_type"] == "parallel" for line in events), 12)

    def test_image_aspect_ratio_change_emits_warning(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is optional")
        with tempfile.TemporaryDirectory() as tmp:
            context = create_trace_context(run_id="run", file_trace_id="aspect", mode="FULL", base_dir=tmp)
            with activate_trace(context) as tracer:
                tracer.image(
                    Image.new("RGB", (100, 100), "white"),
                    name="distorted",
                    source_width=200,
                    source_height=100,
                    output_width=100,
                    output_height=100,
                )
                tracer.finalize({"status": "failed"})
            events = [json.loads(line) for line in (Path(tmp) / "run" / "files" / "aspect" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            warning = next(item for item in events if item["event_type"] == "image_warning")
            self.assertEqual(warning["details"]["warning_code"], "IMAGE_ASPECT_RATIO_CHANGED")


class RetentionTests(unittest.TestCase):
    def test_cleanup_is_limited_to_logs_runs_and_keeps_newer_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "logs" / "runs"
            old, new = root / "old", root / "new"
            old.mkdir(parents=True)
            new.mkdir()
            old_time = time.time() - 3 * 86400
            os.utime(old, (old_time, old_time))
            removed = cleanup_retention(root, retention_days=2)
            self.assertEqual(removed, [old.resolve()])
            self.assertTrue(new.exists())
            with self.assertRaises(ValueError):
                cleanup_retention(Path(tmp))


if __name__ == "__main__":
    unittest.main()
