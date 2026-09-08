"""Local, lazy Scan/OCR reconnaissance with fence-only collector inputs.

This module intentionally keeps full-page renders and recon tokens private to a
single call.  The public result contains only a confirmed section's filtered
OCR tokens and cropped image bytes; it never retains a PDF path, fitz object,
or whole-page image.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import ceil, floor
from pathlib import Path
import re
from typing import Protocol, Sequence

import fitz

from .models import (
    DocumentCapability,
    EvidenceSourceType,
    FenceStatus,
    IsolatedImage,
    LayoutToken,
    PageRegion,
    SectionFence,
    SectionInput,
)
from .pdf_io import FenceDescription, LayoutLine, PdfPage, PdfReadResult, build_section_input, read_pdf_layout
from .sections import LocatedFence, _HEADING, _NUMBERED_HEADING, _heading_search_key, locate_section


Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class OcrToken:
    """One engine observation in rendered-page pixels (top-left origin)."""

    text: str
    bbox: Rect
    confidence: float = 0.0


class OcrEngine(Protocol):
    """The OCR boundary has no PDF, network, or collector knowledge."""

    def recognize(self, image_bytes: bytes) -> Sequence[OcrToken]: ...


@dataclass(frozen=True)
class OcrMetrics:
    initialization_count: int = 0
    invocation_count: int = 0
    render_count: int = 0
    released: bool = False
    external_call_count: int = 0


class LazyPaddleOcrEngine:
    """Optional local Paddle adapter.  Import/model initialization is deferred.

    It has no default Paddle factory, download, or remote fallback policy. An
    explicit injected factory must provide an already-local configured engine.
    """

    def __init__(self, engine_factory=None) -> None:
        self._factory = engine_factory
        self._engine = None
        self._initialization_count = 0
        self._invocation_count = 0
        self._released = False

    @property
    def metrics(self) -> OcrMetrics:
        return OcrMetrics(self._initialization_count, self._invocation_count, 0, self._released, 0)

    def _get_engine(self):
        if self._engine is None:
            if self._factory is None:
                raise RuntimeError("LOCAL_PADDLE_FACTORY_REQUIRED")
            self._engine = self._factory()
            self._initialization_count += 1
        return self._engine

    def recognize(self, image_bytes: bytes) -> Sequence[OcrToken]:
        engine = self._get_engine()
        self._invocation_count += 1
        # Current local Paddle variants do not share the legacy ``cls``
        # keyword contract.  Keep the adapter at the narrow image-in / token-
        # out boundary and do not pass version-specific classifier options.
        rows = engine.ocr(image_bytes)
        result: list[OcrToken] = []
        for page_rows in rows or ():
            for item in page_rows or ():
                points, value = item
                text, confidence = value
                xs = [float(point[0]) for point in points]
                ys = [float(point[1]) for point in points]
                result.append(OcrToken(str(text), (min(xs), min(ys), max(xs), max(ys)), float(confidence)))
        return result

    def release(self) -> None:
        self._engine = None
        self._released = True


@dataclass(frozen=True)
class TargetRoute:
    """Independent target capability and fence outcome for Section 1 or 3."""

    section_no: str
    capability: DocumentCapability
    fence: SectionFence
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ScanOcrResult:
    """Safe handoff: individual target routes plus confirmed SectionInputs only."""

    routes: tuple[TargetRoute, ...]
    inputs: tuple[SectionInput, ...]
    metrics: OcrMetrics

    def input_for(self, section_no: str) -> SectionInput | None:
        return next((item for item in self.inputs if item.section_no == section_no), None)


@dataclass
class _RenderedPage:
    page_index: int
    pdf_rect: Rect
    rotation: int
    pixmap: fitz.Pixmap
    ocr_tokens: tuple[OcrToken, ...]


@dataclass(frozen=True)
class _Recon:
    layout: PdfReadResult
    rendered: tuple[_RenderedPage, ...]
    invocation_count: int


def _engine_metrics(engine: OcrEngine | None, *, invocation_count: int, render_count: int, released: bool) -> OcrMetrics:
    observed = getattr(engine, "metrics", None)
    if callable(observed):
        observed = observed()
    return OcrMetrics(
        int(getattr(observed, "initialization_count", 0)),
        int(getattr(observed, "invocation_count", invocation_count)),
        render_count,
        bool(getattr(observed, "released", released)),
        int(getattr(observed, "external_call_count", 0)),
    )


def _pixel_to_pdf(bbox: Rect, *, pdf_rect: Rect, rotation: int, width: int, height: int) -> Rect:
    """Map rotated render pixels to zero-based, unrotated CropBox PDF points."""
    _, _, right, bottom = pdf_rect
    page_width, page_height = right, bottom
    rotated = rotation % 360
    display_width = page_height if rotated in {90, 270} else page_width
    display_height = page_width if rotated in {90, 270} else page_height
    sx = width / display_width
    sy = height / display_height
    corners = ((bbox[0] / sx, bbox[1] / sy), (bbox[2] / sx, bbox[1] / sy), (bbox[0] / sx, bbox[3] / sy), (bbox[2] / sx, bbox[3] / sy))
    def inverse(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        if rotated == 0:
            return x, y
        if rotated == 90:
            return y, page_height - x
        if rotated == 180:
            return page_width - x, page_height - y
        if rotated == 270:
            return page_width - y, x
        raise ValueError("UNSUPPORTED_PAGE_ROTATION")
    converted = [inverse(point) for point in corners]
    return (min(point[0] for point in converted), min(point[1] for point in converted), max(point[0] for point in converted), max(point[1] for point in converted))


def _pdf_to_pixel(rect: Rect, rendered: _RenderedPage) -> tuple[int, int, int, int]:
    """Inverse mapping used solely to crop an already-rendered fence image."""
    _, _, page_width, page_height = rendered.pdf_rect
    rotated = rendered.rotation % 360
    display_width = page_height if rotated in {90, 270} else page_width
    display_height = page_width if rotated in {90, 270} else page_height
    sx, sy = rendered.pixmap.width / display_width, rendered.pixmap.height / display_height
    corners = ((rect[0], rect[1]), (rect[2], rect[1]), (rect[0], rect[3]), (rect[2], rect[3]))
    def forward(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        if rotated == 0:
            return x, y
        if rotated == 90:
            return page_height - y, x
        if rotated == 180:
            return page_width - x, page_height - y
        if rotated == 270:
            return y, page_width - x
        raise ValueError("UNSUPPORTED_PAGE_ROTATION")
    pixels = [(x * sx, y * sy) for x, y in map(forward, corners)]
    return (
        max(0, floor(min(point[0] for point in pixels))),
        max(0, floor(min(point[1] for point in pixels))),
        min(rendered.pixmap.width, ceil(max(point[0] for point in pixels))),
        min(rendered.pixmap.height, ceil(max(point[1] for point in pixels))),
    )


def _inside(bbox: Rect, rect: Rect) -> bool:
    return rect[0] <= bbox[0] and bbox[1] >= rect[1] and bbox[2] <= rect[2] and bbox[3] <= rect[3]


def _intersects(first: Rect, second: Rect) -> bool:
    return max(first[0], second[0]) < min(first[2], second[2]) and max(first[1], second[1]) < min(first[3], second[3])


def _reconstruct(path: str | Path, layout: PdfReadResult, engine: OcrEngine) -> _Recon:
    """Run OCR once per rendered page; recon stays private and cannot be collected."""
    pages: list[PdfPage] = []
    rendered_pages: list[_RenderedPage] = []
    calls = 0
    with fitz.open(path) as document:
        for page_index, page in enumerate(document):
            pixmap = page.get_pixmap(alpha=False)
            image_bytes = pixmap.tobytes("png")
            observations = tuple(engine.recognize(image_bytes))
            calls += 1
            pdf_page = layout.pages[page_index]
            rendered = _RenderedPage(page_index, pdf_page.rect, pdf_page.rotation, pixmap, observations)
            rendered_pages.append(rendered)
            tokens: list[LayoutToken] = []
            lines: list[LayoutLine] = []
            for observation_index, observation in enumerate(observations):
                if not observation.text:
                    continue
                bbox = _pixel_to_pdf(observation.bbox, pdf_rect=pdf_page.rect, rotation=pdf_page.rotation, width=pixmap.width, height=pixmap.height)
                lines.append(LayoutLine(page_index, observation_index, 0, observation.text, bbox, 0.0))
                width = max(bbox[2] - bbox[0], 0.001)
                for char_index, character in enumerate(observation.text):
                    if character == "\n":
                        continue
                    x0 = bbox[0] + width * char_index / max(len(observation.text), 1)
                    x1 = bbox[0] + width * (char_index + 1) / max(len(observation.text), 1)
                    tokens.append(LayoutToken(
                        f"ocr-p{page_index}-o{observation_index}-c{char_index}", character, page_index,
                        (x0, bbox[1], x1, bbox[3]), observation_index, 0, "OCR",
                    ))
            pages.append(PdfPage(page_index, pdf_page.rect, pdf_page.rotation, tuple(tokens), tuple(lines), 0, ()))
    metrics = tuple((name, value) for name, value in layout.metrics if name not in {"tokens_read", "render_calls", "external_calls"}) + (
        ("tokens_read", sum(len(page.tokens) for page in pages)), ("render_calls", len(pages)), ("external_calls", 0),
    )
    return _Recon(PdfReadResult(layout.document_sha256, tuple(pages), DocumentCapability.OCR, ("OCR_RECON",), metrics), tuple(rendered_pages), calls)


def _validated_ocr_fence(layout: PdfReadResult, fence: FenceDescription) -> FenceDescription:
    located = locate_section(layout, fence.section_no)
    if located.description is None or located.description != fence:
        raise ValueError("OCR_SECTION_INPUT_FENCE_DOES_NOT_MATCH_LOCATOR")
    if fence.status is not FenceStatus.FENCE_CONFIRMED or fence.capability is not DocumentCapability.OCR:
        raise ValueError("OCR_SECTION_INPUT_REQUIRES_CONFIRMED_OCR_FENCE")
    return fence


def _cropped_images(fence: FenceDescription, rendered: tuple[_RenderedPage, ...]) -> tuple[IsolatedImage, ...]:
    by_page = {page.page_index: page for page in rendered}
    images: list[IsolatedImage] = []
    for region in fence.regions:
        page = by_page[region.page_index]
        for allowed in region.allowed_rects:
            if any(_intersects(allowed, excluded) for excluded in region.excluded_rects):
                raise ValueError("OCR_SECTION_INPUT_EXCLUDED_IMAGE_INTERSECTION")
            x0, y0, x1, y1 = _pdf_to_pixel(allowed, page)
            if x1 <= x0 or y1 <= y0:
                raise ValueError("OCR_SECTION_INPUT_EMPTY_IMAGE_CROP")
            # PyMuPDF 1.26 no longer exposes the old Pixmap(src, IRect)
            # overload.  Copy only the fence rows into a new image buffer;
            # this is deliberately not a retained whole-page representation.
            channels = page.pixmap.n
            samples = b"".join(
                page.pixmap.samples[y * page.pixmap.stride + x0 * channels:y * page.pixmap.stride + x1 * channels]
                for y in range(y0, y1)
            )
            crop = fitz.Pixmap(page.pixmap.colorspace, x1 - x0, y1 - y0, samples, page.pixmap.alpha)
            png = crop.tobytes("png")
            images.append(IsolatedImage(region.page_index, allowed, png, sha256(png).hexdigest()))
    return tuple(images)


def build_ocr_section_input(recon_layout: PdfReadResult, fence: FenceDescription, rendered: tuple[_RenderedPage, ...]) -> SectionInput:
    """Create a collector-safe OCR input from only confirmed fence material."""
    if recon_layout.terminal_reason:
        raise ValueError("OCR_SECTION_INPUT_TERMINAL_LAYOUT")
    fence = _validated_ocr_fence(recon_layout, fence)
    pages = {page.page_index: page for page in recon_layout.pages}
    selected: list[LayoutToken] = []
    for region in fence.regions:
        page = pages.get(region.page_index)
        if page is None:
            raise ValueError("OCR_SECTION_INPUT_INVALID_PAGE_REGION")
        for token in page.tokens:
            allowed = any(_inside(token.bbox, rect) for rect in region.allowed_rects)
            excluded = any(_intersects(token.bbox, rect) for rect in region.excluded_rects)
            if allowed and not excluded:
                selected.append(token)
    images = _cropped_images(fence, rendered)
    digest_material = "\n".join(
        [f"{token.token_id}|{token.text}|{token.bbox}" for token in selected] + [image.sha256 for image in images]
    )
    return SectionInput(
        recon_layout.document_sha256, fence.section_no, fence.fence_id, fence.regions, tuple(selected),
        DocumentCapability.OCR, fence.reasons, sha256(digest_material.encode("utf-8")).hexdigest(), images,
    )


def _decorative_margin_image(page: PdfPage, image: Rect) -> bool:
    """Recognize small header, footer, or side-margin decoration."""
    px0, py0, px1, py1 = page.rect
    width, height = px1 - px0, py1 - py0
    image_width, image_height = image[2] - image[0], image[3] - image[1]
    return (
        image_width > 0 and image_height > 0
        and image_width <= width * 0.15 and image_height <= height * 0.15
        and image_width * image_height <= width * height * 0.02
        and (
            image[1] - py0 <= height * 0.10
            or py1 - image[3] <= height * 0.10
            or image[0] - px0 <= width * 0.10
            or px1 - image[2] <= width * 0.10
        )
    )


_SECTION_FIVE_FIRE_FIGHTING = re.compile(r"fire\s*[- ]?fighting\s+measures", re.IGNORECASE)
_CANONICAL_NEXT_SECTION = {"1": "2", "3": "4"}


def _is_semantic_msds_heading(number: str, heading: str) -> bool:
    """Accept only the narrow numbered headings relevant to partial fences."""
    if number in _HEADING:
        return bool(_HEADING[number].search(heading))
    return number == "5" and bool(_SECTION_FIVE_FIRE_FIGHTING.search(heading))


def _next_digital_section_boundary(layout: PdfReadResult, located: LocatedFence) -> tuple[int, float] | None:
    """Find the next semantic digital heading after a partial start.

    A numbered composition row is not a section boundary.  Prefer the target's
    canonical next heading when it is present; a semantic Section 5
    Fire-fighting heading remains a narrow fallback when Section 4 is absent.
    """
    fence = located.fence
    if fence.start_page is None or not fence.evidence:
        return None
    start = fence.evidence[0]
    candidates: list[tuple[int, LayoutLine]] = []
    for page in layout.pages:
        if page.page_index < fence.start_page:
            continue
        for line in page.lines:
            if page.page_index == fence.start_page and line.bbox[1] < start.bbox[3]:
                continue
            match = _NUMBERED_HEADING.match(_heading_search_key(line.text))
            if (
                match is not None
                and match.group("number") != fence.section
                and _is_semantic_msds_heading(match.group("number"), match.group("heading"))
            ):
                candidates.append((page.page_index, line))
    if not candidates:
        return None
    canonical_number = _CANONICAL_NEXT_SECTION.get(fence.section)
    canonical_candidates = [item for item in candidates if _NUMBERED_HEADING.match(_heading_search_key(item[1].text)).group("number") == canonical_number]
    if canonical_candidates:
        candidates = canonical_candidates
    page_index, line = min(
        candidates,
        key=lambda item: (
            item[0], item[1].bbox[1], item[1].bbox[0], item[1].bbox[3], item[1].bbox[2],
            item[1].block_id, item[1].line_id,
        ),
    )
    return page_index, line.bbox[1]


def _partial_target_has_relevant_image(layout: PdfReadResult, located: LocatedFence) -> bool:
    """Return whether a partial target's observed body span contains an image.

    A partial digital heading alone is insufficient reason to OCR.  Limit the
    check to the target's bounded heading-to-boundary span: an image elsewhere
    in the document cannot turn this target into an OCR route.  Unknown image
    placement is also deliberately not guessed at.
    """
    fence = located.fence
    if fence.status is not FenceStatus.FENCE_PARTIAL or fence.start_page is None or not fence.evidence:
        return False
    pages = {page.page_index: page for page in layout.pages}
    start_page = fence.start_page
    start_evidence = fence.evidence[0]
    # A partial fence can carry the *candidate* end page while retaining only
    # start evidence (for example, when the start or body order is ambiguous).
    # That page is not an observed bound.  Continue from the observed start
    # only until a later explicit digital heading for a different section.  It
    # is conservative for an image body continuation, while a later unrelated
    # section cannot trigger OCR for this target.
    end_evidence = fence.evidence[1] if len(fence.evidence) == 2 else None
    boundary = None if end_evidence is not None else _next_digital_section_boundary(layout, located)
    end_page = end_evidence.page if end_evidence is not None else (boundary[0] if boundary is not None else max(pages, default=start_page))
    for page_index in range(start_page, end_page + 1):
        page = pages.get(page_index)
        if page is None:
            continue
        top = start_evidence.bbox[3] if page_index == start_page else page.rect[1]
        bottom = (
            end_evidence.bbox[1]
            if end_evidence is not None and page_index == end_page
            else boundary[1]
            if boundary is not None and page_index == boundary[0]
            else page.rect[3]
        )
        span = (page.rect[0], top, page.rect[2], bottom)
        if any(_intersects(image, span) and not _decorative_margin_image(page, image) for image in page.image_rects):
            return True
    return False


def _has_digital_target_text(layout: PdfReadResult, located: LocatedFence) -> bool:
    """Return whether this target is already observed as digital text.

    A partial fence can retain a digital start/end observation even though it
    cannot safely form a SectionInput.  Such an outcome is not an OCR need,
    unless the locator found that the target also requires image reading.
    For a fully digital document, an absent heading is also a digital locator
    result rather than a reason to render every page.
    """
    if "SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED" in located.reasons or _partial_target_has_relevant_image(layout, located):
        return False
    if any(evidence.source_type is EvidenceSourceType.TEXT for evidence in located.fence.evidence):
        return True
    return layout.capability is DocumentCapability.TEXT and not any(page.image_count for page in layout.pages)


def scan_pdf_sections(path: str | Path, *, engine: OcrEngine | None = None, sections: tuple[str, ...] = ("1", "3")) -> ScanOcrResult:
    """Route each target independently: digital TEXT first, then local OCR recon.

    OCR is not initialized, rendered, or invoked for targets already confirmed
    as digital text.  A missing engine produces an explicit OCR route outcome,
    never a whole-document or first-pages fallback.
    """
    if not set(sections).issubset({"1", "3"}):
        raise ValueError("ONLY_SECTION_1_AND_3_ARE_SUPPORTED")
    layout = read_pdf_layout(path)
    routes: dict[str, TargetRoute] = {}
    inputs: dict[str, SectionInput] = {}
    ocr_targets: list[str] = []
    for section_no in sections:
        located = locate_section(layout, section_no)
        if located.description is not None and located.description.capability is DocumentCapability.TEXT:
            inputs[section_no] = build_section_input(layout, located.description)
            routes[section_no] = TargetRoute(section_no, DocumentCapability.TEXT, located.fence, located.reasons)
        elif _has_digital_target_text(layout, located):
            routes[section_no] = TargetRoute(section_no, DocumentCapability.TEXT, located.fence, located.reasons)
        else:
            ocr_targets.append(section_no)
    if not ocr_targets:
        return ScanOcrResult(tuple(routes[section] for section in sections), tuple(inputs[section] for section in sections if section in inputs), OcrMetrics())
    if engine is None:
        for section_no in ocr_targets:
            prior = locate_section(layout, section_no)
            routes[section_no] = TargetRoute(section_no, DocumentCapability.OCR, prior.fence, prior.reasons + ("OCR_ENGINE_NOT_SUPPLIED",))
        return ScanOcrResult(tuple(routes[section] for section in sections), tuple(inputs[section] for section in sections if section in inputs), OcrMetrics())
    recon: _Recon | None = None
    released = False
    try:
        recon = _reconstruct(path, layout, engine)
    except (fitz.FileDataError, OSError, RuntimeError, ValueError) as error:
        for section_no in ocr_targets:
            prior = routes.get(section_no)
            if prior is None:
                routes[section_no] = TargetRoute(section_no, DocumentCapability.OCR, locate_section(layout, section_no).fence, (f"OCR_RECON_ERROR:{type(error).__name__}",))
    else:
        for section_no in ocr_targets:
            located: LocatedFence = locate_section(recon.layout, section_no)
            route = TargetRoute(section_no, DocumentCapability.OCR, located.fence, located.reasons)
            routes[section_no] = route
            if located.description is None:
                continue
            try:
                inputs[section_no] = build_ocr_section_input(recon.layout, located.description, recon.rendered)
            except (OSError, RuntimeError, ValueError) as error:
                routes[section_no] = TargetRoute(
                    section_no, DocumentCapability.OCR, located.fence,
                    located.reasons + (f"OCR_SECTION_INPUT_ERROR:{type(error).__name__}",),
                )
    finally:
        release = getattr(engine, "release", None)
        if callable(release):
            release()
            released = True
    calls = recon.invocation_count if recon is not None else 0
    renders = len(recon.rendered) if recon is not None else 0
    return ScanOcrResult(
        tuple(routes[section] for section in sections), tuple(inputs[section] for section in sections if section in inputs),
        _engine_metrics(engine, invocation_count=calls, render_count=renders, released=released),
    )
