"""대량 MSDS 처리의 분류, 제한시간, 검증, 계측을 담당하는 경량 유틸리티."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import unicodedata
import uuid
from collections import Counter
from pathlib import Path

try:
    from diagnostic_trace import (
        activate_trace,
        create_trace_context,
        finalize_trace,
        get_tracer,
    )
except Exception:  # 진단 모듈이 배포 전이어도 추출 경로를 막지 않는다.
    from contextlib import nullcontext

    class _NoopTraceContext:
        def __init__(self, **values):
            self.__dict__.update(values)

        def to_dict(self):
            return dict(self.__dict__)

    def create_trace_context(source=None, **values):
        return _NoopTraceContext(source=source, **values)

    def activate_trace(_context):
        return nullcontext(_NoopTracer())

    def get_tracer():
        return _NoopTracer()

    def finalize_trace(_context, result=None, **_details):
        return result

    class _NoopTracer:
        def event(self, *_args, **_kwargs):
            return None

        def candidate(self, *_args, **_kwargs):
            return ""


DIAGNOSTIC_MODES = frozenset({"OFF", "SUMMARY", "FULL"})

DOCUMENT_TIMEOUT_DEFAULTS = {"text": 180.0, "mixed": 240.0, "image": 360.0}
DOCUMENT_TIMEOUT_ENV = {
    "text": "MSDS_TEXT_FILE_TIMEOUT_SECONDS",
    "mixed": "MSDS_MIXED_FILE_TIMEOUT_SECONDS",
    "image": "MSDS_IMAGE_FILE_TIMEOUT_SECONDS",
}
DOCUMENT_ORDER = {"text": 0, "mixed": 1, "image": 2}
ERROR_CODES = frozenset({
    "PDF_OPEN_FAILED", "DOCUMENT_CLASSIFICATION_FAILED", "TEXT_EXTRACTION_EMPTY",
    "SECTION1_NOT_FOUND", "PRODUCT_NAME_NOT_FOUND", "PRODUCT_NAME_MISMATCH",
    "SECTION3_NOT_FOUND", "SECTION4_NOT_FOUND", "OCR_TIMEOUT", "OCR_ENGINE_ERROR",
    "PPSTRUCTURE_ERROR", "AI_TIMEOUT", "AI_HTTP_ERROR", "AI_INVALID_RESPONSE",
    "AI_NO_HARVEST", "CAS_NOT_FOUND", "CAS_INVALID_CHECKDIGIT", "CONTENT_NOT_FOUND",
    "CAS_CONTENT_PAIRING_FAILED", "FILE_TIMEOUT", "PARTIAL_TIMEOUT", "OUT_OF_MEMORY",
    "USER_CANCELLED",
})


def diagnostic_mode_from_sources(config=None, environ=None):
    """환경변수 → 설정 파일 값 → SUMMARY 기본값으로 진단 수준을 고른다."""
    environ = os.environ if environ is None else environ
    if config is None:
        try:
            loaded = json.loads(Path("config.json").read_text(encoding="utf-8"))
            config = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError, TypeError):
            config = {}
    config = config if isinstance(config, dict) else {}
    section = config.get("diagnostic") or config.get("diagnostics") or {}
    section_mode = section.get("mode") if isinstance(section, dict) else None
    raw = environ.get(
        "MSDS_DIAGNOSTIC_MODE",
        config.get("DIAGNOSTIC_MODE", config.get("diagnostic_mode", config.get("MSDS_DIAGNOSTIC_MODE", section_mode or "SUMMARY"))),
    )
    mode = str(raw or "SUMMARY").strip().upper()
    return mode if mode in DIAGNOSTIC_MODES else "SUMMARY"


def file_trace_id_for(run_id, file_hash="", file_path=""):
    """같은 실행에서 같은 파일은 재기록해도 동일 진단 ID를 사용한다."""
    source = f"{run_id}\0{file_hash or os.path.abspath(str(file_path))}"
    return hashlib.sha256(source.encode("utf-8", "replace")).hexdigest()[:24]


def _positive_float(value, fallback):
    try:
        parsed = float(value)
        return parsed if parsed > 0 else float(fallback)
    except (TypeError, ValueError):
        return float(fallback)


def timeout_for_document(document_type, environ=None):
    """유형별 환경변수 → 구형 공통 환경변수 → 코드 기본값 순으로 선택한다."""
    environ = os.environ if environ is None else environ
    kind = document_type if document_type in DOCUMENT_TIMEOUT_DEFAULTS else "text"
    default = DOCUMENT_TIMEOUT_DEFAULTS[kind]
    legacy = environ.get("MSDS_FILE_TIMEOUT_SECONDS")
    fallback = _positive_float(legacy, default) if legacy is not None else default
    specific = environ.get(DOCUMENT_TIMEOUT_ENV[kind])
    return _positive_float(specific, fallback) if specific is not None else fallback


def classify_document(pdf_path, sample_pages=3):
    """OCR 없이 내장 텍스트와 이미지 점유율만으로 문서 유형을 판별한다."""
    import fitz
    doc = fitz.open(pdf_path)
    try:
        page_count = len(doc)
        samples = min(max(1, int(sample_pages)), page_count)
        text_chars = 0
        image_pages = 0
        high_image_pages = 0
        for index in range(samples):
            page = doc[index]
            text_chars += len(page.get_text("text").strip())
            page_area = max(1.0, page.rect.width * page.rect.height)
            image_area = 0.0
            images = page.get_images(full=True)
            if images:
                image_pages += 1
            for image in images:
                try:
                    for rect in page.get_image_rects(image[0]):
                        image_area += max(0.0, rect.width * rect.height)
                except Exception:
                    continue
            if min(1.0, image_area / page_area) >= 0.55:
                high_image_pages += 1

        avg_chars = text_chars / samples
        if avg_chars >= 500 and high_image_pages == 0:
            document_type = "text"
        elif avg_chars < 30 and (image_pages or text_chars == 0):
            document_type = "image"
        else:
            document_type = "mixed"
        return {
            "document_type": document_type,
            "page_count": page_count,
            "sampled_pages": samples,
            "sample_text_chars": text_chars,
            "sample_image_pages": image_pages,
            "sample_high_image_pages": high_image_pages,
        }
    finally:
        doc.close()


def classify_and_order(pdf_paths):
    classified = []
    for original_index, path in enumerate(pdf_paths):
        try:
            info = classify_document(path)
            info["classification_error"] = ""
        except Exception as exc:
            info = {
                "document_type": "text",
                "page_count": 0,
                "classification_error": f"{type(exc).__name__}: {exc}",
            }
        info.update({"path": path, "original_index": original_index})
        classified.append(info)
    return sorted(
        classified,
        key=lambda item: (DOCUMENT_ORDER[item["document_type"]], item["original_index"]),
    )


def normalize_product_name(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\s\-‐‑‒–—―()\[\]{}<>〈〉《》【】'\"`·•_,.:;/\\]+", "", value)


def verify_product_name(ai_name, local_candidate):
    ai_normalized = normalize_product_name(ai_name)
    local_normalized = normalize_product_name(local_candidate)
    if not ai_normalized:
        return "missing", "review"
    if not local_normalized:
        return "unverified", "review"
    if ai_normalized == local_normalized:
        return "match", "verified"
    shorter, longer = sorted((ai_normalized, local_normalized), key=len)
    if shorter and shorter in longer and len(shorter) / len(longer) >= 0.75:
        return "match", "verified"
    return "mismatch", "review"


def build_partial_timeout_result(checkpoint, timeout_seconds, error_message):
    """마지막 정상 체크포인트를 GUI가 보존할 수 있는 표준 결과로 변환한다."""
    checkpoint = checkpoint or {}
    content_matching_complete = bool(checkpoint.get("content_matching_complete"))
    components = checkpoint.get("구성성분", "") if content_matching_complete else ""
    cas_candidates = list(checkpoint.get("cas_candidates") or [])
    return {
        "status": "partial_timeout",
        "제품명": checkpoint.get("product_name", ""),
        "구성성분": components,
        "함유량": checkpoint.get("함유량", components),
        "cas_candidates": cas_candidates,
        "content_matching_complete": content_matching_complete,
        "validation_eligible": content_matching_complete,
        "last_completed_stage": checkpoint.get("stage", ""),
        "failed_stage": checkpoint.get("next_stage", "file_processing"),
        "timeout_seconds": timeout_seconds,
        "error_code": "PARTIAL_TIMEOUT",
        "error_message": error_message,
        "used_engine": "partial_timeout",
        "신호등": "🟡",
    }


class BatchRunLogger:
    """스레드 안전 JSONL append 로거와 종료 요약 작성기."""

    def __init__(self, base_dir="logs/runs", run_id=None, diagnostic_mode=None, config=None):
        self.run_id = run_id or time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self.base_dir = Path(base_dir)
        self.run_dir = self.base_dir / self.run_id
        self.failures_dir = self.run_dir / "failures"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.failures_dir.mkdir(exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self.summary_path = self.run_dir / "summary.json"
        self._lock = threading.Lock()
        self.counters = Counter()
        self.started_at = time.time()
        self.diagnostic_mode = (
            str(diagnostic_mode).upper()
            if diagnostic_mode is not None
            else diagnostic_mode_from_sources(config)
        )
        if self.diagnostic_mode not in DIAGNOSTIC_MODES:
            self.diagnostic_mode = "SUMMARY"
        self.append({"stage": "run", "status": "started", "diagnostic_mode": self.diagnostic_mode})

    def _new_trace_context(self, source, file_trace_id=None):
        """진단 저장 실패·계약 변경이 실행 경로에 영향을 주지 않게 한다."""
        try:
            return create_trace_context(
                source=source,
                run_id=self.run_id,
                file_trace_id=file_trace_id,
                mode=self.diagnostic_mode,
                base_dir=str(self.base_dir),
            )
        except Exception:
            return None

    @staticmethod
    def _trace_event(context, name, **details):
        if context is None:
            return
        try:
            with activate_trace(context):
                get_tracer().event(name, **details)
        except Exception:
            pass

    def file_trace_context(self, info, file_hash=""):
        path = str(info.get("path", ""))
        trace_id = file_trace_id_for(self.run_id, file_hash, path)
        return self._new_trace_context(
            source={
                "component": "batch_file",
                "file_path": path,
                "file_hash": file_hash,
                "document_type": info.get("document_type", ""),
            },
            file_trace_id=trace_id,
        )

    def diagnostic_paths(self, trace_context):
        """결과/캐시에 저장할 경로 계약. OFF에서는 존재하지 않는 링크를 남기지 않는다."""
        if trace_context is None or self.diagnostic_mode == "OFF":
            return {}
        try:
            context_data = trace_context.to_dict()
        except Exception:
            context_data = {}
        trace_id = context_data.get("file_trace_id") or getattr(trace_context, "file_trace_id", "")
        if not trace_id:
            return {}
        directory = self.run_dir / "files" / str(trace_id)
        return {
            "run_id": self.run_id,
            "file_trace_id": str(trace_id),
            "trace_context": context_data,
            "diagnostic_json": str(directory / "diagnostic.json"),
            "diagnostic_markdown": str(directory / "diagnostic.md"),
            "diagnostic_images_dir": str(directory / "images"),
        }

    def record_classification(self, classified, elapsed_seconds=0.0, trace_context=None):
        for item in classified:
            context = trace_context or self.file_trace_context(item, item.get("file_hash", ""))
            self._trace_event(
                context,
                "document_classified",
                stage_id="classification",
                file_path=str(item.get("path", "")),
                document_type=item.get("document_type", "text"),
                page_count=item.get("page_count", 0),
                classification_error=item.get("classification_error", ""),
                classification_elapsed_seconds=round(elapsed_seconds, 3),
            )

    def record_queue(self, info, position, total, trace_context=None, queued_at=None):
        self._trace_event(
            trace_context,
            "queue_dequeued",
            stage_id="queue",
            queue_position=position,
            queue_total=total,
            document_type=info.get("document_type", ""),
            timeout_seconds=timeout_for_document(info.get("document_type")),
            queue_wait_seconds=round(max(0.0, time.monotonic() - queued_at), 3) if queued_at else 0.0,
        )

    def record_cache_policy(self, decision):
        info = {
            "path": decision.get("file_path", ""),
            "document_type": decision.get("document_type", "unknown"),
        }
        context = self.file_trace_context(info, decision.get("file_hash", ""))
        self._trace_event(context, "gui_cache_policy", stage_id="cache", **decision)
        if decision.get("action") == "skip":
            try:
                finalize_trace(
                    context,
                    result={"status": "cache_hit", "cache_disposition": "reuse"},
                    status="cache_hit",
                )
            except Exception:
                pass
        return self.diagnostic_paths(context)

    def record_final_candidate(self, trace_context, result, source="engine_result"):
        """최종 GUI 후보가 어떤 추출 결과에서 왔는지 ID로만 연결한다."""
        if trace_context is None:
            return ""
        try:
            with activate_trace(trace_context):
                engine_diagnostic = result.get("_diagnostic", {}) if isinstance(result.get("_diagnostic"), dict) else {}
                parent_candidate = engine_diagnostic.get("final_candidate_id") or source
                return get_tracer().candidate(
                    {
                        "product_name": result.get("제품명", ""),
                        "components": result.get("구성성분", ""),
                    },
                    derived_from=parent_candidate,
                    role="gui_final_candidate",
                ) or ""
        except Exception:
            return ""

    def append(self, event):
        payload = {"run_id": self.run_id, "timestamp": time.time(), **event}
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock, self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    def record_file(self, info, result, elapsed_seconds, timeout_seconds, file_hash="", trace_context=None):
        path = str(info["path"])
        status = str(result.get("status", "completed"))
        document_type = info["document_type"]
        self.counters["total_pdf"] += 1
        self.counters[f"{document_type}_pdf"] += 1
        status_key = {
            "completed": "completed_count",
            "partial_timeout": "partial_count",
            "timeout": "timeout_count",
            "failed": "failed_count",
            "cancelled": "cancelled_count",
        }.get(status, "completed_count")
        self.counters[status_key] += 1

        metrics = result.get("metrics", {}) if isinstance(result.get("metrics"), dict) else {}
        for key in (
            "recon_ocr_calls", "precision_ocr_calls", "ppstructure_calls",
            "ai_text_calls", "ai_image_calls", "ai_harvest_success", "ai_no_harvest",
            "kosha_network_requests", "kosha_memory_cache_hits",
            "kosha_persistent_cache_hits", "kosha_negative_cache_hits", "kosha_retries",
        ):
            self.counters[key] += int(metrics.get(key, 0) or 0)

        event = {
            "file_name": os.path.basename(path), "file_hash": file_hash,
            "file_path": path, "file_size": os.path.getsize(path) if os.path.exists(path) else 0,
            "page_count": info.get("page_count", 0), "document_type": document_type,
            "timeout_seconds": timeout_seconds, "stage": "file_complete",
            "stage_start": time.time() - elapsed_seconds, "stage_end": time.time(),
            "elapsed_seconds": round(elapsed_seconds, 3), "status": status,
            "error_code": result.get("error_code", ""),
            "error_message": result.get("error_message", ""),
            "last_completed_stage": result.get("last_completed_stage", ""),
            "partial_result_present": bool(result.get("제품명") or result.get("구성성분") or result.get("cas_candidates")),
            "cas_candidates": result.get("cas_candidates", []),
            "content_matching_complete": result.get("content_matching_complete", True),
            "validation_eligible": result.get("validation_eligible", True),
            "product_name_ai": result.get("제품명", ""),
            "product_name_local_candidate": result.get("local_text_candidate", ""),
            "product_name_verification_status": result.get("verification_status", "unverified"),
            "section1_page": result.get("section1_page"),
            "section3_candidate_pages": result.get("section3_candidate_pages", []),
            "section4_page": result.get("section4_page"),
            "cas_candidate_count": metrics.get("cas_candidate_count", 0),
            "valid_cas_count": metrics.get("valid_cas_count", 0),
            "content_match_count": metrics.get("content_match_count", 0),
            "recon_ocr_calls": metrics.get("recon_ocr_calls", 0),
            "precision_ocr_calls": metrics.get("precision_ocr_calls", 0),
            "ppstructure_calls": metrics.get("ppstructure_calls", 0),
            "ocr_pages": metrics.get("ocr_pages", []),
            "ocr_elapsed_seconds": metrics.get("ocr_elapsed_seconds", 0),
            "ai": metrics.get("ai", []), "kosha": metrics.get("kosha", {}),
        }
        self.append(event)
        if status in {"partial_timeout", "timeout", "failed"}:
            failure_path = self.failures_dir / f"{file_hash or hashlib.sha256(path.encode('utf-8')).hexdigest()}.json"
            with self._lock, failure_path.open("w", encoding="utf-8") as stream:
                json.dump(event, stream, ensure_ascii=False, indent=2, default=str)
        trace_context = trace_context or self.file_trace_context(info, file_hash)
        self._trace_event(
            trace_context,
            "file_complete",
            stage_id="file_complete",
            status=status,
            elapsed_seconds=round(elapsed_seconds, 3),
            timeout_seconds=timeout_seconds,
            error_code=result.get("error_code", ""),
            partial_result_present=event["partial_result_present"],
        )
        try:
            finalize_trace(
                trace_context,
                result={
                    "status": status,
                    "제품명": result.get("제품명", ""),
                    "구성성분": result.get("구성성분", ""),
                    "함유량": result.get("함유량", result.get("구성성분", "")),
                    "신호등": result.get("신호등", ""),
                    "used_engine": result.get("used_engine", ""),
                    "document_type": document_type,
                    "product_name_source": result.get("product_name_source", ""),
                    "local_text_candidate": result.get("local_text_candidate", ""),
                    "verification_status": result.get("verification_status", ""),
                    "cas_candidates": result.get("cas_candidates", []),
                    "content_matching_complete": result.get("content_matching_complete", True),
                    "error_code": result.get("error_code", ""),
                    "last_completed_stage": result.get("last_completed_stage", ""),
                },
                status=status,
                elapsed_seconds=round(elapsed_seconds, 3),
            )
        except Exception:
            pass
        paths = self.diagnostic_paths(trace_context)
        if paths:
            result["diagnostics"] = paths
        return paths

    def finalize(self, extra=None):
        summary = dict(self.counters)
        summary.update({
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": time.time(),
            "elapsed_seconds": round(time.time() - self.started_at, 3),
        })
        if extra:
            summary.update(extra)
        with self.summary_path.open("w", encoding="utf-8") as stream:
            json.dump(summary, stream, ensure_ascii=False, indent=2, default=str)
        return summary
