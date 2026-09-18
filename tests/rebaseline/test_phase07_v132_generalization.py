"""Phase 7 v1.3.2 generic grammar and source-relation regressions."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.msds.collectors import collect_product_candidates, collect_section3_candidates
from src.msds.normalization import normalize_content
from src.msds.pdf_io import build_section_input, read_pdf_layout
from src.msds.resolver import resolve, resolve_components
from src.msds.validation import validate_resolved
from src.msds.sections import locate_sds_segments, locate_sections
from tests.rebaseline.pdf_helpers import make_pdf
from tests.rebaseline.test_collectors import _input


def test_heading_grammar_accepts_korean_hang_and_section_syntax_without_widening_sections(pdf_tmp):
    fontfile = Path(r"C:\Windows\Fonts\malgun.ttf")
    path = make_pdf(pdf_tmp / "heading-grammar.pdf", [[
        (72, 72, "항 1: 화학제품과 회사에 관한 정보"), (72, 100, "INSIDE_ONE"),
        (72, 130, "항 2: 위험·유해성"),
        (72, 160, "SECTION 3: Composition/information on ingredients"), (72, 190, "INSIDE_THREE"),
        (72, 220, "Section 4. First-aid measures"), (72, 250, "OUTSIDE_FOUR"),
    ]], fontfile=fontfile)
    one, three = locate_sections(read_pdf_layout(path))
    assert one.description is not None and three.description is not None
    assert "INSIDE_ONE" in "".join(token.text for token in build_section_input(read_pdf_layout(path), one.description).tokens)
    assert "INSIDE_THREE" in "".join(token.text for token in build_section_input(read_pdf_layout(path), three.description).tokens)
    assert "OUTSIDE_FOUR" not in "".join(token.text for token in build_section_input(read_pdf_layout(path), three.description).tokens)


def test_multi_sds_segments_are_independent_and_the_canonical_locator_stays_fail_closed(pdf_tmp):
    pages = []
    for product, cas, content in (("Alpha", "64-17-5", "10%"), ("Beta", "67-64-1", "20%")):
        pages.append([
            (72, 72, "1. Chemical product and company identification"), (72, 100, f"Product: {product}"),
            (72, 130, "2. Hazards identification"), (72, 160, "3. Composition/information on ingredients"),
            (72, 190, cas), (300, 190, content), (72, 220, "4. First-aid measures"),
        ])
    layout = read_pdf_layout(make_pdf(pdf_tmp / "multi-sds.pdf", pages))
    # The legacy canonical route remains a single first-document result.  The
    # new parallel API is what makes every independent sequence observable.
    assert locate_sections(layout)[0].description is not None
    segments = locate_sds_segments(layout)
    actual = []
    for segment in segments:
        assert segment.section_1.description is not None and segment.section_3.description is not None
        resolved = resolve(build_section_input(layout, segment.section_1.description), build_section_input(layout, segment.section_3.description))
        actual.append((resolved.product.raw, [(item.cas.cas_raw, item.content.content_raw) for item in resolved.components]))
    assert actual == [("Alpha", [("64-17-5", "10%")]), ("Beta", [("67-64-1", "20%")])]


@pytest.mark.parametrize(("raw", "expected"), [
    ("0.1 이상 ~\n1 % 미만", ">=0.1~<1%"),
    ("1 초과 ~\n2 % 이하", ">1~<=2%"),
    ("< 1 %", "<1%"),
    (">= 45 - < 50 %", ">=45~<50%"),
])
def test_korean_comparator_normalization_preserves_raw_and_normalizes_structure(raw, expected):
    result = normalize_content(raw)
    assert result.content_raw == raw
    assert result.content_normalized == expected


def test_multiline_korean_table_content_is_paired_only_in_the_explicit_content_column():
    section3 = _input("3", (
        ("Chemical name", "CAS NO", "함유량(%)", "Exposure"),
        ("Water", "7732-18-5", "40 이상 ~", "999%"),
        ("", "", "50 % 미만", "777%"),
    ))
    result = resolve(_input("1", (("Product: structural",),)), section3)
    assert [(item.cas.cas_raw, item.content.content_raw, item.content.content_normalized) for item in result.components] == [
        ("7732-18-5", "40 이상 ~\n50 % 미만", ">=40~<50%"),
    ]


def test_split_cas_header_uses_true_content_and_never_promotes_ec_or_classification_limits():
    # The explicit CAS/value row relation below is the only eligible source
    # relation.  Classification-limit and EC rows have no component promotion.
    direct = _input("3", (("CAS 번호 또는 식별번호", "함유량(%)", "분류"), ("7647-01-0", ">= 35 - < 40 %", ">= 0.1 %")))
    resolved = resolve(_input("1", (("Product: acid",),)), direct)
    assert [(item.cas.cas_raw, item.content.content_raw) for item in resolved.components] == [("7647-01-0", ">= 35 - < 40 %")]


def test_true_split_cas_identifier_header_requires_an_adjacent_same_band_fragment():
    split = _input("3", (
        ("CAS 번호 또는", "함유량(%)"),
        ("식별번호", ""),
        ("64-17-5 / OTHER-1", "10%"),
    ))
    resolved = resolve(_input("1", (("Product: split",),)), split)
    assert [(item.cas.cas_raw, item.content.content_raw) for item in resolved.components] == [("64-17-5", "10%")]
    # A distant or other-column fragment cannot retroactively create a CAS
    # header proof.
    distant = _input("3", (("CAS 번호 또는", "함유량(%)"), ("note", ""), ("식별번호", ""), ("64-17-5", "10%")))
    assert collect_section3_candidates(distant).blocks[0].content_candidates[0].unit_context_raw is None
    wrong_column = _input("3", (("CAS 번호 또는", "함유량(%)"), ("", "식별번호"), ("64-17-5", "10%")))
    assert collect_section3_candidates(wrong_column).blocks[0].content_candidates[0].unit_context_raw is None
    interrupted = _input("3", (("CAS 번호 또는", "함유량(%)"), ("Other table", "Other field"), ("식별번호", ""), ("64-17-5", "10%")))
    assert collect_section3_candidates(interrupted).blocks[0].content_candidates[0].unit_context_raw is None


def test_multi_sds_locator_ignores_toc_and_body_section_references(pdf_tmp):
    path = make_pdf(pdf_tmp / "multi-sds-toc-reference.pdf", [[
        (72, 72, "1. Chemical product and company identification"),
        (72, 90, "2. Hazards identification"),
        (72, 108, "3. Composition/information on ingredients"),
        (72, 126, "4. First-aid measures"),
        (72, 200, "1. Chemical product and company identification"), (72, 220, "Product: Alpha"),
        (72, 240, "Company: Example"), (72, 250, "see Section 1 Identification"), (72, 270, "2. Hazards identification"),
        (72, 320, "3. Composition/information on ingredients"), (72, 340, "64-17-5"),
        (300, 340, "10%"), (72, 380, "4. First-aid measures"),
    ]])
    layout = read_pdf_layout(path)
    segments = locate_sds_segments(layout)
    assert len(segments) == 1
    resolved = resolve(build_section_input(layout, segments[0].section_1.description), build_section_input(layout, segments[0].section_3.description))
    assert (resolved.product.raw, [(item.cas.cas_raw, item.content.content_raw) for item in resolved.components]) == (
        "Alpha", [("64-17-5", "10%")],
    )


def test_multi_sds_locator_keeps_empty_page_and_page_number_reset_out_of_segment_proof(pdf_tmp):
    pages = [
        [
            (72, 72, "1. Chemical product and company identification"), (72, 92, "Product: Alpha"),
            (72, 120, "2. Hazards identification"), (72, 160, "3. Composition/information on ingredients"),
            (72, 180, "64-17-5"), (300, 180, "10%"), (72, 220, "4. First-aid measures"),
        ],
        [],
        [
            (72, 60, "1"), (72, 90, "1. Chemical product and company identification"), (72, 110, "Product: Beta"),
            (72, 140, "2. Hazards identification"), (72, 180, "3. Composition/information on ingredients"),
            (72, 200, "67-64-1"), (300, 200, "20%"), (72, 240, "4. First-aid measures"),
        ],
    ]
    layout = read_pdf_layout(make_pdf(pdf_tmp / "multi-sds-empty-page.pdf", pages))
    segments = locate_sds_segments(layout)
    assert len(segments) == 2
    actual = [
        (resolved.product.raw, [(item.cas.cas_raw, item.content.content_raw) for item in resolved.components])
        for resolved in (
            resolve(build_section_input(layout, segment.section_1.description), build_section_input(layout, segment.section_3.description))
            for segment in segments
        )
    ]
    assert actual == [("Alpha", [("64-17-5", "10%")]), ("Beta", [("67-64-1", "20%")])]


def test_multi_sds_locator_splits_a_second_sds_on_the_same_physical_page(pdf_tmp):
    path = make_pdf(pdf_tmp / "multi-sds-same-page.pdf", [[
        (72, 72, "1. Chemical product and company identification"), (72, 92, "Product: Alpha"),
        (72, 120, "2. Hazards identification"), (72, 160, "3. Composition/information on ingredients"),
        (72, 180, "64-17-5"), (300, 180, "10%"), (72, 220, "4. First-aid measures"),
        (72, 300, "1. Chemical product and company identification"), (72, 320, "Product: Beta"),
        (72, 350, "2. Hazards identification"), (72, 390, "3. Composition/information on ingredients"),
        (72, 410, "67-64-1"), (300, 410, "20%"), (72, 450, "4. First-aid measures"),
    ]])
    layout = read_pdf_layout(path)
    segments = locate_sds_segments(layout)
    assert len(segments) == 2
    actual = [
        (resolved.product.raw, [(item.cas.cas_raw, item.content.content_raw) for item in resolved.components])
        for resolved in (
            resolve(build_section_input(layout, segment.section_1.description), build_section_input(layout, segment.section_3.description))
            for segment in segments
        )
    ]
    assert actual == [("Alpha", [("64-17-5", "10%")]), ("Beta", [("67-64-1", "20%")])]


@pytest.mark.parametrize(("raw", "expected"), [
    ("5 이상", ">=5"), ("5 미만", "<5"), ("5 초과", ">5"), ("5 이하", "<=5"),
])
def test_single_korean_comparators_preserve_raw_and_normalize_semantics(raw, expected):
    result = normalize_content(raw)
    assert result.content_raw == raw
    assert result.content_normalized == expected


def test_named_fields_allow_local_flexible_order_but_do_not_join_across_a_note_boundary():
    flexible = _input("3", (("Ingredient name:Glycine",), ("Content (%):98.5～101.5",), ("CAS No.:56-40-6",)))
    resolved = resolve(_input("1", (("Product: Glycine",),)), flexible)
    assert [(item.cas.cas_raw, item.content.content_raw) for item in resolved.components] == [("56-40-6", "98.5～101.5")]
    distant = _input("3", (("Ingredient name:Glycine",), ("Content (%):98.5～101.5",), ("Note: unrelated block",), ("CAS No.:56-40-6",)))
    assert collect_section3_candidates(distant).blocks == ()
    korean_distant = _input("3", (("Ingredient name:Glycine",), ("Content (%):98.5～101.5",), ("비고: 무관한 블록",), ("CAS No.:56-40-6",)))
    assert collect_section3_candidates(korean_distant).blocks == ()


SOURCE_ROOT = os.environ.get("PHASE7_TEST_FILE_ROOT")


@pytest.mark.skipif(not SOURCE_ROOT, reason="PHASE7_TEST_FILE_ROOT is required for local-only actual-PDF checks")
def test_actual_phase07_v132_generalized_routes():
    root = Path(SOURCE_ROOT)
    segments = locate_sds_segments(read_pdf_layout(next(root.glob("007*.pdf"))))
    assert len(segments) == 3
    products_and_pairs = []
    for segment in segments:
        assert segment.section_1.description is not None and segment.section_3.description is not None
        result = resolve(
            build_section_input(read_pdf_layout(next(root.glob("007*.pdf"))), segment.section_1.description),
            build_section_input(read_pdf_layout(next(root.glob("007*.pdf"))), segment.section_3.description),
        )
        products_and_pairs.append((result.product.raw, [(item.cas.cas_raw, item.content.content_raw, item.status.value) for item in result.components]))
    # Each CAS/content relation is source-local to one of the three Section
    # 1/3 fences.  The other identifier text remains source text, never output.
    assert products_and_pairs == [
        ("- 프로스테인 네오-PC100(크리어)", [("616-38-6", "45~50", "PAIRED"), ("64742-82-1", "13 ~ 20", "PAIRED"), ("68333-70-0", "10 ~ 17", "PAIRED"), ("8001-26-1", "7 ~ 14", "PAIRED"), ("1330-20-7", "4 ~ 11", "PAIRED"), ("22464-99-9", "1 ~ 6", "PAIRED"), ("100-41-4", "1 ~ 6", "PAIRED"), ("41556-26-7", "0.1~1미맊", "PAIRED"), ("96-29-7", "0.1~1미맊", "PAIRED")]),
        ("- 프로스테인 네오-PC420(페퍼)", [("616-38-6", "43~48", "PAIRED"), ("64742-82-1", "13 ~ 20", "PAIRED"), ("68333-70-0", "7 ~ 14", "PAIRED"), ("8001-26-1", "4 ~ 11", "PAIRED"), ("1330-20-7", "4 ~ 11", "PAIRED"), ("22464-99-9", "1 ~ 6", "PAIRED"), ("100-41-4", "1 ~ 6", "PAIRED"), ("64742-95-6", "0.1~1미맊", "PAIRED"), ("1333-86-4", "0.1~1미맊", "PAIRED"), ("41556-26-7", "0.1~1미맊", "PAIRED"), ("96-29-7", "0.1~1미맊", "PAIRED")]),
        ("- 프로스테인 네오-PC220(오크)", [("616-38-6", "42~47", "PAIRED"), ("64742-82-1", "13 ~ 20", "PAIRED"), ("68333-70-0", "7 ~ 14", "PAIRED"), ("8001-26-1", "4 ~ 11", "PAIRED"), ("1330-20-7", "4 ~ 11", "PAIRED"), ("51274-00-1", "1 ~ 6", "PAIRED"), ("22464-99-9", "1 ~ 6", "PAIRED"), ("100-41-4", "1 ~ 6", "PAIRED"), ("64742-95-6", "0.1~1미맊", "PAIRED"), ("41556-26-7", "0.1~1미맊", "PAIRED"), ("96-29-7", "0.1~1미맊", "PAIRED")]),
    ]
    for prefix, expected_product, expected in (
        ("030", "Hydrochloric acid", [("7647-01-0", ">= 35 - < 40 %")]),
        ("032", "Nitric acid", [("7697-37-2", ">= 70 - < 75 %")]),
        ("043", "Glycine", [("56-40-6", "98.5～101.5")]),
    ):
        layout = read_pdf_layout(next(root.glob(prefix + "*.pdf")))
        one, three = locate_sections(layout)
        assert one.description is not None and three.description is not None
        result = resolve(build_section_input(layout, one.description), build_section_input(layout, three.description))
        if expected_product is not None:
            assert result.product.raw == expected_product
        assert [(item.cas.cas_raw, item.content.content_raw) for item in result.components] == expected
    layout = read_pdf_layout(next(root.glob("027*.pdf")))
    one, three = locate_sections(layout)
    assert one.description is not None and three.description is not None
    result = resolve(build_section_input(layout, one.description), build_section_input(layout, three.description))
    assert result.product.raw == "D-(+)-Gluconic acid δ-lactone"
    assert [(item.cas.cas_raw, item.cas.cas_status.value, item.content.content_raw, item.content.content_status.value) for item in result.components] == [
        ("90-80-2", "FOUND", "", "NOT_STATED"),
    ]
    # No content is invented: the intrinsic component status records the
    # explicit not-stated field, while the valid CAS remains usable.
    assert result.components[0].status.value == "NOT_STATED"
    assert validate_resolved(result).status.value == "PASS"
    layout = read_pdf_layout(next(root.glob("036*.pdf")))
    one, three = locate_sections(layout)
    assert one.description is not None and three.description is not None
    resolved = resolve(build_section_input(layout, one.description), build_section_input(layout, three.description))
    assert resolved.product.raw == "아이생각수성내부프로 (M-BASE)"
    components = resolved.components
    assert [
        (item.cas.cas_raw, item.content.content_raw, item.content.content_normalized, item.status.value)
        for item in components
    ] == [
        ("7732-18-5", "40 이상 ~\n50 % 미만", ">=40~<50%", "PAIRED"),
        ("14807-96-6", "20 이상 ~\n30 % 미만", ">=20~<30%", "PAIRED"),
        ("1317-65-3", "10 이상 ~\n20 % 미만", ">=10~<20%", "PAIRED"),
        ("26636-08-8", "1 이상 ~\n10 % 미만", ">=1~<10%", "PAIRED"),
        ("92704-41-1", "1 이상 ~\n10 % 미만", ">=1~<10%", "PAIRED"),
        ("13463-67-7", "1 이상 ~\n10 % 미만", ">=1~<10%", "PAIRED"),
        ("471-34-1", "1 이상 ~\n10 % 미만", ">=1~<10%", "PAIRED"),
        ("57-55-6", "1 이상 ~\n10 % 미만", ">=1~<10%", "PAIRED"),
        ("108-01-0", "0.1 이상 ~\n1 % 미만", ">=0.1~<1%", "PAIRED"),
    ]
