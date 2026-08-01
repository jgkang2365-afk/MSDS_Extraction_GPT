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
    components = checkpoint.get("구성성분", "")
    return {
        "status": "partial_timeout",
        "제품명": checkpoint.get("product_name", ""),
        "구성성분": components,
        "함유량": checkpoint.get("함유량", components),
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

    def __init__(self, base_dir="logs/runs", run_id=None):
        self.run_id = run_id or time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self.run_dir = Path(base_dir) / self.run_id
        self.failures_dir = self.run_dir / "failures"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.failures_dir.mkdir(exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self.summary_path = self.run_dir / "summary.json"
        self._lock = threading.Lock()
        self.counters = Counter()
        self.started_at = time.time()

    def append(self, event):
        payload = {"run_id": self.run_id, "timestamp": time.time(), **event}
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock, self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    def record_file(self, info, result, elapsed_seconds, timeout_seconds, file_hash=""):
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
            "partial_result_present": bool(result.get("제품명") or result.get("구성성분")),
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
