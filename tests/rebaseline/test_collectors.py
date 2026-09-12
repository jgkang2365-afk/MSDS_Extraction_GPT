from __future__ import annotations

from dataclasses import replace

import pytest

import src.msds.collectors as collectors
from src.msds.collectors import collect_product_candidates, collect_section3_candidates
from src.msds.models import (
    CasCandidateValidity, ContentStatus, DocumentCapability, FenceStatus, FindingCode,
    LayoutToken, PageRegion, PairStatus, QualityStatus, ResultStatus, SectionInput,
)
from src.msds.pdf_io import FenceDescription, build_section_input, read_pdf_layout
from src.msds.resolver import resolve
from src.msds.sections import locate_section
from src.msds.validation import validate_resolved
from tests.rebaseline.pdf_helpers import make_pdf


def _input(
    section: str,
    rows: tuple[tuple[str, ...], ...],
    *,
    capability: DocumentCapability = DocumentCapability.TEXT,
    fence_status: FenceStatus | None = FenceStatus.FENCE_CONFIRMED,
) -> SectionInput:
    tokens: list[LayoutToken] = []
    serial = 0
    for row_number, cells in enumerate(rows):
        for cell_number, text in enumerate(cells):
            for character_number, character in enumerate(text):
                x = 72.0 + cell_number * 180.0 + character_number
                tokens.append(LayoutToken(
                    f"t-{serial}", character, 0,
                    (x, 100.0 + row_number * 20, x + 1, 110.0 + row_number * 20),
                    cell_number, row_number,
                    "OCR" if capability is DocumentCapability.OCR else "TEXT",
                ))
                serial += 1
    return SectionInput(
        "a" * 64, section, "confirmed-by-phase-2",
        (PageRegion(0, ((0, 0, 600, 800),)),), tuple(tokens), capability,
        input_digest="synthetic", fence_status=fence_status,
    )


def test_product_label_pipe_and_multiline_raw_preserve_source_order_and_formatting():
    product = collect_product_candidates(_input("1", (("Product name | ABC-100",),)))
    assert product.candidates[0].raw == "ABC-100"
    multiline = _input("1", (("Product:",), ("  Resin (Model-X) Grade A 75%  ",), ("  Lot-B  ",), ("Company: Example",)))
    candidate = collect_product_candidates(multiline).candidates[0]
    assert candidate.raw == "  Resin (Model-X) Grade A 75%  \n  Lot-B  "
    assert candidate.normalized == "resin (model-x) grade a 75% lot-b"
    assert [item.raw_fragment for item in candidate.evidence] == ["  Resin (Model-X) Grade A 75%  ", "  Lot-B  "]


def test_product_ignores_whitespace_only_visual_continuation_without_trimming_meaningful_lines():
    result = collect_product_candidates(_input("1", (
        ("Product:",),
        ("ABC Resin",),
        ("   ",),
        ("Grade A (50%)",),
        ("\t",),
        ("Company: Example",),
    )))
    candidate = result.candidates[0]
    assert candidate.raw == "ABC Resin\nGrade A (50%)"
    assert candidate.normalized == "abc resin grade a (50%)"
    assert [item.raw_fragment for item in candidate.evidence] == ["ABC Resin", "Grade A (50%)"]


def test_product_absence_has_no_filename_or_other_section_fallback():
    empty = _input("1", (("Company: not a product",),))
    changed_elsewhere = _input("1", (("Company: a filename-like ABC-100.pdf",),))
    assert collect_product_candidates(empty).candidates == ()
    assert collect_product_candidates(changed_elsewhere).candidates == ()


def test_p3_fix_01_separate_cell_product_name_value():
    result = collect_product_candidates(_input("1", (("Product name:", "ABC-100"),)))
    assert result.candidates[0].raw == "ABC-100"


def test_p3_fix_01_inline_product_name_continues_until_structural_field():
    result = collect_product_candidates(_input("1", (
        ("Product name: ABC-100",),
        ("Grade A 75%",),
        ("Company: Example Chemical",),
    )))
    candidate = result.candidates[0]
    assert candidate.raw == "ABC-100\nGrade A 75%"
    assert [item.raw_fragment for item in candidate.evidence] == ["ABC-100", "Grade A 75%"]


def test_p3_fix_02_korean_label_value():
    assert collect_product_candidates(_input("1", (("제품명 | 가나다 (Model-A)",),))).candidates[0].raw == "가나다 (Model-A)"


def test_p3_fix_03_korean_identifier_multiline_stops_at_company():
    result = collect_product_candidates(_input("1", (
        ("제품 식별자:",),
        ("ABC Resin (Model-X)",),
        ("Grade A 75%",),
        ("회사명:",),
        ("Example",),
    )))
    assert result.candidates[0].raw == "ABC Resin (Model-X)\nGrade A 75%"


def test_p3_fix_04_english_product_multiline_stops_at_company():
    result = collect_product_candidates(_input("1", (
        ("Product name:",),
        ("ABC-100",),
        ("Company:",),
        ("Example Chemical",),
    )))
    assert result.candidates[0].raw == "ABC-100"


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


def test_p3_fix_05_concentration_percent_header_preserves_bare_range_and_context():
    result = collect_section3_candidates(_input("3", (("CAS", "Concentration (%)"), ("64-17-5", "10~20"))))
    content = result.blocks[0].content_candidates[0]
    assert (content.raw, content.unit_context_raw, content.unit_context_evidence[0].raw_fragment) == ("10~20", "%", "Concentration (%)")


def test_korean_cas_identifier_table_header_selects_only_the_aligned_concentration_cell():
    section3 = _input("3", (
        ("Chemical name", "CAS 번호 또는 식별번호", "함유량(%)"),
        ("Butane (butadiene content 0%)", "106-97-8", "11 ~ 14"),
    ))
    block = collect_section3_candidates(section3).blocks[0]
    assert [(candidate.raw, candidate.unit_context_raw) for candidate in block.content_candidates] == [("11 ~ 14", "%")]
    resolved = resolve(_input("1", (("Product: table context",),)), section3)
    assert [(pair.content.content_raw, pair.content.content_status, pair.status) for pair in resolved.components] == [
        ("11 ~ 14", ContentStatus.FOUND, PairStatus.PAIRED),
    ]


def test_p3_fix_header_context_survives_blank_unit_cell_without_creating_bare_content():
    result = collect_section3_candidates(_input("3", (
        ("CAS", "Concentration (%)"),
        ("64-17-5", ""),
        ("67-56-1", "10"),
    )))
    first, second = result.blocks
    assert first.content_candidates == ()
    content = second.content_candidates[0]
    assert (content.raw, content.unit_context_raw) == ("10", "%")


def test_p5_fix_12_text_header_derived_blank_remains_explicit_blank():
    section3 = _input("3", (
        ("CAS", "Content (%)"),
        ("64-17-5", ""),
    ))
    block = collect_section3_candidates(section3).blocks[0]
    assert block.content_field_state.value == "EXPLICIT_BLANK"
    resolved = resolve(_input("1", (("Product: Text blank",),)), section3)
    assert (resolved.components[0].content.content_status, resolved.components[0].status) == (
        ContentStatus.NOT_STATED, PairStatus.NOT_STATED,
    )


def test_p5_fix_03_ocr_explicit_unreadable_content_is_preserved():
    section3 = _input("3", (("64-17-5", "[unreadable]"),), capability=DocumentCapability.OCR)
    resolved = resolve(_input("1", (("Product: OCR unreadable",),)), section3)
    report = validate_resolved(resolved)
    assert (resolved.components[0].content.content_raw, resolved.components[0].content.content_status) == (
        "[unreadable]", ContentStatus.NOT_READABLE,
    )
    assert report.findings[0].code is FindingCode.CONTENT_NOT_READABLE


def test_p3_fix_05_ec_table_column_is_excluded_while_cas_and_bare_content_remain():
    result = collect_section3_candidates(_input("3", (
        ("EC No.", "CAS No.", "Content (%)"),
        ("2000-01-3", "64-17-5", "10"),
        ("201-000-0", "64-17-4", "20"),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5", "64-17-4"]
    assert result.blocks[1].cas_candidates[0].validity is CasCandidateValidity.CHECK_DIGIT_INVALID
    assert (result.blocks[0].content_candidates[0].raw, result.blocks[0].content_candidates[0].unit_context_raw) == ("10", "%")


def test_p3_fix_06_wt_header_preserves_bare_comparator_and_context():
    result = collect_section3_candidates(_input("3", (("CAS", "Content(wt%)"), ("64-17-5", "<1"))))
    content = result.blocks[0].content_candidates[0]
    assert (content.raw, content.unit_context_raw) == ("<1", "wt%")


def test_p3_fix_07_ppm_header_preserves_bare_value_and_context():
    result = collect_section3_candidates(_input("3", (("CAS", "Content ppm"), ("64-17-5", "50"))))
    content = result.blocks[0].content_candidates[0]
    assert (content.raw, content.unit_context_raw) == ("50", "ppm")


def test_p3_fix_07_bare_ppm_header_preserves_bare_value_and_context():
    result = collect_section3_candidates(_input("3", (("CAS", "ppm"), ("64-17-5", "50"))))
    content = result.blocks[0].content_candidates[0]
    assert (content.raw, content.unit_context_raw) == ("50", "ppm")


def test_p3_fix_08_direct_ppm_stays_raw_without_header_derived_context():
    content = collect_section3_candidates(_input("3", (("64-17-5", "50 ppm"),))).blocks[0].content_candidates[0]
    assert (content.raw, content.unit_context_raw, content.unit_context_evidence) == ("50 ppm", None, ())


def test_p3_fix_09_general_bare_numeric_without_header_is_not_content():
    assert collect_section3_candidates(_input("3", (("64-17-5", "50"),))).blocks[0].content_candidates == ()


def test_p3_fix_09_direct_unit_data_does_not_become_a_reusable_header():
    result = collect_section3_candidates(_input("3", (("64-17-5", "10%"), ("67-64-1", "50"))))
    assert result.blocks[1].content_candidates == ()


def test_p3_fix_09_prior_or_explanatory_unit_text_does_not_upgrade_unrelated_bare_value():
    result = collect_section3_candidates(_input("3", (
        ("CAS", "Content (%)"),
        ("Explanation: values may be reported in %",),
        ("64-17-5", "50"),
    )))
    assert result.blocks[0].content_candidates == ()


def test_p3_fix_10_content_left_of_cas_has_earlier_source_order():
    block = collect_section3_candidates(_input("3", (("10%", "64-17-5"),))).blocks[0]
    assert block.content_candidates[0].source_order < block.cas_candidates[0].source_order


def test_p3_fix_11_cas_left_of_content_has_earlier_source_order():
    block = collect_section3_candidates(_input("3", (("64-17-5", "10%"),))).blocks[0]
    assert block.cas_candidates[0].source_order < block.content_candidates[0].source_order


def test_p3_fix_12_same_text_run_keeps_original_substring_order_after_cas_masking():
    block = collect_section3_candidates(_input("3", (("64-17-5 67-64-1 10%",),))).blocks[0]
    assert [candidate.raw for candidate in block.cas_candidates] == ["64-17-5", "67-64-1"]
    assert [candidate.source_order for candidate in block.cas_candidates] == [0, 1]
    assert block.content_candidates[0].source_order == 2


def test_real_pdf_section3_same_visual_row_separate_cells_preserves_raw_evidence(pdf_tmp):
    path = make_pdf(pdf_tmp / "collector-section3.pdf", [[
        (72, 72, "3. Composition/information on ingredients"),
        (72, 110, "64-17-5"), (300, 110, "10%"),
        (72, 130, "67-64-1"), (300, 130, "20%"),
        (72, 190, "4. First-aid measures"),
    ]])
    layout = read_pdf_layout(path)
    located = locate_section(layout, "3")
    assert located.description is not None
    result = collect_section3_candidates(build_section_input(layout, located.description))
    first = result.blocks[0]
    assert (first.cas_candidates[0].raw, first.content_candidates[0].raw) == ("64-17-5", "10%")
    assert [item.raw_fragment for item in first.content_candidates[0].evidence] == ["10%"]


def test_real_pdf_section3_ec_column_is_not_a_cas_candidate(pdf_tmp):
    path = make_pdf(pdf_tmp / "collector-section3-ec-column.pdf", [[
        (72, 72, "3. Composition/information on ingredients"),
        (72, 100, "EC No."), (220, 100, "CAS No."), (400, 100, "Content (%)"),
        (72, 120, "200-578-6"), (220, 120, "64-17-5"), (400, 120, "10"),
        (72, 180, "4. First-aid measures"),
    ]])
    layout = read_pdf_layout(path)
    located = locate_section(layout, "3")
    assert located.description is not None
    result = collect_section3_candidates(build_section_input(layout, located.description))
    block = result.blocks[0]
    assert [candidate.raw for candidate in block.cas_candidates] == ["64-17-5"]
    assert (block.content_candidates[0].raw, block.content_candidates[0].unit_context_raw) == ("10", "%")


def test_real_pdf_section3_narrow_ec_cas_gap_keeps_cas_column_candidate(pdf_tmp):
    path = make_pdf(pdf_tmp / "collector-section3-narrow-ec-cas.pdf", [[
        (72, 72, "3. Composition/information on ingredients"),
        (72, 100, "EC No."), (130, 100, "CAS No."), (300, 100, "Content (%)"),
        # Keep extracted cells separate while making the CAS cell wider than
        # the 58-point EC/CAS gap that previously caused false EC exclusion.
        (72, 120, "EC ref"), (130, 120, "64-17-5 ingredient"), (300, 120, "10"),
        (72, 180, "4. First-aid measures"),
    ]])
    layout = read_pdf_layout(path)
    # The intentionally narrow columns are ambiguous to the section locator,
    # so exercise the collector with the real PyMuPDF text tokens in a
    # confirmed SectionInput, as Phase 2 would provide it.
    section_input = SectionInput(
        layout.document_sha256,
        "3",
        "confirmed-by-phase-2",
        (PageRegion(0, (layout.pages[0].rect,)),),
        layout.pages[0].tokens,
        DocumentCapability.TEXT,
        input_digest="real-pdf-narrow-ec-cas",
        fence_status=FenceStatus.FENCE_CONFIRMED,
    )
    result = collect_section3_candidates(section_input)
    block = result.blocks[0]
    assert [candidate.raw for candidate in block.cas_candidates] == ["64-17-5"]
    assert (block.content_candidates[0].raw, block.content_candidates[0].unit_context_raw) == ("10", "%")


def test_real_pdf_section3_unit_header_rejects_adjacent_bare_numeric_column(pdf_tmp):
    path = make_pdf(pdf_tmp / "collector-section3-unit-header-column.pdf", [[
        (72, 72, "3. Composition/information on ingredients"),
        (72, 100, "CAS"), (180, 100, "Reference number"), (300, 100, "Content (%)"),
        (72, 120, "64-17-5"), (180, 120, "123456789"), (300, 120, "10"),
        (72, 180, "4. First-aid measures"),
    ]])
    layout = read_pdf_layout(path)
    located = locate_section(layout, "3")
    assert located.description is not None
    result = collect_section3_candidates(build_section_input(layout, located.description))
    content = result.blocks[0].content_candidates
    assert [(candidate.raw, candidate.unit_context_raw) for candidate in content] == [("10", "%")]


def test_real_pdf_product_multiline_stops_before_company(pdf_tmp):
    path = make_pdf(pdf_tmp / "collector-product.pdf", [[
        (72, 72, "1. Chemical product and company identification"),
        (72, 110, "Product name:"), (260, 110, "ABC-100"),
        (260, 130, "Grade A 75%"),
        (72, 150, "Company:"), (260, 150, "Example Chemical"),
        (72, 190, "2. Hazards identification"),
    ]])
    layout = read_pdf_layout(path)
    located = locate_section(layout, "1")
    assert located.description is not None
    result = collect_product_candidates(build_section_input(layout, located.description))
    candidate = result.candidates[0]
    assert candidate.raw == "ABC-100\nGrade A 75%"
    assert [item.raw_fragment for item in candidate.evidence] == ["ABC-100", "Grade A 75%"]


def test_korean_material_name_label_and_fullwidth_percent_content_preserve_raw_source_value():
    product = collect_product_candidates(_input("1", (("물질명 : 수산화나트륨",),)))
    section3 = collect_section3_candidates(_input("3", (("64-17-5", "함유량 : 8-0％"),)))
    assert [(candidate.raw, candidate.normalized) for candidate in product.candidates] == [("수산화나트륨", "수산화나트륨")]
    assert [(candidate.raw, candidate.normalized) for candidate in section3.blocks[0].content_candidates] == [("8-0％", "8~0%")]


def test_named_korean_component_cas_and_content_groups_preserve_fullwidth_values_for_review():
    result = resolve(
        _input("1", (("제품명 : NaOH",),)),
        _input("3", (
            ("성   분 : 수산화나트륨",),
            (" C A S : 1310-73-2",),
            ("함유량 : 92-100％",),
            ("성   분 : 물",),
            (" C A S : 7732-18-5",),
            ("함유량 : 8-0％",),
        )),
    )
    assert [(pair.cas.cas_raw, pair.cas.cas_status, pair.content.content_raw, pair.content.content_normalized, pair.status) for pair in result.components] == [
        ("1310-73-2", ResultStatus.FOUND, "92-100％", "92~100%", PairStatus.PAIRED),
        ("7732-18-5", ResultStatus.FOUND, "8-0％", "8~0%", PairStatus.PAIRED),
    ]


def test_section3_invalid_cas_date_ec_and_content_semantics_are_not_repaired_or_promoted():
    result = collect_section3_candidates(_input("3", (
        ("64-17-4", "< 1%"),
        ("Revision Date: 2000-01-3", "> 2%"),
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


@pytest.mark.parametrize(
    "date_label",
    ["Revision Date", "Issue", "Prepared Date", "작성일", "작성일자", "개정일", "개정일자", "제조일", "제조일자", "작성 날짜", "개정 날짜", "제조 날짜", "날짜"],
)
def test_date_metadata_context_never_admits_an_otherwise_valid_cas(date_label):
    result = collect_section3_candidates(_input("3", ((f"{date_label}: 2000-01-3", "10%"),)))
    assert result.blocks == ()


@pytest.mark.parametrize("date_label", ["Revision Date", "작성일자", "개정일자", "제조일자", "작성 날짜", "날짜"])
def test_only_the_immediately_related_date_value_row_is_excluded(date_label):
    result = collect_section3_candidates(_input("3", (
        (date_label,),
        ("2000-01-3",),
        ("64-17-5", "10%"),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]


@pytest.mark.parametrize(
    "date_row",
    [
        ("문서정보", "작성일자", "2000-01-3"),
        ("문서정보", "날짜: 2000-01-3"),
        ("문서정보", "작성일자 | 2000-01-3"),
    ],
)
def test_date_metadata_peer_cells_and_inline_pipe_never_admit_a_valid_cas(date_row):
    assert collect_section3_candidates(_input("3", (date_row,))).blocks == ()


def test_split_date_label_among_peer_cells_excludes_only_aligned_date_value_cell():
    result = collect_section3_candidates(_input("3", (
        ("문서정보", "작성일자", "작성부서"),
        ("other", "2000-01-3", "other"),
        ("64-17-5", "10%"),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]


def test_split_date_value_with_whitespace_and_peer_content_is_excluded():
    result = collect_section3_candidates(_input("3", (
        ("문서정보", "작성일자", "작성부서"),
        ("other", " 2000-01-3 ", "10%"),
        ("64-17-5", "10%"),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]


def test_same_row_date_label_and_value_do_not_block_the_next_genuine_cas():
    result = collect_section3_candidates(_input("3", (
        ("작성일자", "2000-01-3"),
        ("64-17-5", "10%"),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]


def test_peer_row_date_label_and_value_do_not_block_the_next_aligned_genuine_cas():
    result = collect_section3_candidates(_input("3", (
        ("문서정보", "작성일자", "2000-01-3", "작성부서"),
        ("other", "64-17-5", "10%", "other"),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]


@pytest.mark.parametrize("date_value", ["2024-01-12", "2026.09.11", "2026/09/11", "Sep 11, 2026", "not stated"])
def test_complete_date_field_with_non_cas_value_does_not_block_the_next_genuine_cas(date_value):
    result = collect_section3_candidates(_input("3", (
        ("작성일자", date_value),
        ("64-17-5", "10%"),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]


def test_complete_peer_cell_date_field_with_normal_date_does_not_block_next_aligned_cas():
    result = collect_section3_candidates(_input("3", (
        ("문서정보", "작성일자", "2024-01-12", "작성부서"),
        ("other", "64-17-5", "10%", "other"),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]


def test_completed_date_sibling_does_not_release_an_aligned_label_only_date_field():
    result = collect_section3_candidates(_input("3", (
        ("작성일자", "Revision Date: 2024-01-12"),
        ("2000-01-3", "64-17-5"),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]


def test_each_date_label_uses_its_own_same_row_completion_state():
    result = collect_section3_candidates(_input("3", (
        ("작성일자", "not stated", "개정일자"),
        ("2000-01-3", "other", "2000-01-3"),
    )))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["2000-01-3"]


def test_explicit_cas_label_overrides_peer_date_metadata_context():
    result = collect_section3_candidates(_input("3", (("작성일자", "CAS No.", "2000-01-3", "10%"),)))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["2000-01-3"]


def test_later_date_field_overrides_an_earlier_cas_field_in_the_same_row():
    result = collect_section3_candidates(_input("3", (("CAS No.", "64-17-5", "작성일자", "2000-01-3", "10%"),)))
    assert [block.cas_candidates[0].raw for block in result.blocks] == ["64-17-5"]


def test_explicit_named_cas_no_admits_an_otherwise_date_shaped_valid_cas():
    result = resolve(
        _input("1", (("Product: lexical CAS",),)),
        _input("3", (("성분: test",), ("CAS No: 2000-01-3",), ("함유량: 10%",))),
    )
    assert [(pair.cas.cas_raw, pair.cas.cas_status, pair.status) for pair in result.components] == [
        ("2000-01-3", ResultStatus.FOUND, PairStatus.PAIRED),
    ]


@pytest.mark.parametrize("source_token", ("64-17-5X", "X64-17-5", "64-17-5-99"))
def test_malformed_cas_tokens_preserve_the_whole_source_token_through_review(source_token):
    result = resolve(
        _input("1", (("Product: CAS boundary regression",),)),
        _input("3", ((source_token, "10%"),)),
    )
    candidate = result.section3.blocks[0].cas_candidates[0]
    pair = result.components[0]
    report = validate_resolved(result)

    assert (candidate.raw, candidate.normalized, candidate.validity) == (
        source_token, source_token, CasCandidateValidity.FORMAT_INVALID,
    )
    assert candidate.evidence[0].raw_fragment == source_token
    assert (pair.cas.cas_raw, pair.cas.cas_status, pair.status) == (
        source_token, ResultStatus.INVALID, PairStatus.REVIEW,
    )
    assert (report.status, [finding.code for finding in report.findings]) == (
        QualityStatus.REVIEW_REQUIRED, [FindingCode.CAS_READ_UNCERTAIN],
    )


def test_standalone_valid_cas_remains_valid_through_resolution_and_validation():
    result = resolve(
        _input("1", (("Product: CAS boundary regression",),)),
        _input("3", (("64-17-5", "10%"),)),
    )
    candidate = result.section3.blocks[0].cas_candidates[0]
    pair = result.components[0]

    assert (candidate.raw, candidate.normalized, candidate.validity) == (
        "64-17-5", "64-17-5", CasCandidateValidity.VALID,
    )
    assert (pair.cas.cas_raw, pair.cas.cas_status, pair.status) == (
        "64-17-5", ResultStatus.FOUND, PairStatus.PAIRED,
    )
    assert validate_resolved(result).status is QualityStatus.PASS


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


def test_public_collectors_reject_wrong_section_non_isolated_and_non_input():
    section_one = _input("1", (("Product: ABC",),))
    with pytest.raises(ValueError, match="SECTION_3"):
        collect_section3_candidates(section_one)
    with pytest.raises(ValueError, match="TEXT_OR_OCR"):
        collect_product_candidates(replace(section_one, capability=DocumentCapability.IMAGE_ONLY))
    with pytest.raises(TypeError, match="SECTION_INPUT"):
        collect_product_candidates("not an input")  # type: ignore[arg-type]


@pytest.mark.parametrize("fence_status", (FenceStatus.FENCE_PARTIAL, FenceStatus.FENCE_NOT_FOUND, None))
def test_p5_fix_10_collectors_reject_partial_not_found_and_unconfirmed_inputs(fence_status):
    product = _input("1", (("Product: A",),), fence_status=fence_status)
    section3 = _input("3", (("64-17-5", "10%"),), fence_status=fence_status)
    with pytest.raises(ValueError, match="REQUIRES_CONFIRMED_FENCE"):
        collect_product_candidates(product)
    with pytest.raises(ValueError, match="REQUIRES_CONFIRMED_FENCE"):
        collect_section3_candidates(section3)
