"""MSDS 운영 경로에서 사용하는 사례 독립 검증 유틸리티."""

from __future__ import annotations


class PageMapValidationError(ValueError):
    def __init__(self, error_code, message):
        super().__init__(message)
        self.error_code = error_code


def normalize_page_indexes(value, page_count=None):
    """단일 값, 정수 목록, image_page_map dict 목록을 순서 보존 정규화한다."""
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    normalized = []
    for item in values:
        if isinstance(item, dict):
            if "page_index" not in item:
                raise PageMapValidationError("COMPONENT_IMAGE_PAGE_MAP_INVALID", "page_index가 없는 이미지 매핑입니다.")
            item = item.get("page_index")
        if isinstance(item, bool) or not isinstance(item, int):
            raise PageMapValidationError("COMPONENT_IMAGE_PAGE_MAP_INVALID", "페이지 인덱스는 정수여야 합니다.")
        if item < 0 or (page_count is not None and item >= page_count):
            raise PageMapValidationError("COMPONENT_IMAGE_PAGE_MAP_INVALID", "문서 범위를 벗어난 페이지 인덱스입니다.")
        if item not in normalized:
            normalized.append(item)
    return normalized


def validate_component_image_page_map(details, page_count=None):
    """목표/소스/이미지 매핑의 일관성을 검사하고 정규화된 페이지를 반환한다."""
    details = details or {}
    target_value = details.get("target_page_indexes")
    if target_value is None:
        target_value = details.get("target_page_index")
    targets = normalize_page_indexes(target_value, page_count=page_count)
    sources = normalize_page_indexes(details.get("source_page_indexes"), page_count=page_count)
    image_map_value = details.get("image_page_map")
    image_pages = normalize_page_indexes(image_map_value, page_count=page_count)

    if image_map_value is not None:
        raw_map = image_map_value if isinstance(image_map_value, (list, tuple)) else [image_map_value]
        image_count = details.get("image_count")
        if isinstance(image_count, bool) or (image_count is not None and not isinstance(image_count, int)):
            raise PageMapValidationError("COMPONENT_IMAGE_COUNT_MISMATCH", "image_count가 올바른 정수가 아닙니다.")
        if image_count is not None and image_count != len(raw_map):
            raise PageMapValidationError("COMPONENT_IMAGE_COUNT_MISMATCH", "이미지 수와 페이지 매핑 수가 다릅니다.")
    if sources and image_pages and sources != image_pages:
        raise PageMapValidationError("COMPONENT_IMAGE_PAGE_MAP_INVALID", "소스 페이지와 이미지 페이지 매핑이 모순됩니다.")

    effective_sources = image_pages or sources
    if targets and any(page not in effective_sources for page in targets):
        raise PageMapValidationError("COMPONENT_IMAGE_PAGE_MISMATCH", "모든 목표 페이지가 이미지 소스에 포함되지 않았습니다.")
    return {
        "target_page_indexes": targets,
        "source_page_indexes": effective_sources,
        "image_page_indexes": image_pages,
    }
