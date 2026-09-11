"""Pure, conservative normalization functions for the new MSDS contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata

from .models import CASResult, ContentResult, ContentStatus, ProductResult, ResultStatus


_DASHES = "-\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_DASH_TRANSLATION = str.maketrans({dash: "-" for dash in _DASHES})
_CAS_SHAPE = re.compile(r"^\d{2,7}-\d{2}-\d$")
_DECIMAL_COMMA = re.compile(r"(?<!\d)(\d+),(\d{1,2})(?!\d)")


class CasValidity(str, Enum):
    VALID = "VALID"
    NOT_CANDIDATE = "NOT_CANDIDATE"
    FORMAT_INVALID = "FORMAT_INVALID"
    CHECK_DIGIT_INVALID = "CHECK_DIGIT_INVALID"


@dataclass(frozen=True)
class CasNormalization:
    """Normalization and validation are intentionally separate observations."""

    raw: str
    normalized: str
    validity: CasValidity

    @property
    def is_valid(self) -> bool:
        return self.validity is CasValidity.VALID


def normalize_cas_value(value: object | None) -> str:
    """Normalize only CAS separators and separator-adjacent whitespace."""
    if value is None:
        return ""
    normalized = str(value).translate(_DASH_TRANSLATION)
    return re.sub(r"\s*-\s*", "-", normalized).strip()


def normalize_cas(value: object | None) -> CasNormalization:
    """Apply only lexical CAS normalization, shape, and checksum validation.

    Whether a lexical CAS occurs in a date, EC, or other metadata context is
    a collector responsibility.  This pure function intentionally has no
    document-layout or vocabulary semantics.
    """
    raw = "" if value is None else str(value)
    normalized = normalize_cas_value(raw)
    if not normalized:
        return CasNormalization(raw, normalized, CasValidity.NOT_CANDIDATE)
    if not _CAS_SHAPE.fullmatch(normalized):
        return CasNormalization(raw, normalized, CasValidity.FORMAT_INVALID)
    digits = normalized[:-2].replace("-", "")
    checksum = sum((index + 1) * int(digit) for index, digit in enumerate(reversed(digits)))
    validity = CasValidity.VALID if checksum % 10 == int(normalized[-1]) else CasValidity.CHECK_DIGIT_INVALID
    return CasNormalization(raw, normalized, validity)


def is_valid_cas(value: object | None) -> bool:
    return normalize_cas(value).is_valid


def normalize_cas_result(value: object | None) -> CASResult:
    result = normalize_cas(value)
    return CASResult(
        cas_raw=result.raw,
        cas_normalized=result.normalized,
        cas_status=ResultStatus.FOUND if result.is_valid else ResultStatus.INVALID,
    )


def _normalize_decimal_commas(value: str) -> str:
    """Convert only percentage-context decimal commas with one/two decimals."""
    return _DECIMAL_COMMA.sub(r"\1.\2", value) if "%" in value else value


def normalize_content(value: object | None) -> ContentResult:
    """Normalize presentation equivalents while preserving all concentration meaning."""
    raw = "" if value is None else str(value)
    if not raw.strip():
        return ContentResult(content_raw=raw, content_normalized="", content_status=ContentStatus.NOT_STATED)
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw)).strip()
    normalized = normalized.replace("∼", "~").replace("～", "~")
    normalized = re.sub(r"(?<=\d)\s*[-–—]\s*(?=[<>=≤≥]?\s*\d)", "~", normalized)
    normalized = re.sub(r"\s*([~<>≤≥%])\s*", r"\1", normalized)
    normalized = _normalize_decimal_commas(normalized)
    return ContentResult(content_raw=raw, content_normalized=normalized, content_status=ContentStatus.FOUND)


def normalize_product(value: object | None) -> ProductResult:
    """Make a comparison value while retaining every raw product identifier."""
    raw = "" if value is None else str(value)
    if not raw.strip():
        return ProductResult(raw=raw, normalized="", status=ResultStatus.NOT_FOUND)
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw)).strip().casefold()
    return ProductResult(raw=raw, normalized=normalized, status=ResultStatus.FOUND)
