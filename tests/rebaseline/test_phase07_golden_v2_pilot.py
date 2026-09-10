"""Local Phase 07 Golden v2 regression-pilot contract checks."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from golden.v2.validation import select_approved_cases, validate_case, validate_dataset
from src.msds.models import DocumentCapability, FenceStatus
from src.msds.pdf_io import read_pdf_layout
from src.msds.sections import locate_sections


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PILOT_DIRECTORY = REPOSITORY_ROOT / "golden" / "v2" / "cases" / "regression-pilot"
MANIFEST = json.loads((PILOT_DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
SOURCE_ROOT = os.environ.get("PHASE7_TEST_FILE_ROOT")


def _actual_fence_blockers(source: Path) -> list[str]:
    """Observe only the local TEXT fence route; never invoke OCR or resolution."""
    layout = read_pdf_layout(source)
    section_1, section_3 = locate_sections(layout)

    assert layout.capability is DocumentCapability.TEXT
    assert dict(layout.metrics)["external_calls"] == 0
    assert dict(section_1.metrics)["external_calls"] == 0
    assert dict(section_3.metrics)["external_calls"] == 0
    assert all(
        located.description is None or located.description.capability is DocumentCapability.TEXT
        for located in (section_1, section_3)
    )
    assert not (
        section_1.fence.status is FenceStatus.FENCE_CONFIRMED
        and section_3.fence.status is FenceStatus.FENCE_CONFIRMED
    )

    blockers: list[str] = []
    for section_no, located in (("1", section_1), ("3", section_3)):
        if located.fence.status is not FenceStatus.FENCE_CONFIRMED:
            blockers.extend(
                f"SECTION_{section_no}_{located.fence.status.value}:{reason}"
                for reason in located.reasons
            )
    if "SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED" in section_1.reasons + section_3.reasons:
        blockers.append("OCR_NOT_RUN_BY_PHASE_07_TEXT_ONLY_PILOT")
    return blockers


@pytest.mark.skipif(not SOURCE_ROOT, reason="PHASE7_TEST_FILE_ROOT is required for the local-only Phase 07 PDF pilot")
def test_phase07_candidates_are_portable_unreviewed_and_local_source_validated():
    cases = [json.loads((PILOT_DIRECTORY / filename).read_text(encoding="utf-8")) for filename in MANIFEST["case_files"]]
    source_root = Path(SOURCE_ROOT)
    schema = json.loads((REPOSITORY_ROOT / "golden" / "v2" / "schema.json").read_text(encoding="utf-8"))
    schema_validator = Draft202012Validator(schema, format_checker=FormatChecker())

    assert len(cases) == 3
    assert all(not list(schema_validator.iter_errors(case)) for case in cases)
    assert all(validate_case(case) == [] for case in cases)
    assert all(case["source"]["source_root"] == MANIFEST["source_root"] for case in cases)
    assert all("/" not in case["source"]["relative_path"] and "\\" not in case["source"]["relative_path"] for case in cases)
    assert all(sha256((source_root / case["source"]["relative_path"]).read_bytes()).hexdigest() == case["source_sha256"] for case in cases)
    assert all(case["case_kind"] == "FAILURE_BEHAVIOR" for case in cases)
    assert all(case["expected"] == {"safe_outcome": "FENCE_BLOCKED"} for case in cases)
    assert all(case["components"] == [] for case in cases)
    assert all(case["product"] == {"raw": "", "normalized": "", "status": "REVIEW", "provenance": []} for case in cases)
    assert all(case["blockers"] == _actual_fence_blockers(source_root / case["source"]["relative_path"]) for case in cases)

    result = validate_dataset(cases, source_roots={MANIFEST["source_root"]: source_root})
    assert result.errors == ()
    assert result.findings == ()
    assert select_approved_cases(cases, source_roots={MANIFEST["source_root"]: source_root}) == ()
    assert sum(event["status"] in {"HUMAN_REVIEWED", "APPROVED"} for case in cases for event in case["review_history"]) == 0
    assert all(len(case["review_history"]) == 1 for case in cases)
    assert all(case["review_history"][0]["action"] == case["review_history"][0]["status"] == "CANDIDATE" for case in cases)
    assert all("timestamp" not in case["review_history"][0] for case in cases)
