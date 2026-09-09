"""PASS/REVIEW judgement without rewriting resolver-finalized truth."""

from __future__ import annotations

from .models import (
    ComponentPair, ContentStatus, Evidence, FindingCode, FindingContext, FindingSeverity,
    ProductCandidate, ProductResult, QualityFinding, QualityReport,
    QualityStatus, ResultStatus, Section3Collection,
)
from .resolver import ResolvedCandidates


def _finding(code: FindingCode, section: str, context: FindingContext = FindingContext(), evidence: tuple[Evidence, ...] = (), raw_candidates: tuple[str, ...] = ()) -> QualityFinding:
    return QualityFinding(code, FindingSeverity.REVIEW_REQUIRED, section, context, evidence, raw_candidates)


def _product_findings(product: ProductResult, candidates: tuple[ProductCandidate, ...]) -> tuple[QualityFinding, ...]:
    if product.status is ResultStatus.NOT_FOUND:
        return (_finding(FindingCode.PRODUCT_NOT_FOUND, "1"),)
    normalized_values = {candidate.normalized for candidate in candidates if candidate.normalized}
    if product.status is ResultStatus.REVIEW or len(normalized_values) > 1:
        ordered = tuple(sorted(candidates, key=lambda item: item.source_order))
        return (_finding(
            FindingCode.PRODUCT_CANDIDATE_CONFLICT,
            "1",
            FindingContext(source_orders=tuple(item.source_order for item in ordered)),
            tuple(evidence for item in ordered for evidence in item.evidence),
            tuple(item.raw for item in ordered),
        ),)
    return ()


def _block_raw_candidates(pair: ComponentPair, section3: Section3Collection) -> tuple[str, ...]:
    block = next((item for item in section3.blocks if item.block_id == pair.block_id and item.row_id == pair.row_id), None)
    if block is not None and block.content_candidates:
        return tuple(candidate.raw for candidate in block.content_candidates)
    return (pair.content.content_raw,) if pair.content.content_raw else ()


def _component_findings(components: tuple[ComponentPair, ...], section3: Section3Collection) -> tuple[QualityFinding, ...]:
    findings: list[QualityFinding] = []
    for pair in components:
        context = FindingContext(pair.block_id or None, pair.row_id)
        if pair.cas.cas_status is ResultStatus.INVALID:
            findings.append(_finding(FindingCode.CAS_READ_UNCERTAIN, "3", context, pair.cas.evidence, (pair.cas.cas_raw,)))
        if pair.content.content_status is ContentStatus.NOT_READABLE:
            findings.append(_finding(FindingCode.CONTENT_NOT_READABLE, "3", context, pair.evidence, _block_raw_candidates(pair, section3)))
        if pair.content.content_status is ContentStatus.PAIR_AMBIGUOUS:
            findings.append(_finding(FindingCode.PAIR_AMBIGUOUS, "3", context, pair.evidence, _block_raw_candidates(pair, section3)))
    return tuple(findings)


def validate_resolved(result: ResolvedCandidates) -> QualityReport:
    """Validate a resolver result. The input is only read; it is never rebuilt."""
    if not isinstance(result, ResolvedCandidates):
        raise TypeError("VALIDATOR_REQUIRES_RESOLVED_CANDIDATES")
    findings = list(_product_findings(result.product, result.product_candidates))
    findings.extend(_component_findings(result.components, result.section3))
    if not result.components and not result.section3.explicit_zero_target_evidence:
        findings.append(_finding(FindingCode.SECTION3_EMPTY_UNVERIFIED, "3"))
    return QualityReport(QualityStatus.REVIEW_REQUIRED if findings else QualityStatus.PASS, tuple(findings))


def validate(product: ProductResult, components: tuple[ComponentPair, ...], section3: Section3Collection, product_candidates: tuple[ProductCandidate, ...] = ()) -> QualityReport:
    """Validate already-final values without any mutation or fallback lookup."""
    return validate_resolved(ResolvedCandidates(product, components, product_candidates, section3))
