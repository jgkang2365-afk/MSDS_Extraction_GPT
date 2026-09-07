"""Phase 4 local Scan/OCR foundation contracts (all OCR is deterministic fake data)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.msds.collectors import collect_product_candidates, collect_section3_candidates
from src.msds.models import CasCandidateValidity, DocumentCapability, EvidenceSourceType
from src.msds.ocr import LazyPaddleOcrEngine, OcrMetrics, OcrToken, _pixel_to_pdf, scan_pdf_sections
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


def test_p4_19_ocr_duplicate_cas_occurrences_are_retained(pdf_tmp):
    result = _s3_collected(pdf_tmp, (("64-17-5", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)), ("64-17-5", (50, 150, 110, 170)), ("20%", (300, 150, 330, 170))))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5", "64-17-5"]


def test_p4_20_ocr_invalid_cas_check_digit_is_not_corrected(pdf_tmp):
    candidate = _s3_collected(pdf_tmp, (("64-17-4", (50, 110, 110, 130)), ("10%", (300, 110, 330, 130)))).blocks[0].cas_candidates[0]
    assert (candidate.raw, candidate.validity) == ("64-17-4", CasCandidateValidity.CHECK_DIGIT_INVALID)


def test_p4_21_ocr_ec_or_date_never_upgrades_to_cas(pdf_tmp):
    result = _s3_collected(pdf_tmp, (("Date: 2024-01-1", (50, 100, 180, 120)), ("EC No.", (50, 130, 100, 150)), ("205-399-7", (50, 160, 120, 180)), ("64-17-5", (50, 190, 110, 210)), ("10%", (300, 190, 330, 210))))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]
