"""Read-only PyMuPDF reconnaissance and safe ``SectionInput`` construction."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Callable

import fitz

from .models import DocumentCapability, FenceStatus, LayoutToken, PageRegion, SectionInput


Rect = tuple[float, float, float, float]
StopCheck = Callable[[], bool] | None


@dataclass(frozen=True)
class LayoutLine:
    """Reusable line metadata; geometry is in original, unrotated page coordinates."""

    page_index: int
    block_id: int
    line_id: int
    text: str
    bbox: Rect
    font_size: float


@dataclass(frozen=True)
class PdfPage:
    page_index: int
    rect: Rect
    rotation: int
    tokens: tuple[LayoutToken, ...]
    lines: tuple[LayoutLine, ...]
    image_count: int
    image_rects: tuple[Rect, ...] = ()
    # Parallel to ``image_rects``. An xref is document-local, but stable for a
    # single embedded image while this layout is used.
    image_xrefs: tuple[int, ...] = ()


@dataclass(frozen=True)
class PdfReadResult:
    document_sha256: str
    pages: tuple[PdfPage, ...]
    capability: DocumentCapability
    reasons: tuple[str, ...]
    metrics: tuple[tuple[str, int | float], ...]
    terminal_reason: str | None = None


@dataclass(frozen=True)
class FenceDescription:
    """A locator-owned fence accepted by ``build_section_input`` only when confirmed."""

    status: FenceStatus
    section_no: str
    fence_id: str
    document_sha256: str
    regions: tuple[PageRegion, ...]
    capability: DocumentCapability = DocumentCapability.TEXT
    reasons: tuple[str, ...] = ()


def _stop_reason(cancelled: StopCheck, deadline: float | None) -> str | None:
    if cancelled is not None and cancelled():
        return "CANCELLED"
    if deadline is not None and monotonic() >= deadline:
        return "DEADLINE_EXCEEDED"
    return None


def _rect(value: fitz.Rect) -> Rect:
    return (float(value.x0), float(value.y0), float(value.x1), float(value.y1))


def _unrotated_page_rect(page: fitz.Page) -> Rect:
    """Return the zero-origin CropBox coordinate space used by text extraction.

    ``Page.rect`` is rotation-aware.  Applying ``derotation_matrix`` keeps the
    persisted rectangles in the original, unrotated PyMuPDF coordinate system,
    including when a CropBox has moved the visible-page origin.
    """
    return _rect(page.rect * page.derotation_matrix)


def _metrics(pages: list[PdfPage], started: float) -> tuple[tuple[str, int | float], ...]:
    return (
        ("pages_read", len(pages)),
        ("tokens_read", sum(len(item.tokens) for item in pages)),
        ("render_calls", 0),
        ("external_calls", 0),
        ("read_ms", round((monotonic() - started) * 1000, 3)),
    )


def _capability(pages: list[PdfPage]) -> tuple[DocumentCapability, tuple[str, ...]]:
    text_pages = sum(bool(page.tokens) for page in pages)
    image_pages = sum(page.image_count > 0 for page in pages)
    if text_pages == 0 and image_pages:
        return DocumentCapability.IMAGE_ONLY, ("IMAGE_ONLY_NO_DIGITAL_TEXT",)
    if text_pages == 0:
        return DocumentCapability.UNKNOWN, ("NO_DIGITAL_TEXT_OR_IMAGES",)
    if image_pages:
        return DocumentCapability.TEXT, ("MIXED_TEXT_AND_IMAGE_PAGES",)
    return DocumentCapability.TEXT, ("DIGITAL_TEXT",)


def read_pdf_layout(path: str | Path, *, cancelled: StopCheck = None, deadline: float | None = None) -> PdfReadResult:
    """Read a PDF once without rendering, OCR, AI, ODL, or external calls.

    Each token comes from the page's one full-layout extraction.  Consumers must
    later filter these token boxes themselves; no ``TextPage(..., clip=...)``
    call is used as an isolation mechanism.
    """
    source = Path(path)
    started = monotonic()
    pages: list[PdfPage] = []
    try:
        digest = sha256(source.read_bytes()).hexdigest()
        with fitz.open(source) as document:
            if document.needs_pass:
                return PdfReadResult(digest, (), DocumentCapability.UNKNOWN, ("PASSWORD_REQUIRED",), _metrics(pages, started), "PASSWORD_REQUIRED")
            for page_index, page in enumerate(document):
                stop = _stop_reason(cancelled, deadline)
                if stop:
                    capability, reasons = _capability(pages)
                    return PdfReadResult(digest, tuple(pages), capability, reasons + (stop,), _metrics(pages, started), stop)
                raw = page.get_text("rawdict", sort=True)
                tokens: list[LayoutToken] = []
                lines: list[LayoutLine] = []
                for block_id, block in enumerate(raw.get("blocks", ())):
                    if block.get("type") != 0:
                        continue
                    for line_id, line in enumerate(block.get("lines", ())):
                        spans = line.get("spans", ())
                        text = "".join(
                            span.get("text") or "".join(char.get("c", "") for char in span.get("chars", ()))
                            for span in spans
                        )
                        if text:
                            bbox = tuple(float(value) for value in line["bbox"])
                            lines.append(LayoutLine(page_index, block_id, line_id, text, bbox, max((float(span.get("size", 0.0)) for span in spans), default=0.0)))
                        for span in spans:
                            for char_index, char in enumerate(span.get("chars", ())):
                                value = char.get("c", "")
                                if value:
                                    tokens.append(LayoutToken(f"p{page_index}-b{block_id}-l{line_id}-c{char_index}-{len(tokens)}", value, page_index, tuple(float(item) for item in char["bbox"]), block_id, line_id))
                image_rects: list[Rect] = []
                image_xrefs: list[int] = []
                images = page.get_images(full=True)
                for image in images:
                    # The xref can be placed more than once.  Keep every actual
                    # placement and its document-local identity: an image count
                    # alone says nothing about whether it belongs to a fenced
                    # section or is a repeating decorative header.
                    xref = int(image[0])
                    placements = tuple(_rect(rect) for rect in page.get_image_rects(xref))
                    image_rects.extend(placements)
                    image_xrefs.extend(xref for _ in placements)
                pages.append(PdfPage(page_index, _unrotated_page_rect(page), int(page.rotation), tuple(tokens), tuple(lines), len(images), tuple(image_rects), tuple(image_xrefs)))
    except (fitz.FileDataError, OSError, RuntimeError) as error:
        return PdfReadResult(locals().get("digest", ""), tuple(pages), DocumentCapability.UNKNOWN, (f"PDF_READ_ERROR:{type(error).__name__}",), _metrics(pages, started), "PDF_READ_ERROR")
    capability, reasons = _capability(pages)
    return PdfReadResult(digest, tuple(pages), capability, reasons, _metrics(pages, started))


def _valid_rect(rect: Rect, page: PdfPage) -> bool:
    if len(rect) != 4 or not all(isinstance(value, (int, float)) and value == value for value in rect):
        return False
    x0, y0, x1, y1 = rect
    px0, py0, px1, py1 = page.rect
    return px0 <= x0 < x1 <= px1 and py0 <= y0 < y1 <= py1


def _inside(token: LayoutToken, rect: Rect) -> bool:
    x0, y0, x1, y1 = token.bbox
    rx0, ry0, rx1, ry1 = rect
    return rx0 <= x0 and y0 >= ry0 and x1 <= rx1 and y1 <= ry1


def _intersects(first: Rect, second: Rect) -> bool:
    return max(first[0], second[0]) < min(first[2], second[2]) and max(first[1], second[1]) < min(first[3], second[3])


def _validated_locator_fence(layout: PdfReadResult, fence: FenceDescription) -> FenceDescription:
    """Re-run the locator so a caller cannot substitute a plausible rectangle.

    ``FenceDescription`` is intentionally a plain immutable value for tests and
    transport.  It is therefore not provenance by itself.  The builder compares
    every identity and region field with fresh locator output for this exact
    layout before accepting it.
    """
    from .sections import locate_section

    located = locate_section(layout, fence.section_no)
    expected = located.description
    if expected is None or fence != expected:
        raise ValueError("SECTION_INPUT_FENCE_DOES_NOT_MATCH_LOCATOR")
    return expected


def build_section_input(layout: PdfReadResult, fence: FenceDescription) -> SectionInput:
    """Validate a confirmed fence and physically filter reusable token bboxes."""
    if layout.terminal_reason:
        raise ValueError("SECTION_INPUT_TERMINAL_LAYOUT")
    if fence.status is not FenceStatus.FENCE_CONFIRMED:
        raise ValueError("SECTION_INPUT_REQUIRES_CONFIRMED_FENCE")
    if fence.capability is not DocumentCapability.TEXT:
        raise ValueError("SECTION_INPUT_REQUIRES_TEXT_CAPABILITY")
    if fence.section_no not in {"1", "3"} or not fence.fence_id:
        raise ValueError("SECTION_INPUT_INVALID_FENCE_IDENTITY")
    if not fence.document_sha256 or fence.document_sha256 != layout.document_sha256:
        raise ValueError("SECTION_INPUT_DOCUMENT_SHA256_MISMATCH")
    if not fence.regions:
        raise ValueError("SECTION_INPUT_REQUIRES_REGIONS")
    fence = _validated_locator_fence(layout, fence)
    page_by_index = {page.page_index: page for page in layout.pages}
    selected: list[LayoutToken] = []
    previous_page = -1
    for region in fence.regions:
        if region.page_index <= previous_page:
            raise ValueError("SECTION_INPUT_REGIONS_NOT_STRICTLY_ORDERED")
        previous_page = region.page_index
        page = page_by_index.get(region.page_index)
        if page is None or not region.allowed_rects or any(not _valid_rect(rect, page) for rect in region.allowed_rects):
            raise ValueError("SECTION_INPUT_INVALID_PAGE_REGION")
        if any(not _valid_rect(rect, page) for rect in region.excluded_rects):
            raise ValueError("SECTION_INPUT_INVALID_EXCLUDED_REGION")
        for token in page.tokens:
            allowed = [rect for rect in region.allowed_rects if _intersects(token.bbox, rect)]
            excluded = [rect for rect in region.excluded_rects if _intersects(token.bbox, rect)]
            # A character bbox that straddles either boundary cannot be safely
            # classified.  Do not silently lose it or admit part of an outside
            # token; block SectionInput construction instead.
            if any(not _inside(token, rect) for rect in allowed) or any(not _inside(token, rect) for rect in excluded):
                raise ValueError("SECTION_INPUT_BOUNDARY_CROSSING_TOKEN")
            if allowed and not excluded:
                selected.append(token)
    digest = sha256("\n".join(f"{token.token_id}|{token.text}|{token.bbox}" for token in selected).encode("utf-8")).hexdigest()
    return SectionInput(
        layout.document_sha256, fence.section_no, fence.fence_id, fence.regions,
        tuple(selected), fence.capability, fence.reasons, digest,
        fence_status=FenceStatus.FENCE_CONFIRMED,
    )
