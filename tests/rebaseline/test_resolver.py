from __future__ import annotations

import pytest

from src.msds.models import (
    CasCandidate, CasCandidateValidity, ContentCandidate, ContentFieldState,
    ContentStatus, DocumentCapability, Evidence, EvidenceSourceType,
    PairStatus, ProductCandidate, ProductCollection, ResultStatus,
    Section3BlockCandidate, Section3Collection,
)
from src.msds.resolver import resolve, resolve_candidates, resolve_components, resolve_product


def _evidence(raw: str, page: int = 0) -> Evidence:
    return Evidence("3", page, EvidenceSourceType.TEXT, raw, "a" * 64, (1.0, 2.0, 3.0, 4.0))


def _product(raw: str, normalized: str, order: int, evidence: tuple[Evidence, ...] | None = None) -> ProductCandidate:
    return ProductCandidate(raw, normalized, order, evidence or (_evidence(raw, order),))


def _cas(raw: str, order: int, validity: CasCandidateValidity = CasCandidateValidity.VALID) -> CasCandidate:
    return CasCandidate(raw, raw, validity, order, (_evidence(raw, order),))


def _content(raw: str, order: int, context: str | None = None) -> ContentCandidate:
    return ContentCandidate(raw, raw, order, (_evidence(raw, order),), context, (_evidence(context, order),) if context else ())


def _block(order: int, cas: tuple[CasCandidate, ...], content: tuple[ContentCandidate, ...] = (), state: ContentFieldState = ContentFieldState.UNKNOWN, raw: str | None = None) -> Section3BlockCandidate:
    return Section3BlockCandidate(f"block-{order}", f"row-{order}", order, (_evidence(f"row-{order}", order),), cas, content, state, raw)


def test_p5_r_01_one_clear_product_candidate_is_found():
    result = resolve_product(ProductCollection((_product(" Resin A ", "resin a", 0),)))
    assert (result.raw, result.normalized, result.status) == (" Resin A ", "resin a", ResultStatus.FOUND)


def test_p5_r_02_same_source_duplicate_observation_dedupes_evidence_only():
    evidence = _evidence("Resin A")
    result = resolve_product(ProductCollection((_product("Resin A", "resin a", 0, (evidence,)), _product("Resin A", "resin a", 1, (evidence,)))))
    assert result.status is ResultStatus.FOUND and result.evidence == (evidence,)


def test_p5_r_03_repeated_same_product_from_distinct_sources_resolves():
    result = resolve_product(ProductCollection((_product("Resin A", "resin a", 0), _product("Resin A", "resin a", 1))))
    assert result.status is ResultStatus.FOUND and len(result.evidence) == 2


def test_p5_r_04_different_clear_products_never_selects_first():
    result = resolve_product(ProductCollection((_product("First", "first", 0), _product("Second", "second", 1))))
    assert (result.raw, result.normalized, result.status) == ("", "", ResultStatus.REVIEW)


def test_p5_r_05_confirmed_s1_without_candidate_is_not_found():
    assert resolve_product(ProductCollection()).status is ResultStatus.NOT_FOUND


def test_p5_r_06_resolver_rejects_raw_or_non_section_inputs():
    with pytest.raises(TypeError, match="SECTION_INPUT"):
        resolve("not a SectionInput", "not a SectionInput")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="PRODUCT_COLLECTION"):
        resolve_product("filename fallback")  # type: ignore[arg-type]


def test_p5_r_07_one_cas_and_one_content_are_paired():
    pair = resolve_components(Section3Collection((_block(0, (_cas("64-17-5", 0),), (_content("10%", 1),)),)))[0]
    assert (pair.cas.cas_raw, pair.content.content_raw, pair.status) == ("64-17-5", "10%", PairStatus.PAIRED)


def test_p5_r_08_multiple_cas_share_one_explicit_block_content():
    pairs = resolve_components(Section3Collection((_block(0, (_cas("64-17-5", 0), _cas("67-64-1", 1)), (_content("10%", 2),)),)))
    assert [(pair.cas.cas_raw, pair.content.content_raw) for pair in pairs] == [("64-17-5", "10%"), ("67-64-1", "10%")]


def test_p5_r_09_duplicate_cas_rows_and_block_source_order_are_retained():
    pairs = resolve_components(Section3Collection((_block(2, (_cas("64-17-5", 2),), (_content("20%", 3),)), _block(1, (_cas("64-17-5", 1),), (_content("10%", 2),)))))
    assert [(pair.block_id, pair.content.content_raw) for pair in pairs] == [("block-1", "10%"), ("block-2", "20%")]


def test_p5_r_10_explicitly_blank_content_field_becomes_not_stated():
    pair = resolve_components(Section3Collection((_block(0, (_cas("64-17-5", 0),), state=ContentFieldState.EXPLICIT_BLANK),)))[0]
    assert (pair.content.content_status, pair.status) == (ContentStatus.NOT_STATED, PairStatus.NOT_STATED)


def test_p5_r_11_absence_of_a_candidate_never_becomes_not_stated():
    pair = resolve_components(Section3Collection((_block(0, (_cas("64-17-5", 0),), state=ContentFieldState.ABSENT),)))[0]
    assert (pair.content.content_status, pair.status) == (ContentStatus.PAIR_AMBIGUOUS, PairStatus.PAIR_AMBIGUOUS)


def test_p5_r_12_unreadable_content_remains_raw_and_unreadable():
    pair = resolve_components(Section3Collection((_block(0, (_cas("64-17-5", 0),), state=ContentFieldState.UNREADABLE, raw="[illegible]"),)))[0]
    assert (pair.content.content_raw, pair.content.content_status, pair.status) == ("[illegible]", ContentStatus.NOT_READABLE, PairStatus.NOT_READABLE)


def test_p5_r_13_multiple_content_candidates_without_mapping_are_ambiguous():
    pair = resolve_components(Section3Collection((_block(0, (_cas("64-17-5", 0),), (_content("10%", 1), _content("20%", 2))),)))[0]
    assert (pair.content.content_status, pair.status) == (ContentStatus.PAIR_AMBIGUOUS, PairStatus.PAIR_AMBIGUOUS)


def test_p5_r_14_content_only_source_never_creates_a_component():
    assert resolve_components(Section3Collection()) == ()


def test_p5_r_15_invalid_cas_checksum_is_not_corrected():
    pair = resolve_components(Section3Collection((_block(0, (_cas("64-17-4", 0, CasCandidateValidity.CHECK_DIGIT_INVALID),), (_content("10%", 1),)),)))[0]
    assert (pair.cas.cas_raw, pair.cas.cas_normalized, pair.cas.cas_status, pair.status) == ("64-17-4", "64-17-4", ResultStatus.INVALID, PairStatus.REVIEW)


def test_p5_r_16_content_range_operator_balance_and_over_100_are_raw_preserved():
    raw = ">100 wt% Balance Rem. <1%"
    pair = resolve_components(Section3Collection((_block(0, (_cas("64-17-5", 0),), (_content(raw, 1),)),)))[0]
    assert pair.content.content_raw == raw


def test_p5_r_17_header_unit_context_stays_separate_from_raw():
    pair = resolve_components(Section3Collection((_block(0, (_cas("64-17-5", 0),), (_content("10", 1, "%"),)),)))[0]
    assert (pair.content.content_raw, pair.content.content_normalized) == ("10", "10")
    assert any(item.raw_fragment == "%" for item in pair.evidence)


def test_p5_r_18_no_proximity_or_source_order_pairing_for_multiple_contents():
    pair = resolve_components(Section3Collection((_block(0, (_cas("64-17-5", 0),), (_content("10%", 1), _content("20%", 2))),)))[0]
    assert pair.status is PairStatus.PAIR_AMBIGUOUS


def test_p5_r_19_resolution_has_no_filename_or_other_section_fallback_channel():
    result = resolve_candidates(ProductCollection(), Section3Collection())
    assert (result.product.status, result.components) == (ResultStatus.NOT_FOUND, ())
