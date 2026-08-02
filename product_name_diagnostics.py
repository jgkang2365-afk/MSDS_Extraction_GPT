"""제품명 AI 호출 실패를 민감정보 없이 구조화하는 공통 유틸리티."""

from __future__ import annotations

import re
from typing import Any, Iterable


PRODUCT_NAME_FAILURE_CODES = frozenset({
    "PRODUCT_NAME_PROVIDER_ERROR",
    "PRODUCT_NAME_RATE_LIMITED",
    "PRODUCT_NAME_TIMEOUT",
    "PRODUCT_NAME_EMPTY_RESPONSE",
    "PRODUCT_NAME_RESPONSE_PARSE_FAILED",
    "PRODUCT_NAME_RESPONSE_SCHEMA_MISMATCH",
    "PRODUCT_NAME_EVIDENCE_REJECTED",
    "PRODUCT_NAME_RESULT_EMPTY",
    "PRODUCT_NAME_RESULT_BLACKLISTED",
    "PRODUCT_NAME_RESULT_UNVERIFIED",
    "PRODUCT_NAME_PRIMARY_FAILED",
    "PRODUCT_NAME_FALLBACK_FAILED",
    "PRODUCT_NAME_ALL_PROVIDERS_FAILED",
    "PRODUCT_NAME_CALL_BLOCKED",
    "PRODUCT_NAME_UNKNOWN_FAILURE",
    "PRODUCT_NAME_OUTPUT_TRUNCATED",
})


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\b(?:sk|AIza)[A-Za-z0-9_\-]{12,}\b"),
)


def sanitize_diagnostic_message(value: Any, limit: int = 300) -> str:
    """키·토큰 패턴과 장문 응답을 진단 산출물에서 제거한다."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", text)
    return text[:limit]


class AIProviderCallError(RuntimeError):
    """공급자 호출 실패의 안전한 분류 정보만 운반한다."""

    def __init__(
        self, kind: str, message: str = "", *, http_status: int | None = None,
        error_code: str = "",
    ) -> None:
        super().__init__(sanitize_diagnostic_message(message))
        self.kind = kind
        self.http_status = http_status
        self.error_code = error_code


def provider_failure_reason(exc: BaseException) -> str:
    kind = str(getattr(exc, "kind", "") or "").lower()
    http_status = getattr(exc, "http_status", None)
    name = type(exc).__name__.lower()
    if http_status == 429 or kind == "rate_limited":
        return "PRODUCT_NAME_RATE_LIMITED"
    if kind == "timeout" or "timeout" in name:
        return "PRODUCT_NAME_TIMEOUT"
    if kind == "call_blocked":
        return "PRODUCT_NAME_CALL_BLOCKED"
    if kind == "output_truncated":
        return "PRODUCT_NAME_OUTPUT_TRUNCATED"
    return "PRODUCT_NAME_PROVIDER_ERROR"


def classify_product_response(response_text: str, parsed: Any) -> tuple[str, str]:
    """응답 파싱 결과를 (제품명, 실패 코드)로 정규화한다."""
    clean = str(response_text or "").replace("```json", "").replace("```", "").strip()
    if not clean:
        return "", "PRODUCT_NAME_EMPTY_RESPONSE"
    if isinstance(parsed, dict):
        if not any(key in parsed for key in ("product_name", "제품명")):
            return "", "PRODUCT_NAME_RESPONSE_SCHEMA_MISMATCH"
        product = str(parsed.get("product_name") or parsed.get("제품명") or "").strip()
        return (product, "" if product else "PRODUCT_NAME_RESULT_EMPTY")
    if parsed is not None:
        return "", "PRODUCT_NAME_RESPONSE_SCHEMA_MISMATCH"
    if len(clean) < 100 and not re.search(r"\d{2,7}-\d{2}-\d", clean):
        return clean, ""
    return "", "PRODUCT_NAME_RESPONSE_PARSE_FAILED"


def classify_product_failure(
    metrics: Iterable[dict[str, Any]], *, evidence_present: bool, final_product_name: str = "",
) -> dict[str, Any]:
    """문서 단위 최종 실패와 공급자별 실패 사슬을 분리한다."""
    product_metrics = [item for item in metrics if item.get("purpose") == "product_name"]
    if not evidence_present:
        reason = "PRODUCT_NAME_EVIDENCE_REJECTED"
    elif not product_metrics:
        reason = "PRODUCT_NAME_CALL_BLOCKED"
    else:
        decisive = next((str(item.get("reason_code") or "") for item in reversed(product_metrics) if item.get("reason_code")), "")
        reason = decisive if decisive in PRODUCT_NAME_FAILURE_CODES else "PRODUCT_NAME_UNKNOWN_FAILURE"
        if not reason and not final_product_name:
            reason = "PRODUCT_NAME_RESULT_EMPTY"
    failed_stages = [
        str(item.get("reason_code") or "")
        for item in product_metrics
        if item.get("reason_code")
    ]
    aggregate = ""
    if product_metrics and all(item.get("reason_code") for item in product_metrics):
        aggregate = "PRODUCT_NAME_ALL_PROVIDERS_FAILED"
    return {
        "reason_code": reason,
        "aggregate_reason_code": aggregate,
        "failure_chain": failed_stages,
    }
