import copy
from hashlib import sha256
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from golden.v2.validation import compare_ordered_rows, select_approved_cases, validate_case


def _human_evidence(page, **extra):
    return {"provenance_type": "HUMAN_DIRECT_SOURCE_PDF_REVIEW", "page": page, **extra}


def _review_event(stage):
    event = {"action": stage, "status": stage}
    if stage != "CANDIDATE":
        event.update(
            reviewer_ref="reviewer-ticket-7",
            timestamp="2026-09-09T10:30:00+09:00",
            review_method="DIRECT_SOURCE_PDF_REVIEW",
            source_pdf_directly_confirmed=True,
            section_1_confirmed=True,
            section_3_confirmed=True,
        )
    return event


def _row(cas_raw="64-17-5", block_id="block-1", content_raw="50%", content_status="FOUND", pair_status="PAIRED"):
    return {
        "cas": {"cas_raw": cas_raw, "cas_normalized": cas_raw, "cas_status": "FOUND", "evidence": [_human_evidence(2)]},
        "content": {
            "content_raw": content_raw,
            "content_normalized": content_raw,
            "content_status": content_status,
            "unit_context_raw": None,
            "unit_context_evidence": [],
            "evidence": [_human_evidence(2)],
        },
        "pair_status": pair_status,
        "block_id": block_id,
        "source_relation": {"row_id": "row-1", "shared_content_id": None, "relation_reason": "same source row"},
        "evidence": [_human_evidence(2, section="3", raw_fragment=cas_raw)],
    }


def _case(*, lifecycle="CANDIDATE", kind="VALUE_TRUTH"):
    case = {
        "case_id": "g6-case-001",
        "case_kind": kind,
        "lifecycle": lifecycle,
        "source_sha256": "a" * 64,
        "source": {"source_root": "reviewed-pdfs", "relative_path": "supplier/example.pdf"},
        "product": {"raw": "Product (Grade A)", "normalized": "product (grade a)", "status": "FOUND", "provenance": [_human_evidence(0)]},
        "section_provenance": {"section_1": {"evidence": [_human_evidence(0)]}, "section_3": {"evidence": [_human_evidence(2)]}},
        "components": [_row()],
        "review_history": [_review_event("CANDIDATE")],
    }
    if lifecycle == "HUMAN_REVIEWED":
        case["review_history"].append(_review_event("HUMAN_REVIEWED"))
    if lifecycle == "APPROVED":
        case["review_history"].extend([_review_event("HUMAN_REVIEWED"), _review_event("APPROVED")])
        case["source_transcription"] = {
            "product_raw": "Product (Grade A)",
            "product_evidence": [_human_evidence(0)],
            "transcription_method": "HUMAN_DIRECT_SOURCE_PDF_REVIEW",
            "source_pdf_directly_confirmed": True,
            "component_rows": [{"block_id": "block-1", "cas_raw": "64-17-5", "content_raw": "50%", "evidence": [_human_evidence(2)]}],
        }
    return case


def _approved_with_source(tmp_path, *, name="example.pdf", source_bytes=b"%PDF-1.4\nfixture\n%%EOF\n"):
    root = tmp_path / "reviewed"
    source = root / "supplier" / name
    source.parent.mkdir(parents=True)
    source.write_bytes(source_bytes)
    case = _case(lifecycle="APPROVED")
    case["source"]["relative_path"] = f"supplier/{name}"
    case["source_sha256"] = sha256(source_bytes).hexdigest()
    return case, root


def test_g6_01_candidate_is_valid_but_not_approved_truth():
    candidate = _case()
    assert validate_case(candidate) == []
    assert select_approved_cases([candidate]) == ()


def test_g6_02_human_reviewed_is_not_approved_truth():
    reviewed = _case(lifecycle="HUMAN_REVIEWED")
    assert validate_case(reviewed) == []
    assert select_approved_cases([reviewed]) == ()


def test_g6_03_approved_only_selector_keeps_only_asset_valid_approved_cases(pdf_tmp):
    approved, root = _approved_with_source(pdf_tmp)
    assert select_approved_cases([approved]) == ()
    assert select_approved_cases(
        [_case(), _case(lifecycle="HUMAN_REVIEWED"), approved], source_roots={"reviewed-pdfs": root}
    ) == (approved,)


def test_g6_04_approved_requires_both_review_lifecycle_events():
    case = _case(lifecycle="APPROVED")
    case["review_history"] = [_review_event("APPROVED")]
    assert "review_history must exactly match lifecycle stages: CANDIDATE, HUMAN_REVIEWED, APPROVED" in validate_case(case)


def test_g6_05_review_events_require_direct_pdf_s1_s3_and_reviewer_metadata():
    case = _case(lifecycle="HUMAN_REVIEWED")
    event = case["review_history"][-1]
    for field in ("reviewer_ref", "timestamp", "review_method", "source_pdf_directly_confirmed", "section_1_confirmed", "section_3_confirmed"):
        event.pop(field)
    errors = validate_case(case)
    assert len(errors) == 5
    assert any("reviewer_ref" in error for error in errors)
    assert any("review_method" in error for error in errors)


def test_g6_06_history_must_advance_with_matching_action_and_status():
    case = _case(lifecycle="HUMAN_REVIEWED")
    case["review_history"].append(_review_event("HUMAN_REVIEWED"))
    assert "review_history must exactly match lifecycle stages: CANDIDATE, HUMAN_REVIEWED" in validate_case(case)
    case["review_history"][-1]["status"] = "APPROVED"
    assert "review_history[2].action/status must be matching lifecycle values" in validate_case(case)


def test_g6_f1_history_must_end_at_exact_case_lifecycle_and_selector_rejects_malformed_approved():
    candidate = _case()
    candidate["review_history"].append(_review_event("APPROVED"))
    assert "review_history must exactly match lifecycle stages: CANDIDATE" in validate_case(candidate)
    approved = _case(lifecycle="APPROVED")
    approved["review_history"].pop(1)
    assert select_approved_cases([approved]) == ()


def test_g6_07_case_kind_and_lifecycle_are_enumerated():
    case = _case()
    case["case_kind"] = "UNKNOWN"
    case["lifecycle"] = "draft"
    assert {"case_kind is invalid", "lifecycle is invalid"} <= set(validate_case(case))


def test_g6_08_portable_source_reference_rejects_absolute_escape_and_windows_paths():
    case = _case()
    for path in ("C:/reviewed/a.pdf", "../a.pdf", "supplier\\a.pdf"):
        case["source"]["relative_path"] = path
        assert "source.relative_path must be a portable relative path" in validate_case(case)


def test_g6_09_product_retains_raw_normalized_status_and_provenance():
    case = _case()
    assert validate_case(case) == []
    case["product"].pop("provenance")
    assert "product.provenance must be a list" in validate_case(case)


def test_g6_10_order_and_duplicate_cas_rows_are_material():
    case = _case()
    duplicate = _row(block_id="block-2")
    case["components"].append(duplicate)
    assert validate_case(case) == []
    assert compare_ordered_rows(case["components"], list(reversed(case["components"]))) == [
        "component row 0 differs", "component row 1 differs"
    ]


def test_g6_11_component_requires_lossless_cas_fields_and_evidence():
    case = _case()
    case["components"][0]["cas"].pop("evidence")
    assert "components[0].cas raw/normalized/status/evidence is invalid" in validate_case(case)


def test_g6_12_content_statuses_remain_distinct():
    case = _case()
    case["components"] = [
        _row("64-17-5", "blank", "", "NOT_STATED", "NOT_STATED"),
        _row("67-64-1", "unreadable", "?", "NOT_READABLE", "NOT_READABLE"),
        _row("75-09-2", "ambiguous", "", "PAIR_AMBIGUOUS", "PAIR_AMBIGUOUS"),
    ]
    assert validate_case(case) == []


def test_g6_13_pair_status_and_source_relation_are_required():
    case = _case()
    case["components"][0].pop("source_relation")
    case["components"][0]["pair_status"] = "UNKNOWN"
    errors = validate_case(case)
    assert "components[0].pair_status is invalid" in errors
    assert "components[0].source_relation.relation_reason is required" in errors


def test_g6_14_shared_content_relation_is_retained_per_source_row():
    case = _case()
    first, second = _row("64-17-5", "shared"), _row("67-64-1", "shared")
    for row in (first, second):
        row["source_relation"] = {"row_id": "row-shared", "shared_content_id": "content-7", "relation_reason": "one source content shared by two CAS"}
    case["components"] = [first, second]
    assert validate_case(case) == []


def test_g6_15_header_derived_unit_context_preserves_bare_raw():
    case = _case()
    content = case["components"][0]["content"]
    content.update(content_raw="10", content_normalized="10", unit_context_raw="%", unit_context_evidence=[{"page": 2}])
    assert validate_case(case) == []


def test_g6_16_direct_unit_cannot_also_receive_header_context():
    case = _case()
    content = case["components"][0]["content"]
    content["unit_context_raw"] = "%"
    content["unit_context_evidence"] = [{"page": 2}]
    assert "components[0].content direct unit must not carry header unit context" in validate_case(case)


def test_g6_17_ambiguous_multiple_content_has_no_synthetic_joined_raw():
    case = _case()
    content = case["components"][0]["content"]
    content.update(content_raw="", content_normalized="", content_status="PAIR_AMBIGUOUS")
    case["components"][0]["pair_status"] = "PAIR_AMBIGUOUS"
    assert validate_case(case) == []


def test_g6_f2_pair_ambiguity_rejects_nonempty_synthetic_final_raw():
    case = _case()
    case["components"][0]["pair_status"] = "PAIR_AMBIGUOUS"
    assert "components[0].content ambiguous final raw/normalized must be empty strings" in validate_case(case)


def test_g6_18_safe_review_requires_quality_and_finding_expectations():
    case = _case(kind="SAFE_REVIEW")
    assert "SAFE_REVIEW requires expected" in validate_case(case)
    case["expected"] = {"quality_status": "REVIEW_REQUIRED", "finding_codes": ["PAIR_AMBIGUOUS"]}
    assert validate_case(case) == []


def test_g6_f3_safe_review_rejects_pass_even_with_findings():
    case = _case(kind="SAFE_REVIEW")
    case["expected"] = {"quality_status": "PASS", "finding_codes": ["PAIR_AMBIGUOUS"]}
    assert "SAFE_REVIEW requires expected.quality_status REVIEW_REQUIRED" in validate_case(case)


def test_g6_19_failure_behavior_requires_safe_outcome():
    case = _case(kind="FAILURE_BEHAVIOR")
    case["expected"] = {"safe_outcome": "IGNORE"}
    assert "FAILURE_BEHAVIOR requires expected.safe_outcome" in validate_case(case)
    case["expected"] = {"safe_outcome": "FENCE_BLOCKED"}
    assert validate_case(case) == []


def test_g6_20_validator_never_mutates_input():
    case = _case()
    before = copy.deepcopy(case)
    validate_case(case)
    assert case == before


def test_g6_21_case_id_sha_and_ordered_list_are_required():
    case = _case()
    case.update(case_id="", source_sha256="UPPER", components={})
    errors = validate_case(case)
    assert {"case_id is required", "source_sha256 must be a lowercase SHA-256", "components must be an ordered list, never a CAS-keyed object"} <= set(errors)


def test_g6_22_section_1_and_section_3_provenance_are_required():
    case = _case()
    case["section_provenance"] = {"section_1": {"evidence": []}, "section_3": {}}
    assert "section_provenance.section_3.evidence must be a list" in validate_case(case)


def test_g6_23_optional_review_reason_must_be_text():
    case = _case(lifecycle="HUMAN_REVIEWED")
    case["review_history"][-1]["reason"] = 7
    assert "review_history[1].reason must be a string when present" in validate_case(case)


def test_g6_f5_timestamp_requires_a_real_calendar_date_and_offset():
    case = _case(lifecycle="HUMAN_REVIEWED")
    case["review_history"][-1]["timestamp"] = "2026-02-30T10:30:00+25:00"
    assert "review_history[1].timestamp must be an ISO-8601 timestamp with timezone" in validate_case(case)


def test_g6_f6_header_context_requires_nonempty_evidence_and_direct_units_remain_raw_only():
    case = _case()
    content = case["components"][0]["content"]
    content.update(content_raw="10", content_normalized="10", unit_context_raw="%", unit_context_evidence=[])
    assert "components[0].content header unit context requires non-empty unit_context_evidence" in validate_case(case)


def test_g6_f7_source_transcription_is_human_source_notation_with_its_own_evidence():
    case = _case(lifecycle="APPROVED")
    assert validate_case(case) == []
    case["source_transcription"]["component_rows"][0]["evidence"] = []
    assert "source_transcription.component_rows[0].evidence must be a non-empty list for APPROVED" in validate_case(case)


@pytest.mark.parametrize("evidence", [[None], [{}], [{"raw_reading": "50%"}]])
def test_g6_f8_approved_evidence_requires_meaningful_human_source_provenance(evidence):
    case = _case(lifecycle="APPROVED")
    case["components"][0]["evidence"] = evidence
    errors = validate_case(case)
    assert "components[0].evidence[0] must be human direct-source PDF provenance with a non-negative page" in errors


def test_g6_f8_approved_header_unit_context_evidence_is_human_source_provenance():
    case = _case(lifecycle="APPROVED")
    content = case["components"][0]["content"]
    content.update(content_raw="10", content_normalized="10", unit_context_raw="%", unit_context_evidence=[{"page": 2}])
    assert "components[0].content.unit_context_evidence[0] must be human direct-source PDF provenance with a non-negative page" in validate_case(case)


def test_g6_f9_approved_transcription_rows_match_component_source_order_and_human_origin():
    case = _case(lifecycle="APPROVED")
    case["components"].append(_row("67-64-1", "block-2", "40%"))
    case["source_transcription"]["component_rows"].append(
        {"block_id": "block-2", "cas_raw": "67-64-1", "content_raw": "40%", "evidence": [_human_evidence(2)]}
    )
    assert validate_case(case) == []
    case["source_transcription"]["component_rows"][1]["cas_raw"] = "wrong"
    assert "source_transcription.component_rows[1] must correspond to components[1] source order, raw values, and evidence" in validate_case(case)
    case["source_transcription"]["component_rows"][1]["cas_raw"] = "67-64-1"
    case["source_transcription"]["component_rows"][1]["evidence"] = [_human_evidence(9)]
    assert "source_transcription.component_rows[1] must correspond to components[1] source order, raw values, and evidence" in validate_case(case)
    case["source_transcription"]["component_rows"][1]["evidence"] = [_human_evidence(2)]
    case["source_transcription"]["component_rows"][1]["raw_reading"] = "40%"
    assert "APPROVED source_transcription must not contain OCR raw_reading" in validate_case(case)


def test_g6_f9_candidate_may_remain_without_source_transcription():
    assert validate_case(_case()) == []


def test_g6_f12_approved_pdf_kind_is_case_validation_and_selector_gate(pdf_tmp):
    text_case, text_root = _approved_with_source(pdf_tmp, name="example.txt")
    assert "APPROVED source.relative_path must end in .pdf" in validate_case(text_case)
    assert select_approved_cases([text_case], source_roots={"reviewed-pdfs": text_root}) == ()
    fake_pdf, fake_root = _approved_with_source(pdf_tmp / "fake", source_bytes=b"not a PDF")
    assert select_approved_cases([fake_pdf], source_roots={"reviewed-pdfs": fake_root}) == ()


def test_g6_f13_transcription_evidence_requires_ordered_one_to_one_occurrences():
    case = _case(lifecycle="APPROVED")
    component = case["components"][0]
    component["evidence"] = [_human_evidence(2), _human_evidence(3)]
    transcription = case["source_transcription"]["component_rows"][0]
    transcription["evidence"] = [_human_evidence(2), _human_evidence(3)]
    assert validate_case(case) == []
    transcription["evidence"] = [_human_evidence(2)]
    assert "source_transcription.component_rows[0] must correspond to components[0] source order, raw values, and evidence" in validate_case(case)
    transcription["evidence"] = [_human_evidence(2), _human_evidence(2)]
    assert "source_transcription.component_rows[0] must correspond to components[0] source order, raw values, and evidence" in validate_case(case)


def test_g6_f13_duplicate_cas_occurrences_remain_distinct_by_ordered_row_evidence():
    case = _case(lifecycle="APPROVED")
    duplicate = _row("64-17-5", "block-2", "50%")
    duplicate["evidence"] = [_human_evidence(3)]
    case["components"].append(duplicate)
    case["source_transcription"]["component_rows"].append(
        {"block_id": "block-2", "cas_raw": "64-17-5", "content_raw": "50%", "evidence": [_human_evidence(3)]}
    )
    assert validate_case(case) == []
    case["source_transcription"]["component_rows"].reverse()
    assert "source_transcription.component_rows[0] must correspond to components[0] source order, raw values, and evidence" in validate_case(case)


def test_g6_f14_null_unit_context_rejects_context_evidence_even_if_source_evidence_exists():
    case = _case(lifecycle="APPROVED")
    content = case["components"][0]["content"]
    content.update(content_raw="10", content_normalized="10", unit_context_raw=None, unit_context_evidence=[_human_evidence(2, raw_reading="%")])
    assert "components[0].content null unit context must not carry unit_context_evidence" in validate_case(case)


@pytest.mark.parametrize("raw", ["500ppm", "10wt%", "20vol%"])
def test_g6_f11_no_space_direct_units_cannot_receive_header_context(raw):
    case = _case()
    content = case["components"][0]["content"]
    content.update(content_raw=raw, content_normalized=raw, unit_context_raw="%", unit_context_evidence=[_human_evidence(2)])
    assert "components[0].content direct unit must not carry header unit context" in validate_case(case)


def test_g6_f4_approved_requires_all_product_section_and_component_provenance():
    case = _case(lifecycle="APPROVED")
    case["section_provenance"]["section_1"]["evidence"] = []
    case["section_provenance"]["section_3"]["evidence"] = []
    case["components"][0]["cas"]["evidence"] = []
    case["components"][0]["content"]["evidence"] = []
    case["components"][0]["evidence"] = []
    errors = validate_case(case)
    assert "section_provenance.section_1.evidence must be a non-empty list for APPROVED" in errors
    assert "section_provenance.section_3.evidence must be a non-empty list for APPROVED" in errors
    assert "components[0].cas.evidence must be a non-empty list for APPROVED" in errors
    assert "components[0].content.evidence must be a non-empty list for APPROVED" in errors
    assert "components[0].evidence must be a non-empty list for APPROVED" in errors


def test_g6_24_schema_declares_the_same_core_contract_fields():
    schema_path = Path(__file__).resolve().parents[2] / "golden" / "v2" / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert {"case_id", "case_kind", "lifecycle", "source", "review_history"} <= set(schema["required"])
    assert schema["properties"]["case_kind"]["enum"] == ["VALUE_TRUTH", "SAFE_REVIEW", "FAILURE_BEHAVIOR"]
    component = schema["$defs"]["component"]["properties"]
    assert component["content"]["required"] == ["content_raw", "content_normalized", "content_status", "unit_context_raw", "unit_context_evidence", "evidence"]
    assert component["source_relation"]["required"] == ["relation_reason"]
    assert schema["properties"]["source_transcription"]["required"] == ["product_raw", "product_evidence", "component_rows"]
    assert schema["$defs"]["approved_human_source_evidence"]["required"] == ["provenance_type", "page"]
    assert component["content"]["allOf"][0]["then"]["properties"]["unit_context_evidence"]["maxItems"] == 0


def test_g6_25_schema_has_no_absolute_source_path_field():
    schema = json.loads((Path(__file__).resolve().parents[2] / "golden" / "v2" / "schema.json").read_text(encoding="utf-8"))
    assert set(schema["properties"]["source"]["properties"]) == {"source_root", "relative_path"}


def test_g6_26_v2_contract_has_no_golden_v1_import_or_copy_path():
    module = (Path(__file__).resolve().parents[2] / "golden" / "v2" / "validation.py").read_text(encoding="utf-8")
    assert "golden.v1" not in module
    assert "msds_golden_v1" not in module


def _schema_errors(case):
    schema_path = Path(__file__).resolve().parents[2] / "golden" / "v2" / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return list(validator.iter_errors(case))


def test_g6_r4_schema_accepts_the_valid_candidate_and_approved_contracts():
    assert _schema_errors(_case()) == []
    assert _schema_errors(_case(lifecycle="APPROVED")) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda case: case["review_history"][-1].pop("reviewer_ref"),
        lambda case: case["review_history"][-1].__setitem__("timestamp", "2026-02-30T10:30:00+09:00"),
        lambda case: case["review_history"][-1].__setitem__("review_method", "OCR"),
        lambda case: case["review_history"][-1].__setitem__("source_pdf_directly_confirmed", False),
        lambda case: case["review_history"][-1].__setitem__("section_1_confirmed", False),
        lambda case: case["review_history"][-1].__setitem__("section_3_confirmed", False),
        lambda case: case["product"].__setitem__("provenance", [{"provenance_type": "OCR", "page": 0}]),
        lambda case: case["source_transcription"].__setitem__("source_pdf_directly_confirmed", False),
        lambda case: case["components"][0]["content"].update(unit_context_raw="%", unit_context_evidence=[_human_evidence(2)]),
        lambda case: case["components"][0]["content"].update(content_raw="50% / 40%", content_normalized="50% / 40%", content_status="PAIR_AMBIGUOUS"),
    ],
)
def test_g6_r4_schema_rejects_approved_history_provenance_and_content_contract_violations(mutate):
    case = _case(lifecycle="APPROVED")
    mutate(case)
    assert _schema_errors(case)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("SAFE_REVIEW", None), ("SAFE_REVIEW", {"quality_status": "PASS", "finding_codes": ["PAIR_AMBIGUOUS"]}), ("FAILURE_BEHAVIOR", None), ("FAILURE_BEHAVIOR", {"safe_outcome": "IGNORE"})],
)
def test_g6_r4_schema_requires_safe_review_and_failure_expected_outcomes(kind, expected):
    case = _case(kind=kind)
    if expected is not None:
        case["expected"] = expected
    assert _schema_errors(case)


def test_g6_r4_schema_and_selector_reject_nonportable_or_nonprimitive_structural_bypasses(pdf_tmp):
    approved, root = _approved_with_source(pdf_tmp)
    invalid_cases = []
    for mutate in (
        lambda case: case["source"].__setitem__("absolute_path", "C:/private/source.pdf"),
        lambda case: case["components"][0]["evidence"][0].__setitem__("page", True),
        lambda case: case["components"][0]["source_relation"].__setitem__("shared_content_id", 7),
        lambda case: case.__setitem__("expected", "not-an-object"),
        lambda case: case.__setitem__("blockers", [7]),
    ):
        case = copy.deepcopy(approved)
        mutate(case)
        assert _schema_errors(case)
        assert validate_case(case)
        invalid_cases.append(case)
    assert select_approved_cases(invalid_cases, source_roots={"reviewed-pdfs": root}) == ()


def test_g6_r5_schema_requires_transcription_rows_when_approved_case_has_components():
    case = _case(lifecycle="APPROVED")
    case["source_transcription"]["component_rows"] = []
    assert _schema_errors(case)
    assert "APPROVED source_transcription.component_rows must cover every component row" in validate_case(case)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row.__setitem__("block_id", ""),
        lambda row: row.__setitem__("cas_raw", ""),
        lambda row: row.__setitem__("content_raw", 50),
        lambda row: row.__setitem__("evidence", []),
        lambda row: row.__setitem__("evidence", [{"provenance_type": "OCR", "page": 2}]),
    ],
)
def test_g6_r5_schema_rejects_malformed_approved_transcription_component_row_shapes(mutate):
    case = _case(lifecycle="APPROVED")
    mutate(case["source_transcription"]["component_rows"][0])
    assert _schema_errors(case)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda transcription: transcription.__setitem__("raw_reading", "Product (Grade A)"),
        lambda transcription: transcription["product_evidence"][0].__setitem__("raw_reading", "Product (Grade A)"),
        lambda transcription: transcription["component_rows"][0]["evidence"][0].__setitem__("raw_reading", "50%"),
    ],
)
def test_g6_r5_schema_rejects_ocr_raw_reading_anywhere_in_approved_source_transcription(mutate):
    case = _case(lifecycle="APPROVED")
    mutate(case["source_transcription"])
    assert _schema_errors(case)
    assert "APPROVED source_transcription must not contain OCR raw_reading" in validate_case(case)


def test_g6_r4_transcription_evidence_rejects_same_page_reversed_bbox_locators():
    case = _case(lifecycle="APPROVED")
    component = case["components"][0]
    component["evidence"] = [
        _human_evidence(2, bbox=[10, 10, 20, 20], raw_fragment="CAS"),
        _human_evidence(2, bbox=[30, 10, 40, 20], raw_fragment="content"),
    ]
    transcription = case["source_transcription"]["component_rows"][0]
    transcription["evidence"] = [
        _human_evidence(2, bbox=[10, 10, 20, 20], reviewer_note="first"),
        _human_evidence(2, bbox=[30, 10, 40, 20], reviewer_note="second"),
    ]
    assert validate_case(case) == []
    transcription["evidence"].reverse()
    # Draft 2020-12 validates each locator's local shape, but cannot compare
    # arbitrary values and order across the two evidence arrays.
    assert _schema_errors(case) == []
    assert "source_transcription.component_rows[0] must correspond to components[0] source order, raw values, and evidence" in validate_case(case)
