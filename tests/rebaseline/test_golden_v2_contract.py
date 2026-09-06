import json
from pathlib import Path

from golden.v2.validation import compare_ordered_rows, validate_case


def _row(cas_raw, block_id, content_status="FOUND", pair_status="PAIRED"):
    return {
        "cas": {"cas_raw": cas_raw, "cas_normalized": cas_raw, "cas_status": "FOUND"},
        "content": {"content_raw": "50%", "content_normalized": "50%", "content_status": content_status},
        "pair_status": pair_status,
        "block_id": block_id,
        "evidence": [{"section": "3", "page": 2, "raw_fragment": cas_raw}],
    }


def test_golden_v2_retains_ordered_duplicate_rows_and_section_provenance():
    case = {
        "source_sha256": "a" * 64,
        "product": {"raw": "Product (Grade A)", "normalized": "product (grade a)"},
        "section_provenance": {"section_1": {"page": 1}, "section_3": {"page": 2}},
        "components": [_row("64-17-5", "block-1"), _row("64-17-5", "block-2")],
    }
    assert validate_case(case) == []
    assert compare_ordered_rows(case["components"], list(reversed(case["components"]))) == [
        "component row 0 differs", "component row 1 differs"
    ]


def test_golden_v2_statuses_include_not_stated_not_readable_ambiguous_and_review():
    base = {
        "source_sha256": "b" * 64,
        "product": {"raw": "Product"},
        "section_provenance": {"section_1": {"page": 1}, "section_3": {"page": 2}},
        "components": [
            _row("64-17-5", "missing", "NOT_STATED", "NOT_STATED"),
            _row("67-64-1", "unreadable", "NOT_READABLE", "NOT_READABLE"),
            _row("67-64-1", "ambiguous", "PAIR_AMBIGUOUS", "PAIR_AMBIGUOUS"),
            _row("67-64-1", "review", "FOUND", "REVIEW"),
        ],
    }
    assert validate_case(base) == []


def test_golden_v2_rejects_cas_keyed_component_dicts():
    case = {"source_sha256": "c" * 64, "product": {"raw": "P"}, "section_provenance": {}, "components": {}}
    assert "components must be an ordered list, never a CAS-keyed object" in validate_case(case)


def test_golden_v2_validates_schema_required_contract_fields_and_provenance():
    case = {
        "source_sha256": "d" * 64,
        "product": {"raw": "P"},
        "section_provenance": {"section_3": {"page": 2}},
        "components": [_row("64-17-5", "block-1")],
    }
    case["components"][0]["cas"].pop("cas_normalized")
    case["components"][0]["content"].pop("content_normalized")
    errors = validate_case(case)
    assert "section_provenance.section_1 is required" in errors
    assert "components[0].cas cas_raw/cas_normalized/cas_status is invalid" in errors
    assert "components[0].content content_raw/content_normalized/content_status is invalid" in errors


def test_golden_v2_schema_declares_section_and_component_contract_fields():
    schema_path = Path(__file__).resolve().parents[2] / "golden" / "v2" / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["section_provenance"]["required"] == ["section_1", "section_3"]
    component_properties = schema["properties"]["components"]["items"]["properties"]
    assert component_properties["cas"]["required"] == ["cas_raw", "cas_normalized", "cas_status"]
    assert component_properties["content"]["required"] == ["content_raw", "content_normalized", "content_status"]
