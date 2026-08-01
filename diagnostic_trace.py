"""Fail-soft, file-scoped diagnostics for the MSDS extraction pipeline.

This module deliberately has no dependency on the extraction, OCR, or AI code.
Callers may opt into it at pipeline boundaries without making diagnostics a
precondition for producing an extraction result.
"""

from __future__ import annotations

import base64
import contextlib
import contextvars
import datetime as _dt
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Union


_LOG = logging.getLogger(__name__)
_ACTIVE_TRACER: contextvars.ContextVar[Optional["DiagnosticTracer"]] = contextvars.ContextVar(
    "msds_diagnostic_tracer", default=None
)
_SENSITIVE_KEY = re.compile(r"(api[._-]?key|token|secret|password|authorization|private[._-]?key)", re.I)
_AUTH_VALUE = re.compile(r"\b(Bearer|Basic|Token)\s+[^\s,;]+", re.I)
_PEM = re.compile(r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", re.S)
_LONG_BASE64 = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{80,}={0,2}(?![A-Za-z0-9+/=_-])")


class DiagnosticMode(str, Enum):
    OFF = "OFF"
    SUMMARY = "SUMMARY"
    FULL = "FULL"

    @classmethod
    def parse(cls, value: Any) -> "DiagnosticMode":
        try:
            return cls(str(value or "SUMMARY").upper())
        except ValueError:
            return cls.SUMMARY


@dataclass(frozen=True)
class TraceContext:
    """Serializable identity and destination information for one input file."""

    run_id: str
    file_trace_id: str
    mode: str = DiagnosticMode.SUMMARY.value
    base_dir: str = "logs/runs"
    source_name: str = ""
    file_hash: str = ""
    file_path: str = ""
    created_at: str = ""

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "TraceContext":
        return cls(
            run_id=str(raw["run_id"]), file_trace_id=str(raw["file_trace_id"]),
            mode=DiagnosticMode.parse(raw.get("mode")).value,
            base_dir=str(raw.get("base_dir") or "logs/runs"),
            source_name=str(raw.get("source_name") or ""),
            file_hash=str(raw.get("file_hash") or ""),
            file_path=str(raw.get("file_path") or ""),
            created_at=str(raw.get("created_at") or ""),
        )

def _config_value(config_path: Optional[Union[str, Path]]) -> Mapping[str, Any]:
    if not config_path:
        config_path = Path("config.json")
    try:
        raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
        return raw if isinstance(raw, Mapping) else {}
    except (OSError, ValueError, TypeError):
        return {}


def diagnostic_mode(config_path: Optional[Union[str, Path]] = None) -> DiagnosticMode:
    """Resolve the environment override, then optional config, then SUMMARY."""
    env = os.getenv("MSDS_DIAGNOSTIC_MODE")
    if env:
        return DiagnosticMode.parse(env)
    config = _config_value(config_path)
    section = config.get("diagnostic") or config.get("diagnostics") or {}
    value = section.get("mode") if isinstance(section, Mapping) else config.get("MSDS_DIAGNOSTIC_MODE")
    return DiagnosticMode.parse(value)


def retention_settings(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Optional[int]]:
    """Read optional ``diagnostic.retention`` limits without requiring config changes."""
    config = _config_value(config_path)
    section = config.get("diagnostic") or config.get("diagnostics") or {}
    retention = section.get("retention", {}) if isinstance(section, Mapping) else {}
    if not isinstance(retention, Mapping):
        return {"retention_days": None, "max_runs": None, "max_total_mb": None}
    result: Dict[str, Optional[int]] = {"retention_days": None, "max_runs": None, "max_total_mb": None}
    for key in result:
        try:
            value = retention.get(key)
            result[key] = int(value) if value is not None else None
        except (TypeError, ValueError):
            pass
    return result


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def _redact_text(value: str) -> str:
    value = _AUTH_VALUE.sub(lambda m: "%s [REDACTED]" % m.group(1), value)
    value = _PEM.sub("[REDACTED SERVICE ACCOUNT KEY]", value)
    return _LONG_BASE64.sub("[REDACTED BASE64]", value)


def redact(value: Any, key: str = "") -> Any:
    """Return a JSON-safe value with credentials and large encoded blobs removed."""
    if _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact(v) for v in value]
    if isinstance(value, bytes):
        return "[REDACTED BINARY]"
    if isinstance(value, str):
        return _redact_text(value)
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def create_trace_context(
    source: Any = None, *, run_id: Optional[str] = None, file_trace_id: Optional[str] = None,
    mode: Optional[Union[str, DiagnosticMode]] = None, base_dir: Union[str, Path] = "logs/runs",
    config_path: Optional[Union[str, Path]] = None,
) -> TraceContext:
    selected = DiagnosticMode.parse(mode) if mode is not None else diagnostic_mode(config_path)
    source_data = source if isinstance(source, Mapping) else {}
    source_name = source_data.get("file_name") or source_data.get("file_path") or source or ""
    return TraceContext(
        run_id=run_id or uuid.uuid4().hex,
        file_trace_id=file_trace_id or uuid.uuid4().hex,
        mode=selected.value, base_dir=str(base_dir), source_name=str(source_name),
        file_hash=str(source_data.get("file_hash") or ""),
        file_path=str(source_data.get("file_path") or ""), created_at=_now(),
    )


class _NullTracer:
    def __getattr__(self, _name: str):
        return lambda *args, **kwargs: None


NULL_TRACER = _NullTracer()


class DiagnosticTracer:
    def __init__(self, context: TraceContext):
        self.context = context
        self.mode = DiagnosticMode.parse(context.mode)
        self.started = time.monotonic()
        self._lock = threading.RLock()
        self._stages: list[Dict[str, Any]] = []
        self._candidates: Dict[str, Dict[str, Any]] = {}
        self._images: list[Dict[str, Any]] = []
        self._failed = False
        self._closed = False
        # BatchRunLogger publishes this location in result metadata; keeping the
        # file namespace explicit prevents a run-level artifact being mistaken
        # for a particular source document.
        self._dir = Path(context.base_dir) / context.run_id / "files" / context.file_trace_id
        self._events_path = self._dir / "events.jsonl"
        self._init_storage()

    @property
    def directory(self) -> Path:
        return self._dir

    def _init_storage(self) -> None:
        if self.mode is DiagnosticMode.OFF:
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self.event("trace_started", source_name=self.context.source_name)
        except Exception:  # diagnostics must never break extraction
            _LOG.debug("diagnostic storage initialization failed", exc_info=True)

    def _fields(self, stage_id: Optional[str] = None, parent_stage_id: Optional[str] = None,
                candidate_id: Optional[str] = None) -> Dict[str, Any]:
        active = self._stages[-1] if self._stages else {}
        return {
            "run_id": self.context.run_id, "file_trace_id": self.context.file_trace_id,
            "file_hash": self.context.file_hash, "file_path": self.context.file_path,
            "stage_id": stage_id if stage_id is not None else active.get("stage_id"),
            "parent_stage_id": parent_stage_id if parent_stage_id is not None else active.get("parent_stage_id"),
            "candidate_id": candidate_id, "timestamp": _now(),
            "elapsed_ms": round((time.monotonic() - self.started) * 1000, 3),
        }

    def event(self, name: str, /, *, stage_id: Optional[str] = None, parent_stage_id: Optional[str] = None,
              candidate_id: Optional[str] = None, level: str = "info", **details: Any) -> None:
        if self.mode is DiagnosticMode.OFF:
            return
        record = self._fields(stage_id, parent_stage_id, candidate_id)
        record.update({"event_type": name, "event": name, "level": level, "details": redact(details)})
        if level.lower() in {"error", "failure", "critical"} or name.endswith("_error"):
            self._failed = True
        try:
            with self._lock:
                self._dir.mkdir(parents=True, exist_ok=True)
                with self._events_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception:
            _LOG.debug("diagnostic event write failed", exc_info=True)

    @contextlib.contextmanager
    def stage(self, stage_id: str, *, status: str = "completed", output_summary: Any = None,
              candidate_count: Optional[int] = None, **details: Any) -> Iterator["DiagnosticTracer"]:
        parent = self._stages[-1]["stage_id"] if self._stages else None
        state = {"stage_id": str(stage_id), "parent_stage_id": parent, "started": time.monotonic()}
        self._stages.append(state)
        self.event("stage_start", stage_id=state["stage_id"], parent_stage_id=parent, **details)
        try:
            yield self
        except Exception as exc:
            self.event("stage_error", stage_id=state["stage_id"], parent_stage_id=parent,
                       level="error", error_type=type(exc).__name__, error=str(exc))
            raise
        else:
            self.event("stage_result", stage_id=state["stage_id"], parent_stage_id=parent,
                       status=status, output_summary=output_summary,
                       candidate_count=len(self._candidates) if candidate_count is None else candidate_count,
                       duration_ms=round((time.monotonic() - state["started"]) * 1000, 3))
        finally:
            if self._stages and self._stages[-1] is state:
                self._stages.pop()

    def skip(self, stage_id: str, reason: str = "", **details: Any) -> None:
        self.event("stage_skip", stage_id=stage_id, reason=reason, **details)

    def stage_result(self, stage_id: Optional[str] = None, *, status: str = "completed",
                     output_summary: Any = None, candidate_count: Optional[int] = None,
                     **details: Any) -> None:
        """Emit an explicit result when a stage is not represented by a CM."""
        self.event("stage_result", stage_id=stage_id, status=status, output_summary=output_summary,
                   candidate_count=len(self._candidates) if candidate_count is None else candidate_count,
                   **details)

    def candidate(self, value: Any = None, *, candidate_id: Optional[str] = None,
                  derived_from: Optional[str] = None, **details: Any) -> str:
        if candidate_id:
            ident = candidate_id
        else:
            # Short, ordered identifiers are useful in image overlays and human
            # reports. UUIDs remain accepted when callers need global IDs.
            existing = set(self._candidates)
            for item in self._disk_events():
                if item.get("candidate_id"):
                    existing.add(str(item["candidate_id"]))
            sequence = 1
            while "candidate-%03d" % sequence in existing:
                sequence += 1
            ident = "candidate-%03d" % sequence
        record = {"candidate_id": ident, "derived_from": derived_from, "value": redact(value), **redact(details)}
        self._candidates[ident] = record
        self.event("candidate_registered", candidate_id=ident, derived_from=derived_from, value=value, **details)
        return ident

    def transform(self, candidate_id: str, value: Any = None, *, derived_from: Optional[str] = None,
                  **details: Any) -> str:
        """Update a candidate in place; an explicit parent records derivation lineage."""
        old = self._candidates.get(candidate_id, {})
        parent = derived_from if derived_from is not None else old.get("derived_from")
        self._candidates[candidate_id] = {**old, "candidate_id": candidate_id, "derived_from": parent,
                                          "value": redact(value), **redact(details)}
        self.event("candidate_transform", candidate_id=candidate_id, derived_from=parent, value=value, **details)
        return candidate_id

    def reject(self, candidate_id: str, reason: str, **details: Any) -> None:
        self.event("candidate_rejected", candidate_id=candidate_id, reason=reason, **details)

    def merge(self, candidate_ids: Sequence[str], into: str, **details: Any) -> str:
        self.event("candidate_merged", candidate_id=into, source_candidate_ids=list(candidate_ids), **details)
        return into

    def override(self, candidate_id: str, reason: str, **details: Any) -> None:
        self.event("candidate_override", candidate_id=candidate_id, reason=reason, **details)

    def image(self, image: Any, *, name: str = "image", format: str = "PNG", critical: bool = False,
              failure: bool = False, candidate_boxes: Optional[Mapping[str, Sequence[float]]] = None,
              table_lines: Optional[Sequence[Sequence[float]]] = None, **details: Any) -> Optional[Path]:
        if self.mode is DiagnosticMode.OFF:
            return None
        try:
            from PIL import Image, ImageDraw  # optional runtime dependency
            if isinstance(image, (str, Path)):
                with Image.open(image) as opened:
                    canvas = opened.convert("RGB")
            elif isinstance(image, bytes):
                import io
                canvas = Image.open(io.BytesIO(image)).convert("RGB")
            else:
                canvas = image.copy().convert("RGB")
            source_width = details.get("source_width")
            source_height = details.get("source_height")
            output_width = details.get("output_width", canvas.width)
            output_height = details.get("output_height", canvas.height)
            try:
                ratio_before = float(source_width) / float(source_height)
                ratio_after = float(output_width) / float(output_height)
                details.setdefault("aspect_ratio_before", round(ratio_before, 6))
                details.setdefault("aspect_ratio_after", round(ratio_after, 6))
                if ratio_before and abs(ratio_before - ratio_after) / ratio_before > 0.02:
                    self.event(
                        "image_warning",
                        level="warning",
                        warning_code="IMAGE_ASPECT_RATIO_CHANGED",
                        image_name=name,
                        aspect_ratio_before=ratio_before,
                        aspect_ratio_after=ratio_after,
                    )
            except (TypeError, ValueError, ZeroDivisionError):
                pass
            draw = ImageDraw.Draw(canvas)
            for ident, box in (candidate_boxes or {}).items():
                if len(box) != 4:
                    continue
                draw.rectangle(tuple(box), outline="red", width=2)
                draw.text((box[0], max(0, box[1] - 12)), str(ident), fill="red")
            for line in table_lines or []:
                if len(line) == 4:
                    draw.line(tuple(line), fill="blue", width=1)
            ext = "webp" if str(format).upper() == "WEBP" else "png"
            target = self._dir / "images" / (re.sub(r"[^A-Za-z0-9_.-]+", "_", name) + "." + ext)
            target.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(target, format=ext.upper())
            entry = {"path": str(target.relative_to(self._dir)), "critical": critical, "failure": failure,
                     "intermediate": bool(details.get("intermediate", True)),
                     "pending_summary": self.mode is DiagnosticMode.SUMMARY,
                     "details": redact(details)}
            self._images.append(entry)
            self.event("image_saved", image=entry, level="error" if failure else "info")
            return target
        except Exception as exc:
            self.event("image_error", level="error", error_type=type(exc).__name__, error=str(exc))
            return None

    def _disk_events(self) -> list[Dict[str, Any]]:
        """Best-effort read: a concurrently appended partial line is ignored."""
        try:
            return [json.loads(line) for line in self._events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, ValueError):
            return []

    @staticmethod
    def _event_name(item: Mapping[str, Any]) -> str:
        return str(item.get("event_type") or item.get("event") or "")

    def _reconstruct(self, events: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        candidates: Dict[str, Dict[str, Any]] = {}
        transforms: list[Dict[str, Any]] = []
        rejections: list[Dict[str, Any]] = []
        merges: list[Dict[str, Any]] = []
        overrides: list[Dict[str, Any]] = []
        images: list[Dict[str, Any]] = []
        stages: list[Dict[str, Any]] = []
        engines: list[Dict[str, Any]] = []
        failures: list[Dict[str, Any]] = []
        for raw in events:
            event = dict(raw)
            name = self._event_name(event)
            details = event.get("details") if isinstance(event.get("details"), Mapping) else {}
            cid = event.get("candidate_id")
            if name in {"candidate_registered", "candidate_transform"} and cid:
                candidates[str(cid)] = {"candidate_id": str(cid), "derived_from": details.get("derived_from"),
                                        "value": details.get("value"), **dict(details)}
            if name == "candidate_transform":
                transforms.append(event)
            elif name == "candidate_rejected":
                rejections.append(event)
            elif name == "candidate_merged":
                merges.append(event)
            elif name == "candidate_override":
                overrides.append(event)
            elif name == "image_saved" and isinstance(details.get("image"), Mapping):
                images.append(dict(details["image"]))
            if name in {"stage_start", "stage_result", "stage_error", "stage_skip"}:
                stages.append(event)
            if (name.startswith("engine_") or name.startswith(("pymupdf.", "section3.", "ocr.", "ai.", "kosha.", "cache."))
                    or "engine" in details):
                engines.append(event)
            if event.get("level", "").lower() in {"error", "failure", "critical"} or name.endswith("_error"):
                failures.append(event)
        return {"candidates": list(candidates.values()), "transforms": transforms, "rejections": rejections,
                "merges": merges, "overrides": overrides, "images": images, "stages": stages,
                "engine_results": engines, "failures": failures}

    @staticmethod
    def _brief(value: Any, limit: int = 240) -> str:
        text = json.dumps(redact(value), ensure_ascii=False, default=str) if isinstance(value, (Mapping, list)) else str(redact(value))
        return text if len(text) <= limit else text[:limit - 1] + "…"

    def _markdown_report(self, result: Any, reconstructed: Mapping[str, Any]) -> str:
        failures = list(reconstructed["failures"])
        if not failures and reconstructed.get("rejections"):
            failures = list(reconstructed["rejections"])
        first = failures[0] if failures else None
        first_details = first.get("details", {}) if first else {}
        lines = ["# MSDS Diagnostic Trace", "", "## 문서 요약", "",
                 "- run_id: `%s`" % self.context.run_id, "- file_trace_id: `%s`" % self.context.file_trace_id,
                 "- source: %s" % self._brief(self.context.source_name), "- mode: `%s`" % self.context.mode,
                 "", "## 최종 결과", "", "```json", self._brief(result, 3000), "```",
                 "", "## 실행 단계 (시간순)", ""]
        lines += ["- %s `%s` (%s ms)%s" % (x.get("event_type", x.get("event")), x.get("stage_id") or "-",
                    x.get("elapsed_ms", 0), " — " + self._brief(x.get("details", {})) if x.get("details") else "")
                  for x in reconstructed["stages"]] or ["- 기록된 단계 없음"]
        lines += ["", "## 엔진별 결과", ""]
        lines += ["- %s: %s" % (x.get("event_type", x.get("event")), self._brief(x.get("details", {})))
                  for x in reconstructed["engine_results"]] or ["- 엔진 이벤트 없음"]
        lines += ["", "## 후보 변화", ""]
        lines += ["- `%s` ← `%s`" % (x["candidate_id"], x.get("derived_from") or "source")
                  for x in reconstructed["candidates"]] or ["- 후보 없음"]
        lines += ["- 변환: %d / 탈락: %d / 병합: %d / 수동 재정의: %d" %
                  (len(reconstructed["transforms"]), len(reconstructed["rejections"]),
                   len(reconstructed["merges"]), len(reconstructed["overrides"]))]
        lines += ["", "## 이미지 분석", ""]
        lines += ["- %s%s" % (x.get("path", "unknown"), " (failure)" if x.get("failure") else "")
                  for x in reconstructed["images"]] or ["- 저장된 이미지 없음"]
        lines += ["", "## 최종 원인", ""]
        if first:
            direct_reason = first_details.get("error") or first_details.get("reason") or first_details.get("reason_code") or first_details
            lines += ["최초 실패 지점: `%s` / `%s`" % (first.get("stage_id") or "-", self._event_name(first)),
                      "직접 실패 원인: %s" % self._brief(direct_reason),
                      "후속 우회 경로: %s" % self._brief(first_details.get("workaround") or first_details.get("fallback") or "기록 없음"),
                      "우회 경로 실패 원인: %s" % self._brief(first_details.get("fallback_error") or "기록 없음"),
                      "최종 결과에 미친 영향: %s" % self._brief(first_details.get("impact") or "해당 후보가 최종 결과에서 제외됨"),
                      "권장 확인 지점: %s" % self._brief(first_details.get("recommended_check") or first.get("stage_id") or "원본 이벤트")]
        else:
            lines += ["최초 실패 지점: 없음", "직접 실패 원인: 없음", "후속 우회 경로: 해당 없음",
                      "우회 경로 실패 원인: 해당 없음", "최종 결과에 미친 영향: 없음", "권장 확인 지점: 해당 없음"]
        return "\n".join(lines) + "\n"

    def finalize(self, result: Any = None, **details: Any) -> Optional[Path]:
        if self.mode is DiagnosticMode.OFF or self._closed:
            return None
        self._closed = True
        try:
            # Child processes may hold an independent tracer. Reconstruct from
            # the shared append-only journal so a parent finalizer never writes
            # an empty in-memory candidate/image view over child evidence.
            events = self._disk_events()
            reconstructed = self._reconstruct(events)
            previous: Mapping[str, Any] = {}
            try:
                previous = json.loads((self._dir / "diagnostic.json").read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                pass
            final_result = redact(result) if result is not None else previous.get("result")
            result_status = str((final_result or {}).get("status", "")) if isinstance(final_result, Mapping) else ""
            review_required = bool(
                isinstance(final_result, Mapping)
                and final_result.get("verification_status") == "mismatch"
            )
            trace_failed = bool(reconstructed["failures"]) or result_status in {
                "failed", "timeout", "partial_timeout", "cancelled"
            } or review_required
            if self.mode is DiagnosticMode.SUMMARY and not trace_failed:
                for entry in list(reconstructed["images"]):
                    if not entry.get("failure") and (entry.get("intermediate", True) or not entry.get("critical")):
                        try:
                            (self._dir / entry["path"]).unlink(missing_ok=True)
                        except OSError:
                            pass
                reconstructed["images"] = [
                    entry for entry in reconstructed["images"]
                    if entry.get("failure") or (entry.get("critical") and not entry.get("intermediate", True))
                ]
            payload = {"context": self.context.to_dict(), "result": final_result, "details": redact(details),
                       "failed": trace_failed, "events_count": len(events), **reconstructed}
            path = self._dir / "diagnostic.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            (self._dir / "diagnostic.md").write_text(self._markdown_report(final_result, reconstructed), encoding="utf-8")
            self.event("trace_finalized", result=result, **details)
            return path
        except Exception:
            _LOG.debug("diagnostic finalization failed", exc_info=True)
            return None


@contextlib.contextmanager
def activate_trace(context: Optional[Union[TraceContext, Mapping[str, Any]]]) -> Iterator[Union[DiagnosticTracer, _NullTracer]]:
    if context is None:
        yield NULL_TRACER
        return
    tracer = DiagnosticTracer(TraceContext.from_dict(context) if isinstance(context, Mapping) else context)
    token = _ACTIVE_TRACER.set(tracer)
    try:
        yield tracer
    finally:
        _ACTIVE_TRACER.reset(token)


def get_tracer() -> Union[DiagnosticTracer, _NullTracer]:
    return _ACTIVE_TRACER.get() or NULL_TRACER


def finalize_trace(context: Optional[TraceContext], result: Any = None, **details: Any) -> Optional[Path]:
    if context is None:
        return None
    tracer = _ACTIVE_TRACER.get()
    if tracer is not None and tracer.context == context:
        return tracer.finalize(result, **details)
    return DiagnosticTracer(context).finalize(result, **details)


def cleanup_retention(base_dir: Union[str, Path] = "logs/runs", *, retention_days: Optional[int] = None,
                      max_runs: Optional[int] = None, max_total_mb: Optional[int] = None,
                      now: Optional[float] = None,
                      config_path: Optional[Union[str, Path]] = None) -> list[Path]:
    """Delete only expired run directories directly below a ``logs/runs`` directory."""
    root = Path(base_dir).resolve()
    if root.name != "runs" or root.parent.name != "logs":
        raise ValueError("cleanup is restricted to a logs/runs directory")
    if not root.exists():
        return []
    configured = retention_settings(config_path)
    retention_days = configured["retention_days"] if retention_days is None else retention_days
    max_runs = configured["max_runs"] if max_runs is None else max_runs
    max_total_mb = configured["max_total_mb"] if max_total_mb is None else max_total_mb
    cutoff = (now or time.time()) - (max(0, retention_days) * 86400) if retention_days is not None else None
    runs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    size_limit = max(0, max_total_mb) * 1024 * 1024 if max_total_mb is not None else None
    sizes = {
        run: sum(item.stat().st_size for item in run.rglob("*") if item.is_file())
        for run in runs
    }
    retained_size = 0
    removed: list[Path] = []
    for index, run in enumerate(runs):
        expired = cutoff is not None and run.stat().st_mtime < cutoff
        excess = max_runs is not None and index >= max(0, max_runs)
        size_excess = size_limit is not None and retained_size + sizes[run] > size_limit
        if not (expired or excess or size_excess):
            retained_size += sizes[run]
            continue
        try:
            target = run.resolve()
            if target.parent != root:
                continue
            shutil.rmtree(target)
            removed.append(target)
        except OSError:
            _LOG.debug("diagnostic retention cleanup failed", exc_info=True)
    return removed
