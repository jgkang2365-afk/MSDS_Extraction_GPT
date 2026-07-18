from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DATASET_VERSION = "2026-07-18.1"
SOURCE_VERSION = "msds_index_V24"
BUILDER_VERSION = "1.0.0"
REVIEW_SET_NAME = "2026-07-18_msds_index_review"


@dataclass(slots=True)
class ReviewWarning:
    code: str
    message: str
    sheet: str | None = None
    row: int | None = None
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewLoadResult:
    workbook_path: Path
    same_cas_decisions: list[dict[str, Any]] = field(default_factory=list)
    cross_cas_decisions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[ReviewWarning] = field(default_factory=list)

    @property
    def decision_count(self) -> int:
        return len(self.same_cas_decisions) + len(self.cross_cas_decisions)


@dataclass(slots=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    entity_type: str | None = None
    entity_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "ERROR"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "WARNING"]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> None:
        self.issues.append(
            ValidationIssue(severity, code, message, entity_type, entity_id)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS" if self.is_valid else "FAIL",
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }
