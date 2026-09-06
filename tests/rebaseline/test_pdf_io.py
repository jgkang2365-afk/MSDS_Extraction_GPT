from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import fitz
import pytest

from src.msds.models import DocumentCapability, FenceStatus, PageRegion
from src.msds.pdf_io import FenceDescription, build_section_input, read_pdf_layout
from src.msds.sections import locate_section
from tests.rebaseline.pdf_helpers import make_pdf


def test_p2_01_reads_real_digital_pdf_once_with_zero_render_calls(pdf_tmp):
    path = make_pdf(pdf_tmp / "digital.pdf", [[(72, 72, "1. Chemical product and company identification"), (72, 100, "INSIDE")]])
    result = read_pdf_layout(path)
    assert result.document_sha256 == sha256(path.read_bytes()).hexdigest()
    assert result.capability is DocumentCapability.TEXT
    assert dict(result.metrics)["pages_read"] == 1
    assert dict(result.metrics)["render_calls"] == 0
    assert dict(result.metrics)["external_calls"] == 0
    assert result.pages[0].tokens and result.pages[0].tokens[0].page_index == 0


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_p2_07_preserves_unrotated_source_coordinate_contract(pdf_tmp, rotation):
    path = make_pdf(pdf_tmp / f"rotated-{rotation}.pdf", [[(72, 72, "1. Chemical product and company identification")]], rotations=[rotation])
    result = read_pdf_layout(path)
    assert result.pages[0].page_index == 0
    assert result.pages[0].rotation == rotation
    assert result.pages[0].rect == (0.0, 0.0, 595.0, 842.0)
    assert result.pages[0].tokens[0].bbox[1] >= 0


def test_p2_07_cropbox_origin_uses_unrotated_zero_based_coordinate_space(pdf_tmp):
    path = make_pdf(
        pdf_tmp / "cropbox.pdf",
        [[(100, 100, "1. Chemical product and company identification"), (100, 130, "INSIDE"), (100, 160, "2. Hazards identification")]],
        cropboxes=[(50, 60, 500, 700)],
    )
    layout = read_pdf_layout(path)
    assert layout.pages[0].rect == (0.0, 0.0, 450.0, 640.0)
    token = next(token for token in layout.pages[0].tokens if token.text == "I")
    assert token.bbox[0] == pytest.approx(50.0)


def test_p2_09_actual_bbox_filtering_excludes_outside_sentinel(pdf_tmp):
    path = make_pdf(pdf_tmp / "filter.pdf", [[
        (72, 72, "1. Chemical product and company identification"), (72, 120, "INSIDE"),
        (72, 200, "2. Hazards identification"), (72, 230, "OUTSIDE_TWO"),
    ]])
    layout = read_pdf_layout(path)
    fence = locate_section(layout, "1").description
    assert fence is not None
    section_input = build_section_input(layout, fence)
    text = "".join(token.text for token in section_input.tokens)
    assert text == "INSIDE"
    assert "OUTSIDE" not in text


@pytest.mark.parametrize(
    "fence",
    [
        lambda layout: FenceDescription(FenceStatus.FENCE_PARTIAL, "1", "f", layout.document_sha256, (PageRegion(0, ((0, 1, 10, 10),)),)),
        lambda layout: FenceDescription(FenceStatus.FENCE_CONFIRMED, "1", "f", "bad", (PageRegion(0, ((0, 1, 10, 10),)),)),
        lambda layout: FenceDescription(FenceStatus.FENCE_CONFIRMED, "1", "f", layout.document_sha256, (PageRegion(99, ((0, 1, 10, 10),)),)),
    ],
)
def test_p2_11_rejects_partial_hash_mismatch_and_invalid_page(pdf_tmp, fence):
    layout = read_pdf_layout(make_pdf(pdf_tmp / "reject.pdf", [[(72, 72, "text")]]))
    with pytest.raises(ValueError):
        build_section_input(layout, fence(layout))


def test_p2_11_rejects_correct_sha_wrong_section_page_or_rectangle(pdf_tmp):
    layout = read_pdf_layout(make_pdf(pdf_tmp / "locator-owned.pdf", [[
        (72, 72, "1. Chemical product and company identification"), (72, 110, "INSIDE"),
        (72, 150, "2. Hazards identification"),
    ]]))
    valid = locate_section(layout, "1").description
    assert valid is not None
    assert build_section_input(layout, valid).tokens
    invalid = (
        replace(valid, section_no="3"),
        replace(valid, fence_id="other"),
        replace(valid, regions=(PageRegion(0, ((0, 100, 595, 120),)),)),
    )
    for candidate in invalid:
        with pytest.raises(ValueError, match="FENCE_DOES_NOT_MATCH_LOCATOR"):
            build_section_input(layout, candidate)


@pytest.mark.parametrize("capability", [DocumentCapability.UNKNOWN, DocumentCapability.IMAGE_ONLY, DocumentCapability.OCR])
def test_p2_11_builder_never_accepts_a_non_text_confirmed_fence(pdf_tmp, capability):
    layout = read_pdf_layout(make_pdf(pdf_tmp / f"non-text-{capability.value}.pdf", [[
        (72, 72, "1. Chemical product and company identification"), (72, 110, "INSIDE"),
        (72, 150, "2. Hazards identification"),
    ]]))
    valid = locate_section(layout, "1").description
    assert valid is not None
    with pytest.raises(ValueError, match="REQUIRES_TEXT_CAPABILITY"):
        build_section_input(layout, replace(valid, capability=capability))


def test_p2_12_read_errors_and_cancellation_are_explicit_and_next_input_is_independent(pdf_tmp):
    broken = pdf_tmp / "broken.pdf"
    broken.write_bytes(b"not-a-pdf")
    broken_result = read_pdf_layout(broken)
    assert broken_result.terminal_reason == "PDF_READ_ERROR"
    cancelled = read_pdf_layout(make_pdf(pdf_tmp / "cancel.pdf", [[(72, 72, "text")]]), cancelled=lambda: True)
    assert cancelled.terminal_reason == "CANCELLED"
    deadline = read_pdf_layout(make_pdf(pdf_tmp / "deadline.pdf", [[(72, 72, "text")]]), deadline=0)
    assert deadline.terminal_reason == "DEADLINE_EXCEEDED"
    good = read_pdf_layout(make_pdf(pdf_tmp / "next.pdf", [[(72, 72, "text")]]))
    assert good.terminal_reason is None


def test_p2_12_password_required_pdf_is_not_treated_as_empty_input(pdf_tmp):
    path = pdf_tmp / "encrypted.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "private")
    document.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    document.close()
    result = read_pdf_layout(path)
    assert result.terminal_reason == "PASSWORD_REQUIRED"
    assert result.capability is DocumentCapability.UNKNOWN


def test_p2_12_terminal_layout_never_confirms_or_builds_even_after_a_complete_first_section(pdf_tmp):
    path = make_pdf(pdf_tmp / "terminal-after-section-one.pdf", [
        [(72, 72, "1. Chemical product and company identification"), (72, 110, "COMPLETE_FIRST_SECTION"), (72, 150, "2. Hazards identification")],
        [(72, 72, "3. Composition/information on ingredients")],
    ])
    calls = 0
    def cancelled():
        nonlocal calls
        calls += 1
        return calls > 1
    interrupted = read_pdf_layout(path, cancelled=cancelled)
    assert interrupted.terminal_reason == "CANCELLED" and len(interrupted.pages) == 1
    located = locate_section(interrupted, "1")
    assert located.fence.status is FenceStatus.FENCE_PARTIAL
    assert located.description is None and located.reasons == ("CANCELLED",)
    complete = read_pdf_layout(make_pdf(pdf_tmp / "complete-first-section.pdf", [
        [(72, 72, "1. Chemical product and company identification"), (72, 110, "COMPLETE_FIRST_SECTION"), (72, 150, "2. Hazards identification")],
    ]))
    fence = locate_section(complete, "1").description
    assert fence is not None
    with pytest.raises(ValueError, match="SECTION_INPUT_TERMINAL_LAYOUT"):
        build_section_input(replace(complete, terminal_reason="CANCELLED"), fence)
