"""Single final-selection authority for isolated MSDS candidates.

This module deliberately has no filename, database, network, legacy, Golden,
or AI dependency. It finalizes only the source relations observed by Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass

from .collectors import collect_product_candidates, collect_section3_candidates
from .models import (
    CASResult, CasCandidate, CasCandidateValidity, ComponentPair,
    ContentFieldState, ContentResult, ContentStatus, Evidence, FenceStatus, PairStatus,
    ProductCandidate, ProductCollection, ProductResult, ResultStatus,
    Section3BlockCandidate, Section3Collection, SectionInput,
)


@dataclass(frozen=True)
class ResolvedCandidates:
    """Finalized Phase 5 output plus candidate facts required for validation."""

    product: ProductResult
    components: tuple[ComponentPair, ...]
    product_candidates: tuple[ProductCandidate, ...]
    section3: Section3Collection


def _unique_evidence(evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    """Deduplicate an exact source fact while retaining first observed order."""
    return tuple(dict.fromkeys(evidence))


def _require_product_collection(collection: ProductCollection) -> None:
    if not isinstance(collection, ProductCollection):
        raise TypeError("RESOLVER_REQUIRES_PRODUCT_COLLECTION")


def _require_section3_collection(collection: Section3Collection) -> None:
    if not isinstance(collection, Section3Collection):
        raise TypeError("RESOLVER_REQUIRES_SECTION3_COLLECTION")


def resolve_product(collection: ProductCollection) -> ProductResult:
    """Resolve one unambiguous product value, never selecting a conflict."""
    _require_product_collection(collection)
    candidates = tuple(sorted(collection.candidates, key=lambda item: item.source_order))
    if not candidates:
        return ProductResult("", "", ResultStatus.NOT_FOUND)
    normalized_values = {candidate.normalized for candidate in candidates if candidate.normalized}
    if len(normalized_values) != 1:
        evidence = _unique_evidence(tuple(item for candidate in candidates for item in candidate.evidence))
        return ProductResult("", "", ResultStatus.REVIEW, evidence)
    selected = next(candidate for candidate in candidates if candidate.normalized)
    evidence = _unique_evidence(tuple(item for candidate in candidates for item in candidate.evidence))
    return ProductResult(selected.raw, selected.normalized, ResultStatus.FOUND, evidence)


def _cas_result(candidate: CasCandidate) -> CASResult:
    status = ResultStatus.FOUND if candidate.validity is CasCandidateValidity.VALID else ResultStatus.INVALID
    return CASResult(candidate.raw, candidate.normalized, status, candidate.evidence)


def _content_result(state: ContentFieldState, raw: str | None) -> ContentResult:
    if state is ContentFieldState.EXPLICIT_BLANK:
        return ContentResult(raw or "", "", ContentStatus.NOT_STATED)
    if state is ContentFieldState.UNREADABLE:
        return ContentResult(raw or "", "", ContentStatus.NOT_READABLE)
    return ContentResult(raw or "", "", ContentStatus.PAIR_AMBIGUOUS)


def _pair(block: Section3BlockCandidate, cas: CasCandidate, content: ContentResult, status: PairStatus, extra: tuple[Evidence, ...] = ()) -> ComponentPair:
    evidence = _unique_evidence(cas.evidence + extra + block.content_field_evidence)
    if cas.validity is not CasCandidateValidity.VALID:
        status = PairStatus.REVIEW
    return ComponentPair(_cas_result(cas), content, status, evidence, block.block_id, block.row_id)


def _resolve_block(block: Section3BlockCandidate) -> tuple[ComponentPair, ...]:
    """Use only explicit source block relationships; never proximity/order."""
    if len(block.content_candidates) == 1:
        candidate = block.content_candidates[0]
        content = ContentResult(
            candidate.raw,
            candidate.normalized,
            ContentStatus.FOUND,
            candidate.unit_context_raw,
            candidate.unit_context_evidence,
        )
        evidence = candidate.evidence + candidate.unit_context_evidence
        return tuple(_pair(block, cas, content, PairStatus.PAIRED, evidence) for cas in block.cas_candidates)
    if not block.content_candidates:
        content = _content_result(block.content_field_state, block.content_field_raw)
        pair_status = {
            ContentStatus.NOT_STATED: PairStatus.NOT_STATED,
            ContentStatus.NOT_READABLE: PairStatus.NOT_READABLE,
        }.get(content.content_status, PairStatus.PAIR_AMBIGUOUS)
        return tuple(_pair(block, cas, content, pair_status) for cas in block.cas_candidates)
    # Candidate facts remain on Section3Collection and all their evidence is
    # surfaced on the pair/finding.  A final content value must never invent a
    # synthetic joined concentration when no explicit mapping exists.
    content = ContentResult("", "", ContentStatus.PAIR_AMBIGUOUS)
    evidence = tuple(item for candidate in block.content_candidates for item in candidate.evidence + candidate.unit_context_evidence)
    return tuple(_pair(block, cas, content, PairStatus.PAIR_AMBIGUOUS, evidence) for cas in block.cas_candidates)


def resolve_components(collection: Section3Collection) -> tuple[ComponentPair, ...]:
    """Finalize each source row, preserving blocks, order, and duplicate CAS rows."""
    _require_section3_collection(collection)
    pairs: list[ComponentPair] = []
    for block in sorted(collection.blocks, key=lambda item: item.source_order):
        pairs.extend(_resolve_block(block))
    return tuple(pairs)


def resolve_candidates(product_collection: ProductCollection, section3_collection: Section3Collection) -> ResolvedCandidates:
    """Finalize candidate collections without opening any fallback channel."""
    _require_product_collection(product_collection)
    _require_section3_collection(section3_collection)
    return ResolvedCandidates(resolve_product(product_collection), resolve_components(section3_collection), product_collection.candidates, section3_collection)


def resolve(section1_input: SectionInput, section3_input: SectionInput) -> ResolvedCandidates:
    """Convenience route that accepts only collector-validated SectionInput values."""
    if not isinstance(section1_input, SectionInput) or not isinstance(section3_input, SectionInput):
        raise TypeError("RESOLVER_REQUIRES_SECTION_INPUT")
    if (
        section1_input.fence_status is not FenceStatus.FENCE_CONFIRMED
        or section3_input.fence_status is not FenceStatus.FENCE_CONFIRMED
    ):
        raise ValueError("RESOLVER_REQUIRES_CONFIRMED_FENCE")
    # Collectors also reject wrong-section and non-TEXT/OCR inputs.
    return resolve_candidates(collect_product_candidates(section1_input), collect_section3_candidates(section3_input))
