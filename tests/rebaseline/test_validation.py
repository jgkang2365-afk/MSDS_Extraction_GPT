from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.msds.models import (
    CasCandidate, CasCandidateValidity, ContentCandidate, ContentFieldState,
    Evidence, EvidenceSourceType, FindingCode, FindingSeverity, ProductCandidate,
    ProductCollection, QualityStatus, Section3BlockCandidate, Section3Collection,
)
from src.msds.resolver import resolve_candidates
from src.msds.validation import validate, validate_resolved


def _evidence(raw: str) -> Evidence:
    return Evidence("3", 0, EvidenceSourceType.TEXT, raw, "b" * 64)


def _cas(raw: str, validity: CasCandidateValidity = CasCandidateValidity.VALID) -> CasCandidate:
    return CasCandidate(raw, raw, validity, 0, (_evidence(raw),))


def _content(raw: str) -> ContentCandidate:
    return ContentCandidate(raw, raw, 1, (_evidence(raw),))


def _block(cas: CasCandidate, content: tuple[ContentCandidate, ...] = (), state: ContentFieldState = ContentFieldState.UNKNOWN, raw: str | None = None) -> Section3BlockCandidate:
    return Section3BlockCandidate("block", "row", 0, (_evidence("row"),), (cas,), content, state, raw)


def _resolved(product: ProductCollection = ProductCollection((ProductCandidate("A", "a", 0, (_evidence("A"),)),)), section3: Section3Collection | None = None):
    return resolve_candidates(product, section3 or Section3Collection((_block(_cas("64-17-5"), (_content("10%"),)),)))


def test_p5_v_01_clean_final_result_passes():
    assert validate_resolved(_resolved()).status is QualityStatus.PASS


def test_p5_v_02_product_not_found_is_typed_review_finding():
    report = validate_resolved(_resolved(ProductCollection()))
    assert report.status is QualityStatus.REVIEW_REQUIRED and report.findings[0].code is FindingCode.PRODUCT_NOT_FOUND


def test_p5_v_03_product_conflict_preserves_raw_candidates_and_evidence():
    products = ProductCollection((ProductCandidate("A", "a", 0, (_evidence("A"),)), ProductCandidate("B", "b", 1, (_evidence("B"),))))
    finding = validate_resolved(_resolved(products)).findings[0]
    assert (finding.code, finding.raw_candidates, len(finding.evidence)) == (FindingCode.PRODUCT_CANDIDATE_CONFLICT, ("A", "B"), 2)


def test_p5_v_04_empty_section3_without_positive_zero_target_evidence_requires_review():
    report = validate_resolved(_resolved(section3=Section3Collection()))
    assert report.findings[-1].code is FindingCode.SECTION3_EMPTY_UNVERIFIED


def test_p5_v_05_positive_zero_target_evidence_allows_empty_components():
    report = validate_resolved(_resolved(section3=Section3Collection((), (_evidence("No ingredients"),))))
    assert report.status is QualityStatus.PASS


def test_p5_v_06_invalid_cas_is_cas_read_uncertain():
    report = validate_resolved(_resolved(section3=Section3Collection((_block(_cas("64-17-4", CasCandidateValidity.CHECK_DIGIT_INVALID), (_content("10%"),)),))))
    assert report.findings[0].code is FindingCode.CAS_READ_UNCERTAIN


def test_p5_v_07_unreadable_content_is_content_not_readable():
    report = validate_resolved(_resolved(section3=Section3Collection((_block(_cas("64-17-5"), state=ContentFieldState.UNREADABLE, raw="[bad OCR]"),))))
    assert report.findings[0].code is FindingCode.CONTENT_NOT_READABLE


def test_p5_v_08_ambiguous_content_mapping_is_pair_ambiguous():
    report = validate_resolved(_resolved(section3=Section3Collection((_block(_cas("64-17-5"), (_content("10%"), _content("20%"))),))))
    assert report.findings[0].code is FindingCode.PAIR_AMBIGUOUS


def test_p5_v_09_validator_never_changes_final_result():
    result = _resolved(section3=Section3Collection((_block(_cas("64-17-4", CasCandidateValidity.CHECK_DIGIT_INVALID), (_content("10%"),)),)))
    before = (result.product, result.components, result.section3)
    validate_resolved(result)
    assert (result.product, result.components, result.section3) == before


def test_p5_v_10_findings_use_authoritative_code_and_review_severity():
    finding = validate_resolved(_resolved(ProductCollection())).findings[0]
    assert (finding.code.value, finding.severity) == ("PRODUCT_NOT_FOUND", FindingSeverity.REVIEW_REQUIRED)


def test_p5_v_11_multiple_independent_findings_are_retained_in_order():
    report = validate_resolved(_resolved(ProductCollection(), Section3Collection((_block(_cas("64-17-4", CasCandidateValidity.CHECK_DIGIT_INVALID), state=ContentFieldState.UNREADABLE, raw="?"),))))
    assert [item.code for item in report.findings] == [FindingCode.PRODUCT_NOT_FOUND, FindingCode.CAS_READ_UNCERTAIN, FindingCode.CONTENT_NOT_READABLE]


def test_p5_v_12_result_and_report_are_immutable_and_validate_accepts_final_values():
    result = _resolved()
    report = validate(result.product, result.components, result.section3, result.product_candidates)
    with pytest.raises(FrozenInstanceError):
        report.status = QualityStatus.PASS  # type: ignore[misc]
    assert report.status is QualityStatus.PASS
