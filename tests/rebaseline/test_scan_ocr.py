"""Phase 4 local Scan/OCR foundation contracts (all OCR is deterministic fake data)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.msds.collectors import collect_product_candidates, collect_section3_candidates
from src.msds.models import CasCandidateValidity, DocumentCapability, EvidenceSourceType, FenceStatus
from src.msds.ocr import LazyPaddleOcrEngine, OcrMetrics, OcrToken, _pixel_to_pdf, scan_pdf_sections
from src.msds.pdf_io import LayoutLine, read_pdf_layout
from src.msds.sections import locate_section
import src.msds.ocr as ocr
from tests.rebaseline.pdf_helpers import make_pdf


class FakeOcr:
    """In-memory local engine: no imports, model files, network, or subprocesses."""

    def __init__(self, pages: list[list[tuple[str, tuple[float, float, float, float]]]]) -> None:
        self.pages = pages
        self.calls = 0
        self.released = False

    @property
    def metrics(self) -> OcrMetrics:
        return OcrMetrics(1 if self.calls else 0, self.calls, 0, self.released, 0)

    def recognize(self, _image: bytes):
        result = [OcrToken(text, bbox, 0.99) for text, bbox in self.pages[self.calls]]
        self.calls += 1
        return result

    def release(self):
        self.released = True


def _page(*rows: tuple[str, tuple[float, float, float, float]]):
    return list(rows)


S1 = "1. Chemical product and company identification"
S2 = "2. Hazards identification"
S3 = "3. Composition/information on ingredients"
S4 = "4. First-aid measures"


def _image_pdf(pdf_tmp, name: str, count: int = 1, *, rotations=None, cropboxes=None, **pdf_args):
    return make_pdf(pdf_tmp / name, [[] for _ in range(count)], images=set(range(count)), rotations=rotations, cropboxes=cropboxes, **pdf_args)


def _scan_s1(pdf_tmp, rows, *, name="s1.pdf", **kwargs):
    return scan_pdf_sections(_image_pdf(pdf_tmp, name, **kwargs), engine=FakeOcr([_page(*rows)]), sections=("1",))


def _rotated_ocr_rows(rows, rotation):
    """Convert fixed unrotated test geometry into the rendered OCR coordinate space."""
    page_width, page_height = 595, 842

    def forward(point):
        x, y = point
        if rotation == 0:
            return x, y
        if rotation == 90:
            return page_height - y, x
        if rotation == 180:
            return page_width - x, page_height - y
        return y, page_width - x

    converted = []
    for text, bbox in rows:
        corners = [forward(point) for point in ((bbox[0], bbox[1]), (bbox[2], bbox[1]), (bbox[0], bbox[3]), (bbox[2], bbox[3]))]
        converted.append((text, (min(x for x, _ in corners), min(y for _, y in corners), max(x for x, _ in corners), max(y for _, y in corners))))
    return converted


def test_p4_01_digital_only_never_initializes_or_renders_ocr(pdf_tmp):
    path = make_pdf(pdf_tmp / "digital.pdf", [[(72, 72, S1), (72, 110, "Product: Stable"), (72, 160, S2)]])
    fake = FakeOcr([])
    result = scan_pdf_sections(path, engine=fake, sections=("1",))
    assert result.input_for("1").capability is DocumentCapability.TEXT
    assert (fake.calls, result.metrics.initialization_count, result.metrics.render_count) == (0, 0, 0)
    assert not fake.released


def test_p4_digital_partial_fence_remains_text_without_ocr(pdf_tmp):
    path = make_pdf(pdf_tmp / "digital-partial.pdf", [[(72, 72, S1), (72, 110, "Product: Stable")]])
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("1",))

    assert result.input_for("1") is None
    assert result.routes[0].capability is DocumentCapability.TEXT
    assert result.routes[0].fence.status.value == "FENCE_PARTIAL"
    assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count, result.metrics.render_count) == (0, 0, 0, 0)
    assert not fake.released


def test_p4_digital_blank_page_missing_target_remains_text_without_ocr(pdf_tmp):
    path = make_pdf(pdf_tmp / "digital-blank-missing-s3.pdf", [[(72, 72, S1)], []])
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert result.input_for("3") is None
    assert result.routes[0].capability is DocumentCapability.TEXT
    assert result.routes[0].fence.status.value == "FENCE_NOT_FOUND"
    assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count, result.metrics.render_count) == (0, 0, 0, 0)
    assert not fake.released


def test_p4_02_image_only_uses_local_ocr_route_and_releases_batch_engine(pdf_tmp):
    fake = FakeOcr([
        _page((S1, (50, 70, 400, 90)), ("Product: OCR Resin", (50, 110, 240, 130)), (S2, (50, 170, 260, 190))),
        _page((S3, (50, 70, 400, 90)), ("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), (S4, (50, 170, 240, 190))),
    ])
    result = scan_pdf_sections(_image_pdf(pdf_tmp, "image-only.pdf", 2), engine=fake)
    assert {item.section_no for item in result.inputs} == {"1", "3"}
    assert all(item.capability is DocumentCapability.OCR for item in result.inputs)
    assert (result.metrics.initialization_count, result.metrics.invocation_count, result.metrics.render_count, result.metrics.released, result.metrics.external_call_count) == (1, 2, 2, True, 0)


def test_lazy_paddle_adapter_uses_injected_current_contract_without_cls_keyword():
    class CurrentShape:
        def __init__(self):
            self.calls = []

        def ocr(self, image):
            self.calls.append(image)
            return [[([[1, 2], [3, 2], [3, 4], [1, 4]], ("local", 0.9))]]

    current = CurrentShape()
    adapter = LazyPaddleOcrEngine(lambda: current)
    assert adapter.recognize(b"image") == [OcrToken("local", (1.0, 2.0, 3.0, 4.0), 0.9)]
    assert current.calls == [b"image"] and adapter.metrics.initialization_count == 1


def test_lazy_paddle_adapter_has_no_default_download_capable_factory():
    with pytest.raises(RuntimeError, match="LOCAL_PADDLE_FACTORY_REQUIRED"):
        LazyPaddleOcrEngine().recognize(b"image")


def test_p4_03_mixed_targets_route_s1_text_and_s3_ocr_independently(pdf_tmp):
    path = make_pdf(pdf_tmp / "mixed.pdf", [[(72, 72, S1), (72, 110, "Product: Digital"), (72, 160, S2)], []], images={1})
    fake = FakeOcr([_page(), _page((S3, (50, 70, 400, 90)), ("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), (S4, (50, 170, 240, 190)))])
    result = scan_pdf_sections(path, engine=fake)
    assert result.input_for("1").capability is DocumentCapability.TEXT
    assert result.input_for("3").capability is DocumentCapability.OCR
    assert fake.calls == 2  # one batch recon, never a per-target engine init


def test_p4_mixed_text_and_image_required_target_uses_ocr_despite_digital_heading(pdf_tmp):
    path = make_pdf(pdf_tmp / "mixed-s3-image-required.pdf", [[
        (72, 72, S3), (72, 110, "DIGITAL BODY HAS ENOUGH TEXT FOR SAFE TEXT FENCE"), (72, 180, S4),
    ]], images={0}, image_rects={0: (300, 95, 420, 135)})
    initial = locate_section(read_pdf_layout(path), "3")
    fake = FakeOcr([_page(
        (S3, (50, 70, 400, 90)), ("64-17-5", (50, 110, 110, 130)),
        ("10%", (300, 110, 330, 130)), (S4, (50, 170, 240, 190)),
    )])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert initial.reasons == ("SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED",)
    assert result.routes[0].capability is DocumentCapability.OCR
    assert result.input_for("3").capability is DocumentCapability.OCR
    assert fake.calls == 1


def test_p4_fix_01_partial_digital_s1_body_image_uses_ocr_recon(pdf_tmp):
    path = make_pdf(pdf_tmp / "partial-s1-body-image.pdf", [[(72, 72, S1)]], images={0}, image_rects={0: (72, 110, 430, 250)})
    fake = FakeOcr([_page((S1, (50, 70, 400, 90)), ("Product: OCR body", (50, 110, 240, 130)), (S2, (50, 280, 260, 300)))])

    result = scan_pdf_sections(path, engine=fake, sections=("1",))

    assert result.input_for("1").capability is DocumentCapability.OCR
    assert fake.calls == 1


def test_p4_fix_02_partial_digital_target_ignores_unrelated_page_image(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-s1-unrelated-image.pdf", [[(72, 72, S1)], [(72, 72, S2)], []], images={2},
        image_rects={2: (72, 110, 430, 250)},
    )
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("1",))

    assert result.routes[0].capability is DocumentCapability.TEXT
    assert result.routes[0].fence.status.value == "FENCE_PARTIAL"
    assert fake.calls == 0


def test_p4_fix_02_partial_ambiguous_end_ignores_later_section_image(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-s1-ambiguous-end-image.pdf",
        [[(72, 72, S1)], [(72, 72, S1)], [(72, 72, S2)]],
        images={2}, image_rects={2: (72, 110, 430, 250)},
    )
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("1",))

    assert result.routes[0].capability is DocumentCapability.TEXT
    assert result.routes[0].fence.status.value == "FENCE_PARTIAL"
    assert result.routes[0].reasons == ("SECTION_START_AMBIGUOUS",)
    assert fake.calls == 0


def test_p4_fix_03_partial_digital_target_ignores_top_left_decorative_logo(pdf_tmp):
    path = make_pdf(pdf_tmp / "partial-s1-logo.pdf", [[(72, 72, S1)]], images={0}, image_rects={0: (12, 76, 62, 82)})
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("1",))

    assert result.routes[0].capability is DocumentCapability.TEXT
    assert fake.calls == 0


def test_p4_fix_04_partial_digital_s3_boundary_image_uses_ocr_recon(pdf_tmp):
    path = make_pdf(pdf_tmp / "partial-s3-boundary-image.pdf", [[(72, 72, S3)]], images={0}, image_rects={0: (72, 105, 430, 250)})
    fake = FakeOcr([_page((S3, (50, 70, 400, 90)), ("64-17-5", (50, 120, 110, 140)), ("10%", (300, 120, 330, 140)), (S4, (50, 280, 260, 300)))])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert result.input_for("3").capability is DocumentCapability.OCR
    assert fake.calls == 1


def test_p4_fix_05_partial_s3_image_keeps_confirmed_s1_text(pdf_tmp):
    path = make_pdf(pdf_tmp / "mixed-partial-s3-image.pdf", [[(72, 72, S1), (72, 110, "Product: Digital"), (72, 170, S2)], [(72, 72, S3)]], images={1}, image_rects={1: (72, 110, 430, 250)})
    fake = FakeOcr([
        _page((S1, (50, 70, 400, 90)), ("Product: Digital", (50, 110, 240, 130)), (S2, (50, 170, 260, 190))),
        _page((S3, (50, 70, 400, 90)), ("64-17-5", (50, 120, 110, 140)), ("10%", (300, 120, 330, 140)), (S4, (50, 280, 260, 300))),
    ])

    result = scan_pdf_sections(path, engine=fake)

    assert result.input_for("1").capability is DocumentCapability.TEXT
    assert result.input_for("3").capability is DocumentCapability.OCR
    assert fake.calls == 2


@pytest.mark.parametrize(
    ("name", "pages", "images", "image_rects", "expects_ocr"),
    [
        ("no-image", [[(72, 72, S1), (72, 110, "Product: Digital"), (400, 115, "Other column"), (72, 220, S2)]], set(), {}, False),
        ("body-image", [[(72, 72, S1), (72, 110, "Product: Digital"), (400, 115, "Other column"), (72, 220, S2)]], {0}, {0: (72, 145, 430, 180)}, True),
        ("decorative-logo", [[(72, 72, S1), (72, 110, "Product: Digital"), (400, 115, "Other column"), (72, 220, S2)]], {0}, {0: (540, 110, 550, 120)}, False),
        ("later-unrelated-image", [[(72, 72, S1), (72, 110, "Product: Digital"), (400, 115, "Other column"), (72, 220, S2)], [(72, 72, S3)]], {1}, {1: (72, 110, 430, 250)}, False),
    ],
)
def test_p4_fix_13_partial_digital_start_end_evidence_image_route_is_bounded(
    pdf_tmp, name, pages, images, image_rects, expects_ocr,
):
    path = make_pdf(pdf_tmp / f"partial-start-end-{name}.pdf", pages, images=images, image_rects=image_rects)
    initial = locate_section(read_pdf_layout(path), "1")
    fake = FakeOcr([_page(
        (S1, (50, 70, 400, 90)), ("Product: OCR body", (50, 110, 240, 130)), (S2, (50, 220, 260, 240)),
    )])

    result = scan_pdf_sections(path, engine=fake, sections=("1",))

    assert initial.fence.status.value == "FENCE_PARTIAL"
    assert initial.reasons == ("MULTI_COLUMN_BOUNDARY_AMBIGUOUS",)
    assert tuple(evidence.page for evidence in initial.fence.evidence) == (0, 0)
    if expects_ocr:
        assert result.routes[0].capability is DocumentCapability.OCR
        assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count) == (1, 1, 1)
    else:
        assert result.routes[0].capability is DocumentCapability.TEXT
        assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count) == (0, 0, 0)


def test_p4_fix_14_partial_digital_s3_continuation_image_routes_to_confirmed_ocr(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-digital-s3-continuation.pdf",
        [[(72, 72, S3)], [], []], images={1, 2},
        image_rects={1: (72, 110, 430, 250), 2: (72, 110, 430, 250)},
    )
    initial = locate_section(read_pdf_layout(path), "3")
    fake = FakeOcr([
        _page((S3, (50, 70, 400, 90))),
        _page(("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130))),
        _page((S4, (50, 170, 240, 190))),
    ])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert initial.fence.status.value == "FENCE_PARTIAL" and len(initial.fence.evidence) == 1
    assert result.input_for("3").capability is DocumentCapability.OCR
    assert [(block.cas_candidates[0].raw, block.content_candidates[0].raw) for block in collect_section3_candidates(result.input_for("3")).blocks] == [("64-17-5", "10%")]
    assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count) == (3, 1, 3)


def test_p4_fix_15_partial_digital_next_explicit_section_blocks_later_image(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-digital-s3-next-section.pdf",
        [[(72, 72, S3)], [(72, 72, "5. Fire-fighting measures")], []], images={2},
        image_rects={2: (72, 110, 430, 250)},
    )
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert result.routes[0].capability is DocumentCapability.TEXT
    assert result.routes[0].fence.status.value == "FENCE_PARTIAL"
    assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count, result.metrics.render_count) == (0, 0, 0, 0)


def test_p4_fix_28_partial_s3_false_section_five_acetone_keeps_image_continuation(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-s3-false-s5-acetone.pdf",
        [[(72, 72, S3)], [(72, 72, "5. Acetone")], []], images={2},
        image_rects={2: (72, 110, 430, 250)},
    )
    fake = FakeOcr([
        _page((S3, (50, 70, 400, 90))),
        _page(("5. Acetone", (50, 70, 180, 90))),
        _page(("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), (S4, (50, 170, 240, 190))),
    ])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert [(block.cas_candidates[0].raw, block.content_candidates[0].raw) for block in collect_section3_candidates(result.input_for("3")).blocks] == [("64-17-5", "10%")]
    assert fake.calls == 3


def test_p4_fix_29_partial_s3_numbered_component_rows_keep_image_continuation(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-s3-numbered-components.pdf",
        [[(72, 72, S3)], [(72, 72, "5. Acetone"), (72, 96, "4. Acetone"), (72, 120, "2. Methanol")], []], images={2},
        image_rects={2: (72, 110, 430, 250)},
    )
    fake = FakeOcr([
        _page((S3, (50, 70, 400, 90))),
        _page(("5. Acetone", (50, 70, 180, 90)), ("4. Acetone", (50, 96, 180, 116)), ("2. Methanol", (50, 120, 180, 140))),
        _page(("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), (S4, (50, 170, 240, 190))),
    ])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert [(block.cas_candidates[0].raw, block.content_candidates[0].raw) for block in collect_section3_candidates(result.input_for("3")).blocks] == [("64-17-5", "10%")]
    assert fake.calls == 3


def test_p4_fix_30_partial_s3_true_section_five_fire_fighting_blocks_unrelated_image(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-s3-true-s5-fire-fighting.pdf",
        [[(72, 72, S3)], [(72, 72, "5. Fire-fighting measures")], []], images={2},
        image_rects={2: (72, 110, 430, 250)},
    )
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert result.routes[0].capability is DocumentCapability.TEXT
    assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count, result.metrics.render_count) == (0, 0, 0, 0)


def test_p4_fix_31_partial_target_canonical_next_section_wins_over_later_semantic_section(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-s3-canonical-s4-wins.pdf",
        [[(72, 72, S3)], [(72, 72, "5. Fire-fighting measures")], [], [(72, 72, S4)]], images={2},
        image_rects={2: (72, 110, 430, 250)},
    )
    fake = FakeOcr([
        _page((S3, (50, 70, 400, 90))),
        _page(("5. Fire-fighting measures", (50, 70, 260, 90))),
        _page(("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130))),
        _page((S4, (50, 170, 240, 190))),
    ])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert [(block.cas_candidates[0].raw, block.content_candidates[0].raw) for block in collect_section3_candidates(result.input_for("3")).blocks] == [("64-17-5", "10%")]
    assert fake.calls == 4

    s1_path = make_pdf(
        pdf_tmp / "partial-s1-canonical-s2-wins.pdf",
        [[(72, 72, S1)], [(72, 72, S3)], [], [(72, 72, S2)]], images={2},
        image_rects={2: (72, 110, 430, 250)},
    )
    s1_fake = FakeOcr([
        _page((S1, (50, 70, 400, 90))),
        _page((S3, (50, 70, 400, 90))),
        _page(("Product: OCR Resin", (50, 110, 240, 130))),
        _page((S2, (50, 170, 260, 190))),
    ])

    s1_result = scan_pdf_sections(s1_path, engine=s1_fake, sections=("1",))

    assert collect_product_candidates(s1_result.input_for("1")).candidates[0].raw == "OCR Resin"
    assert s1_fake.calls == 4


def test_p4_fix_32_partial_s3_false_section_four_acetone_keeps_image_continuation(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-s3-false-s4-acetone.pdf",
        [[(72, 72, S3)], [(72, 72, "4. Acetone")], []], images={2},
        image_rects={2: (72, 110, 430, 250)},
    )
    fake = FakeOcr([
        _page((S3, (50, 70, 400, 90))),
        _page(("4. Acetone", (50, 70, 180, 90))),
        _page(("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), (S4, (50, 170, 240, 190))),
    ])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert [(block.cas_candidates[0].raw, block.content_candidates[0].raw) for block in collect_section3_candidates(result.input_for("3")).blocks] == [("64-17-5", "10%")]
    assert fake.calls == 3


def test_p4_fix_33_partial_s3_korean_numbered_component_row_keeps_image_continuation(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-s3-korean-numbered-component.pdf",
        [[(72, 72, S3)], [(72, 72, "5. 아세톤")], []], images={2},
        image_rects={2: (72, 110, 430, 250)},
    )
    fake = FakeOcr([
        _page((S3, (50, 70, 400, 90))),
        _page(("5. 아세톤", (50, 70, 180, 90))),
        _page(("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), (S4, (50, 170, 240, 190))),
    ])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert [(block.cas_candidates[0].raw, block.content_candidates[0].raw) for block in collect_section3_candidates(result.input_for("3")).blocks] == [("64-17-5", "10%")]
    assert fake.calls == 3


def test_p4_fix_27_partial_digital_boundary_uses_visual_not_stored_line_order(pdf_tmp, monkeypatch):
    path = make_pdf(
        pdf_tmp / "partial-digital-s3-visual-boundary.pdf",
        [[(72, 72, S3)]], images={0}, image_rects={0: (72, 155, 430, 190)},
    )
    original = ocr.read_pdf_layout

    def read_with_reversed_headings(*args, **kwargs):
        layout = original(*args, **kwargs)
        page = layout.pages[0]
        later_heading = LayoutLine(0, 2, 0, "6. Accidental release measures", (72, 180, 360, 195), 12)
        earlier_heading = LayoutLine(0, 1, 0, "5. Fire-fighting measures", (72, 140, 330, 150), 12)
        return replace(layout, pages=(replace(page, lines=page.lines + (later_heading, earlier_heading)),))

    monkeypatch.setattr(ocr, "read_pdf_layout", read_with_reversed_headings)
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert result.routes[0].capability is DocumentCapability.TEXT
    assert result.routes[0].fence.status.value == "FENCE_PARTIAL"
    assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count, result.metrics.render_count) == (0, 0, 0, 0)


@pytest.mark.parametrize("rect", [(12, 76, 62, 82), (12, 810, 62, 820), (540, 410, 550, 420)])
def test_p4_fix_16_partial_digital_margin_images_never_start_ocr(pdf_tmp, rect):
    path = make_pdf(pdf_tmp / f"partial-margin-{rect[1]}.pdf", [[(72, 72, S1)]], images={0}, image_rects={0: rect})
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("1",))

    assert result.routes[0].capability is DocumentCapability.TEXT
    assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count, result.metrics.render_count) == (0, 0, 0, 0)


def test_p4_fix_16_partial_digital_unknown_image_placement_never_starts_ocr(pdf_tmp, monkeypatch):
    path = make_pdf(pdf_tmp / "partial-unknown-image.pdf", [[(72, 72, S1)]])
    original = ocr.read_pdf_layout

    def read_with_unknown_image(*args, **kwargs):
        layout = original(*args, **kwargs)
        return replace(layout, pages=(replace(layout.pages[0], image_count=1, image_rects=()),))

    monkeypatch.setattr(ocr, "read_pdf_layout", read_with_unknown_image)
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("1",))

    assert result.routes[0].capability is DocumentCapability.TEXT
    assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count, result.metrics.render_count) == (0, 0, 0, 0)


def test_p4_fix_17_partial_s3_ocr_keeps_confirmed_s1_text_route(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-s3-with-confirmed-s1.pdf",
        [[(72, 72, S1), (72, 110, "Product: Digital"), (72, 170, S2)], [(72, 72, S3)], [], []],
        images={2, 3}, image_rects={2: (72, 110, 430, 250), 3: (72, 110, 430, 250)},
    )
    fake = FakeOcr([
        _page((S1, (50, 70, 400, 90)), ("Product: Digital", (50, 110, 240, 130)), (S2, (50, 170, 260, 190))),
        _page((S3, (50, 70, 400, 90))),
        _page(("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130))),
        _page((S4, (50, 170, 240, 190))),
    ])

    result = scan_pdf_sections(path, engine=fake)

    assert result.input_for("1").capability is DocumentCapability.TEXT
    assert result.input_for("3").capability is DocumentCapability.OCR
    assert fake.calls == 4


def test_p4_fix_18_single_strong_product_row_keeps_right_value_and_ocr_evidence(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), ("Product:", (50, 110, 120, 130)), ("OCR Resin", (300, 110, 390, 130)),
        (S2, (50, 170, 260, 190)),
    ))
    candidate = collect_product_candidates(result.input_for("1")).candidates[0]

    assert result.routes[0].fence.status.value == "FENCE_CONFIRMED"
    assert (candidate.raw, candidate.evidence[0].source_type) == ("OCR Resin", EvidenceSourceType.OCR)


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("Product:", "Product"),
        ("Product name:", "Product Model (Grade A)"),
        ("Product identifier:", "ABC-100 (10%)"),
        ("제품명:", "제품명"),
        ("제품 식별자:", "제품 Grade A 농도 10%"),
    ],
)
def test_p4_fix_19_strong_product_values_preserve_raw_product_korean_and_detail(pdf_tmp, label, value):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), (label, (50, 110, 170, 130)), (value, (300, 110, 520, 130)),
        (S2, (50, 170, 260, 190)),
    ), name=f"strong-product-{label.encode('utf-8').hex()}.pdf")
    candidate = collect_product_candidates(result.input_for("1")).candidates[0]

    assert (candidate.raw, candidate.evidence[0].source_type) == (value, EvidenceSourceType.OCR)


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("Product", "Target Product"),
        ("Product name", "Product Model (Grade A)"),
        ("Product identifier", "ABC-100 (10%)"),
        ("제품명", "제품명 Product"),
        ("제품 식별자", "제품 Grade A 농도 10%"),
    ],
)
def test_p4_fix_25_colonless_strong_product_label_keeps_same_row_raw_and_evidence(pdf_tmp, label, value):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), (label, (50, 110, 170, 130)), (value, (300, 110, 520, 130)),
        (S2, (50, 170, 260, 190)),
    ), name=f"colonless-strong-product-{label.encode('utf-8').hex()}.pdf")
    section_input = result.input_for("1")
    candidate = collect_product_candidates(section_input).candidates[0]

    assert result.routes[0].fence.status.value == "FENCE_CONFIRMED"
    assert (candidate.raw, candidate.evidence[0].source_type) == (value, EvidenceSourceType.OCR)
    assert value in "".join(token.text for token in section_input.tokens)


def test_p4_fix_26_strong_product_pipe_label_keeps_same_row_value(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), ("Product |", (50, 110, 170, 130)), ("Target Product", (300, 110, 520, 130)),
        (S2, (50, 170, 260, 190)),
    ))
    candidate = collect_product_candidates(result.input_for("1")).candidates[0]

    assert (candidate.raw, candidate.evidence[0].source_type) == ("Target Product", EvidenceSourceType.OCR)


def test_p4_fix_20_two_independent_product_columns_keep_only_target_band(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), ("Product:", (50, 110, 120, 130)), ("Target Product", (260, 110, 390, 130)),
        ("Product:", (410, 110, 480, 130)), ("Foreign Product", (510, 110, 590, 130)),
        (S2, (50, 170, 260, 190)),
    ))
    section_input = result.input_for("1")

    assert result.routes[0].fence.status.value == "FENCE_CONFIRMED"
    assert [candidate.raw for candidate in collect_product_candidates(section_input).candidates] == ["Target Product"]
    assert "Foreign Product" not in "".join(token.text for token in section_input.tokens)


def test_p4_fix_21_strong_product_with_unproven_far_right_column_is_partial(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), ("Product:", (50, 110, 120, 130)), ("Target resin", (260, 110, 350, 130)),
        ("Foreign column", (440, 110, 570, 130)), (S2, (50, 170, 260, 190)),
    ))

    assert result.input_for("1") is None
    assert result.routes[0].fence.status.value == "FENCE_PARTIAL"
    assert result.routes[0].reasons == ("SAME_PAGE_READING_ORDER_AMBIGUOUS",)


def test_p4_fix_22_multiline_product_and_company_boundary_keep_collector_semantics(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), ("Product:", (50, 110, 120, 130)), ("ABC-100", (50, 140, 150, 160)),
        ("Company: Example", (50, 170, 200, 190)), (S2, (50, 220, 260, 240)),
    ))

    assert [candidate.raw for candidate in collect_product_candidates(result.input_for("1")).candidates] == ["ABC-100"]


def test_p4_fix_23_inline_product_value_stays_collector_owned(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), ("Product: ABC-100 (Model A, Grade 2, 10%)", (50, 110, 360, 130)),
        (S2, (50, 170, 260, 190)),
    ))
    candidate = collect_product_candidates(result.input_for("1")).candidates[0]

    assert (candidate.raw, candidate.evidence[0].source_type) == ("ABC-100 (Model A, Grade 2, 10%)", EvidenceSourceType.OCR)


def test_p4_fix_24_partial_s3_next_section_then_margin_image_stays_text(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "partial-s3-next-section-margin.pdf",
        [[(72, 72, S3)], [(72, 72, "5. Regulatory information")], []], images={2},
        image_rects={2: (12, 810, 62, 820)},
    )
    fake = FakeOcr([])

    result = scan_pdf_sections(path, engine=fake, sections=("3",))

    assert result.routes[0].capability is DocumentCapability.TEXT
    assert (fake.calls, result.metrics.initialization_count, result.metrics.invocation_count, result.metrics.render_count) == (0, 0, 0, 0)


def test_p4_ocr_input_build_failure_isolated_per_confirmed_target(pdf_tmp, monkeypatch):
    path = _image_pdf(pdf_tmp, "isolated-build-failure.pdf", 2)
    fake = FakeOcr([
        _page((S1, (50, 70, 400, 90)), ("Product: OCR Resin", (50, 110, 240, 130)), (S2, (50, 170, 260, 190))),
        _page((S3, (50, 70, 400, 90)), ("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), (S4, (50, 170, 240, 190))),
    ])
    original = ocr.build_ocr_section_input

    def fail_section_one(layout, fence, rendered):
        if fence.section_no == "1":
            raise ValueError("synthetic isolated input failure")
        return original(layout, fence, rendered)

    monkeypatch.setattr(ocr, "build_ocr_section_input", fail_section_one)
    result = scan_pdf_sections(path, engine=fake)

    assert result.input_for("1") is None
    assert result.input_for("3") is not None
    assert result.routes[0].fence.status.value == "FENCE_CONFIRMED"
    assert "OCR_SECTION_INPUT_ERROR:ValueError" in result.routes[0].reasons


def test_p4_engine_metric_preserves_observed_external_calls(pdf_tmp):
    class NonzeroExternalMetricFake(FakeOcr):
        @property
        def metrics(self) -> OcrMetrics:
            return OcrMetrics(1 if self.calls else 0, self.calls, 0, self.released, 7)

    result = scan_pdf_sections(
        _image_pdf(pdf_tmp, "external-metric.pdf"),
        engine=NonzeroExternalMetricFake([_page((S1, (50, 70, 400, 90)), (S2, (50, 170, 260, 190)))]),
        sections=("1",),
    )

    assert result.metrics.external_call_count == 7


def test_p4_04_ocr_s1_to_s2_is_confirmed(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page((S1, (50, 70, 400, 90)), ("Product: OCR Resin", (50, 110, 240, 130)), (S2, (50, 170, 260, 190))))
    assert result.routes[0].fence.status.value == "FENCE_CONFIRMED"
    assert collect_product_candidates(result.input_for("1")).candidates[0].raw == "OCR Resin"


def test_p4_05_ocr_s3_to_s4_is_confirmed(pdf_tmp):
    path = _image_pdf(pdf_tmp, "s3.pdf")
    result = scan_pdf_sections(path, engine=FakeOcr([_page((S3, (50, 70, 400, 90)), ("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), (S4, (50, 170, 240, 190)))]), sections=("3",))
    assert result.routes[0].fence.status.value == "FENCE_CONFIRMED"
    assert collect_section3_candidates(result.input_for("3")).blocks[0].cas_candidates[0].raw == "64-17-5"


def test_p4_fix_06_ocr_s1_repeated_label_value_rows_are_safe(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), ("Product:", (50, 110, 120, 130)), ("Target resin", (300, 110, 390, 130)),
        ("Company:", (50, 145, 130, 165)), ("Example", (300, 145, 370, 165)), (S2, (50, 210, 260, 230)),
    ))

    assert collect_product_candidates(result.input_for("1")).candidates[0].raw == "Target resin"


def test_p4_fix_07_ocr_s3_repeated_cas_content_rows_are_safe(pdf_tmp):
    path = _image_pdf(pdf_tmp, "safe-s3-table.pdf")
    result = scan_pdf_sections(path, engine=FakeOcr([_page(
        (S3, (50, 70, 400, 90)), ("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)),
        ("67-64-1", (50, 145, 110, 165)), ("20%", (300, 145, 330, 165)), (S4, (50, 210, 240, 230)),
    )]), sections=("3",))

    assert [block.cas_candidates[0].raw for block in collect_section3_candidates(result.input_for("3")).blocks] == ["64-17-5", "67-64-1"]


def test_p4_fix_08_ocr_same_page_independent_column_is_x_bounded(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), ("Product:", (50, 110, 120, 130)), ("Target resin", (260, 110, 350, 130)),
        ("Product:", (390, 110, 460, 130)), ("Foreign resin", (530, 110, 590, 130)),
        ("Company:", (50, 145, 130, 165)), ("Target Co.", (260, 145, 350, 165)),
        ("Company:", (390, 145, 470, 165)), ("Foreign Co.", (530, 145, 590, 165)),
        (S2, (50, 210, 260, 230)),
    ))
    section_input = result.input_for("1")

    assert collect_product_candidates(section_input).candidates[0].raw == "Target resin"
    assert "Foreign" not in "".join(token.text for token in section_input.tokens)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_p4_fix_12_ocr_s1_independent_value_product_columns_are_x_bounded(pdf_tmp, rotation):
    result = _scan_s1(pdf_tmp, _rotated_ocr_rows(_page(
        (S1, (50, 70, 400, 90)), ("Product", (50, 110, 120, 130)), ("Target Product", (260, 110, 390, 130)),
        ("Product", (390, 110, 460, 130)), ("Foreign Product", (530, 110, 650, 130)),
        ("Company", (50, 145, 130, 165)), ("Target Co.", (260, 145, 350, 165)),
        ("Company", (390, 145, 470, 165)), ("Foreign Co.", (530, 145, 620, 165)),
        (S2, (50, 210, 260, 230)),
    ), rotation), name=f"independent-value-product-{rotation}.pdf", rotations=[rotation])
    section_input = result.input_for("1")
    candidates = collect_product_candidates(section_input).candidates
    token_text = "".join(token.text for token in section_input.tokens)

    assert result.routes[0].fence.status.value == "FENCE_CONFIRMED"
    assert [candidate.raw for candidate in candidates] == ["Target Product"]
    assert "Foreign Product" not in token_text
    assert all(candidate.raw != "Foreign Product" for candidate in candidates)


def test_p4_fix_09_ocr_same_page_crossing_column_is_partial(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page(
        (S1, (50, 70, 400, 90)), ("Product:", (50, 110, 120, 130)), ("Target resin", (300, 110, 400, 130)),
        ("Product:", (360, 110, 430, 130)), ("Foreign resin", (520, 110, 590, 130)),
        ("Company:", (50, 145, 130, 165)), ("Target Co.", (300, 145, 400, 165)),
        ("Company:", (360, 145, 440, 165)), ("Foreign Co.", (520, 145, 590, 165)),
        (S2, (50, 210, 260, 230)),
    ))

    assert result.input_for("1") is None
    assert result.routes[0].fence.status.value == "FENCE_PARTIAL"
    assert result.routes[0].reasons == ("SAME_PAGE_READING_ORDER_AMBIGUOUS",)


def test_p4_fix_09_ocr_s3_independent_table_excludes_foreign_cas(pdf_tmp):
    path = _image_pdf(pdf_tmp, "independent-s3-columns.pdf")
    result = scan_pdf_sections(path, engine=FakeOcr([_page(
        (S3, (50, 70, 400, 90)), ("64-17-5", (50, 110, 110, 130)), ("10%", (200, 110, 230, 130)),
        ("67-64-1", (360, 110, 420, 130)), ("20%", (510, 110, 540, 130)),
        ("71-43-2", (50, 145, 110, 165)), ("30%", (200, 145, 230, 165)),
        ("75-07-0", (360, 145, 420, 165)), ("40%", (510, 145, 540, 165)),
        (S4, (50, 210, 240, 230)),
    )]), sections=("3",))
    section_input = result.input_for("3")

    assert [block.cas_candidates[0].raw for block in collect_section3_candidates(section_input).blocks] == ["64-17-5", "71-43-2"]
    assert "67-64-1" not in "".join(token.text for token in section_input.tokens)


def test_p4_fix_09_cropbox_s3_independent_table_excludes_foreign_cas(pdf_tmp):
    path = _image_pdf(pdf_tmp, "independent-s3-columns-crop.pdf", cropboxes=[(50, 60, 500, 700)])
    result = scan_pdf_sections(path, engine=FakeOcr([_page(
        (S3, (30, 30, 300, 50)), ("64-17-5", (30, 70, 90, 90)), ("10%", (180, 70, 210, 90)),
        ("67-64-1", (290, 70, 350, 90)), ("20%", (400, 70, 430, 90)),
        ("71-43-2", (30, 105, 90, 125)), ("30%", (180, 105, 210, 125)),
        ("75-07-0", (290, 105, 350, 125)), ("40%", (400, 105, 430, 125)),
        (S4, (30, 170, 220, 190)),
    )]), sections=("3",))

    assert [block.cas_candidates[0].raw for block in collect_section3_candidates(result.input_for("3")).blocks] == ["64-17-5", "71-43-2"]


def test_p4_fix_10_ocr_middle_independent_column_is_partial(pdf_tmp):
    path = _image_pdf(pdf_tmp, "middle-independent-columns.pdf", 3)
    result = scan_pdf_sections(path, engine=FakeOcr([
        _page((S3, (50, 70, 400, 90))),
        _page(("Target narrative", (50, 110, 180, 130)), ("67-64-1", (360, 110, 420, 130))),
        _page((S4, (50, 170, 240, 190))),
    ]), sections=("3",))

    assert result.input_for("3") is None
    assert result.routes[0].fence.status.value == "FENCE_PARTIAL"
    assert result.routes[0].reasons == ("MIDDLE_PAGE_READING_ORDER_AMBIGUOUS",)


def test_p4_fix_11_ocr_three_page_s3_table_remains_confirmed(pdf_tmp):
    path = _image_pdf(pdf_tmp, "three-page-s3-table.pdf", 4)
    result = scan_pdf_sections(path, engine=FakeOcr([
        _page((S3, (50, 70, 400, 90)), ("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130))),
        _page(("67-64-1", (50, 110, 110, 130)), ("20%", (300, 110, 330, 130))),
        _page(("71-43-2", (50, 110, 110, 130)), ("30%", (300, 110, 330, 130))),
        _page((S4, (50, 170, 240, 190))),
    ]), sections=("3",))

    assert [block.cas_candidates[0].raw for block in collect_section3_candidates(result.input_for("3")).blocks] == ["64-17-5", "67-64-1", "71-43-2"]


def test_p4_06_ocr_s3_multi_page_has_no_fixed_page_cutoff(pdf_tmp):
    rows = [
        _page((S3, (50, 70, 400, 90)), ("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130))),
        _page(("67-64-1", (50, 110, 110, 130)), ("20%", (300, 110, 330, 130))),
        _page(("71-43-2", (50, 110, 110, 130)), ("30%", (300, 110, 330, 130))),
        _page((S4, (50, 170, 240, 190))),
    ]
    result = scan_pdf_sections(_image_pdf(pdf_tmp, "s3-many.pdf", 4), engine=FakeOcr(rows), sections=("3",))
    assert len(collect_section3_candidates(result.input_for("3")).blocks) == 3
    assert result.metrics.invocation_count == 4


@pytest.mark.parametrize("section, rows", [("1", _page((S1, (50, 70, 400, 90)))), ("3", _page((S3, (50, 70, 400, 90))))])
def test_p4_07_unclear_boundary_is_partial_without_whole_document_fallback(pdf_tmp, section, rows):
    result = scan_pdf_sections(_image_pdf(pdf_tmp, f"unclear-{section}.pdf"), engine=FakeOcr([rows]), sections=(section,))
    assert result.input_for(section) is None
    assert result.routes[0].fence.status.value == "FENCE_PARTIAL"


def test_p4_08_same_page_s1_s2_fence_physically_isolates_ocr_tokens_and_image(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page((S1, (50, 70, 400, 90)), ("Product: INSIDE", (50, 110, 220, 130)), (S2, (50, 170, 260, 190)), ("OUTSIDE", (50, 210, 120, 230))))
    section_input = result.input_for("1")
    assert "OUTSIDE" not in "".join(token.text for token in section_input.tokens)
    assert section_input.isolated_images and section_input.isolated_images[0].bbox[1] >= 90


def test_p4_09_same_page_s3_s4_fence_physically_isolates_ocr_tokens(pdf_tmp):
    path = _image_pdf(pdf_tmp, "same-s3.pdf")
    result = scan_pdf_sections(path, engine=FakeOcr([_page((S3, (50, 70, 400, 90)), ("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), (S4, (50, 170, 240, 190)), ("99-99-9 99%", (50, 210, 180, 230)))]), sections=("3",))
    assert "99-99-9" not in "".join(token.text for token in result.input_for("3").tokens)


def test_p4_10_fence_outside_text_or_image_changes_do_not_change_s1_input_or_candidates(pdf_tmp):
    rows = _page((S1, (50, 70, 400, 90)), ("Product: Stable", (50, 110, 220, 130)), (S2, (50, 170, 260, 190)), ("OUTSIDE A", (50, 210, 180, 230)))
    first = _scan_s1(pdf_tmp, rows, name="outside-a.pdf", image_rects={0: (500, 10, 510, 20)})
    changed = rows[:-1] + [("OUTSIDE B", (50, 210, 180, 230))]
    second = _scan_s1(pdf_tmp, changed, name="outside-b.pdf", image_rects={0: (480, 10, 490, 20)})
    assert first.input_for("1").input_digest == second.input_for("1").input_digest
    assert collect_product_candidates(first.input_for("1")).candidates[0].raw == collect_product_candidates(second.input_for("1")).candidates[0].raw


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_p4_11_rotation_pixel_bbox_maps_to_unrotated_pdf_coordinates(rotation):
    bbox = _pixel_to_pdf((10, 20, 30, 40), pdf_rect=(0, 0, 100, 200), rotation=rotation, width=200 if rotation in {90, 270} else 100, height=100 if rotation in {90, 270} else 200)
    assert 0 <= bbox[0] < bbox[2] <= 100 and 0 <= bbox[1] < bbox[3] <= 200


def test_p4_12_cropbox_ocr_coordinates_are_zero_based_unrotated(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page((S1, (30, 30, 300, 50)), ("Product: Crop", (30, 70, 180, 90)), (S2, (30, 130, 240, 150))), name="crop.pdf", cropboxes=[(50, 60, 500, 700)])
    assert result.input_for("1").tokens[0].bbox[0] >= 0


def test_p4_13_multicolumn_table_bbox_preserves_row_and_source_order(pdf_tmp):
    path = _image_pdf(pdf_tmp, "columns.pdf")
    result = scan_pdf_sections(path, engine=FakeOcr([_page((S3, (50, 70, 400, 90)), ("CAS", (50, 100, 80, 120)), ("Content (%)", (300, 100, 390, 120)), ("64-17-5", (50, 130, 110, 150)), ("10", (300, 130, 320, 150)), (S4, (50, 180, 240, 200)))]), sections=("3",))
    block = collect_section3_candidates(result.input_for("3")).blocks[0]
    assert block.cas_candidates[0].source_order < block.content_candidates[0].source_order
    assert block.content_candidates[0].raw == "10"


def test_p4_14_ocr_product_keeps_raw_and_ocr_evidence(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page((S1, (50, 70, 400, 90)), ("Product: OCR Resin (X)", (50, 110, 260, 130)), (S2, (50, 170, 260, 190))))
    candidate = collect_product_candidates(result.input_for("1")).candidates[0]
    assert candidate.raw == "OCR Resin (X)" and candidate.evidence[0].source_type is EvidenceSourceType.OCR


def test_p4_15_ocr_product_multiline_stops_at_structural_field(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page((S1, (50, 70, 400, 90)), ("Product:", (50, 110, 130, 130)), ("OCR Resin", (50, 140, 150, 160)), ("Company: Example", (50, 170, 200, 190)), (S2, (50, 220, 260, 240))))
    assert collect_product_candidates(result.input_for("1")).candidates[0].raw == "OCR Resin"


def _s3_collected(pdf_tmp, rows):
    path = _image_pdf(pdf_tmp, "s3-collector.pdf")
    result = scan_pdf_sections(path, engine=FakeOcr([_page((S3, (50, 70, 400, 90)), *rows, (S4, (50, 300, 240, 320)))]), sections=("3",))
    return collect_section3_candidates(result.input_for("3"))


def test_p4_16_ocr_cas_and_percent_have_raw_ocr_evidence(pdf_tmp):
    block = _s3_collected(pdf_tmp, (("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)))).blocks[0]
    assert block.cas_candidates[0].evidence[0].source_type is EvidenceSourceType.OCR and block.content_candidates[0].raw == "10%"


def test_p4_17_ocr_blank_content_keeps_cas_without_content(pdf_tmp):
    block = _s3_collected(pdf_tmp, (("64-17-5", (50, 110, 110, 130)),)).blocks[0]
    assert block.cas_candidates and not block.content_candidates


def test_p4_18_ocr_percent_header_keeps_raw_10_and_unit_context(pdf_tmp):
    block = _s3_collected(pdf_tmp, (("CAS", (50, 100, 80, 120)), ("Content (%)", (300, 100, 390, 120)), ("64-17-5", (50, 140, 110, 160)), ("10", (300, 140, 320, 160)))).blocks[0]
    content = block.content_candidates[0]
    assert (content.raw, content.unit_context_raw) == ("10", "%")


def test_p5_fix_02_ocr_header_and_cas_without_content_stays_unknown_not_explicit_blank(pdf_tmp):
    path = _image_pdf(pdf_tmp, "p5-ocr-missing-content.pdf")
    result = scan_pdf_sections(path, engine=FakeOcr([_page(
        (S3, (50, 70, 400, 90)), ("CAS", (50, 100, 80, 120)), ("Content (%)", (300, 100, 390, 120)),
        ("64-17-5", (50, 140, 110, 160)), ("10", (300, 140, 320, 160)), (S4, (50, 180, 240, 200)),
    )]), sections=("3",))
    section_input = replace(result.input_for("3"), tokens=tuple(
        token for token in result.input_for("3").tokens
        if not (token.bbox[0] >= 300 and token.bbox[1] >= 140)
    ))
    block = collect_section3_candidates(section_input).blocks[0]
    assert (block.content_field_state.value, block.content_candidates) == ("UNKNOWN", ())


def test_p5_fix_06_ocr_header_ppm_propagates_typed_context(pdf_tmp):
    block = _s3_collected(pdf_tmp, (
        ("CAS", (50, 100, 80, 120)), ("Content ppm", (300, 100, 390, 120)),
        ("64-17-5", (50, 140, 110, 160)), ("500", (300, 140, 330, 160)),
    )).blocks[0]
    assert (block.content_candidates[0].raw, block.content_candidates[0].unit_context_raw) == ("500", "ppm")


def test_p5_fix_13_phase4_confirmed_ocr_input_propagates_fence_status(pdf_tmp):
    result = _scan_s1(pdf_tmp, _page((S1, (50, 70, 400, 90)), ("Product: OCR Resin", (50, 110, 240, 130)), (S2, (50, 170, 260, 190))))
    assert result.input_for("1").fence_status is FenceStatus.FENCE_CONFIRMED


def test_p4_19_ocr_duplicate_cas_occurrences_are_retained(pdf_tmp):
    result = _s3_collected(pdf_tmp, (("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), ("64-17-5", (50, 150, 110, 170)), ("20%", (300, 150, 330, 170))))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5", "64-17-5"]


def test_p4_20_ocr_invalid_cas_check_digit_is_not_corrected(pdf_tmp):
    candidate = _s3_collected(pdf_tmp, (("64-17-4", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)))).blocks[0].cas_candidates[0]
    assert (candidate.raw, candidate.validity) == ("64-17-4", CasCandidateValidity.CHECK_DIGIT_INVALID)


def test_p4_21_ocr_ec_or_date_never_upgrades_to_cas(pdf_tmp):
    result = _s3_collected(pdf_tmp, (("Date: 2024-01-1", (50, 100, 180, 120)), ("EC No.", (50, 130, 100, 150)), ("205-399-7", (50, 160, 120, 180)), ("64-17-5", (50, 190, 110, 210)), ("10%", (300, 190, 330, 210))))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]
