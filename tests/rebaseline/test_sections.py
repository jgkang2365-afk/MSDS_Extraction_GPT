from __future__ import annotations

from dataclasses import replace
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


@pytest.mark.parametrize("heading", ["SECTION 1 IDENTIFICATION", "1 IDENTIFICATION", "１．　ＩＤＥＮＴＩＦＩＣＡＴＩＯＮ"])
def test_p2_01_heading_search_keys_accept_section_prefix_optional_separator_and_nfkc(pdf_tmp, heading):
    fontfile = Path(r"C:\Windows\Fonts\malgun.ttf")
    path = make_pdf(pdf_tmp / f"heading-{ord(heading[0])}.pdf", [[
        (72, 72, heading), (72, 100, "ＦＵＬＬ　ＷＩＤＴＨ　ＶＡＬＵＥ　１２３％"),
        (72, 130, "2 Hazards identification"),
        (72, 160, "3 Composition/information on ingredients"), (72, 190, "INSIDE_THREE"),
        (72, 220, "4 First-aid measures"),
    ]], fontfile=fontfile)
    one, three, input1, input3 = _inputs(path)
    assert one.fence.status is FenceStatus.FENCE_CONFIRMED
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert "ＦＵＬＬ　ＷＩＤＴＨ　ＶＡＬＵＥ　１２３％" in "".join(token.text for token in input1.tokens)
    assert "INSIDE_THREE" in "".join(token.text for token in input3.tokens)


def test_p2_03_section_three_has_no_page_count_cutoff(pdf_tmp):
    pages = [[(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST_3")]]
    pages += [[(72, 100, f"CONTINUED_{number}")] for number in range(1, 5)]
    pages += [[(72, 100, "LAST_3"), (72, 150, "4. First-aid measures")]]
    _, three, _, input3 = _inputs(make_pdf(pdf_tmp / "long.pdf", pages))
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert "LAST_3" in "".join(token.text for token in input3.tokens)


def test_p2_03_middle_pages_are_fenced_body_regions_with_repeated_margins_excluded(pdf_tmp):
    pages = [[(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST")]]
    pages += [[(72, 20, "REPEATED HEADER"), (72, 100, f"BODY_{number}"), (72, 810, "REPEATED FOOTER")] for number in range(1, 3)]
    pages += [[(72, 100, "LAST"), (72, 150, "4. First-aid measures")]]
    _, three, _, input3 = _inputs(make_pdf(pdf_tmp / "middle-margins.pdf", pages))
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert three.description is not None
    middle = three.description.regions[1]
    assert middle.allowed_rects != (read_pdf_layout(pdf_tmp / "middle-margins.pdf").pages[1].rect,)
    assert middle.excluded_rects
    text = "".join(token.text for token in input3.tokens)
    assert "BODY_1" in text and "REPEATED" not in text


def test_p2_03_section_three_repeated_margin_table_headers_remain_in_section_input(pdf_tmp):
    path = make_pdf(pdf_tmp / "repeated-section-three-table-header.pdf", [
        [(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST_BODY")],
        [(72, 20, "CAS No."), (220, 20, "Concentration"), (72, 100, "111-11-1"), (220, 100, "5%")],
        [(72, 20, "CAS No."), (220, 20, "Concentration"), (72, 100, "222-22-2"), (220, 100, "10%"), (72, 180, "4. First-aid measures")],
    ])
    _, three, _, input3 = _inputs(path)
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    header_tokens = "".join(
        token.text
        for token in input3.tokens
        if token.page_index in {1, 2} and token.bbox[1] < 50
    )
    assert header_tokens == "CAS No.ConcentrationCAS No.Concentration"


@pytest.mark.parametrize(
    "headers",
    [
        ("CAS 번호", "성분명", "함유량"),
        ("등록번호", "물질 이름", "농도"),
    ],
)
def test_p2_03_structural_repeated_table_headers_preserve_korean_and_alternate_labels(pdf_tmp, headers):
    path = make_pdf(pdf_tmp / "structural-repeated-table-header.pdf", [
        [(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST_BODY")],
        [(72, 20, headers[0]), (220, 20, headers[1]), (430, 20, headers[2]), (72, 100, "111-11-1"), (220, 100, "Ingredient A"), (430, 100, "5%"), (72, 130, "333-33-3"), (220, 130, "Ingredient C"), (430, 130, "15%")],
        [(72, 20, headers[0]), (220, 20, headers[1]), (430, 20, headers[2]), (72, 100, "222-22-2"), (220, 100, "Ingredient B"), (430, 100, "10%"), (72, 130, "444-44-4"), (220, 130, "Ingredient D"), (430, 130, "20%"), (72, 180, "4. First-aid measures")],
    ], fontfile=Path(r"C:\Windows\Fonts\malgun.ttf"))
    _, three, _, input3 = _inputs(path)
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    retained = "".join(token.text for token in input3.tokens if token.page_index in {1, 2} and token.bbox[1] < 50)
    assert retained == "".join(headers) * 2


def test_p2_03_repeated_margin_text_without_table_structure_is_excluded(pdf_tmp):
    path = make_pdf(pdf_tmp / "ordinary-repeated-margin.pdf", [
        [(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST_BODY")],
        [(72, 20, "ORDINARY MARGIN"), (72, 100, "111-11-1")],
        [(72, 20, "ORDINARY MARGIN"), (72, 100, "222-22-2"), (72, 180, "4. First-aid measures")],
    ])
    _, three, _, input3 = _inputs(path)
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert "ORDINARY MARGIN" not in "".join(token.text for token in input3.tokens)


def test_p2_03_repeated_two_cell_running_headers_without_aligned_body_are_excluded(pdf_tmp):
    path = make_pdf(pdf_tmp / "running-header.pdf", [
        [(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST_BODY")],
        [(72, 20, "Example Chemical Company"), (440, 20, "Page"), (72, 100, "111-11-1 5%")],
        [(72, 20, "Example Chemical Company"), (440, 20, "Page"), (72, 100, "222-22-2 10%"), (72, 180, "4. First-aid measures")],
    ])
    _, three, _, input3 = _inputs(path)
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    text = "".join(token.text for token in input3.tokens)
    assert "Example Chemical Company" not in text and "Page" not in text


def test_p2_02_section_input_preserves_multiline_product_source_order_and_whitespace(pdf_tmp):
    raw_product_lines = ("  Product (Technical ", "Grade)  75 %  ")
    path = make_pdf(pdf_tmp / "product-whitespace.pdf", [[
        (72, 72, "1. Chemical product and company identification"), (72, 110, raw_product_lines[0]), (72, 130, raw_product_lines[1]),
        (72, 170, "2. Hazards identification"),
    ]])
    one, _, input1, _ = _inputs(path)
    assert one.fence.status is FenceStatus.FENCE_CONFIRMED
    lines: list[tuple[tuple[int, int], str]] = []
    for token in input1.tokens:
        line_key = (token.block_id, token.line_id)
        if not lines or lines[-1][0] != line_key:
            lines.append((line_key, token.text))
        else:
            lines[-1] = (line_key, lines[-1][1] + token.text)
    product_lines = [line for line in lines if line[1] in raw_product_lines]
    assert [line_key for line_key, _ in product_lines] == sorted(line_key for line_key, _ in product_lines)
    assert [text for _, text in product_lines] == list(raw_product_lines)


def test_p2_03_wide_three_column_section_table_is_not_page_multicolumn(pdf_tmp):
    rows = [
        (72, 110, "111-11-1"), (220, 110, "Ingredient A"), (440, 110, "5%"),
        (72, 140, "222-22-2"), (220, 140, "Ingredient B"), (440, 140, "10%"),
    ]
    same_page = make_pdf(pdf_tmp / "wide-table-same-page.pdf", [[
        (72, 72, "3. Composition/information on ingredients"), *rows, (72, 180, "4. First-aid measures"),
    ]])
    _, same_page_three, _, same_page_input = _inputs(same_page)
    assert same_page_three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert "Ingredient B" in "".join(token.text for token in same_page_input.tokens)
    continuation = make_pdf(pdf_tmp / "wide-table-continuation.pdf", [
        [(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST")],
        rows,
        [(72, 110, "LAST"), (72, 180, "4. First-aid measures")],
    ])
    _, continuation_three, _, continuation_input = _inputs(continuation)
    assert continuation_three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert "Ingredient B" in "".join(token.text for token in continuation_input.tokens)


def test_p2_03_multi_page_start_and_end_use_observed_body_and_exclude_repeated_sentinels(pdf_tmp):
    path = make_pdf(pdf_tmp / "boundary-margins.pdf", [
        [(72, 20, "REPEATED HEADER"), (72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST_BODY"), (72, 810, "REPEATED FOOTER")],
        [(72, 20, "REPEATED HEADER"), (72, 100, "MIDDLE_BODY"), (72, 810, "REPEATED FOOTER")],
        [(72, 20, "REPEATED HEADER"), (72, 110, "LAST_BODY"), (72, 150, "4. First-aid measures"), (72, 810, "REPEATED FOOTER")],
    ])
    layout = read_pdf_layout(path)
    _, three = locate_sections(layout)
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert three.description is not None
    first, _, last = three.description.regions
    assert first.allowed_rects[0][1] > layout.pages[0].lines[1].bbox[3]
    assert last.allowed_rects[0][3] < layout.pages[2].lines[-2].bbox[1]
    text = "".join(token.text for token in build_section_input(layout, three.description).tokens)
    assert "FIRST_BODY" in text and "MIDDLE_BODY" in text and "LAST_BODY" in text
    assert "REPEATED" not in text


@pytest.mark.parametrize(
    ("page_entries", "reason"),
    [
        ([(72, 72, "3. Composition/information on ingredients"), (72, 110, "LEFT"), (360, 110, "RIGHT")], "START_PAGE_READING_ORDER_AMBIGUOUS"),
        ([(72, 110, "LEFT"), (360, 110, "RIGHT"), (72, 150, "4. First-aid measures")], "END_PAGE_READING_ORDER_AMBIGUOUS"),
    ],
)
def test_p2_03_multi_page_boundary_columns_are_rejected(pdf_tmp, page_entries, reason):
    pages = [
        [(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST")],
        [(72, 100, "MIDDLE")],
        [(72, 110, "LAST"), (72, 150, "4. First-aid measures")],
    ]
    if reason.startswith("START"):
        pages[0] = page_entries
    else:
        pages[2] = page_entries
    _, three = locate_sections(read_pdf_layout(make_pdf(pdf_tmp / f"boundary-columns-{reason}.pdf", pages)))
    assert three.fence.status is FenceStatus.FENCE_PARTIAL
    assert three.reasons == (reason,)


def test_p2_05_multi_column_continuation_page_blocks_section_input(pdf_tmp):
    path = make_pdf(pdf_tmp / "middle-columns.pdf", [
        [(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST")],
        [(72, 100, "LEFT"), (360, 100, "RIGHT")],
        [(72, 100, "LAST"), (72, 150, "4. First-aid measures")],
    ])
    _, three = locate_sections(read_pdf_layout(path))
    assert three.fence.status is FenceStatus.FENCE_PARTIAL
    assert "MIDDLE_PAGE_READING_ORDER_AMBIGUOUS" in three.reasons


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


@pytest.mark.parametrize("image_page", [0, 2])
def test_p2_06_header_only_boundary_image_is_not_omitted_from_capability(pdf_tmp, image_page):
    path = make_pdf(pdf_tmp / f"header-only-boundary-image-{image_page}.pdf", [
        [(72, 72, "3. Composition/information on ingredients")],
        [(72, 110, "DIGITAL MIDDLE BODY HAS SUFFICIENT SEPARATE TOKENS TO OTHERWISE ADMIT DECORATIVE LOGO")],
        [(72, 180, "4. First-aid measures")],
    ], images={image_page}, image_rects={image_page: (550, 100, 570, 120)})
    _, three = locate_sections(read_pdf_layout(path))
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert three.reasons == ("SECTION_DIGITAL_TEXT_WITH_DECORATIVE_LOGO",)


@pytest.mark.parametrize("image_page", [0, 2])
def test_p2_06_boundary_image_outside_observed_text_x_bounds_is_classified(pdf_tmp, image_page):
    path = make_pdf(pdf_tmp / f"boundary-outside-x-image-{image_page}.pdf", [
        [(72, 72, "3. Composition/information on ingredients"), (72, 110, "START BODY HAS SUFFICIENT SEPARATE TOKENS")],
        [(72, 110, "MIDDLE BODY HAS SUFFICIENT SEPARATE TOKENS")],
        [(72, 110, "END BODY HAS SUFFICIENT SEPARATE TOKENS"), (72, 180, "4. First-aid measures")],
    ], images={image_page}, image_rects={image_page: (300, 135, 420, 155)})
    _, three = locate_sections(read_pdf_layout(path))
    assert three.fence.status is FenceStatus.FENCE_PARTIAL
    assert three.reasons == ("SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED",)


def test_p2_03_middle_page_uses_observed_text_x_body_bounds(pdf_tmp):
    path = make_pdf(pdf_tmp / "middle-observed-x-bounds.pdf", [
        [(72, 72, "3. Composition/information on ingredients"), (72, 110, "FIRST")],
        [(144, 100, "MIDDLE_OBSERVED_BODY")],
        [(72, 110, "LAST"), (72, 180, "4. First-aid measures")],
    ])
    layout = read_pdf_layout(path)
    _, three = locate_sections(layout)
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert three.description is not None
    middle = three.description.regions[1]
    middle_line = layout.pages[1].lines[0]
    assert middle.allowed_rects == ((middle_line.bbox[0], middle_line.bbox[1], middle_line.bbox[2], middle_line.bbox[3]),)


def test_p2_06_same_region_text_and_image_is_blocked_but_title_only_image_is_classified(pdf_tmp):
    mixed = make_pdf(pdf_tmp / "same-region-mixed.pdf", [[
        (72, 72, "3. Composition/information on ingredients"), (72, 110, "DIGITAL_BODY"),
        (72, 180, "4. First-aid measures"),
    ]], images={0}, image_rects={0: (300, 95, 420, 135)})
    _, mixed_three = locate_sections(read_pdf_layout(mixed))
    assert mixed_three.fence.status is FenceStatus.FENCE_PARTIAL
    assert mixed_three.reasons == ("SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED",)
    image_only = make_pdf(pdf_tmp / "title-only-image.pdf", [[
        (72, 72, "3. Composition/information on ingredients"), (72, 180, "4. First-aid measures"),
    ]], images={0}, image_rects={0: (300, 95, 420, 135)})
    _, image_three = locate_sections(read_pdf_layout(image_only))
    assert image_three.fence.status is FenceStatus.FENCE_PARTIAL
    assert image_three.reasons == ("SECTION_IMAGE_READING_REQUIRED",)


def test_p2_06_small_right_margin_logo_with_normal_digital_body_is_confirmed(pdf_tmp):
    path = make_pdf(pdf_tmp / "decorative-logo.pdf", [[
        (72, 72, "3. Composition/information on ingredients"),
        (72, 110, "DIGITAL BODY HAS ENOUGH TEXT FOR SAFE TEXT FENCE"),
        (72, 180, "4. First-aid measures"),
    ]], images={0}, image_rects={0: (550, 135, 570, 155)})
    layout = read_pdf_layout(path)
    _, three = locate_sections(layout)
    assert three.fence.status is FenceStatus.FENCE_CONFIRMED
    assert three.description is not None
    assert three.reasons == ("SECTION_DIGITAL_TEXT_WITH_DECORATIVE_LOGO",)
    assert "DIGITAL" in "".join(token.text for token in build_section_input(layout, three.description).tokens)


@pytest.mark.parametrize("image_rect", [(300, 80, 330, 100), (500, 100, 590, 220), (72, 100, 92, 120)])
def test_p2_06_non_decorative_central_large_or_body_overlapping_image_stays_partial(pdf_tmp, image_rect):
    path = make_pdf(pdf_tmp / f"non-decorative-{image_rect[0]}.pdf", [[
        (72, 72, "3. Composition/information on ingredients"),
        (72, 110, "DIGITAL BODY HAS ENOUGH TEXT FOR SAFE TEXT FENCE"),
        (72, 180, "4. First-aid measures"),
    ]], images={0}, image_rects={0: image_rect})
    _, three = locate_sections(read_pdf_layout(path))
    assert three.fence.status is FenceStatus.FENCE_PARTIAL
    assert three.reasons == ("SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED",)


def test_p2_06_image_count_without_observable_placement_is_partial(pdf_tmp):
    path = make_pdf(pdf_tmp / "image-placement-unknown.pdf", [[
        (72, 72, "3. Composition/information on ingredients"), (72, 110, "DIGITAL_BODY"),
        (72, 180, "4. First-aid measures"),
    ]], images={0}, image_rects={0: (300, 95, 420, 135)})
    layout = read_pdf_layout(path)
    missing_placement = replace(layout, pages=(replace(layout.pages[0], image_rects=()),))
    _, three = locate_sections(missing_placement)
    assert three.fence.status is FenceStatus.FENCE_PARTIAL
    assert three.reasons == ("SECTION_IMAGE_PLACEMENT_UNKNOWN",)


def test_p2_08_boundary_crossing_text_blocks_input_without_silent_loss(pdf_tmp):
    path = make_pdf(pdf_tmp / "boundary.pdf", [[(72, 72, "1. Chemical product and company identification"), (72, 125, "CROSSING"), (72, 130, "2. Hazards identification")]])
    layout = read_pdf_layout(path)
    one, _ = locate_sections(layout)
    assert one.fence.status is FenceStatus.FENCE_CONFIRMED
    assert one.description is not None
    with pytest.raises(ValueError, match="BOUNDARY_CROSSING_TOKEN"):
        build_section_input(layout, one.description)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_p2_07_rotation_and_cropbox_keep_adjacent_sentinels_outside_the_input(pdf_tmp, rotation):
    path = make_pdf(pdf_tmp / f"crop-rotation-{rotation}.pdf", [[
        (100, 100, "1. Chemical product and company identification"), (100, 150, "INSIDE"),
        (100, 230, "2. Hazards identification"), (100, 260, "OUTSIDE"),
    ]], rotations=[rotation], cropboxes=[(50, 60, 500, 700)])
    one, _, input1, _ = _inputs(path)
    assert one.fence.status is FenceStatus.FENCE_CONFIRMED
    text = "".join(token.text for token in input1.tokens)
    assert "INSIDE" in text and "OUTSIDE" not in text


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
