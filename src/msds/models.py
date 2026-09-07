"""Structured, lossless contracts for the re-baselined MSDS domain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DocumentCapability(str, Enum):
    TEXT = "TEXT"
    OCR = "OCR"
    IMAGE_ONLY = "IMAGE_ONLY"
    UNKNOWN = "UNKNOWN"


class DocumentType(str, Enum):
    PDF = "PDF"
    IMAGE = "IMAGE"
    OTHER = "OTHER"


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    NOT_READABLE = "NOT_READABLE"


class EvidenceSourceType(str, Enum):
    TEXT = "TEXT"
    OCR = "OCR"
    TABLE = "TABLE"
    HUMAN = "HUMAN"
    OTHER = "OTHER"


class FenceStatus(str, Enum):
    FENCE_CONFIRMED = "FENCE_CONFIRMED"
    FENCE_PARTIAL = "FENCE_PARTIAL"
    FENCE_NOT_FOUND = "FENCE_NOT_FOUND"


@dataclass(frozen=True)
class PageRegion:
    """A 0-based, unrotated PyMuPDF top-left PDF-point safe region."""

    page_index: int
    allowed_rects: tuple[tuple[float, float, float, float], ...]
    excluded_rects: tuple[tuple[float, float, float, float], ...] = ()


@dataclass(frozen=True)
class LayoutToken:
    """One reusable digital-text token, retaining its source-page geometry."""

    token_id: str
    text: str
    page_index: int
    bbox: tuple[float, float, float, float]
    block_id: int
    line_id: int
    source_reading: str = "TEXT"


@dataclass(frozen=True)
class SectionInput:
    """The only digital collector input: confirmed regions and filtered tokens."""

    document_sha256: str
    section_no: str
    fence_id: str
    ordered_regions: tuple[PageRegion, ...]
    tokens: tuple[LayoutToken, ...]
    capability: DocumentCapability
    reasons: tuple[str, ...] = ()
    input_digest: str = ""


class CasCandidateValidity(str, Enum):
    """Observed CAS syntax/checksum state; collection never repairs it."""

    VALID = "VALID"
    NOT_CANDIDATE = "NOT_CANDIDATE"
    FORMAT_INVALID = "FORMAT_INVALID"
    CHECK_DIGIT_INVALID = "CHECK_DIGIT_INVALID"


@dataclass(frozen=True)
class ProductCandidate:
    """One lossless Section 1 product-name observation, before resolution."""

    raw: str
    normalized: str
    source_order: int
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class ProductCollection:
    """Candidate-only Section 1 output; absence is represented by no candidates."""

    candidates: tuple[ProductCandidate, ...] = ()


@dataclass(frozen=True)
class CasCandidate:
    """One source occurrence, including invalid values which are never corrected."""

    raw: str
    normalized: str
    validity: CasCandidateValidity
    source_order: int
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class ContentCandidate:
    """A raw Section 3 concentration expression with separately observed unit context."""

    raw: str
    normalized: str
    source_order: int
    evidence: tuple[Evidence, ...]
    unit_context_raw: str | None = None
    unit_context_evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class Section3BlockCandidate:
    """A source row/block retaining CAS/content relation without pairing it."""

    block_id: str
    row_id: str
    source_order: int
    evidence: tuple[Evidence, ...]
    cas_candidates: tuple[CasCandidate, ...]
    content_candidates: tuple[ContentCandidate, ...] = ()


@dataclass(frozen=True)
class Section3Collection:
    """Ordered source blocks only; no resolver/validator result is embedded."""

    blocks: tuple[Section3BlockCandidate, ...] = ()


class ResultStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    NOT_STATED = "NOT_STATED"
    NOT_READABLE = "NOT_READABLE"
    REVIEW = "REVIEW"
    INVALID = "INVALID"


class ContentStatus(str, Enum):
    FOUND = "FOUND"
    NOT_STATED = "NOT_STATED"
    NOT_READABLE = "NOT_READABLE"
    PAIR_AMBIGUOUS = "PAIR_AMBIGUOUS"


class PairStatus(str, Enum):
    PAIRED = "PAIRED"
    NOT_STATED = "NOT_STATED"
    NOT_READABLE = "NOT_READABLE"
    PAIR_AMBIGUOUS = "PAIR_AMBIGUOUS"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class Document:
    """Identity and observed execution state of one source document."""

    document_id: str
    path: str
    sha256: str
    capability: DocumentCapability = DocumentCapability.UNKNOWN
    document_type: DocumentType = DocumentType.PDF
    execution_status: ExecutionStatus = ExecutionStatus.PENDING


@dataclass(frozen=True)
class Evidence:
    """A lossless pointer to source material supporting a result."""

    section: str | None
    page: int | None
    source_type: EvidenceSourceType
    raw_fragment: str
    document_sha256: str
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class SectionFence:
    status: FenceStatus
    section: str
    start_page: int | None
    end_page: int | None
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class ProductResult:
    raw: str
    normalized: str
    status: ResultStatus
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class CASResult:
    cas_raw: str
    cas_normalized: str
    cas_status: ResultStatus
    evidence: tuple[Evidence, ...] = ()

    @property
    def normalized(self) -> str:
        """Compatibility read alias; the contract field is cas_normalized."""
        return self.cas_normalized

    @property
    def status(self) -> ResultStatus:
        """Compatibility read alias; the contract field is cas_status."""
        return self.cas_status


@dataclass(frozen=True)
class ContentResult:
    content_raw: str
    content_normalized: str
    content_status: ContentStatus

    @property
    def raw(self) -> str:
        """Compatibility read alias; the contract field is content_raw."""
        return self.content_raw

    @property
    def normalized(self) -> str:
        """Compatibility read alias; the contract field is content_normalized."""
        return self.content_normalized

    @property
    def status(self) -> ContentStatus:
        """Compatibility read alias; the contract field is content_status."""
        return self.content_status


@dataclass(frozen=True)
class ComponentPair:
    """One Section 3 CAS-to-content relationship, never a serialized chain."""

    cas: CASResult
    content: ContentResult
    status: PairStatus
    evidence: tuple[Evidence, ...] = ()
    block_id: str = ""
    row_id: str | None = None


@dataclass(frozen=True)
class MachineResult:
    """Complete machine result; component order and duplicate rows are retained."""

    document: Document
    fences: tuple[SectionFence, ...] = ()
    product: ProductResult | None = None
    components: tuple[ComponentPair, ...] = ()
    validation: tuple[Any, ...] = ()
    review: tuple[Any, ...] = ()
    warnings: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
