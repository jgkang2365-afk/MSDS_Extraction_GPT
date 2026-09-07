"""Conservative Section 1 / 3 header locator and rectangular fence builder."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from time import monotonic
from typing import Callable

from .models import DocumentCapability, Evidence, EvidenceSourceType, FenceStatus, PageRegion, SectionFence
from .pdf_io import FenceDescription, LayoutLine, PdfPage, PdfReadResult


StopCheck = Callable[[], bool] | None

_NUMBERED_HEADING = re.compile(r"^\s*(?:section\s*)?(?P<number>[1-9]|1[0-6])\s*(?:[.)]|[-:])\s*(?!\d)(?P<heading>.+?)\s*$", re.IGNORECASE)
_HEADING = {
    "1": re.compile(r"(?:화학제품.*회사|chemical\s+product.*company|identification)", re.IGNORECASE),
    "2": re.compile(r"(?:유해성.*위험성|hazard(?:s)?\s+identification)", re.IGNORECASE),
    "3": re.compile(r"(?:구성성분|성분.*정보|composition|information\s+on\s+ingredients)", re.IGNORECASE),
    "4": re.compile(r"(?:응급|first\s*[- ]?aid)", re.IGNORECASE),
}


@dataclass(frozen=True)
class LocatedFence:
    """Locator result kept separate from value extraction and pairing."""

    fence: SectionFence
    description: FenceDescription | None
    reasons: tuple[str, ...]
    metrics: tuple[tuple[str, int | float], ...]


@dataclass(frozen=True)
class _Header:
    section_no: str
    page_index: int
    line: LayoutLine


def _stop_reason(cancelled: StopCheck, deadline: float | None) -> str | None:
    if cancelled is not None and cancelled():
        return "CANCELLED"
    if deadline is not None and monotonic() >= deadline:
        return "DEADLINE_EXCEEDED"
    return None


def _toc_line_ids(page: PdfPage) -> set[tuple[int, int]]:
    """Only a compact run of three numbered lines is a table-of-contents run."""
    candidates = [line for line in page.lines if _NUMBERED_HEADING.match(line.text)]
    ignored: set[tuple[int, int]] = set()
    run: list[LayoutLine] = []
    for line in candidates:
        if run and line.bbox[1] - run[-1].bbox[1] > 32:
            if len(run) >= 3:
                ignored.update((item.block_id, item.line_id) for item in run)
            run = []
        run.append(line)
    if len(run) >= 3:
        ignored.update((item.block_id, item.line_id) for item in run)
    return ignored


def _find_headers(layout: PdfReadResult, *, cancelled: StopCheck, deadline: float | None) -> tuple[list[_Header], str | None]:
    headers: list[_Header] = []
    for page in layout.pages:
        stop = _stop_reason(cancelled, deadline)
        if stop:
            return headers, stop
        toc_lines = _toc_line_ids(page)
        for line in page.lines:
            if (line.block_id, line.line_id) in toc_lines:
                continue
            match = _NUMBERED_HEADING.match(line.text)
            if not match:
                continue
            number = match.group("number")
            if number in _HEADING and _HEADING[number].search(match.group("heading")):
                headers.append(_Header(number, page.page_index, line))
    return headers, None


def _has_ambiguous_columns(page: PdfPage, start: _Header, end: _Header) -> bool:
    """Reject a same-page multi-column boundary rather than joining a broad rect."""
    if start.page_index != end.page_index:
        return False
    starts = sorted({round(line.bbox[0], 1) for line in page.lines if line.bbox[1] >= start.line.bbox[1] and line.bbox[1] <= end.line.bbox[1]})
    return len(starts) >= 2 and starts[-1] - starts[0] > (page.rect[2] - page.rect[0]) * 0.35


def _intersects(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
    return max(first[0], second[0]) < min(first[2], second[2]) and max(first[1], second[1]) < min(first[3], second[3])


def _inside_token(token, rect: tuple[float, float, float, float]) -> bool:
    return rect[0] <= token.bbox[0] and token.bbox[1] >= rect[1] and token.bbox[2] <= rect[2] and token.bbox[3] <= rect[3]


def _margin_repetitions(layout: PdfReadResult) -> dict[tuple[int, int, int], tuple[float, float, float, float]]:
    """Find exact repeated top/bottom lines, retaining their per-page boxes."""
    occurrences: dict[str, list[LayoutLine]] = {}
    for page in layout.pages:
        height = page.rect[3] - page.rect[1]
        for line in page.lines:
            if line.bbox[1] <= page.rect[1] + height * 0.20 or line.bbox[3] >= page.rect[3] - height * 0.20:
                normalized = re.sub(r"\s+", " ", line.text).strip().casefold()
                if normalized:
                    occurrences.setdefault(normalized, []).append(line)
    repeated: dict[tuple[int, int, int], tuple[float, float, float, float]] = {}
    for lines in occurrences.values():
        if len({line.page_index for line in lines}) >= 2:
            repeated.update({(line.page_index, line.block_id, line.line_id): line.bbox for line in lines})
    return repeated


def _safe_middle_region(page: PdfPage, repeated: dict[tuple[int, int, int], tuple[float, float, float, float]]) -> tuple[PageRegion | None, str | None]:
    """Fence one continuation page only when its readable body is unambiguous."""
    excluded = tuple(repeated[key] for key in repeated if key[0] == page.page_index)
    body_lines = [line for line in page.lines if not any(_intersects(line.bbox, rect) for rect in excluded)]
    if not body_lines:
        if page.image_rects:
            # A textless continuation page can still be fenced to its known
            # image placement, which lets capability classification block it as
            # image-required instead of pretending it has a full-page text area.
            return PageRegion(page.page_index, page.image_rects, excluded), None
        if page.image_count:
            return None, "MIDDLE_PAGE_IMAGE_PLACEMENT_UNKNOWN"
        return None, "MIDDLE_PAGE_BODY_UNAVAILABLE"
    starts = sorted({round(line.bbox[0], 1) for line in body_lines})
    if len(starts) >= 2 and starts[-1] - starts[0] > (page.rect[2] - page.rect[0]) * 0.35:
        return None, "MIDDLE_PAGE_READING_ORDER_AMBIGUOUS"
    x0 = min(line.bbox[0] for line in body_lines)
    x1 = max(line.bbox[2] for line in body_lines)
    top = min(line.bbox[1] for line in body_lines)
    bottom = max(line.bbox[3] for line in body_lines)
    if x1 <= x0 or top >= bottom:
        return None, "MIDDLE_PAGE_BODY_BOUNDS_AMBIGUOUS"
    return PageRegion(page.page_index, ((x0, top, x1, bottom),), excluded), None


def _safe_boundary_region(
    page: PdfPage,
    repeated: dict[tuple[int, int, int], tuple[float, float, float, float]],
    *,
    top: float,
    bottom: float,
    failure_prefix: str,
) -> tuple[PageRegion | None, str | None]:
    """Fence a start/end page to its observed, single-column body only."""
    excluded = tuple(repeated[key] for key in repeated if key[0] == page.page_index)
    if bottom <= top:
        return None, f"{failure_prefix}_BOUNDARY_ORDER_AMBIGUOUS"
    boundary = (page.rect[0], top, page.rect[2], bottom)
    if any(
        _intersects(line.bbox, boundary)
        and not (top <= line.bbox[1] and line.bbox[3] <= bottom)
        for line in page.lines
    ):
        return None, f"{failure_prefix}_BOUNDARY_CROSSING_AMBIGUOUS"
    body_lines = [
        line for line in page.lines
        if top <= line.bbox[1] and line.bbox[3] <= bottom
        and not any(_intersects(line.bbox, rect) for rect in excluded)
    ]
    if not body_lines:
        images_in_span = tuple(
            (max(page.rect[0], image[0]), max(top, image[1]), min(page.rect[2], image[2]), min(bottom, image[3]))
            for image in page.image_rects
            if _intersects(image, (page.rect[0], top, page.rect[2], bottom))
        )
        if images_in_span:
            # Keep an image-only observation for a header-only boundary page.
            # It is never used to widen text input because such a section is
            # classified as non-text before SectionInput can be built.
            return PageRegion(page.page_index, images_in_span, excluded), None
        if page.image_count:
            # Placement cannot be observed, but the bounded vertical span must
            # still reach capability classification and block the section.
            return PageRegion(page.page_index, ((page.rect[0], top, page.rect[2], bottom),), excluded), None
        return None, None
    starts = sorted({round(line.bbox[0], 1) for line in body_lines})
    if len(starts) >= 2 and starts[-1] - starts[0] > (page.rect[2] - page.rect[0]) * 0.35:
        return None, f"{failure_prefix}_READING_ORDER_AMBIGUOUS"
    x0 = min(line.bbox[0] for line in body_lines)
    x1 = max(line.bbox[2] for line in body_lines)
    body_top = min(line.bbox[1] for line in body_lines)
    body_bottom = max(line.bbox[3] for line in body_lines)
    if x1 <= x0 or body_bottom <= body_top:
        return None, f"{failure_prefix}_BODY_BOUNDS_AMBIGUOUS"
    return PageRegion(page.page_index, ((x0, body_top, x1, body_bottom),), excluded), None


def _regions(layout: PdfReadResult, start: _Header, end: _Header) -> tuple[tuple[PageRegion, ...] | None, str | None]:
    pages = {page.page_index: page for page in layout.pages}
    start_page = pages[start.page_index]
    end_page = pages[end.page_index]
    if _has_ambiguous_columns(start_page, start, end):
        return None, "MULTI_COLUMN_BOUNDARY_AMBIGUOUS"
    if start.page_index == end.page_index:
        x0, y0, x1, y1 = start_page.rect
        top = start.line.bbox[3]
        bottom = end.line.bbox[1]
        if bottom <= top:
            return None, "SAME_PAGE_BOUNDARY_ORDER_AMBIGUOUS"
        return (PageRegion(start.page_index, ((x0, top, x1, bottom),)),), None
    repeated = _margin_repetitions(layout)
    _, py0, _, py1 = start_page.rect
    start_region, failure = _safe_boundary_region(
        start_page, repeated, top=start.line.bbox[3], bottom=py1, failure_prefix="START_PAGE"
    )
    if failure:
        return None, failure
    regions: list[PageRegion] = [start_region] if start_region is not None else []
    for page_index in range(start.page_index + 1, end.page_index):
        page = pages[page_index]
        region, failure = _safe_middle_region(page, repeated)
        if failure:
            return None, failure
        regions.append(region)
    _, ey0, _, _ = end_page.rect
    end_region, failure = _safe_boundary_region(
        end_page, repeated, top=ey0, bottom=end.line.bbox[1], failure_prefix="END_PAGE"
    )
    if failure:
        return None, failure
    if end_region is not None:
        regions.append(end_region)
    if not regions:
        return None, "SECTION_BODY_UNAVAILABLE"
    return tuple(regions), None


def _section_capability(
    layout: PdfReadResult,
    regions: tuple[PageRegion, ...] | None,
    start: _Header,
    end: _Header,
) -> tuple[DocumentCapability, tuple[str, ...]]:
    if not regions:
        return DocumentCapability.UNKNOWN, ("NO_CONFIRMED_REGIONS",)
    pages = {page.page_index: page for page in layout.pages}
    region_pages = [pages[region.page_index] for region in regions]
    regions_by_page = {region.page_index: region for region in regions}
    def has_text_in_region(page: PdfPage, region: PageRegion) -> bool:
        return any(
            any(_inside_token(token, rect) for rect in region.allowed_rects)
            for token in page.tokens
        )

    def image_span(page: PdfPage) -> tuple[float, float, float, float]:
        if page.page_index == start.page_index:
            top = start.line.bbox[3]
        else:
            top = page.rect[1]
        if page.page_index == end.page_index:
            bottom = end.line.bbox[1]
        else:
            bottom = page.rect[3]
        return (page.rect[0], top, page.rect[2], bottom)

    section_pages = [pages[index] for index in range(start.page_index, end.page_index + 1)]
    image_coverage_unknown = any(page.image_count > 0 and not page.image_rects for page in section_pages)
    images_in_region = [
        (page, image)
        for page in section_pages
        for image in page.image_rects
        if _intersects(image, image_span(page))
    ]
    if image_coverage_unknown:
        return DocumentCapability.UNKNOWN, ("SECTION_IMAGE_PLACEMENT_UNKNOWN",)
    if images_in_region:
        digital_text = sum(
            1 for page, region in zip(region_pages, regions) for token in page.tokens
            if any(_inside_token(token, rect) for rect in region.allowed_rects)
        )
        def image_is_within_observed_text_x_span(page: PdfPage, image: tuple[float, float, float, float]) -> bool:
            region = regions_by_page[page.page_index]
            observed_tokens = [
                token for token in page.tokens
                if any(_inside_token(token, rect) for rect in region.allowed_rects)
            ]
            return bool(observed_tokens) and (
                min(token.bbox[0] for token in observed_tokens) <= image[0]
                and image[2] <= max(token.bbox[2] for token in observed_tokens)
            )

        header_only_boundary_image = any(
            page.page_index in {start.page_index, end.page_index}
            and not has_text_in_region(page, regions_by_page[page.page_index])
            for page, _ in images_in_region
        )
        image_outside_observed_text_x_span = any(
            not image_is_within_observed_text_x_span(page, image)
            for page, image in images_in_region
        )
        if header_only_boundary_image or image_outside_observed_text_x_span:
            if any(has_text_in_region(page, region) for page, region in zip(region_pages, regions)):
                return DocumentCapability.UNKNOWN, ("SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED",)
            return DocumentCapability.IMAGE_ONLY, ("SECTION_IMAGE_READING_REQUIRED",)

        def decorative_logo(page: PdfPage, image: tuple[float, float, float, float]) -> bool:
            px0, py0, px1, py1 = page.rect
            width, height = px1 - px0, py1 - py0
            image_width, image_height = image[2] - image[0], image[3] - image[1]
            margin = min(image[0] - px0, px1 - image[2], image[1] - py0, py1 - image[3])
            return (
                image_width > 0 and image_height > 0
                and image_width <= width * 0.15 and image_height <= height * 0.15
                and image_width * image_height <= width * height * 0.02
                and margin <= min(width, height) * 0.10
            )
        images_are_decorative = all(
            decorative_logo(page, image)
            and not any(
                _intersects(image, token.bbox)
                for token in page.tokens
                if any(_inside_token(token, rect) for rect in regions_by_page[page.page_index].allowed_rects)
            )
            for page, image in images_in_region
        )
        if images_are_decorative and digital_text >= 12:
            return DocumentCapability.TEXT, ("SECTION_DIGITAL_TEXT_WITH_DECORATIVE_LOGO",)
        if any(has_text_in_region(page, region) for page, region in zip(region_pages, regions)):
            return DocumentCapability.UNKNOWN, ("SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED",)
        return DocumentCapability.IMAGE_ONLY, ("SECTION_IMAGE_READING_REQUIRED",)
    if any(not page.tokens for page in region_pages):
        return DocumentCapability.UNKNOWN, ("SECTION_DIGITAL_TEXT_UNAVAILABLE",)
    return DocumentCapability.TEXT, ("SECTION_DIGITAL_TEXT",)


def locate_section(layout: PdfReadResult, section_no: str, *, cancelled: StopCheck = None, deadline: float | None = None) -> LocatedFence:
    """Locate one section independently; no missing sibling can erase a good fence."""
    started = monotonic()
    metric = lambda: (("locator_ms", round((monotonic() - started) * 1000, 3)), ("headers_seen", 0), ("external_calls", 0))
    if section_no not in {"1", "3"}:
        raise ValueError("ONLY_SECTION_1_AND_3_ARE_SUPPORTED")
    if layout.terminal_reason:
        status = FenceStatus.FENCE_PARTIAL if layout.pages else FenceStatus.FENCE_NOT_FOUND
        return LocatedFence(SectionFence(status, section_no, None, None), None, (layout.terminal_reason,), metric())
    headers, stop = _find_headers(layout, cancelled=cancelled, deadline=deadline)
    metric = lambda: (("locator_ms", round((monotonic() - started) * 1000, 3)), ("headers_seen", len(headers)), ("external_calls", 0))
    if stop:
        fence = SectionFence(FenceStatus.FENCE_PARTIAL, section_no, None, None)
        return LocatedFence(fence, None, (stop,), metric())
    starts = [header for header in headers if header.section_no == section_no]
    ends = [header for header in headers if header.section_no == str(int(section_no) + 1)]
    if not starts:
        return LocatedFence(SectionFence(FenceStatus.FENCE_NOT_FOUND, section_no, None, None), None, ("SECTION_START_NOT_FOUND",), metric())
    start = starts[0]
    end = next((candidate for candidate in ends if (candidate.page_index, candidate.line.bbox[1]) > (start.page_index, start.line.bbox[1])), None)
    start_evidence = Evidence(section_no, start.page_index, EvidenceSourceType.TEXT, start.line.text, layout.document_sha256, start.line.bbox)
    if end is None:
        return LocatedFence(SectionFence(FenceStatus.FENCE_PARTIAL, section_no, start.page_index, None, (start_evidence,)), None, ("SECTION_END_NOT_FOUND",), metric())
    if any((candidate.page_index, candidate.line.bbox[1]) < (end.page_index, end.line.bbox[1]) for candidate in starts[1:]):
        return LocatedFence(SectionFence(FenceStatus.FENCE_PARTIAL, section_no, start.page_index, end.page_index, (start_evidence,)), None, ("SECTION_START_AMBIGUOUS",), metric())
    end_evidence = Evidence(section_no, end.page_index, EvidenceSourceType.TEXT, end.line.text, layout.document_sha256, end.line.bbox)
    regions, failure = _regions(layout, start, end)
    if failure:
        return LocatedFence(SectionFence(FenceStatus.FENCE_PARTIAL, section_no, start.page_index, end.page_index, (start_evidence, end_evidence)), None, (failure,), metric())
    capability, reasons = _section_capability(layout, regions, start, end)
    if capability is not DocumentCapability.TEXT:
        return LocatedFence(SectionFence(FenceStatus.FENCE_PARTIAL, section_no, start.page_index, end.page_index, (start_evidence, end_evidence)), None, reasons, metric())
    fence_id = sha256(f"{layout.document_sha256}:{section_no}:{start.page_index}:{start.line.bbox}:{end.page_index}:{end.line.bbox}".encode("utf-8")).hexdigest()
    description = FenceDescription(FenceStatus.FENCE_CONFIRMED, section_no, fence_id, layout.document_sha256, regions, capability, reasons)
    return LocatedFence(SectionFence(FenceStatus.FENCE_CONFIRMED, section_no, start.page_index, end.page_index, (start_evidence, end_evidence)), description, reasons, metric())


def locate_sections(layout: PdfReadResult, *, cancelled: StopCheck = None, deadline: float | None = None) -> tuple[LocatedFence, LocatedFence]:
    """Return independent Section 1 then Section 3 results without value extraction."""
    return (locate_section(layout, "1", cancelled=cancelled, deadline=deadline), locate_section(layout, "3", cancelled=cancelled, deadline=deadline))
