"""Dependency-free structural checks for lossless Golden v2 fixtures."""

from __future__ import annotations

import re
from typing import Any


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_STATUSES = {"FOUND", "NOT_STATED", "NOT_READABLE", "PAIR_AMBIGUOUS"}
_PAIR_STATUSES = {"PAIRED", "NOT_STATED", "NOT_READABLE", "PAIR_AMBIGUOUS", "REVIEW"}


def validate_case(case: Any) -> list[str]:
    """Return errors while preserving component order and duplicate CAS rows."""
    errors: list[str] = []
    if not isinstance(case, dict):
        return ["case must be an object"]
    if not isinstance(case.get("source_sha256"), str) or not _SHA256.fullmatch(case["source_sha256"]):
        errors.append("source_sha256 must be a lowercase SHA-256")
    if not isinstance(case.get("product"), dict) or not isinstance(case["product"].get("raw"), str):
        errors.append("product.raw is required")
    if not isinstance(case.get("section_provenance"), dict):
        errors.append("section_provenance is required")
    rows = case.get("components")
    if not isinstance(rows, list):
        return errors + ["components must be an ordered list, never a CAS-keyed object"]
    for index, row in enumerate(rows):
        prefix = f"components[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if not isinstance(row.get("cas"), dict) or not isinstance(row["cas"].get("cas_raw"), str):
            errors.append(f"{prefix}.cas.cas_raw is required")
        content = row.get("content")
        if not isinstance(content, dict) or not isinstance(content.get("content_raw"), str) or content.get("content_status") not in _CONTENT_STATUSES:
            errors.append(f"{prefix}.content content_raw/content_status is invalid")
        if row.get("pair_status") not in _PAIR_STATUSES:
            errors.append(f"{prefix}.pair_status is invalid")
        if not isinstance(row.get("block_id"), str):
            errors.append(f"{prefix}.block_id is required")
        if not isinstance(row.get("evidence"), list):
            errors.append(f"{prefix}.evidence must be a list")
    return errors


def compare_ordered_rows(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> list[str]:
    """Compare list positions directly; duplicate CAS rows are meaningful."""
    differences: list[str] = []
    if len(expected) != len(actual):
        differences.append(f"component count differs: expected {len(expected)}, got {len(actual)}")
    for index, (expected_row, actual_row) in enumerate(zip(expected, actual)):
        if expected_row != actual_row:
            differences.append(f"component row {index} differs")
    return differences
