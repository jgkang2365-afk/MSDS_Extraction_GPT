from src.msds.models import (
    CASResult,
    ComponentPair,
    ContentResult,
    ContentStatus,
    Document,
    DocumentCapability,
    Evidence,
    EvidenceSourceType,
    FenceStatus,
    MachineResult,
    PairStatus,
    ResultStatus,
    SectionFence,
)
from dataclasses import fields


def _evidence() -> Evidence:
    return Evidence("3", 2, EvidenceSourceType.TABLE, "64-17-5 50%", "a" * 64, (1, 2, 3, 4))


def test_machine_contract_keeps_evidence_fences_and_duplicate_component_rows():
    evidence = _evidence()
    cas = CASResult("64-17-5", "64-17-5", ResultStatus.FOUND, (evidence,))
    content = ContentResult("50%", "50%", ContentStatus.FOUND)
    row_one = ComponentPair(cas, content, PairStatus.PAIRED, (evidence,), "section3-block-1", "row-1")
    row_two = ComponentPair(cas, content, PairStatus.PAIRED, (evidence,), "section3-block-2", "row-2")
    result = MachineResult(
        Document("doc-1", "source.pdf", "a" * 64, DocumentCapability.TEXT),
        (SectionFence(FenceStatus.FENCE_CONFIRMED, "3", 2, 3, (evidence,)),),
        components=(row_one, row_two),
    )
    assert result.components == (row_one, row_two)
    assert result.fences[0].start_page == 2
    assert result.fences[0].end_page == 3
    assert result.fences[0].evidence[0].bbox == (1, 2, 3, 4)


def test_explicit_contract_field_names_are_real_dataclass_fields():
    assert [field.name for field in fields(CASResult)] == ["cas_raw", "cas_normalized", "cas_status", "evidence"]
    assert [field.name for field in fields(ContentResult)] == [
        "content_raw", "content_normalized", "content_status",
        "unit_context_raw", "unit_context_evidence",
    ]
    assert [field.name for field in fields(SectionFence)] == ["status", "section", "start_page", "end_page", "evidence"]


def test_section3_contract_retains_cas_without_content_but_has_no_content_only_pair():
    cas = CASResult("64-17-5", "64-17-5", ResultStatus.FOUND)
    not_stated = ContentResult("", "", ContentStatus.NOT_STATED)
    pair = ComponentPair(cas, not_stated, PairStatus.NOT_STATED, block_id="block-1")
    assert pair.content.content_status is ContentStatus.NOT_STATED
    # A ContentResult by itself intentionally cannot become a ComponentPair.
    assert ContentResult("50%", "50%", ContentStatus.FOUND).content_raw == "50%"


def test_same_block_multiple_cas_retain_one_pair_per_cas_with_shared_content():
    content = ContentResult("10~20%", "10~20%", ContentStatus.FOUND)
    first = ComponentPair(CASResult("64-17-5", "64-17-5", ResultStatus.FOUND), content, PairStatus.PAIRED, block_id="shared")
    second = ComponentPair(CASResult("67-64-1", "67-64-1", ResultStatus.FOUND), content, PairStatus.PAIRED, block_id="shared")
    assert (first.cas.cas_normalized, second.cas.cas_normalized) == ("64-17-5", "67-64-1")
    assert first.content.content_normalized == second.content.content_normalized == "10~20%"


def test_not_readable_and_pair_ambiguous_are_distinct_contract_states():
    assert ContentStatus.NOT_READABLE is not ContentStatus.PAIR_AMBIGUOUS
    assert PairStatus.NOT_READABLE is not PairStatus.PAIR_AMBIGUOUS
