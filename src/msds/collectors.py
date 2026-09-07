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


_PRODUCT_LABEL = re.compile(r"^\s*(?:product(?:\s+(?:name|identifier))?|제품명|제품\s*식별자)\s*(?:(?::|\|)\s*(.*))?\s*$", re.IGNORECASE)
_FIELD_LABEL = re.compile(r"^\s*(?:[A-Za-z][A-Za-z /()_-]{0,40}|[가-힣][가-힣 /()_-]{0,40})\s*(?::|\|)")
_NAMED_STRUCTURAL_FIELD = re.compile(r"^\s*(?:company|supplier|manufacturer|회사명|공급(?:자|업체)|제조(?:자|업체))\b", re.IGNORECASE)
_CAS = re.compile(r"(?<!\d)(\d{2,7}\s*[-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]\s*\d{2}\s*[-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]\s*\d)(?!\d)")
_EC_CONTEXT = re.compile(r"\bEC(?:\s*(?:No\.?|number))?\s*[:|#-]?\s*$", re.IGNORECASE)
_DIRECT_CONTENT = re.compile(
    r"(?:[<>≤≥]\s*)?\d+(?:[.,]\d+)?(?:\s*[-–—~∼～]\s*(?:[<>≤≥]\s*)?\d+(?:[.,]\d+)?)?\s*(?:(?:wt|vol)\s*%|%|ppm)|Rem\.|Balance",
    re.IGNORECASE,
)
_BARE_CONTENT = re.compile(r"^(?:[<>≤≥]\s*)?\d+(?:[.,]\d+)?(?:\s*[-–—~∼～]\s*(?:[<>≤≥]\s*)?\d+(?:[.,]\d+)?)?\s*$")
_UNIT_HEADER = re.compile(r"(?<![A-Za-z])(?P<unit>wt\s*%|vol\s*%|%|ppm)(?![A-Za-z])", re.IGNORECASE)


@dataclass(frozen=True)
class _Line:
    page: int
    block: int
    line: int
    text: str
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class _UnitHeader:
    """An explicit CAS/unit table header, limited to its following table rows."""

    page: int
    row_number: int
    cas_x: float
    unit_x: float
    unit: str
    evidence: Evidence


@dataclass(frozen=True)
class _EcHeader:
    """An explicit EC/CAS table header, limited to its following table rows."""

    page: int
    row_number: int
    ec_x: float
    cas_x: float


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
    rows = _rows(section_input)
    def line_key(item: _Line) -> tuple[int, int, int, tuple[float, float, float, float]]:
        return item.page, item.block, item.line, item.bbox

    row_for_line = {line_key(item): row for row in rows for item in row}
    for line in lines:
        match = _PRODUCT_LABEL.match(line.text)
        if not match:
            continue
        values: list[_Line] = []
        inline = match.group(1) or ""
        if inline.strip():
            # The raw product value excludes only the explicit label delimiter.
            value_start = line.text.find(inline)
            values.append(_Line(line.page, line.block, line.line, line.text[value_start:], line.bbox))
        else:
            row = row_for_line[line_key(line)]
            label_index = row.index(line)
            for cell in row[label_index + 1:]:
                if _FIELD_LABEL.match(cell.text) or _NAMED_STRUCTURAL_FIELD.match(cell.text):
                    break
                values.append(cell)
        # Every supported label form can continue on later rows.  Inline
        # values deliberately do not consume a same-row right-hand cell.
        current_row_index = next(i for i, candidate_row in enumerate(rows) if any(line_key(cell) == line_key(line) for cell in candidate_row))
        for candidate_row in rows[current_row_index + 1:]:
            if any(_FIELD_LABEL.match(cell.text) or _NAMED_STRUCTURAL_FIELD.match(cell.text) for cell in candidate_row):
                break
            values.extend(candidate_row)
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


def _cas_matches(row: tuple[_Line, ...], ec_headers: list[_EcHeader]) -> list[tuple[_Line, re.Match[str]]]:
    matches: list[tuple[_Line, re.Match[str]]] = []
    for line_index, line in enumerate(row):
        for match in _CAS.finditer(line.text):
            row_prefix = " ".join(item.text for item in row[:line_index]) + " " + line.text[:match.start()]
            if _EC_CONTEXT.search(row_prefix):
                continue
            if any(line.page == header.page and abs(line.bbox[0] - header.ec_x) <= max(12.0, line.bbox[2] - line.bbox[0]) for header in ec_headers):
                continue
            raw = match.group(1)
            result = normalize_cas(raw)
            if result.validity.value == "NOT_CANDIDATE":
                continue
            matches.append((line, match))
    return matches


def _unit_headers(row: tuple[_Line, ...], section_input: SectionInput, row_number: int) -> list[_UnitHeader]:
    """Observe units only in an explicit CAS table header, never explanatory prose."""
    cas_label = next((line for line in row if re.fullmatch(r"\s*CAS(?:\s+(?:No\.?|Number))?\s*", line.text, re.IGNORECASE)), None)
    if cas_label is None:
        return []
    return [
        _UnitHeader(cas_label.page, row_number, cas_label.bbox[0], line.bbox[0], match.group("unit"), _evidence(section_input, line))
        for line in row
        if (match := _UNIT_HEADER.search(line.text)) and not _DIRECT_CONTENT.search(line.text)
    ]


def _ec_headers(row: tuple[_Line, ...], row_number: int) -> list[_EcHeader]:
    """Observe an explicit EC column only when it shares a header row with CAS."""
    ec_label = next((line for line in row if re.fullmatch(r"\s*EC\s+(?:No\.?|Number)\s*", line.text, re.IGNORECASE)), None)
    cas_label = next((line for line in row if re.fullmatch(r"\s*CAS(?:\s+(?:No\.?|Number))?\s*", line.text, re.IGNORECASE)), None)
    if ec_label is None or cas_label is None:
        return []
    return [_EcHeader(ec_label.page, row_number, ec_label.bbox[0], cas_label.bbox[0])]


def _header_for(line: _Line, headers: list[_UnitHeader]) -> tuple[str, Evidence] | None:
    if not headers:
        return None
    header = min(headers, key=lambda candidate: abs(candidate.unit_x - line.bbox[0]))
    if abs(header.unit_x - line.bbox[0]) <= max(12.0, line.bbox[2] - line.bbox[0]):
        return header.unit, header.evidence
    return None


def _content_matches(section_input: SectionInput, row: tuple[_Line, ...], has_cas: bool, headers: list[_UnitHeader]) -> list[tuple[_Line, int, str, str | None, Evidence | None]]:
    matches: list[tuple[_Line, int, str, str | None, Evidence | None]] = []
    for line in row:
        # Retain original offsets: deleting a preceding CAS would move content
        # left and corrupt page/y/x/subsequence source ordering.
        without_cas = _CAS.sub(lambda candidate: " " * len(candidate.group(0)), line.text)
        for match in _DIRECT_CONTENT.finditer(without_cas):
            raw = match.group(0)
            # Direct units belong to the raw observation; they are not header
            # context and cannot serve as unit-context evidence.
            matches.append((line, match.start(), raw, None, None))
        if has_cas and not _DIRECT_CONTENT.search(without_cas) and _BARE_CONTENT.match(line.text):
            if header := _header_for(line, headers):
                matches.append((line, 0, line.text, *header))
    return matches


def _same_table_row(row: tuple[_Line, ...], headers: list[_UnitHeader]) -> bool:
    """Keep header context only for the next aligned rows of the same table."""
    if not headers or any(line.page != headers[0].page for line in row):
        return False
    cas_header = headers[0]
    has_aligned_cas = any(
        _CAS.search(line.text) and abs(line.bbox[0] - cas_header.cas_x) <= max(12.0, line.bbox[2] - line.bbox[0])
        for line in row
    )
    has_aligned_unit_column = any(_header_for(line, headers) for line in row)
    return has_aligned_cas and has_aligned_unit_column


def _same_ec_table_row(row: tuple[_Line, ...], headers: list[_EcHeader]) -> bool:
    """Keep EC-column exclusion scoped to aligned rows of its own table."""
    if not headers or any(line.page != headers[0].page for line in row):
        return False
    header = headers[0]
    return any(
        _CAS.search(line.text)
        and min(abs(line.bbox[0] - header.ec_x), abs(line.bbox[0] - header.cas_x)) <= max(12.0, line.bbox[2] - line.bbox[0])
        for line in row
    )


def collect_section3_candidates(section_input: SectionInput) -> Section3Collection:
    """Collect ordered Section 3 source rows without creating ComponentPair values."""
    _require_confirmed_text_input(section_input, "3")
    blocks: list[Section3BlockCandidate] = []
    source_order = 0
    headers: list[_UnitHeader] = []
    ec_headers: list[_EcHeader] = []
    for row_number, row in enumerate(_rows(section_input)):
        if row_headers := _unit_headers(row, section_input, row_number):
            headers = row_headers
        elif headers and not _same_table_row(row, headers):
            headers = []
        if row_ec_headers := _ec_headers(row, row_number):
            ec_headers = row_ec_headers
        elif ec_headers and not _same_ec_table_row(row, ec_headers):
            ec_headers = []
        cas_matches = _cas_matches(row, ec_headers)
        content_matches = _content_matches(section_input, row, bool(cas_matches), headers)
        occurrences = [(line, match.start(), "cas", match) for line, match in cas_matches]
        occurrences += [(line, start, "content", (raw, unit, unit_evidence)) for line, start, raw, unit, unit_evidence in content_matches]
        occurrences.sort(key=lambda item: (item[0].page, item[0].bbox[1], item[0].bbox[0], item[1]))
        cas_candidates: list[CasCandidate] = []
        content_candidates: list[ContentCandidate] = []
        for line, _position, kind, payload in occurrences:
            if kind == "cas":
                match = payload
                raw = match.group(1)
                result = normalize_cas(raw)
                cas_candidates.append(CasCandidate(raw, result.normalized, CasCandidateValidity(result.validity.value), source_order, (_evidence(section_input, line),)))
            else:
                raw, unit, unit_evidence = payload
                content_candidates.append(ContentCandidate(raw, normalize_content(raw).content_normalized, source_order, (_evidence(section_input, line),), unit, (unit_evidence,) if unit_evidence else ()))
            source_order += 1
        # A content-only row has no component/block candidate in this stage.
        if not cas_candidates:
            continue
        row_evidence = tuple(_evidence(section_input, line) for line in row)
        first = row[0]
        blocks.append(Section3BlockCandidate(
            f"section3-page-{first.page}-block-{first.block}",
            f"section3-row-{row_number}", len(blocks), row_evidence,
            tuple(cas_candidates), tuple(content_candidates),
        ))
    return Section3Collection(tuple(blocks))
