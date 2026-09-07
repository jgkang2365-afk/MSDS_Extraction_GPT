"""Local, candidate-only collectors for confirmed digital SectionInput values."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .models import (
    CasCandidate,
    CasCandidateValidity,
    ContentCandidate,
    DocumentCapability,
    Evidence,
    EvidenceSourceType,
    LayoutToken,
    ProductCandidate,
    ProductCollection,
    Section3BlockCandidate,
    Section3Collection,
    SectionInput,
)
from .normalization import normalize_cas, normalize_content, normalize_product


_PRODUCT_LABEL = re.compile(r"^\s*product(?:\s+name)?\s*(?::|\|)\s*(.*)$", re.IGNORECASE)
_FIELD_LABEL = re.compile(r"^\s*[A-Za-z][A-Za-z /()_-]{1,40}(?::|\|)\s*\S")
_CAS = re.compile(r"(?<!\d)(\d{2,7}\s*[-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]\s*\d{2}\s*[-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]\s*\d)(?!\d)")
_EC_CONTEXT = re.compile(r"\bEC(?:\s*(?:No\.?|number))?\s*[:|#-]?\s*$", re.IGNORECASE)
_CONTENT = re.compile(
    r"(?:[<>≤≥]\s*)?(?:\d+(?:[.,]\d+)?\s*(?:[-–—~∼～]\s*(?:[<>≤≥]\s*)?\d+(?:[.,]\d+)?\s*)?%|"
    r"\d+(?:[.,]\d+)?\s*(?:wt|vol)\s*%|Rem\.|Balance)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Line:
    page: int
    block: int
    line: int
    text: str
    bbox: tuple[float, float, float, float]


def _require_confirmed_text_input(section_input: SectionInput, section_no: str) -> None:
    """Reject every non-SectionInput, unconfirmed, non-text, or wrong-section call."""
    if not isinstance(section_input, SectionInput):
        raise TypeError("COLLECTOR_REQUIRES_SECTION_INPUT")
    if section_input.capability is not DocumentCapability.TEXT:
        raise ValueError("COLLECTOR_REQUIRES_TEXT_CAPABILITY")
    if section_input.section_no != section_no:
        raise ValueError(f"COLLECTOR_REQUIRES_SECTION_{section_no}")


def _lines(section_input: SectionInput) -> tuple[_Line, ...]:
    grouped: dict[tuple[int, int, int], list[LayoutToken]] = {}
    for token in section_input.tokens:
        grouped.setdefault((token.page_index, token.block_id, token.line_id), []).append(token)
    lines = []
    for (page, block, line), tokens in grouped.items():
        ordered = sorted(tokens, key=lambda token: (token.bbox[0], token.bbox[1], token.token_id))
        lines.append(_Line(
            page, block, line, "".join(token.text for token in ordered),
            (min(token.bbox[0] for token in tokens), min(token.bbox[1] for token in tokens),
             max(token.bbox[2] for token in tokens), max(token.bbox[3] for token in tokens)),
        ))
    return tuple(sorted(lines, key=lambda item: (item.page, item.bbox[1], item.bbox[0], item.block, item.line)))


def _evidence(section_input: SectionInput, line: _Line) -> Evidence:
    return Evidence(section_input.section_no, line.page, EvidenceSourceType.TEXT, line.text, section_input.document_sha256, line.bbox)


def collect_product_candidates(section_input: SectionInput) -> ProductCollection:
    """Collect only explicit Section 1 product labels and their source values."""
    _require_confirmed_text_input(section_input, "1")
    lines = _lines(section_input)
    candidates: list[ProductCandidate] = []
    for index, line in enumerate(lines):
        match = _PRODUCT_LABEL.match(line.text)
        if not match:
            continue
        values: list[_Line] = []
        inline = match.group(1)
        if inline:
            # The raw product value excludes only the explicit label delimiter.
            value_start = line.text.find(inline)
            values.append(_Line(line.page, line.block, line.line, line.text[value_start:], line.bbox))
        else:
            for following in lines[index + 1:]:
                if _FIELD_LABEL.match(following.text):
                    break
                values.append(following)
        if not values:
            continue
        raw = "\n".join(value.text for value in values)
        if not raw.strip():
            continue
        normalized = normalize_product(raw).normalized
        evidence = tuple(_evidence(section_input, value) for value in values)
        candidates.append(ProductCandidate(raw, normalized, len(candidates), evidence))
    return ProductCollection(tuple(candidates))


def _rows(section_input: SectionInput) -> tuple[tuple[_Line, ...], ...]:
    """Use shared visual baselines as source rows while retaining every cell."""
    rows: list[list[_Line]] = []
    for line in _lines(section_input):
        if rows and rows[-1][0].page == line.page and abs(rows[-1][0].bbox[1] - line.bbox[1]) <= 1.0:
            rows[-1].append(line)
        else:
            rows.append([line])
    return tuple(tuple(sorted(row, key=lambda item: (item.bbox[0], item.block, item.line))) for row in rows)


def _cas_candidates(section_input: SectionInput, row: tuple[_Line, ...], order: int) -> tuple[CasCandidate, ...]:
    candidates: list[CasCandidate] = []
    for line_index, line in enumerate(row):
        for match in _CAS.finditer(line.text):
            row_prefix = " ".join(item.text for item in row[:line_index]) + " " + line.text[:match.start()]
            if _EC_CONTEXT.search(row_prefix):
                continue
            raw = match.group(1)
            result = normalize_cas(raw)
            if result.validity.value == "NOT_CANDIDATE":
                continue
            candidates.append(CasCandidate(raw, result.normalized, CasCandidateValidity(result.validity.value), order + len(candidates), (_evidence(section_input, line),)))
    return tuple(candidates)


def _content_candidates(section_input: SectionInput, row: tuple[_Line, ...], order: int) -> tuple[ContentCandidate, ...]:
    candidates: list[ContentCandidate] = []
    for line in row:
        # CAS substrings are structural keys, never concentration text.
        without_cas = _CAS.sub("", line.text)
        for match in _CONTENT.finditer(without_cas):
            raw = match.group(0)
            if not raw.strip():
                continue
            normalized = normalize_content(raw).content_normalized
            candidates.append(ContentCandidate(raw, normalized, order + len(candidates), (_evidence(section_input, line),)))
    return tuple(candidates)


def collect_section3_candidates(section_input: SectionInput) -> Section3Collection:
    """Collect ordered Section 3 source rows without creating ComponentPair values."""
    _require_confirmed_text_input(section_input, "3")
    blocks: list[Section3BlockCandidate] = []
    source_order = 0
    for row_number, row in enumerate(_rows(section_input)):
        cas_candidates = _cas_candidates(section_input, row, source_order)
        content_candidates = _content_candidates(section_input, row, source_order + len(cas_candidates))
        source_order += len(cas_candidates) + len(content_candidates)
        # A content-only row has no component/block candidate in this stage.
        if not cas_candidates:
            continue
        row_evidence = tuple(_evidence(section_input, line) for line in row)
        first = row[0]
        blocks.append(Section3BlockCandidate(
            f"section3-page-{first.page}-block-{first.block}",
            f"section3-row-{row_number}", len(blocks), row_evidence,
            cas_candidates, content_candidates,
        ))
    return Section3Collection(tuple(blocks))
