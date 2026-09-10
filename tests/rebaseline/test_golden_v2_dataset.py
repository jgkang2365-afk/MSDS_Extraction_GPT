import copy
from hashlib import sha256

import pytest

from golden.v2 import validation
from golden.v2.validation import select_approved_cases, validate_case, validate_dataset

from test_golden_v2_contract import _case


def _approved_case(path):
    case = _case(lifecycle="APPROVED")
    case["source_sha256"] = sha256(path.read_bytes()).hexdigest()
    return case


def test_b01_approved_source_file_must_exist_and_match_sha256(pdf_tmp):
    root = pdf_tmp / "reviewed"
    source = root / "supplier" / "example.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4\nminimal local test fixture\n%%EOF\n")
    case = _approved_case(source)
    result = validate_dataset([case], source_roots={"reviewed-pdfs": root})
    assert result.errors == ()
    assert result.findings == ()
    source.write_bytes(b"changed")
    result = validate_dataset([case], source_roots={"reviewed-pdfs": root})
    assert any("SHA-256 does not match" in error for error in result.errors)


def test_b01_approved_source_requires_pdf_extension_signature_and_nonempty_provenance(pdf_tmp):
    root = pdf_tmp / "reviewed"
    source = root / "supplier" / "example.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"not a PDF")
    case = _approved_case(source)
    result = validate_dataset([case], source_roots={"reviewed-pdfs": root})
    assert any("PDF signature" in error for error in result.errors)
    case["product"]["provenance"] = []
    result = validate_dataset([case], source_roots={"reviewed-pdfs": root})
    assert any("product.provenance must be a non-empty list" in error for error in result.errors)


def test_b01_approved_source_requires_a_pdf_portable_reference(pdf_tmp):
    root = pdf_tmp / "reviewed"
    source = root / "supplier" / "example.txt"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
    case = _approved_case(source)
    case["source"]["relative_path"] = "supplier/example.txt"
    result = validate_dataset([case], source_roots={"reviewed-pdfs": root})
    assert any("must end in .pdf" in error for error in result.errors)


def test_b02_missing_candidate_asset_is_a_blocker_finding_not_an_approval_error(pdf_tmp):
    result = validate_dataset([_case()], source_roots={"reviewed-pdfs": pdf_tmp})
    assert result.errors == ()
    assert result.findings == ("cases[0]: source asset is unavailable: file does not exist",)


def test_b03_duplicate_case_id_and_malformed_case_are_errors_without_mutation():
    first, second = _case(), _case()
    malformed = _case()
    malformed["components"] = {"64-17-5": _case()["components"][0]}
    dataset = [first, second, malformed]
    before = copy.deepcopy(dataset)
    result = validate_dataset(dataset)
    assert any("duplicate case_id g6-case-001" in error for error in result.errors)
    assert any("ordered list" in error for error in result.errors)
    assert dataset == before


def test_b03_selector_rejects_the_entire_dataset_when_case_ids_are_duplicated(pdf_tmp):
    sources = (pdf_tmp / "first.pdf", pdf_tmp / "second.pdf")
    for source in sources:
        source.write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
    first, second = (_approved_case(source) for source in sources)
    for case, source in zip((first, second), sources):
        case["source"] = {"source_root": "reviewed-pdfs", "relative_path": source.name}
    assert validate_dataset([first, second], source_roots={"reviewed-pdfs": pdf_tmp}).errors
    assert select_approved_cases([first, second], source_roots={"reviewed-pdfs": pdf_tmp}) == ()


def test_b03_selector_rejects_any_schema_invalid_case_even_when_semantic_validation_passes(pdf_tmp):
    root = pdf_tmp / "reviewed"
    source = root / "supplier" / "example.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
    approved = _approved_case(source)
    candidate = _case()
    candidate["case_id"] = "g6-case-schema-invalid"
    candidate["source_transcription"] = {
        "product_raw": "candidate transcription",
        "product_evidence": [],
        "component_rows": [],
        "transcription_method": "OCR",
    }
    assert validate_case(candidate) == []
    assert validate_dataset([candidate, approved], source_roots={"reviewed-pdfs": root}).valid
    assert select_approved_cases([candidate, approved], source_roots={"reviewed-pdfs": root}) == ()


def test_b04_safe_review_and_failure_expectations_are_dataset_errors_when_missing():
    safe = _case(kind="SAFE_REVIEW")
    failure = _case(kind="FAILURE_BEHAVIOR")
    result = validate_dataset([safe, failure])
    assert "cases[0]: SAFE_REVIEW requires expected" in result.errors
    assert "cases[1]: FAILURE_BEHAVIOR requires expected" in result.errors


def test_b05_selector_does_not_promote_candidate_or_human_reviewed_cases():
    candidate = _case()
    reviewed = _case(lifecycle="HUMAN_REVIEWED")
    assert select_approved_cases([candidate, reviewed]) == ()


@pytest.mark.parametrize(
    ("lifecycle", "target", "operation"),
    [("APPROVED", "errors", "read_bytes"), ("CANDIDATE", "findings", "resolve")],
)
def test_b06_source_asset_oserror_is_returned_without_propagating(pdf_tmp, monkeypatch, lifecycle, target, operation):
    root = pdf_tmp / "reviewed"
    source = root / "supplier" / "example.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
    case = _approved_case(source) if lifecycle == "APPROVED" else _case()
    case["lifecycle"] = lifecycle
    if lifecycle == "CANDIDATE":
        case["review_history"] = [{"action": "CANDIDATE", "status": "CANDIDATE"}]

    def denied(_path, *args, **kwargs):
        raise PermissionError("fixture access denied")

    monkeypatch.setattr(validation.Path, operation, denied)
    result = validate_dataset([case], source_roots={"reviewed-pdfs": root})
    assert getattr(result, target) == ("cases[0]: source asset is unavailable: could not resolve or read file",)


@pytest.mark.parametrize("invalid_root", [False, 0, [], {}])
@pytest.mark.parametrize(("lifecycle", "target"), [("APPROVED", "errors"), ("CANDIDATE", "findings")])
def test_b06_invalid_mapped_source_root_value_fails_closed_without_path_typeerror(invalid_root, lifecycle, target):
    case = _case(lifecycle=lifecycle)
    result = validate_dataset([case], source_roots={"reviewed-pdfs": invalid_root})
    assert getattr(result, target) == ("cases[0]: source asset is unavailable: could not resolve or read file",)
    assert select_approved_cases([case], source_roots={"reviewed-pdfs": invalid_root}) == ()


@pytest.mark.parametrize("empty_root", ["", " \t "])
@pytest.mark.parametrize(("lifecycle", "target"), [("APPROVED", "errors"), ("CANDIDATE", "findings")])
def test_b06_empty_mapped_source_root_string_never_resolves_to_the_working_directory(empty_root, lifecycle, target):
    case = _case(lifecycle=lifecycle)
    result = validate_dataset([case], source_roots={"reviewed-pdfs": empty_root})
    assert getattr(result, target) == ("cases[0]: source asset is unavailable: source root is not mapped",)
    assert select_approved_cases([case], source_roots={"reviewed-pdfs": empty_root}) == ()
