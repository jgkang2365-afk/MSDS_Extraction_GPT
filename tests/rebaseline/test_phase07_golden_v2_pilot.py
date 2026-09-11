"""Local Phase 07 Golden v2 regression-pilot contract and core-route checks."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from golden.v2.validation import select_approved_cases, validate_case, validate_dataset
from src.msds.models import DocumentCapability, FenceStatus
from src.msds.pdf_io import build_section_input, read_pdf_layout
from src.msds.resolver import resolve
from src.msds.sections import locate_sections
from src.msds.validation import validate_resolved


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PILOT_DIRECTORY = REPOSITORY_ROOT / "golden" / "v2" / "cases" / "regression-pilot"
MANIFEST = json.loads((PILOT_DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
SOURCE_ROOT = os.environ.get("PHASE7_TEST_FILE_ROOT")


def _actual_core(source: Path):
    """Run the existing local TEXT Phase 1--5 route; no OCR or external I/O."""
    layout = read_pdf_layout(source)
    section_1, section_3 = locate_sections(layout)
    assert layout.capability is DocumentCapability.TEXT
    assert section_1.fence.status is FenceStatus.FENCE_CONFIRMED
    assert section_3.fence.status is FenceStatus.FENCE_CONFIRMED
    assert all(
        located.description is not None and located.description.capability is DocumentCapability.TEXT
        for located in (section_1, section_3)
    )
    assert dict(layout.metrics)["external_calls"] == 0
    assert dict(section_1.metrics)["external_calls"] == 0
    assert dict(section_3.metrics)["external_calls"] == 0
    resolved = resolve(
        build_section_input(layout, section_1.description),
        build_section_input(layout, section_3.description),
    )
    return layout, section_3, resolved, validate_resolved(resolved)


def _component_projection(component):
    return {
        "cas_raw": component.cas.cas_raw,
        "cas_normalized": component.cas.cas_normalized,
        "cas_status": component.cas.cas_status.value,
        "content_raw": component.content.content_raw,
        "content_normalized": component.content.content_normalized,
        "content_status": component.content.content_status.value,
        "unit_context_raw": component.content.unit_context_raw,
        "pair_status": component.status.value,
        "block_id": component.block_id,
        "row_id": component.row_id,
    }


def _case_component_projection(component: dict):
    return {
        "cas_raw": component["cas"]["cas_raw"],
        "cas_normalized": component["cas"]["cas_normalized"],
        "cas_status": component["cas"]["cas_status"],
        "content_raw": component["content"]["content_raw"],
        "content_normalized": component["content"]["content_normalized"],
        "content_status": component["content"]["content_status"],
        "unit_context_raw": component["content"]["unit_context_raw"],
        "pair_status": component["pair_status"],
        "block_id": component["block_id"],
        "row_id": component["source_relation"].get("row_id"),
    }


@pytest.mark.skipif(not SOURCE_ROOT, reason="PHASE7_TEST_FILE_ROOT is required for the local-only Phase 07 PDF pilot")
def test_phase07_value_candidates_match_local_text_core_and_remain_unreviewed():
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
    assert all(case["case_kind"] == "VALUE_TRUTH" and case["lifecycle"] == "CANDIDATE" for case in cases)
    assert all("expected" not in case for case in cases)
    assert all("source_transcription" not in case for case in cases)
    assert all(len(case["review_history"]) == 1 for case in cases)
    assert all(case["review_history"][0]["action"] == case["review_history"][0]["status"] == "CANDIDATE" for case in cases)
    assert all("timestamp" not in case["review_history"][0] for case in cases)
    assert sum(event["status"] in {"HUMAN_REVIEWED", "APPROVED"} for case in cases for event in case["review_history"]) == 0
    assert all(case["blockers"] == [] for case in cases)

    actual = {}
    for case in cases:
        layout, section_3, resolved, report = _actual_core(source_root / case["source"]["relative_path"])
        actual[case["case_id"]] = (layout, section_3, resolved, report)
        assert case["product"] == {
            "raw": resolved.product.raw,
            "normalized": resolved.product.normalized,
            "status": resolved.product.status.value,
            "provenance": [],
        }
        assert [_case_component_projection(component) for component in case["components"]] == [
            _component_projection(component) for component in resolved.components
        ]

    sarapong = actual["phase7-regression-pilot-008-sarapong"]
    assert [component.cas.cas_raw for component in sarapong[2].components] == ["7732-18-5", "1310-73-2"]
    assert [component.content.content_raw for component in sarapong[2].components] == ["60 ~ 70", "< 1"]
    assert [(component.cas.cas_status.value, component.status.value) for component in sarapong[2].components] == [("FOUND", "PAIRED"), ("FOUND", "PAIRED")]
    assert sarapong[3].status.value == "PASS"
    assert [finding.code.value for finding in sarapong[3].findings] == []

    teca = actual["phase7-regression-pilot-015-teca-biome"]
    assert len(teca[0].pages) == 5
    assert all(len(page.image_xrefs) == 1 for page in teca[0].pages)
    assert len({page.image_xrefs for page in teca[0].pages}) == 1
    assert len(teca[2].components) == 12
    assert [(component.cas.cas_status.value, component.status.value) for component in teca[2].components] == [("FOUND", "PAIRED")] * 12
    assert [component.content.content_raw for component in teca[2].components if component.cas.cas_raw in {"92128-87-5", "308068-11-3"}] == ["1.00", "1.00"]
    teca_case = next(case for case in cases if case["case_id"] == "phase7-regression-pilot-015-teca-biome")
    shared_rows = [component["source_relation"] for component in teca_case["components"] if component["cas"]["cas_raw"] in {"92128-87-5", "308068-11-3"}]
    assert shared_rows == [
        {"row_id": "section3-row-9", "shared_content_id": "section3-page-0-block-15:content", "relation_reason": "shared source row content"},
        {"row_id": "section3-row-9", "shared_content_id": "section3-page-0-block-15:content", "relation_reason": "shared source row content"},
    ]
    assert teca[3].status.value == "PASS"
    assert [finding.code.value for finding in teca[3].findings] == []

    sodium = actual["phase7-regression-pilot-024-sodium-hydroxide"]
    assert [component.cas.cas_raw for component in sodium[2].components] == ["1310-73-2", "7732-18-5"]
    assert [component.content.content_raw for component in sodium[2].components] == ["92-100％", "8-0％"]
    assert [(component.cas.cas_status.value, component.status.value) for component in sodium[2].components] == [("FOUND", "PAIRED"), ("FOUND", "PAIRED")]
    assert sodium[3].status.value == "PASS"
    assert [finding.code.value for finding in sodium[3].findings] == []

    result = validate_dataset(cases, source_roots={MANIFEST["source_root"]: source_root})
    assert result.errors == ()
    assert result.findings == ()
    assert select_approved_cases(cases, source_roots={MANIFEST["source_root"]: source_root}) == ()
