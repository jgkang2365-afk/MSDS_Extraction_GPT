from __future__ import annotations

from pathlib import Path

import pytest

from src.msds.models import FenceStatus
from src.msds.pdf_io import build_section_input, read_pdf_layout
from src.msds.sections import locate_sections
from tests.rebaseline.pdf_helpers import make_pdf


def _inputs(path):
    layout = read_pdf_layout(path)
    section1, section3 = locate_sections(layout)
    return section1, section3, build_section_input(layout, section1.description) if section1.description else None, build_section_input(layout, section3.description) if section3.description else None


def test_p2_01_and_p2_02_same_page_korean_and_english_fences_keep_only_internal_tokens(pdf_tmp):
    path = make_pdf(pdf_tmp / "basic.pdf", [[
        (72, 72, "1. Chemical product and company identification"), (72, 100, "SECTION1_FIRST"), (72, 130, "SECTION1_LAST"),
        (72, 160, "2. Hazards identification"), (72, 190, "OUTSIDE_2"),
        (72, 220, "3. Composition/information on ingredients"), (72, 250, "SECTION3_FIRST"), (72, 280, "SECTION3_LAST"),
        (72, 310, "4. First-aid measures"), (72, 340, "OUTSIDE_4"),
    ]])
    one, three, input1, input3 = _inputs(path)
    assert one.fence.status is FenceStatus.FENCE_CONFIRMED
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    text1 = "".join(token.text for token in input1.tokens)
    text3 = "".join(token.text for token in input3.tokens)
    assert "SECTION1_FIRST" in text1 and "OUTSIDE_2" not in text1
    assert "SECTION3_LAST" in text3 and "OUTSIDE_4" not in text3


def test_p2_01_korean_digital_headings_are_located_with_real_pdf_text(pdf_tmp):
    fontfile = Path(r"C:\Windows\Fonts\malgun.ttf")
    assert fontfile.is_file(), "Windows test environment must provide Malgun Gothic"
    path = make_pdf(pdf_tmp / "korean.pdf", [[
        (72, 72, "1. 화학제품과 회사에 관한 정보"), (72, 100, "INSIDE_ONE"),
        (72, 130, "2. 유해성·위험성"),
        (72, 160, "3. 구성성분의 명칭 및 함유량"), (72, 190, "INSIDE_THREE"),
        (72, 220, "4. 응급조치 요령"),
    ]], fontfile=fontfile)
    one, three, input1, input3 = _inputs(path)
    assert one.fence.status is FenceStatus.FENCE_CONFIRMED
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert "INSIDE_ONE" in "".join(token.text for token in input1.tokens)
    assert "INSIDE_THREE" in "".join(token.text for token in input3.tokens)


def test_p2_03_section_three_has_no_page_count_cutoff(pdf_tmp):
    pages = [[(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST_3")]]
    pages += [[(72, 100, f"CONTINUED_{number}")] for number in range(1, 5)]
    pages += [[(72, 100, "LAST_3"), (72, 150, "4. First-aid measures")]]
    _, three, _, input3 = _inputs(make_pdf(pdf_tmp / "long.pdf", pages))
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert "LAST_3" in "".join(token.text for token in input3.tokens)


def test_p2_04_toc_footer_references_subsections_and_cas_numbers_are_not_headers(pdf_tmp):
    path = make_pdf(pdf_tmp / "noise.pdf", [[
        (72, 72, "1. Chemical product and company identification"), (72, 90, "2. Hazards identification"), (72, 108, "3. Composition/information on ingredients"), (72, 126, "4. First-aid measures"),
        (72, 200, "1. Chemical product and company identification"), (72, 230, "ONE"), (72, 260, "2. Hazards identification"),
        (72, 290, "3. Composition/information on ingredients"), (72, 320, "3.1 Subsection"), (72, 350, "see section 3 reference"), (72, 380, "64-17-5"), (72, 410, "THREE"), (72, 440, "4. First-aid measures"),
    ]])
    one, three, input1, input3 = _inputs(path)
    assert one.fence.status is FenceStatus.FENCE_CONFIRMED
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert "ONE" in "".join(token.text for token in input1.tokens)
    assert "THREE" in "".join(token.text for token in input3.tokens)


def test_p2_05_missing_exit_and_multi_column_boundary_block_section_input(pdf_tmp):
    missing = make_pdf(pdf_tmp / "missing.pdf", [[(72, 72, "3. Composition/information on ingredients"), (72, 100, "NO_EXIT")]])
    _, three = locate_sections(read_pdf_layout(missing))
    assert three.fence.status is FenceStatus.FENCE_PARTIAL
    assert three.description is None and "SECTION_END_NOT_FOUND" in three.reasons
    columns = make_pdf(pdf_tmp / "columns.pdf", [[(72, 72, "3. Composition/information on ingredients"), (360, 110, "RIGHT_COLUMN"), (72, 160, "4. First-aid measures")]])
    _, ambiguous = locate_sections(read_pdf_layout(columns))
    assert ambiguous.fence.status is FenceStatus.FENCE_PARTIAL
    assert "MULTI_COLUMN_BOUNDARY_AMBIGUOUS" in ambiguous.reasons


def test_p2_06_section_one_stays_confirmed_when_section_three_is_missing(pdf_tmp):
    path = make_pdf(pdf_tmp / "independent.pdf", [[(72, 72, "1. Chemical product and company identification"), (72, 100, "GOOD_ONE"), (72, 130, "2. Hazards identification"), (72, 180, "3. Composition/information on ingredients")]])
    one, three, input1, input3 = _inputs(path)
    assert one.fence.status is FenceStatus.FENCE_CONFIRMED and input1 is not None
    assert three.fence.status is FenceStatus.FENCE_PARTIAL and input3 is None


def test_p2_06_image_section_is_partial_without_loading_ocr_and_keeps_section_one(pdf_tmp):
    path = make_pdf(pdf_tmp / "mixed.pdf", [
        [(72, 72, "1. Chemical product and company identification"), (72, 100, "GOOD_ONE"), (72, 130, "2. Hazards identification")],
        [(72, 72, "3. Composition/information on ingredients")],
        [],
        [(72, 72, "4. First-aid measures")],
    ], images={2})
    one, three, input1, input3 = _inputs(path)
    assert one.fence.status is FenceStatus.FENCE_CONFIRMED and input1 is not None
    assert three.fence.status is FenceStatus.FENCE_PARTIAL and input3 is None
    assert "SECTION_IMAGE_READING_REQUIRED" in three.reasons


def test_p2_08_boundary_crossing_text_is_filtered_at_character_token_granularity(pdf_tmp):
    path = make_pdf(pdf_tmp / "boundary.pdf", [[(72, 72, "1. Chemical product and company identification"), (72, 100, "INSIDE"), (72, 130, "2. Hazards identification")]])
    one, _, input1, _ = _inputs(path)
    assert one.fence.status is FenceStatus.FENCE_CONFIRMED
    assert "INSIDE" in "".join(token.text for token in input1.tokens)


def test_p2_10_filename_and_other_section_content_do_not_change_fence_tokens(pdf_tmp):
    pages = [[(72, 72, "1. Chemical product and company identification"), (72, 100, "STABLE"), (72, 130, "2. Hazards identification"), (72, 160, "CHANGED_OUTSIDE")]]
    first = _inputs(make_pdf(pdf_tmp / "first.pdf", pages))[2]
    pages[0][-1] = (72, 160, "OTHER_CHANGED_OUTSIDE")
    second = _inputs(make_pdf(pdf_tmp / "renamed.pdf", pages))[2]
    assert "".join(token.text for token in first.tokens) == "".join(token.text for token in second.tokens)
    assert first.document_sha256 != second.document_sha256


def test_p2_05_repeated_section_start_before_exit_is_ambiguous(pdf_tmp):
    path = make_pdf(pdf_tmp / "repeated.pdf", [[
        (72, 72, "3. Composition/information on ingredients"), (72, 100, "FIRST"),
        (72, 150, "3. Composition/information on ingredients"), (72, 190, "4. First-aid measures"),
    ]])
    _, three = locate_sections(read_pdf_layout(path))
    assert three.fence.status is FenceStatus.FENCE_PARTIAL
    assert "SECTION_START_AMBIGUOUS" in three.reasons
