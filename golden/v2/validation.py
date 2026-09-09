"""Dependency-free, non-mutating validation for the Golden v2 contract.

Golden v2 deliberately has no loader for Golden v1. Callers supply decoded
JSON-compatible objects and, optionally, local mappings for portable sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
CASE_KINDS = frozenset({"VALUE_TRUTH", "SAFE_REVIEW", "FAILURE_BEHAVIOR"})
LIFECYCLES = frozenset({"CANDIDATE", "HUMAN_REVIEWED", "APPROVED"})
PRODUCT_STATUSES = frozenset({"FOUND", "NOT_FOUND", "NOT_STATED", "NOT_READABLE", "REVIEW", "INVALID"})
_COMPONENT_CAS_STATUSES = frozenset({"FOUND", "NOT_READABLE", "REVIEW", "INVALID"})
_CONTENT_STATUSES = frozenset({"FOUND", "NOT_STATED", "NOT_READABLE", "PAIR_AMBIGUOUS"})
_PAIR_STATUSES = frozenset({"PAIRED", "NOT_STATED", "NOT_READABLE", "PAIR_AMBIGUOUS", "REVIEW"})
_CONTENT_TO_PAIR_STATUS = {
    "FOUND": "PAIRED",
    "NOT_STATED": "NOT_STATED",
    "NOT_READABLE": "NOT_READABLE",
    "PAIR_AMBIGUOUS": "PAIR_AMBIGUOUS",
}
_FAILURE_OUTCOMES = frozenset({"REJECT", "REVIEW_REQUIRED", "NO_OUTPUT", "FENCE_BLOCKED"})
_REVIEW_METHOD = "DIRECT_SOURCE_PDF_REVIEW"
_UNIT_IN_RAW = re.compile(r"(?:%|(?<![A-Za-z])ppm\b)", re.IGNORECASE)
_HUMAN_SOURCE_EVIDENCE = "HUMAN_DIRECT_SOURCE_PDF_REVIEW"


@dataclass(frozen=True)
class DatasetValidationResult:
    """Blocking errors and non-mutating review findings."""

    errors: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _enum_member(value: Any, values: frozenset[str]) -> bool:
    return isinstance(value, str) and value in values


def _evidence(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict) or not item:
            errors.append(f"{item_path} must be a non-empty evidence object")
            continue
        if "provenance_type" in item and not isinstance(item["provenance_type"], str):
            errors.append(f"{item_path}.provenance_type must be a string when present")
        if "page" in item and (type(item["page"]) is not int or item["page"] < 0):
            errors.append(f"{item_path}.page must be a non-negative integer when present")


def _nonempty_evidence(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{path} must be a non-empty list for APPROVED")


def _human_source_evidence(value: Any, path: str, errors: list[str]) -> None:
    """Require real, located human-PDF provenance only at the approval gate."""
    _nonempty_evidence(value, path, errors)
    if not isinstance(value, list):
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict) or item.get("provenance_type") != _HUMAN_SOURCE_EVIDENCE or type(item.get("page")) is not int or item["page"] < 0:
            errors.append(f"{item_path} must be human direct-source PDF provenance with a non-negative page")
        if isinstance(item, dict) and _has_raw_reading(item):
            errors.append(f"{item_path} must not contain OCR raw_reading for APPROVED")


def _has_raw_reading(value: Any) -> bool:
    if isinstance(value, dict):
        return "raw_reading" in value or any(_has_raw_reading(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_raw_reading(child) for child in value)
    return False


def _evidence_corresponds(transcription_evidence: Any, component_evidence: Any) -> bool:
    """Require a 1:1 ordered occurrence match without erasing duplicate locators."""
    if not isinstance(transcription_evidence, list) or not isinstance(component_evidence, list):
        return False
    if len(transcription_evidence) != len(component_evidence):
        return False
    return all(
        isinstance(transcription_item, dict)
        and isinstance(component_item, dict)
        and _locator_identity(transcription_item) == _locator_identity(component_item)
        for transcription_item, component_item in zip(transcription_evidence, component_evidence)
    )


def _locator_identity(evidence: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Compare source locators, while leaving non-locator annotations independent."""
    return tuple(
        (field, _freeze_locator_value(evidence[field]))
        for field in ("provenance_type", "page", "bbox", "region")
        if field in evidence
    )


def _freeze_locator_value(value: Any) -> Any:
    if isinstance(value, dict):
        return ("object", tuple(sorted((str(key), _freeze_locator_value(child)) for key, child in value.items())))
    if isinstance(value, list):
        return ("array", tuple(_freeze_locator_value(child) for child in value))
    if value is None:
        return ("null", None)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, int):
        return ("integer", value)
    if isinstance(value, float):
        return ("number", value)
    if isinstance(value, str):
        return ("string", value)
    return (type(value).__name__, value)


def _source_ref(case: dict[str, Any], errors: list[str]) -> None:
    source = case.get("source")
    if not isinstance(source, dict):
        errors.append("source is required")
        return
    if set(source) != {"source_root", "relative_path"}:
        errors.append("source must contain only portable source_root and relative_path")
    root, relative_path = source.get("source_root"), source.get("relative_path")
    if not _nonempty(root):
        errors.append("source.source_root is required")
    if not _nonempty(relative_path):
        errors.append("source.relative_path is required")
        return
    portable = PurePosixPath(relative_path)
    if portable.is_absolute() or re.match(r"^[A-Za-z]:", relative_path) or "\\" in relative_path or ".." in portable.parts:
        errors.append("source.relative_path must be a portable relative path")
    if case.get("lifecycle") == "APPROVED" and not relative_path.lower().endswith(".pdf"):
        errors.append("APPROVED source.relative_path must end in .pdf")


def _history(case: dict[str, Any], errors: list[str]) -> None:
    lifecycle, history = case.get("lifecycle"), case.get("review_history")
    if not isinstance(history, list):
        errors.append("review_history must be a list")
        return
    expected_stages = {
        "CANDIDATE": ("CANDIDATE",),
        "HUMAN_REVIEWED": ("CANDIDATE", "HUMAN_REVIEWED"),
        "APPROVED": ("CANDIDATE", "HUMAN_REVIEWED", "APPROVED"),
    }.get(lifecycle) if isinstance(lifecycle, str) else None
    actual_stages: list[str] = []
    previous_timestamp: datetime | None = None
    for index, event in enumerate(history):
        prefix = f"review_history[{index}]"
        if not isinstance(event, dict):
            errors.append(f"{prefix} must be an object")
            continue
        action, status = event.get("action"), event.get("status")
        if not _enum_member(action, LIFECYCLES) or not _enum_member(status, LIFECYCLES) or action != status:
            errors.append(f"{prefix}.action/status must be matching lifecycle values")
            continue
        actual_stages.append(action)
        if action == "CANDIDATE" and "timestamp" in event:
            errors.append(f"{prefix}.timestamp is not permitted for CANDIDATE")
        if action in {"HUMAN_REVIEWED", "APPROVED"}:
            if not _nonempty(event.get("reviewer_ref")):
                errors.append(f"{prefix}.reviewer_ref is required")
            timestamp = event.get("timestamp")
            parsed_timestamp = _parse_timestamp(timestamp) if isinstance(timestamp, str) and _TIMESTAMP.fullmatch(timestamp) else None
            if parsed_timestamp is None:
                errors.append(f"{prefix}.timestamp must be an ISO-8601 timestamp with timezone")
            elif previous_timestamp is not None and parsed_timestamp < previous_timestamp:
                errors.append(f"{prefix}.timestamp must be nondecreasing across review_history")
            else:
                previous_timestamp = parsed_timestamp
            if event.get("review_method") != _REVIEW_METHOD:
                errors.append(f"{prefix}.review_method must be {_REVIEW_METHOD}")
            if event.get("source_pdf_directly_confirmed") is not True:
                errors.append(f"{prefix}.source_pdf_directly_confirmed must be true")
            if event.get("section_1_confirmed") is not True or event.get("section_3_confirmed") is not True:
                errors.append(f"{prefix}.section_1_confirmed and section_3_confirmed must be true")
        if "reason" in event and not isinstance(event["reason"], str):
            errors.append(f"{prefix}.reason must be a string when present")
    if expected_stages is not None and tuple(actual_stages) != expected_stages:
        errors.append(f"review_history must exactly match lifecycle stages: {', '.join(expected_stages)}")


def _parse_timestamp(value: str) -> datetime | None:
    if value.endswith("Z"):
        offset_is_valid = True
    else:
        try:
            offset_hours, offset_minutes = int(value[-5:-3]), int(value[-2:])
            offset_is_valid = offset_hours <= 23 and offset_minutes <= 59
        except ValueError:
            offset_is_valid = False
    if not offset_is_valid:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _expected(case: dict[str, Any], errors: list[str]) -> None:
    kind, expected = case.get("case_kind"), case.get("expected")
    if not isinstance(kind, str) or kind not in {"SAFE_REVIEW", "FAILURE_BEHAVIOR"}:
        return
    if not isinstance(expected, dict):
        errors.append(f"{kind} requires expected")
        return
    if kind == "SAFE_REVIEW":
        if expected.get("quality_status") != "REVIEW_REQUIRED":
            errors.append("SAFE_REVIEW requires expected.quality_status REVIEW_REQUIRED")
        findings = expected.get("finding_codes")
        if not isinstance(findings, list) or not findings or not all(_nonempty(item) for item in findings):
            errors.append("SAFE_REVIEW requires non-empty expected.finding_codes")
    if kind == "FAILURE_BEHAVIOR" and not _enum_member(expected.get("safe_outcome"), _FAILURE_OUTCOMES):
        errors.append("FAILURE_BEHAVIOR requires expected.safe_outcome")


def _source_transcription(case: dict[str, Any], errors: list[str]) -> None:
    transcription = case.get("source_transcription")
    if transcription is None:
        if case.get("lifecycle") == "APPROVED":
            errors.append("APPROVED requires source_transcription")
        return
    if not isinstance(transcription, dict):
        errors.append("source_transcription must be an object")
        return
    if not isinstance(transcription.get("product_raw"), str):
        errors.append("source_transcription.product_raw must be a string")
    _evidence(transcription.get("product_evidence"), "source_transcription.product_evidence", errors)
    rows = transcription.get("component_rows")
    if not isinstance(rows, list):
        errors.append("source_transcription.component_rows must be an ordered list")
        return
    if case.get("lifecycle") == "APPROVED":
        if transcription.get("transcription_method") != _HUMAN_SOURCE_EVIDENCE or transcription.get("source_pdf_directly_confirmed") is not True:
            errors.append("APPROVED source_transcription must record direct human source-PDF review")
        if _has_raw_reading(transcription):
            errors.append("APPROVED source_transcription must not contain OCR raw_reading")
        _human_source_evidence(transcription.get("product_evidence"), "source_transcription.product_evidence", errors)
        components = case.get("components")
        if not isinstance(components, list):
            errors.append("APPROVED source_transcription requires components to be an ordered list")
        elif len(rows) != len(components):
            errors.append("APPROVED source_transcription.component_rows must cover every component row")
        product = case.get("product")
        if isinstance(product, dict):
            if transcription.get("product_raw") != product.get("raw"):
                errors.append("APPROVED source_transcription.product_raw must match product.raw")
            if not _evidence_corresponds(transcription.get("product_evidence"), product.get("provenance")):
                errors.append("APPROVED source_transcription.product_evidence must match product.provenance locator order")
    for index, row in enumerate(rows):
        prefix = f"source_transcription.component_rows[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if not all(isinstance(row.get(field), str) for field in ("block_id", "cas_raw", "content_raw")):
            errors.append(f"{prefix} block_id/cas_raw/content_raw must be strings")
        _evidence(row.get("evidence"), f"{prefix}.evidence", errors)
        if case.get("lifecycle") == "APPROVED":
            _human_source_evidence(row.get("evidence"), f"{prefix}.evidence", errors)
            components = case.get("components")
            component = components[index] if isinstance(components, list) and index < len(components) else None
            if isinstance(component, dict):
                cas, content = component.get("cas"), component.get("content")
                if (
                    row.get("block_id") != component.get("block_id")
                    or not isinstance(cas, dict)
                    or row.get("cas_raw") != cas.get("cas_raw")
                    or not isinstance(content, dict)
                    or row.get("content_raw") != content.get("content_raw")
                    or not _evidence_corresponds(row.get("evidence"), component.get("evidence"))
                ):
                    errors.append(f"{prefix} must correspond to components[{index}] source order, raw values, and evidence")


def _approved_provenance(case: dict[str, Any], errors: list[str]) -> None:
    if case.get("lifecycle") != "APPROVED":
        return
    product = case.get("product")
    if isinstance(product, dict):
        _human_source_evidence(product.get("provenance"), "product.provenance", errors)
    provenance = case.get("section_provenance")
    if isinstance(provenance, dict):
        for section_name in ("section_1", "section_3"):
            section = provenance.get(section_name)
            if isinstance(section, dict):
                _human_source_evidence(section.get("evidence"), f"section_provenance.{section_name}.evidence", errors)
    rows = case.get("components")
    if isinstance(rows, list):
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            prefix = f"components[{index}]"
            cas, content = row.get("cas"), row.get("content")
            if isinstance(cas, dict):
                _human_source_evidence(cas.get("evidence"), f"{prefix}.cas.evidence", errors)
            if isinstance(content, dict):
                _human_source_evidence(content.get("evidence"), f"{prefix}.content.evidence", errors)
                if content.get("unit_context_raw") is not None:
                    _human_source_evidence(content.get("unit_context_evidence"), f"{prefix}.content.unit_context_evidence", errors)
            _human_source_evidence(row.get("evidence"), f"{prefix}.evidence", errors)


def _shared_content_relations(rows: list[Any], errors: list[str]) -> None:
    """Require source-declared shared content rows to retain one content fact."""
    first_by_content_id: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        relation, content = row.get("source_relation"), row.get("content")
        if not isinstance(relation, dict) or not isinstance(relation.get("shared_content_id"), str) or not isinstance(content, dict):
            continue
        content_id = relation["shared_content_id"]
        first = first_by_content_id.get(content_id)
        if first is None:
            first_by_content_id[content_id] = (index, content)
            continue
        first_index, first_content = first
        fields = ("content_raw", "content_normalized", "content_status", "unit_context_raw")
        if any(content.get(field) != first_content.get(field) for field in fields):
            errors.append(
                f"components[{index}].source_relation.shared_content_id {content_id!r} must match "
                f"components[{first_index}] content raw/normalized/status/unit context"
            )
        elif first_content.get("unit_context_raw") is not None and not _evidence_corresponds(
            content.get("unit_context_evidence"), first_content.get("unit_context_evidence")
        ):
            errors.append(
                f"components[{index}].source_relation.shared_content_id {content_id!r} must match "
                f"components[{first_index}] unit_context_evidence source locators"
            )


def validate_case(case: Any) -> list[str]:
    """Return one case's structural errors, preserving every input value."""
    errors: list[str] = []
    if not isinstance(case, dict):
        return ["case must be an object"]
    if not _nonempty(case.get("case_id")):
        errors.append("case_id is required")
    if not _enum_member(case.get("case_kind"), CASE_KINDS):
        errors.append("case_kind is invalid")
    if not _enum_member(case.get("lifecycle"), LIFECYCLES):
        errors.append("lifecycle is invalid")
    if not isinstance(case.get("source_sha256"), str) or not _SHA256.fullmatch(case["source_sha256"]):
        errors.append("source_sha256 must be a lowercase SHA-256")
    _source_ref(case, errors)
    product = case.get("product")
    if not isinstance(product, dict):
        errors.append("product is required")
    elif not all(isinstance(product.get(field), str) for field in ("raw", "normalized")) or not _enum_member(product.get("status"), PRODUCT_STATUSES):
        errors.append("product raw/normalized/status is invalid")
    elif not isinstance(product.get("provenance"), list):
        errors.append("product.provenance must be a list")
    else:
        _evidence(product["provenance"], "product.provenance", errors)
    provenance = case.get("section_provenance")
    if not isinstance(provenance, dict):
        errors.append("section_provenance is required")
    else:
        for section_name in ("section_1", "section_3"):
            section = provenance.get(section_name)
            if not isinstance(section, dict):
                errors.append(f"section_provenance.{section_name} is required")
            elif not isinstance(section.get("evidence"), list):
                errors.append(f"section_provenance.{section_name}.evidence must be a list")
            else:
                _evidence(section["evidence"], f"section_provenance.{section_name}.evidence", errors)
    rows = case.get("components")
    if not isinstance(rows, list):
        errors.append("components must be an ordered list, never a CAS-keyed object")
    else:
        for index, row in enumerate(rows):
            prefix = f"components[{index}]"
            if not isinstance(row, dict):
                errors.append(f"{prefix} must be an object")
                continue
            cas = row.get("cas")
            if (not isinstance(cas, dict) or not _nonempty(cas.get("cas_raw")) or not isinstance(cas.get("cas_normalized"), str)
                    or not _enum_member(cas.get("cas_status"), _COMPONENT_CAS_STATUSES) or not isinstance(cas.get("evidence"), list)):
                errors.append(f"{prefix}.cas raw/normalized/status/evidence is invalid")
            else:
                _evidence(cas["evidence"], f"{prefix}.cas.evidence", errors)
            content = row.get("content")
            if (not isinstance(content, dict) or not isinstance(content.get("content_raw"), str)
                    or not isinstance(content.get("content_normalized"), str) or not _enum_member(content.get("content_status"), _CONTENT_STATUSES)
                    or "unit_context_raw" not in content or (content.get("unit_context_raw") is not None and not isinstance(content.get("unit_context_raw"), str))
                    or not isinstance(content.get("unit_context_evidence"), list) or not isinstance(content.get("evidence"), list)):
                errors.append(f"{prefix}.content raw/normalized/status/unit_context/evidence is invalid")
            elif _UNIT_IN_RAW.search(content["content_raw"]) and (content["unit_context_raw"] is not None or content["unit_context_evidence"]):
                errors.append(f"{prefix}.content direct unit must not carry header unit context")
            elif content["unit_context_raw"] is None and content["unit_context_evidence"]:
                errors.append(f"{prefix}.content null unit context must not carry unit_context_evidence")
            elif content["unit_context_raw"] is not None and (not content["unit_context_raw"].strip() or not content["unit_context_evidence"]):
                errors.append(f"{prefix}.content header unit context requires non-empty unit_context_evidence")
            if isinstance(content, dict) and isinstance(content.get("evidence"), list):
                _evidence(content["evidence"], f"{prefix}.content.evidence", errors)
            if isinstance(content, dict) and isinstance(content.get("unit_context_evidence"), list):
                _evidence(content["unit_context_evidence"], f"{prefix}.content.unit_context_evidence", errors)
            if isinstance(content, dict) and (content.get("content_status") == "PAIR_AMBIGUOUS" or row.get("pair_status") == "PAIR_AMBIGUOUS"):
                if content.get("content_raw") != "" or content.get("content_normalized") != "":
                    errors.append(f"{prefix}.content ambiguous final raw/normalized must be empty strings")
            if isinstance(content, dict) and content.get("content_status") == "NOT_STATED":
                if content.get("content_raw") != "" or content.get("content_normalized") != "" or row.get("pair_status") == "PAIRED":
                    errors.append(f"{prefix}.content NOT_STATED requires empty raw/normalized and non-PAIRED pair_status")
            if isinstance(content, dict):
                content_status = content.get("content_status")
                expected_pair_status = _CONTENT_TO_PAIR_STATUS.get(content_status) if isinstance(content_status, str) else None
                if expected_pair_status is not None and row.get("pair_status") != expected_pair_status:
                    errors.append(f"{prefix}.pair_status must match content_status {content.get('content_status')} ({expected_pair_status})")
            if not _enum_member(row.get("pair_status"), _PAIR_STATUSES):
                errors.append(f"{prefix}.pair_status is invalid")
            if not _nonempty(row.get("block_id")):
                errors.append(f"{prefix}.block_id is required")
            relation = row.get("source_relation")
            if not isinstance(relation, dict) or not _nonempty(relation.get("relation_reason")):
                errors.append(f"{prefix}.source_relation.relation_reason is required")
            elif any(
                field in relation and relation[field] is not None and not isinstance(relation[field], str)
                for field in ("row_id", "shared_content_id")
            ):
                errors.append(f"{prefix}.source_relation row_id/shared_content_id must be null or strings")
            _evidence(row.get("evidence"), f"{prefix}.evidence", errors)
        _shared_content_relations(rows, errors)
    _history(case, errors)
    if "expected" in case and not isinstance(case["expected"], dict):
        errors.append("expected must be an object when present")
    if "blockers" in case and (
        not isinstance(case["blockers"], list) or not all(isinstance(blocker, str) for blocker in case["blockers"])
    ):
        errors.append("blockers must be a list of strings when present")
    _expected(case, errors)
    _source_transcription(case, errors)
    _approved_provenance(case, errors)
    return errors


def _source_asset_errors(case: dict[str, Any], source_roots: Mapping[str, str | Path] | None) -> list[str]:
    source = case.get("source")
    if not isinstance(source, dict) or not isinstance(source_roots, Mapping):
        return ["source asset is unavailable: no local source root mapping"]
    root_name, relative_path = source.get("source_root"), source.get("relative_path")
    root = source_roots.get(root_name) if isinstance(root_name, str) else None
    if root is None or (isinstance(root, str) and not root.strip()) or not isinstance(relative_path, str):
        return ["source asset is unavailable: source root is not mapped"]
    try:
        candidate = Path(root).joinpath(*PurePosixPath(relative_path).parts)
        resolved_root, resolved_candidate = Path(root).resolve(), candidate.resolve()
        resolved_candidate.relative_to(resolved_root)
    except (OSError, TypeError):
        return ["source asset is unavailable: could not resolve or read file"]
    except ValueError:
        return ["source asset is unavailable: relative path escapes source root"]
    try:
        if not resolved_candidate.is_file():
            return ["source asset is unavailable: file does not exist"]
        source_bytes = resolved_candidate.read_bytes()
    except (OSError, PermissionError):
        return ["source asset is unavailable: could not resolve or read file"]
    errors: list[str] = []
    if case.get("lifecycle") == "APPROVED" and not source_bytes.startswith(b"%PDF-"):
        errors.append("APPROVED source asset must have a PDF signature")
    if sha256(source_bytes).hexdigest() != case.get("source_sha256"):
        errors.append("source asset SHA-256 does not match source_sha256")
    return errors


def validate_dataset(dataset: Any, *, source_roots: Mapping[str, str | Path] | None = None) -> DatasetValidationResult:
    """Validate a list of cases and optional local source assets without mutation."""
    if not isinstance(dataset, Sequence) or isinstance(dataset, (str, bytes, bytearray)):
        return DatasetValidationResult(errors=("dataset must be a list of cases",))
    errors: list[str] = []
    findings: list[str] = []
    seen_ids: set[str] = set()
    for index, case in enumerate(dataset):
        prefix = f"cases[{index}]"
        errors.extend(f"{prefix}: {error}" for error in validate_case(case))
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        if _nonempty(case_id):
            if case_id in seen_ids:
                errors.append(f"{prefix}: duplicate case_id {case_id}")
            seen_ids.add(case_id)
        asset_errors = _source_asset_errors(case, source_roots)
        target = errors if case.get("lifecycle") == "APPROVED" else findings
        target.extend(f"{prefix}: {error}" for error in asset_errors)
    return DatasetValidationResult(tuple(errors), tuple(findings))


def select_approved_cases(
    cases: Sequence[dict[str, Any]], *, source_roots: Mapping[str, str | Path] | None = None
) -> tuple[dict[str, Any], ...]:
    """Return approved truth only from a dataset that passes semantic and schema gates."""
    if not validate_dataset(cases, source_roots=source_roots).valid:
        return ()
    if any(_schema_validation_errors(case) for case in cases):
        return ()
    return tuple(
        case for case in cases
        if (
            isinstance(case, dict)
            and case.get("lifecycle") == "APPROVED"
            and not validate_case(case)
            and not _source_asset_errors(case, source_roots)
        )
    )


def _schema_validation_errors(case: Any) -> tuple[str, ...]:
    """Fail closed when the local Draft 2020-12 approval contract cannot validate."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        schema = json.loads(Path(__file__).with_name("schema.json").read_text(encoding="utf-8"))
    except (ImportError, OSError, json.JSONDecodeError):
        return ("schema validation is unavailable",)
    return tuple(str(error) for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(case))


def compare_ordered_rows(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> list[str]:
    """Compare source-list positions directly; duplicate CAS rows are material."""
    differences: list[str] = []
    if len(expected) != len(actual):
        differences.append(f"component count differs: expected {len(expected)}, got {len(actual)}")
    for index, (expected_row, actual_row) in enumerate(zip(expected, actual)):
        if expected_row != actual_row:
            differences.append(f"component row {index} differs")
    return differences
