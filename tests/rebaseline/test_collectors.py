from __future__ import annotations

from dataclasses import replace

import pytest

import src.msds.collectors as collectors
from src.msds.collectors import collect_product_candidates, collect_section3_candidates
from src.msds.models import CasCandidateValidity, DocumentCapability, FenceStatus, LayoutToken, PageRegion, SectionInput
from src.msds.pdf_io import FenceDescription, build_section_input, read_pdf_layout
from src.msds.sections import locate_section
from tests.rebaseline.pdf_helpers import make_pdf


def _input(section: str, rows: tuple[tuple[str, ...], ...]) -> SectionInput:
    tokens: list[LayoutToken] = []
    serial = 0
    for row_number, cells in enumerate(rows):
        for cell_number, text in enumerate(cells):
            for character_number, character in enumerate(text):
                x = 72.0 + cell_number * 180.0 + character_number
                tokens.append(LayoutToken(f"t-{serial}", character, 0, (x, 100.0 + row_number * 20, x + 1, 110.0 + row_number * 20), cell_number, row_number))
                serial += 1
    return SectionInput("a" * 64, section, "confirmed-by-phase-2", (PageRegion(0, ((0, 0, 600, 800),)),), tuple(tokens), DocumentCapability.TEXT, input_digest="synthetic")


def test_product_label_pipe_and_multiline_raw_preserve_source_order_and_formatting():
    product = collect_product_candidates(_input("1", (("Product name | ABC-100",),)))
    assert product.candidates[0].raw == "ABC-100"
    multiline = _input("1", (("Product:",), ("  Resin (Model-X) Grade A 75%  ",), ("  Lot-B  ",), ("Company: Example",)))
    candidate = collect_product_candidates(multiline).candidates[0]
    assert candidate.raw == "  Resin (Model-X) Grade A 75%  \n  Lot-B  "
    assert candidate.normalized == "resin (model-x) grade a 75% lot-b"
    assert [item.raw_fragment for item in candidate.evidence] == ["  Resin (Model-X) Grade A 75%  ", "  Lot-B  "]


def test_product_absence_has_no_filename_or_other_section_fallback():
    empty = _input("1", (("Company: not a product",),))
    changed_elsewhere = _input("1", (("Company: a filename-like ABC-100.pdf",),))
    assert collect_product_candidates(empty).candidates == ()
    assert collect_product_candidates(changed_elsewhere).candidates == ()


def test_section3_two_and_three_column_rows_keep_only_cas_and_content_candidates():
    two = collect_section3_candidates(_input("3", (("64-17-5", "< 1 wt %"),)))
    three = collect_section3_candidates(_input("3", (("67-64-1", "Acetone ingredient name", "10 vol%"),)))
    assert two.blocks[0].cas_candidates[0].raw == "64-17-5"
    assert two.blocks[0].content_candidates[0].raw == "< 1 wt %"
    assert three.blocks[0].content_candidates[0].raw == "10 vol%"
    assert "Acetone ingredient name" not in repr(three.blocks[0].cas_candidates + three.blocks[0].content_candidates)


def test_section3_duplicate_cas_missing_content_and_content_only_rows_are_preserved_or_excluded():
    result = collect_section3_candidates(_input("3", (
        ("64-17-5", "50%"),
        ("64-17-5", ""),
        ("Balance",),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5", "64-17-5"]
    assert [block.source_order for block in result.blocks] == [0, 1]
    assert result.blocks[1].content_candidates == ()


def test_section3_multiple_cas_share_source_block_without_final_pairing():
    result = collect_section3_candidates(_input("3", (("64-17-5 67-64-1", "10~20%"),)))
    block = result.blocks[0]
    assert [cas.raw for cas in block.cas_candidates] == ["64-17-5", "67-64-1"]
    assert [content.raw for content in block.content_candidates] == ["10~20%"]
    assert not hasattr(block, "components") and not hasattr(block, "pair_status")


def test_section3_range_weight_and_volume_percentages_preserve_full_raw_candidates():
    result = collect_section3_candidates(_input("3", (
        ("111-11-1", "10-20 wt%"),
        ("222-22-2", "10-20 vol%"),
    )))
    assert [block.content_candidates[0].raw for block in result.blocks] == ["10-20 wt%", "10-20 vol%"]


def test_section3_invalid_cas_date_ec_and_content_semantics_are_not_repaired_or_promoted():
    result = collect_section3_candidates(_input("3", (
        ("64-17-4", "< 1%"),
        ("Date: 2024-01-1", "> 2%"),
        ("EC No.", "205-399-7", "≤ 3%"),
        ("111-11-1", "≥4%"),
        ("222-22-2", "10-20%"),
        ("333-33-3", "Rem."),
        ("444-44-4", "Balance"),
        ("555-55-5", "5 wt%"),
        ("666-66-6", "6 vol%"),
    )))
    first = result.blocks[0].cas_candidates[0]
    assert (first.raw, first.normalized, first.validity) == ("64-17-4", "64-17-4", CasCandidateValidity.CHECK_DIGIT_INVALID)
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-4", "111-11-1", "222-22-2", "333-33-3", "444-44-4", "555-55-5", "666-66-6"]
    assert [block.content_candidates[0].raw for block in result.blocks] == ["< 1%", "≥4%", "10-20%", "Rem.", "Balance", "5 wt%", "6 vol%"]


def test_collectors_are_isolated_to_their_confirmed_section_inputs():
    product_one = _input("1", (("Product: Stable-1",),))
    product_changed = _input("1", (("Product: Stable-1",),))
    section_three = _input("3", (("64-17-5", "10%"),))
    section_three_changed = _input("3", (("64-17-5", "20%"),))
    assert collect_product_candidates(product_one) == collect_product_candidates(product_changed)
    assert collect_section3_candidates(section_three).blocks[0].content_candidates[0].raw == "10%"
    assert collect_section3_candidates(section_three_changed).blocks[0].content_candidates[0].raw == "20%"


@pytest.mark.parametrize(
    ("section", "status", "entries"),
    [
        ("1", FenceStatus.FENCE_PARTIAL, [(72, 72, "1. Chemical product and company identification"), (72, 110, "unclosed section")]),
        ("3", FenceStatus.FENCE_PARTIAL, [(72, 72, "3. Composition/information on ingredients"), (72, 110, "unclosed section")]),
        ("1", FenceStatus.FENCE_NOT_FOUND, [(72, 72, "ordinary body without section heading")]),
        ("3", FenceStatus.FENCE_NOT_FOUND, [(72, 72, "ordinary body without section heading")]),
    ],
)
def test_partial_and_not_found_fences_cannot_build_input_or_call_collectors(pdf_tmp, monkeypatch, section, status, entries):
    path = make_pdf(pdf_tmp / f"{section}-{status.value}.pdf", [entries])
    layout = read_pdf_layout(path)
    located = locate_section(layout, section)
    assert located.fence.status is status
    called = False
    def forbidden(_input):
        nonlocal called
        called = True
        raise AssertionError("collector must not run")
    collector_name = "collect_product_candidates" if section == "1" else "collect_section3_candidates"
    monkeypatch.setattr(collectors, collector_name, forbidden)
    blocked_fence = FenceDescription(status, section, "blocked", layout.document_sha256, ())
    with pytest.raises(ValueError, match="REQUIRES_CONFIRMED_FENCE"):
        build_section_input(layout, blocked_fence)
    if located.description is not None:
        getattr(collectors, collector_name)(located.description)  # pragma: no cover - only documents the required route
    assert not called


def test_public_collectors_reject_wrong_section_non_text_and_non_input():
    section_one = _input("1", (("Product: ABC",),))
    with pytest.raises(ValueError, match="SECTION_3"):
        collect_section3_candidates(section_one)
    with pytest.raises(ValueError, match="TEXT"):
        collect_product_candidates(replace(section_one, capability=DocumentCapability.OCR))
    with pytest.raises(TypeError, match="SECTION_INPUT"):
        collect_product_candidates("not an input")  # type: ignore[arg-type]
