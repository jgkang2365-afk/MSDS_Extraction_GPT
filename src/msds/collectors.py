"""Local, candidate-only collectors for confirmed TEXT/OCR SectionInput values."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .models import (
    CasCandidate,
    CasCandidateValidity,
    ContentCandidate,
    ContentFieldState,
    DocumentCapability,
    Evidence,
    EvidenceSourceType,
    FenceStatus,
    LayoutToken,
    ProductCandidate,
    ProductCollection,
    Section3BlockCandidate,
    Section3Collection,
    SectionInput,
)
from .normalization import normalize_cas, normalize_content, normalize_product


_PRODUCT_LABEL = re.compile(r"^\s*(?:[A-Za-z가-하]\.\s*)?(?:product(?:\s+(?:name|identifier))?|제\s*품\s*명|제품\s*식별자|물질명)\s*(?:(?::|\|)\s*(.*))?\s*$", re.IGNORECASE)
_SECTION_ONE_NON_PRODUCT_LABEL = (
    r"(?:"
    r"(?:company|supplier|manufacturer|distributor|importer)(?:\s*(?:name|information|details?|address))?"
    r"|(?:product\s*(?:number|no\.?|identifier|id|code)|catalog(?:ue)?\s*(?:no\.?|number|code))"
    r"|(?:reference\s*(?:number|no\.?|code)(?:\s*\([^)]*\))?|product\s*type)"
    r"|(?:synonyms?|trade\s*names?|other\s+means\s+of\s+identification)"
    r"|(?:emergency\s*(?:telephone|phone|contact|number)|contact\s*(?:information|details?|person))"
    r"|(?:recommended\s+use(?:\s+and\s+restrictions?\s+on\s+use)?|restrictions?\s+on\s+use)"
    r"|회사(?:명|정보|주소)?|공급(?:자|업체|회사|자명|자\s*정보)?|제조(?:자|업체|회사|자명|자\s*정보)?"
    r"|유통(?:사|업체|회사|자)?|수입(?:자|업체|회사)?|판매(?:원|자|업체|회사)?"
    r"|제품\s*(?:번호|식별(?:자|번호)?|코드)|(?:긴급|응급)\s*(?:연락처|전화(?:번호)?)"
    r"|동의어(?:\s*/\s*상품명)?|상품명"
    r"|(?:색상|colour|color|용도(?:분류)?)"
    r"|제품(?:의)?\s*(?:권고\s*용도(?:와\s*사용상(?:의)?\s*제[한핚])?|용도|사용상(?:의)?\s*제[한핚])|사용상(?:의)?\s*제[한핚]"
    r"|(?:제조(?:자)?|공급(?:자)?|유통(?:업자|사|업체|회사|자)?)(?:\s*/\s*(?:제조(?:자)?|공급(?:자)?|유통(?:업자|사|업체|회사|자)?)){1,2}\s*정보"
    r")"
)
_SECTION_ONE_FIELD_PREFIX = rf"(?:[A-Za-z가-하]\.\s*)?{_SECTION_ONE_NON_PRODUCT_LABEL}"
_FIELD_LABEL = re.compile(rf"^\s*{_SECTION_ONE_FIELD_PREFIX}\s*(?::|\|)", re.IGNORECASE)
_FIELD_LABEL_NAME = re.compile(rf"^\s*{_SECTION_ONE_FIELD_PREFIX}\s*$", re.IGNORECASE)
_FIELD_VALUE_DELIMITER = re.compile(r"^\s*(?::|\|)\s*\S")
_CAS = re.compile(r"(?<!\d)(\d{2,7}\s*[-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]\s*\d{2}\s*[-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]\s*\d)(?!\d)")
_CAS_TOKEN_PUNCTUATION = frozenset("_-\u2010\u2011\u2012\u2013\u2014\u2015\u2212")
_EC_CONTEXT = re.compile(r"(?:\bEC(?:\s*(?:No\.?|number))?|E\s*C\s*번호)\s*[:|#-]?\s*$", re.IGNORECASE)
_NON_CAS_IDENTIFIER_LABEL = re.compile(
    r"\s*(?:E\s*C\s*번호|EINECS(?:\s*(?:No\.?|number))?|색인\s*번호|index\s+number)\s*[:|#-]?\s*$",
    re.IGNORECASE,
)
# These terms have document meaning, unlike lexical CAS validation.  Keep
# them at collection time where the preceding row/cell context is available.
_DATE_METADATA_LABEL = re.compile(
    r"\s*(?:\b(?:revision|issue|prepared|effective|release|publication|print)"
    r"(?:\s+date)?\b|\bdate\b|(?:작성|개정|제조|발행|발급|검토|준비)\s*(?:일(?:자)?|날짜)|날짜)\s*[:|#-]?\s*$",
    re.IGNORECASE,
)
_DATE_METADATA_INLINE_VALUE = re.compile(
    r"^\s*(?:\b(?:revision|issue|prepared|effective|release|publication|print)"
    r"(?:\s+date)?\b|\bdate\b|(?:작성|개정|제조|발행|발급|검토|준비)\s*(?:일(?:자)?|날짜)|날짜)\s*[:|#-]\s*\S.+?\s*$",
    re.IGNORECASE,
)
_PEER_METADATA_LABEL = re.compile(
    r"^\s*(?:[가-힣\s]*(?:부서|정보|구분|번호|작성자|검토자|승인자)|"
    r"(?:document|department|prepared\s+by|reviewed\s+by|approved\s+by|information))\s*[:|]?\s*$",
    re.IGNORECASE,
)
_CAS_CONTEXT = re.compile(r"\s*C\s*A\s*S\s*(?:(?:No\.?|Number)\s*)?[:|]?\s*$", re.IGNORECASE)
_STRUCTURED_IDENTIFIER_VALUE = re.compile(r"\s*[A-Za-z][A-Za-z0-9]*(?:[-_/][A-Za-z0-9]+)+\s*\Z")
_CAS_TABLE_HEADER = re.compile(
    r"^\s*C\s*A\s*S\s*(?:(?:No\.?|Number)|(?:번호(?:\s*또는\s*식별번호)?)|식별번호)?\s*$",
    re.IGNORECASE,
)
_DATE_METADATA_ADJACENCY_Y_TOLERANCE = 36.0
_DIRECT_CONTENT = re.compile(
    r"(?:(?:>=|<=|[<>≤≥])\s*)?\d+(?:[.,]\d+)?(?:\s*[-–—~∼～]\s*(?:(?:>=|<=|[<>≤≥])\s*)?\d+(?:[.,]\d+)?)?\s*(?:(?:wt|vol)\s*[%％]|[%％]|ppm)|Rem\.|Balance",
    re.IGNORECASE,
)
_BARE_CONTENT = re.compile(r"^(?:(?:>=|<=|[<>≤≥])\s*)?\d+(?:[.,]\d+)?(?:\s*[-–—~∼～]\s*(?:(?:>=|<=|[<>≤≥])\s*)?\d+(?:[.,]\d+)?)?\s*$")
_UNIT_HEADER = re.compile(r"(?<![A-Za-z])(?P<unit>wt\s*[%％]|vol\s*[%％]|[%％]|ppm)(?![A-Za-z])", re.IGNORECASE)
_UNREADABLE_CONTENT = re.compile(r"^\s*\[?(?:unreadable|illegible|not\s+readable|판독\s*불가|식별\s*불가)\]?\s*$", re.IGNORECASE)
_NAMED_COMPONENT = re.compile(r"^\s*(?:성\s*분|component|ingredient(?:\s+name)?|chemical\s+name)\s*[:|]\s*.+$", re.IGNORECASE)
_NAMED_CAS = re.compile(r"^\s*C\s*A\s*S\s*(?:(?:No\.?|Number)\s*)?[:|]\s*(?P<value>.+?)\s*$", re.IGNORECASE)
_NAMED_CONTENT = re.compile(r"^\s*(?:함\s*유\s*량|content(?:\s*\([^)]*\))?|concentration(?:\s*\([^)]*\))?)\s*[:|]\s*(?P<value>.+?)\s*$", re.IGNORECASE)
_NAMED_BLOCK_BOUNDARY = re.compile(r"^\s*(?:note\b|remarks?\b|비고\s*:?|주\s*:)", re.IGNORECASE)
_KOREAN_CONTENT_START = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*(?:이상|초과)\s*[~∼～]\s*$")
_KOREAN_CONTENT_END = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*[%％]?\s*(?:미만|이하)\s*$")
# A header-proven concentration cell can retain a source spelling that the
# semantic comparator normalizer does not recognize.  This only proves that a
# numeric range belongs to the explicit content column; it never searches
# free text or an identifier cell for a number.
_HEADER_PROVEN_CONTENT = re.compile(
    r"^\s*(?:(?:>=|<=|[<>≤≥])\s*)?\d+(?:[.,]\d+)?"
    r"(?:\s*[-–—~∼～]\s*(?:(?:>=|<=|[<>≤≥])\s*)?\d+(?:[.,]\d+)?)?"
    r"(?:\s*[%％])?(?:\s*[가-힣]+)?\s*$"
)
_HEADER_X_TOLERANCE = 12.0


@dataclass(frozen=True)
class _Line:
    page: int
    block: int
    line: int
    text: str
    bbox: tuple[float, float, float, float]
    source_type: EvidenceSourceType


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


def _is_ec_column(line: _Line, header: _EcHeader) -> bool:
    """Match only the EC side of an explicit EC/CAS header boundary."""
    midpoint = (header.ec_x + header.cas_x) / 2
    return header.ec_x - _HEADER_X_TOLERANCE <= line.bbox[0] < midpoint


def _is_cas_column(line: _Line, cas_x: float) -> bool:
    """Allow only small PDF start-coordinate drift from an explicit CAS header."""
    # Individual CAS cells in a visually single PDF column can drift slightly
    # beyond the general header tolerance because of glyph metrics.  This
    # remains far narrower than an adjacent table column while preserving the
    # established TECA multi-CAS source row.
    return abs(line.bbox[0] - cas_x) <= _HEADER_X_TOLERANCE + 2.0


def _require_confirmed_text_input(section_input: SectionInput, section_no: str) -> None:
    """Reject every non-SectionInput, non-isolated, or wrong-section call."""
    if not isinstance(section_input, SectionInput):
        raise TypeError("COLLECTOR_REQUIRES_SECTION_INPUT")
    if section_input.capability not in {DocumentCapability.TEXT, DocumentCapability.OCR}:
        raise ValueError("COLLECTOR_REQUIRES_TEXT_OR_OCR_CAPABILITY")
    if section_input.fence_status is not FenceStatus.FENCE_CONFIRMED:
        raise ValueError("COLLECTOR_REQUIRES_CONFIRMED_FENCE")
    if section_input.section_no != section_no:
        raise ValueError(f"COLLECTOR_REQUIRES_SECTION_{section_no}")


def _lines(section_input: SectionInput) -> tuple[_Line, ...]:
    grouped: dict[tuple[int, int, int], list[LayoutToken]] = {}
    for token in section_input.tokens:
        grouped.setdefault((token.page_index, token.block_id, token.line_id), []).append(token)
    lines = []
    for (page, block, line), tokens in grouped.items():
        ordered = sorted(tokens, key=lambda token: (token.bbox[0], token.bbox[1], token.token_id))
        source_type = EvidenceSourceType.OCR if any(token.source_reading == "OCR" for token in tokens) else EvidenceSourceType.TEXT
        if any((token.source_reading == "OCR") != (source_type is EvidenceSourceType.OCR) for token in tokens):
            raise ValueError("SECTION_INPUT_MIXED_LINE_SOURCE")
        lines.append(_Line(
            page, block, line, "".join(token.text for token in ordered),
            (min(token.bbox[0] for token in tokens), min(token.bbox[1] for token in tokens),
             max(token.bbox[2] for token in tokens), max(token.bbox[3] for token in tokens)),
            source_type,
        ))
    return tuple(sorted(lines, key=lambda item: (item.page, item.bbox[1], item.bbox[0], item.block, item.line)))


def _evidence(section_input: SectionInput, line: _Line) -> Evidence:
    return Evidence(section_input.section_no, line.page, line.source_type, line.text, section_input.document_sha256, line.bbox)


def _product_value_before_next_field(value: str) -> str:
    """Keep an inline value before the next semantic Section 1 field label."""
    for index in range(1, len(value)):
        previous, current = value[index - 1], value[index]
        crosses_script = (previous.isascii() and previous.isalnum() and "가" <= current <= "힣") or (
            "가" <= previous <= "힣" and current.isascii() and current.isalnum()
        )
        if not (previous.isspace() or crosses_script):
            continue
        if _FIELD_LABEL.match(value[index:]):
            return value[:index].rstrip()
    return value


def _is_split_section_one_field(row: tuple[_Line, ...], next_row: tuple[_Line, ...] | None) -> bool:
    """Recognize an explicit field label whose delimiter/value is on the next row."""
    return (
        next_row is not None
        and any(_FIELD_LABEL_NAME.match(cell.text) for cell in row)
        and any(_FIELD_VALUE_DELIMITER.match(cell.text) for cell in next_row)
    )


def _starts_next_section_one_field(row: tuple[_Line, ...], next_row: tuple[_Line, ...] | None) -> bool:
    """Recognize both inline and split explicit Section 1 label/value fields."""
    return (
        any(_FIELD_LABEL.match(cell.text) or _FIELD_LABEL_NAME.match(cell.text) for cell in row)
        or _is_split_section_one_field(row, next_row)
    )


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
        inline_source = match.group(1) or ""
        # Inline labelled values have no separate visual cell whose edge is
        # meaningful.  Trim only their terminal layout padding; multiline and
        # separate-cell raw fragments remain lossless below.
        inline = _product_value_before_next_field(inline_source).rstrip()
        if inline.strip():
            # The raw product value excludes only the explicit label delimiter.
            value_start = line.text.find(inline_source)
            values.append(_Line(
                line.page, line.block, line.line,
                line.text[value_start:value_start + len(inline)], line.bbox,
                line.source_type,
            ))
        else:
            row = row_for_line[line_key(line)]
            label_index = row.index(line)
            for cell in row[label_index + 1:]:
                if _starts_next_section_one_field((cell,), None):
                    break
                values.append(cell)
                # A discrete label/value cell is a complete same-row product
                # relation.  Further columns belong to independent fields and
                # must not be folded into the product merely by reading order.
                break
        # Every supported label form can continue on later rows.  Inline
        # values deliberately do not consume a same-row right-hand cell.
        current_row_index = next(i for i, candidate_row in enumerate(rows) if any(line_key(cell) == line_key(line) for cell in candidate_row))
        for row_index, candidate_row in enumerate(rows[current_row_index + 1:], start=current_row_index + 1):
            next_row = rows[row_index + 1] if row_index + 1 < len(rows) else None
            if _starts_next_section_one_field(candidate_row, next_row) or any(_PRODUCT_LABEL.match(cell.text) for cell in candidate_row):
                if values and _is_split_section_one_field(candidate_row, next_row):
                    for value_index in range(len(values) - 1, -1, -1):
                        last = values[value_index]
                        if last.text.strip():
                            values[value_index] = _Line(
                                last.page, last.block, last.line, last.text.rstrip(),
                                last.bbox, last.source_type,
                            )
                            break
                break
            values.extend(candidate_row)
        # A visual continuation made only of whitespace is not a product
        # value.  Exclude that source cell before raw joining so the product
        # fact and its provenance identify the same meaningful source span.
        # Do not trim non-empty cells: their raw source text remains lossless.
        values = [value for value in values if value.text.strip()]
        if values and (delimiter := re.match(r"^\s*[:|]\s*(?P<value>.+)$", values[0].text)):
            first = values[0]
            values[0] = _Line(first.page, first.block, first.line, delimiter.group("value"), first.bbox, first.source_type)
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
    """Use overlapping visual row bands, retaining wrapped cells as one source row."""
    rows: list[list[_Line]] = []
    for line in _lines(section_input):
        if rows and rows[-1][0].page == line.page and any(
            max(existing.bbox[1], line.bbox[1]) < min(existing.bbox[3], line.bbox[3])
            for existing in rows[-1]
        ):
            rows[-1].append(line)
        else:
            rows.append([line])
    return tuple(tuple(sorted(row, key=lambda item: (item.bbox[0], item.block, item.line))) for row in rows)


def _is_cas_token_character(character: str) -> bool:
    return character.isalnum() or character in _CAS_TOKEN_PUNCTUATION


def _cas_token_span(text: str, match: re.Match[str]) -> tuple[int, int]:
    """Expand a CAS-shaped substring to its unbroken source token."""
    start, end = match.span(1)
    while start and _is_cas_token_character(text[start - 1]):
        start -= 1
    while end < len(text) and _is_cas_token_character(text[end]):
        end += 1
    return start, end


def _nearest_field_context(row: tuple[_Line, ...], line_index: int, line_prefix: str) -> str | None:
    """Return only the field label local to this candidate, never a stale row label."""
    if _DATE_METADATA_LABEL.search(line_prefix) is not None:
        return "DATE"
    if _CAS_CONTEXT.fullmatch(line_prefix) is not None:
        return "CAS"
    for line in reversed(row[:line_index]):
        if _DATE_METADATA_LABEL.fullmatch(line.text) is not None:
            return "DATE"
        if _CAS_CONTEXT.fullmatch(line.text) is not None:
            return "CAS"
    return None


def _date_label_has_same_row_value(row: tuple[_Line, ...], label_index: int) -> bool:
    """Determine completion for one date field, never for the entire row."""
    label = row[label_index]
    if _DATE_METADATA_INLINE_VALUE.fullmatch(label.text) is not None:
        return True
    next_cell = row[label_index + 1] if label_index + 1 < len(row) else None
    return bool(
        _DATE_METADATA_LABEL.fullmatch(label.text) is not None
        and next_cell is not None
        and next_cell.text.strip()
        and _PEER_METADATA_LABEL.fullmatch(next_cell.text) is None
        and _DATE_METADATA_LABEL.fullmatch(next_cell.text) is None
        and _DATE_METADATA_INLINE_VALUE.fullmatch(next_cell.text) is None
        and _CAS_CONTEXT.fullmatch(next_cell.text) is None
    )


def _cas_matches(
    row: tuple[_Line, ...], ec_headers: list[_EcHeader], headers: list[_UnitHeader],
    previous_row: tuple[_Line, ...] | None = None,
) -> list[tuple[_Line, int, str]]:
    matches: list[tuple[_Line, int, str]] = []
    for line_index, line in enumerate(row):
        # A proven CAS/content table is also a proof boundary for candidate
        # admission.  Do not promote a CAS-shaped substring from an ingredient,
        # reference, exposure, or note column merely because its row belongs to
        # that table.  Headerless named-field and free-form paths retain their
        # existing local-context behavior below.
        if headers and not any(_is_cas_column(line, header.cas_x) for header in headers):
            continue
        seen_token_spans: set[tuple[int, int]] = set()
        for match in _CAS.finditer(line.text):
            line_prefix = line.text[:match.start()]
            field_context = _nearest_field_context(row, line_index, line_prefix)
            row_prefix = " ".join(item.text for item in row[:line_index]) + " " + line_prefix
            if _EC_CONTEXT.search(row_prefix) or any(
                _NON_CAS_IDENTIFIER_LABEL.fullmatch(item.text)
                for item in row[:line_index]
            ):
                continue
            if field_context == "DATE":
                continue
            if field_context != "CAS" and _is_immediately_related_date_value_line(previous_row, line):
                continue
            if any(line.page == header.page and _is_ec_column(line, header) for header in ec_headers):
                continue
            start, end = _cas_token_span(line.text, match)
            if (start, end) in seen_token_spans:
                continue
            seen_token_spans.add((start, end))
            raw = line.text[start:end]
            result = normalize_cas(raw)
            matches.append((line, start, raw))
    return matches


def _is_immediately_related_date_value_line(
    previous_row: tuple[_Line, ...] | None, line: _Line,
) -> bool:
    """Exclude only the next aligned CAS-shaped value cell of a date label.

    This deliberately does not retain a cross-row state: a later genuine CAS
    row is not affected by an earlier revision/date label.
    """
    if previous_row is None or _CAS.fullmatch(line.text.strip()) is None:
        return False
    return any(
        _DATE_METADATA_LABEL.fullmatch(label.text) is not None
        and not _date_label_has_same_row_value(previous_row, label_index)
        and label.page == line.page
        and 0.0 <= line.bbox[1] - label.bbox[3] <= _DATE_METADATA_ADJACENCY_Y_TOLERANCE
        and abs(line.bbox[0] - label.bbox[0]) <= _HEADER_X_TOLERANCE
        for label_index, label in enumerate(previous_row)
    )


def _unit_headers(row: tuple[_Line, ...], section_input: SectionInput, row_number: int) -> list[_UnitHeader]:
    """Observe units only in an explicit CAS table header, never explanatory prose."""
    cas_label = next((line for line in row if _CAS_TABLE_HEADER.fullmatch(line.text)), None)
    if cas_label is None:
        return []
    return [
        _UnitHeader(cas_label.page, row_number, cas_label.bbox[0], line.bbox[0], match.group("unit"), _evidence(section_input, line))
        for line in row
        if (match := _UNIT_HEADER.search(line.text)) and not _DIRECT_CONTENT.search(line.text)
    ]


def _split_unit_headers(
    row: tuple[_Line, ...], next_row: tuple[_Line, ...] | None,
    section_input: SectionInput, row_number: int,
) -> list[_UnitHeader]:
    """Prove a vertically split Korean CAS/identifier header in one band.

    This deliberately requires the first fragment, its immediately adjacent
    second fragment, and a same-band concentration header.  It is not a page
    text concatenation rule.
    """
    if next_row is None or any(line.page != row[0].page for line in (*row, *next_row)):
        return []
    cas_start = next((line for line in row if re.fullmatch(r"\s*CAS\s*번호\s*또는\s*", line.text, re.IGNORECASE)), None)
    content = next((line for line in row if _UNIT_HEADER.search(line.text) and not _DIRECT_CONTENT.search(line.text)), None)
    if cas_start is None or content is None or content.bbox[0] <= cas_start.bbox[0]:
        return []
    cas_end = next((line for line in next_row if re.fullmatch(r"\s*식별번호\s*", line.text)), None)
    if cas_end is None or abs(cas_end.bbox[0] - cas_start.bbox[0]) > _HEADER_X_TOLERANCE:
        return []
    if not 0 <= cas_end.bbox[1] - cas_start.bbox[3] <= 18.0:
        return []
    unit = _UNIT_HEADER.search(content.text)
    assert unit is not None
    return [_UnitHeader(cas_start.page, row_number, cas_start.bbox[0], content.bbox[0], unit.group("unit"), _evidence(section_input, content))]


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
    if abs(header.unit_x - line.bbox[0]) <= _HEADER_X_TOLERANCE:
        return header.unit, header.evidence
    return None


def _content_matches(section_input: SectionInput, row: tuple[_Line, ...], has_cas: bool, headers: list[_UnitHeader]) -> list[tuple[_Line, int, str, str | None, Evidence | None]]:
    matches: list[tuple[_Line, int, str, str | None, Evidence | None]] = []
    for line in row:
        header = _header_for(line, headers) if has_cas and headers else None
        if headers and has_cas:
            # Within an explicit CAS/unit table, only the unit-aligned cell can
            # establish the row concentration.  A percentage embedded in an
            # ingredient or synonym cell is not a concentration observation.
            if header is None:
                continue
            if _BARE_CONTENT.fullmatch(line.text):
                matches.append((line, 0, line.text, *header))
            elif _DIRECT_CONTENT.fullmatch(line.text):
                matches.append((line, 0, line.text, None, None))
            elif _HEADER_PROVEN_CONTENT.fullmatch(line.text):
                matches.append((line, 0, line.text, *header))
            continue
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
    if not headers or not row:
        return False
    cas_header = headers[0]
    has_aligned_cas = any(
        _CAS.search(line.text) and _is_cas_column(line, cas_header.cas_x)
        for line in row
    )
    has_proven_table_band = any(
        line.text.strip()
        and (
            # A prose cell must not keep a table header alive.  Actual CAS
            # values already satisfy has_aligned_cas; this branch is only for
            # a non-CAS, structured source identifier such as KE-11278.
            (_is_cas_column(line, cas_header.cas_x) and _STRUCTURED_IDENTIFIER_VALUE.fullmatch(line.text))
            or (
                abs(line.bbox[0] - cas_header.unit_x) <= _HEADER_X_TOLERANCE
                and (
                    _DIRECT_CONTENT.fullmatch(line.text)
                    or _BARE_CONTENT.fullmatch(line.text)
                    or _HEADER_PROVEN_CONTENT.fullmatch(line.text)
                    or _UNREADABLE_CONTENT.fullmatch(line.text)
                    or _KOREAN_CONTENT_START.fullmatch(line.text)
                    or _KOREAN_CONTENT_END.fullmatch(line.text)
                )
            )
        )
        for line in row
    )
    # A CAS/identifier or content cell can be blank, unreadable, or contain
    # only a non-CAS identifier such as KE-11278.  Retain the already-proven
    # row geometry whenever either table band is visibly present so
    # _cas_matches can reject CAS-shaped text from every other column; never
    # treat the identifier itself as a CAS candidate.
    if not has_aligned_cas and not has_proven_table_band:
        return False
    if all(line.page == cas_header.page for line in row):
        return True
    # A continued table page is admitted only when the next physical page has
    # both the original CAS and content bands populated on the same source
    # row.  This preserves an established table relation without letting a
    # header leak into a foreign page or column.
    return (
        all(line.page == cas_header.page + 1 for line in row)
        and any(
            _is_cas_column(line, cas_header.cas_x)
            for line in row
        )
        and any(
            abs(line.bbox[0] - cas_header.unit_x) <= _HEADER_X_TOLERANCE
            and (_DIRECT_CONTENT.fullmatch(line.text) or _BARE_CONTENT.fullmatch(line.text) or _HEADER_PROVEN_CONTENT.fullmatch(line.text))
            for line in row
        )
    )


def _same_table_content_row(row: tuple[_Line, ...], headers: list[_UnitHeader]) -> bool:
    """Keep a table header across an aligned content continuation cell.

    A Korean upper-bound fragment is not independently a bare concentration,
    but it is the only admissible next row for an immediately preceding
    header-aligned lower-bound fragment.  Retaining the header through that
    one physical row lets the next CAS row use the same proven table relation;
    it never turns the continuation row into its own component.
    """
    return bool(headers) and all(line.page == headers[0].page for line in row) and any(
        (_BARE_CONTENT.fullmatch(line.text) or _KOREAN_CONTENT_END.fullmatch(line.text))
        and abs(line.bbox[0] - headers[0].unit_x) <= _HEADER_X_TOLERANCE
        for line in row
    )


def _unit_header_continuation_row(row: tuple[_Line, ...], headers: list[_UnitHeader]) -> bool:
    """Keep a split table header only through its immediately adjacent cells."""
    if not headers or any(line.page != headers[0].page for line in row):
        return False
    header_bottom = max(header.evidence.bbox[3] if header.evidence.bbox else 0.0 for header in headers)
    return (
        not any(_CAS.search(line.text) for line in row)
        and min(line.bbox[1] for line in row) <= header_bottom + 12.0
        and any(
            re.sub(r"\s+", " ", line.text).strip().casefold().endswith(" id")
            or re.fullmatch(r"\s*식별번호\s*", line.text) is not None
            for line in row
        )
    )


def _same_ec_table_row(row: tuple[_Line, ...], headers: list[_EcHeader]) -> bool:
    """Keep EC-column exclusion scoped to aligned rows of its own table."""
    if not headers or any(line.page != headers[0].page for line in row):
        return False
    header = headers[0]
    return any(
        _CAS.search(line.text) and (_is_ec_column(line, header) or _is_cas_column(line, header.cas_x))
        for line in row
    )


def _content_field_observation(section_input: SectionInput, row: tuple[_Line, ...], has_content: bool, headers: list[_UnitHeader]) -> tuple[ContentFieldState, str | None, tuple[Evidence, ...]]:
    """Retain explicit blank, unreadable, unknown, and absent field states."""
    if has_content:
        return ContentFieldState.UNKNOWN, None, ()
    residuals = tuple(
        (line, "" if _CAS_TABLE_HEADER.fullmatch(line.text) else _CAS.sub("", line.text).strip(" :|"))
        for line in row
    )
    unreadable = next(((line, text) for line, text in residuals if _UNREADABLE_CONTENT.fullmatch(text)), None)
    if unreadable is not None:
        line, raw = unreadable
        return ContentFieldState.UNREADABLE, raw, (_evidence(section_input, line),)
    if headers and _same_table_row(row, headers):
        # The header evidence establishes that this otherwise textless cell is
        # a content field, rather than merely a missing candidate.
        # OCR absence is not a visual observation of a blank cell.  It stays
        # unresolved even within a confirmed, unit-bearing table fence.
        if section_input.capability is DocumentCapability.OCR:
            return ContentFieldState.UNKNOWN, None, tuple(header.evidence for header in headers)
        return ContentFieldState.EXPLICIT_BLANK, None, tuple(header.evidence for header in headers)
    # A labelled standalone CAS field is an explicit source observation that
    # the component has no accompanying concentration field.  This is unlike
    # an unlabelled bare CAS token, whose absent context must remain ambiguous.
    if any(_CAS_TABLE_HEADER.fullmatch(line.text) for line in row) and not any(text for _line, text in residuals):
        return ContentFieldState.EXPLICIT_BLANK, None, ()
    unknown = next(((line, text) for line, text in residuals if text), None)
    if unknown is not None:
        line, raw = unknown
        return ContentFieldState.UNKNOWN, raw, (_evidence(section_input, line),)
    return ContentFieldState.ABSENT, None, ()


def _multiline_korean_content(
    section_input: SectionInput,
    row: tuple[_Line, ...],
    next_row: tuple[_Line, ...] | None,
    has_cas: bool,
    headers: list[_UnitHeader],
) -> tuple[str, str, tuple[Evidence, ...]] | None:
    """Join only an adjacent, header-aligned Korean range split across lines.

    The source raw stays lossless (including the line break).  This is a
    structural table operation: it requires an explicit CAS/unit header, a
    CAS in the first row, and both fragments in that header's content column.
    It deliberately cannot join values from a classification or distant block.
    """
    if not has_cas or next_row is None or not headers:
        return None
    header = headers[0]
    first = next((line for line in row if abs(line.bbox[0] - header.unit_x) <= _HEADER_X_TOLERANCE and _KOREAN_CONTENT_START.fullmatch(line.text)), None)
    second = next((line for line in next_row if line.page == first.page and abs(line.bbox[0] - header.unit_x) <= _HEADER_X_TOLERANCE and _KOREAN_CONTENT_END.fullmatch(line.text)), None) if first else None
    if first is None or second is None:
        return None
    if not (0 <= second.bbox[1] - first.bbox[3] <= 18.0):
        return None
    raw = f"{first.text}\n{second.text}"
    return raw, header.unit, (_evidence(section_input, first), _evidence(section_input, second), header.evidence)


def _named_component_blocks(section_input: SectionInput, rows: tuple[tuple[_Line, ...], ...]) -> tuple[Section3BlockCandidate, ...]:
    """Collect explicit name/CAS/content field groups when no table exists."""
    blocks: list[Section3BlockCandidate] = []
    group: list[_Line] = []

    def flush() -> None:
        if not group:
            return
        cas_line = next((line for line in group if (match := _NAMED_CAS.fullmatch(line.text))), None)
        content_line = next((line for line in group if _NAMED_CONTENT.fullmatch(line.text)), None)
        if cas_line is None or content_line is None:
            return
        cas_match = _NAMED_CAS.fullmatch(cas_line.text)
        content_match = _NAMED_CONTENT.fullmatch(content_line.text)
        assert cas_match is not None and content_match is not None
        cas_raw = cas_match.group("value")
        cas_shape = _CAS.fullmatch(cas_raw)
        content_raw = content_match.group("value")
        content_shape = _DIRECT_CONTENT.fullmatch(content_raw)
        content_header_has_percent = "%" in content_line.text or "％" in content_line.text
        if cas_shape is None or (content_shape is None and not (content_header_has_percent and _BARE_CONTENT.fullmatch(content_raw))):
            return
        normalized_cas = normalize_cas(cas_raw)
        first = group[0]
        blocks.append(Section3BlockCandidate(
            f"section3-page-{first.page}-block-{first.block}",
            f"section3-named-row-{len(blocks)}", len(blocks),
            tuple(_evidence(section_input, line) for line in group),
            (CasCandidate(cas_raw, normalized_cas.normalized, CasCandidateValidity(normalized_cas.validity.value), len(blocks), (_evidence(section_input, cas_line),)),),
            (ContentCandidate(
                content_raw, normalize_content(content_raw).content_normalized, len(blocks) + 1,
                (_evidence(section_input, content_line),),
                "%" if content_shape is None and content_header_has_percent else None,
                (_evidence(section_input, content_line),) if content_shape is None and content_header_has_percent else (),
            ),),
            ContentFieldState.UNKNOWN,
        ))

    for row in rows:
        if group and any(_NAMED_BLOCK_BOUNDARY.match(line.text) for line in row):
            flush()
            group = []
        if any(_NAMED_COMPONENT.fullmatch(line.text) for line in row):
            flush()
            group = list(row)
        elif group:
            group.extend(row)
    flush()
    return tuple(blocks)


def collect_section3_candidates(section_input: SectionInput) -> Section3Collection:
    """Collect ordered Section 3 source rows without creating ComponentPair values."""
    _require_confirmed_text_input(section_input, "3")
    blocks: list[Section3BlockCandidate] = []
    source_order = 0
    headers: list[_UnitHeader] = []
    ec_headers: list[_EcHeader] = []
    rows = _rows(section_input)
    # Explicit repeated name/CAS/content groups describe their own row
    # relationship.  Do not first reinterpret their separate CAS line as a
    # table row and lose the following declared content value.
    if any(any(_NAMED_COMPONENT.fullmatch(line.text) for line in row) for row in rows):
        return Section3Collection(_named_component_blocks(section_input, rows))
    for row_number, row in enumerate(rows):
        if row_headers := _unit_headers(row, section_input, row_number):
            headers = row_headers
        elif split_headers := _split_unit_headers(
            row, rows[row_number + 1] if row_number + 1 < len(rows) else None,
            section_input, row_number,
        ):
            headers = split_headers
        elif headers and not (
            _same_table_row(row, headers)
            or _same_table_content_row(row, headers)
            or _unit_header_continuation_row(row, headers)
        ):
            headers = []
        if row_ec_headers := _ec_headers(row, row_number):
            ec_headers = row_ec_headers
        elif ec_headers and not _same_ec_table_row(row, ec_headers):
            ec_headers = []
        previous_row = rows[row_number - 1] if row_number else None
        cas_matches = _cas_matches(row, ec_headers, headers, previous_row)
        content_matches = _content_matches(section_input, row, bool(cas_matches), headers)
        multiline_content = _multiline_korean_content(
            section_input, row, rows[row_number + 1] if row_number + 1 < len(rows) else None,
            bool(cas_matches), headers,
        )
        occurrences = [(line, start, "cas", raw) for line, start, raw in cas_matches]
        occurrences += [(line, start, "content", (raw, unit, unit_evidence)) for line, start, raw, unit, unit_evidence in content_matches]
        occurrences.sort(key=lambda item: (item[0].page, item[0].bbox[1], item[0].bbox[0], item[1]))
        cas_candidates: list[CasCandidate] = []
        content_candidates: list[ContentCandidate] = []
        for line, _position, kind, payload in occurrences:
            if kind == "cas":
                raw = payload
                result = normalize_cas(raw)
                cas_candidates.append(CasCandidate(raw, result.normalized, CasCandidateValidity(result.validity.value), source_order, (_evidence(section_input, line),)))
            else:
                raw, unit, unit_evidence = payload
                content_candidates.append(ContentCandidate(raw, normalize_content(raw).content_normalized, source_order, (_evidence(section_input, line),), unit, (unit_evidence,) if unit_evidence else ()))
            source_order += 1
        if multiline_content is not None:
            raw, unit, evidence = multiline_content
            content_candidates.append(ContentCandidate(
                raw, normalize_content(raw).content_normalized, source_order,
                evidence[:2], unit, (evidence[2],),
            ))
            source_order += 1
        # A content-only row has no component/block candidate in this stage.
        if not cas_candidates:
            continue
        row_evidence = tuple(_evidence(section_input, line) for line in row)
        first = row[0]
        # A bare aligned table cell is source-proven blank only when an
        # explicit content header established that cell's meaning.  In every
        # other case no candidate is simply absent; resolver must not turn it
        # into NOT_STATED.
        field_state, field_raw, field_evidence = _content_field_observation(
            section_input, row, bool(content_candidates), headers,
        )
        blocks.append(Section3BlockCandidate(
            f"section3-page-{first.page}-block-{first.block}",
            f"section3-row-{row_number}", len(blocks), row_evidence,
            tuple(cas_candidates), tuple(content_candidates), field_state,
            field_raw, field_evidence,
        ))
    # Named fields are an alternative, not a supplement to an already-proven
    # table.  This avoids cross-layout pairing or synthetic joins.
    if not blocks:
        blocks.extend(_named_component_blocks(section_input, rows))
    return Section3Collection(tuple(blocks))
