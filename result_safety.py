"""운영 결과와 실행 중 전용 데이터를 분리하는 저장 경계 유틸리티."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


INTERNAL_RESULT_KEYS = frozenset({"_shadow_context"})


class RuntimeExtractionResult(dict):
    """dict 호환 결과에 비직렬화 런타임 문맥만 별도 보관한다."""

    def __init__(self, value: Mapping[str, Any] | None = None, *, shadow_context=None):
        super().__init__(value or {})
        self.runtime_shadow_context = dict(shadow_context or {})


def detach_shadow_context(result):
    """결과 mapping에서 shadow 문맥을 제거하고 별도 값으로 반환한다."""
    if not isinstance(result, dict):
        return result, {}
    context = {}
    runtime_context = getattr(result, "runtime_shadow_context", None)
    if isinstance(runtime_context, Mapping):
        context.update(runtime_context)
    embedded = result.pop("_shadow_context", None)
    if isinstance(embedded, Mapping):
        context.update(embedded)
    if hasattr(result, "runtime_shadow_context"):
        result.runtime_shadow_context = {}
    return result, context


def encapsulate_runtime_result(result):
    """프로세스 경계를 지난 내부 문맥을 직렬화되지 않는 속성으로 옮긴다."""
    if not isinstance(result, dict):
        return result
    result, context = detach_shadow_context(result)
    return RuntimeExtractionResult(result, shadow_context=context)


def public_result(value):
    """내부 키를 모든 중첩 수준에서 제거한 JSON 호환 복사본을 만든다."""
    if isinstance(value, Mapping):
        return {
            str(key): public_result(item)
            for key, item in value.items()
            if str(key) not in INTERNAL_RESULT_KEYS
        }
    if isinstance(value, (list, tuple, set)):
        return [public_result(item) for item in value]
    return value
