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
    regions: list[PageRegion] = []
    x0, _, x1, y1 = start_page.rect
    top = start.line.bbox[3]
    if top >= y1:
        return None, "START_BOUNDARY_OUTSIDE_PAGE"
    regions.append(PageRegion(start.page_index, ((x0, top, x1, y1),)))
    for page_index in range(start.page_index + 1, end.page_index):
        page = pages[page_index]
        regions.append(PageRegion(page_index, (page.rect,)))
    x0, y0, x1, _ = end_page.rect
    bottom = end.line.bbox[1]
    if bottom <= y0:
        return None, "END_BOUNDARY_OUTSIDE_PAGE"
    regions.append(PageRegion(end.page_index, ((x0, y0, x1, bottom),)))
    return tuple(regions), None


def _section_capability(layout: PdfReadResult, regions: tuple[PageRegion, ...] | None) -> tuple[DocumentCapability, tuple[str, ...]]:
    if not regions:
        return DocumentCapability.UNKNOWN, ("NO_CONFIRMED_REGIONS",)
    pages = {page.page_index: page for page in layout.pages}
    region_pages = [pages[region.page_index] for region in regions]
    def has_text_in_region(page: PdfPage, region: PageRegion) -> bool:
        return any(
            any(rect[0] <= token.bbox[0] and token.bbox[1] >= rect[1] and token.bbox[2] <= rect[2] and token.bbox[3] <= rect[3] for rect in region.allowed_rects)
            for token in page.tokens
        )

    if any(page.image_count > 0 and not has_text_in_region(page, region) for page, region in zip(region_pages, regions)):
        return DocumentCapability.IMAGE_ONLY, ("SECTION_IMAGE_READING_REQUIRED",)
    if any(page.image_count > 0 for page in region_pages):
        return DocumentCapability.TEXT, ("SECTION_MIXED_TEXT_AND_IMAGE",)
    if any(not page.tokens for page in region_pages):
        return DocumentCapability.UNKNOWN, ("SECTION_DIGITAL_TEXT_UNAVAILABLE",)
    return DocumentCapability.TEXT, ("SECTION_DIGITAL_TEXT",)


def locate_section(layout: PdfReadResult, section_no: str, *, cancelled: StopCheck = None, deadline: float | None = None) -> LocatedFence:
    """Locate one section independently; no missing sibling can erase a good fence."""
    started = monotonic()
    if section_no not in {"1", "3"}:
        raise ValueError("ONLY_SECTION_1_AND_3_ARE_SUPPORTED")
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
    capability, reasons = _section_capability(layout, regions)
    if capability is not DocumentCapability.TEXT:
        return LocatedFence(SectionFence(FenceStatus.FENCE_PARTIAL, section_no, start.page_index, end.page_index, (start_evidence, end_evidence)), None, reasons, metric())
    fence_id = sha256(f"{layout.document_sha256}:{section_no}:{start.page_index}:{start.line.bbox}:{end.page_index}:{end.line.bbox}".encode("utf-8")).hexdigest()
    description = FenceDescription(FenceStatus.FENCE_CONFIRMED, section_no, fence_id, layout.document_sha256, regions, capability, reasons)
    return LocatedFence(SectionFence(FenceStatus.FENCE_CONFIRMED, section_no, start.page_index, end.page_index, (start_evidence, end_evidence)), description, reasons, metric())


def locate_sections(layout: PdfReadResult, *, cancelled: StopCheck = None, deadline: float | None = None) -> tuple[LocatedFence, LocatedFence]:
    """Return independent Section 1 then Section 3 results without value extraction."""
    return (locate_section(layout, "1", cancelled=cancelled, deadline=deadline), locate_section(layout, "3", cancelled=cancelled, deadline=deadline))
