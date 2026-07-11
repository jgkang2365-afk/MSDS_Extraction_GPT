#!/usr/bin/env python3
"""Approved MSDS golden dataset validator and regression runner.

Dataset validation and saved-result comparison use only the Python standard
library.  Importing the production engine is deliberately deferred until
``--run-engine`` is requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "golden" / "msds_golden_v1.json"
DEFAULT_PDF_DIR = ROOT / "TEST_File"
CAS_RE = re.compile(r"(?<!\d)(\d{2,7}-\d{2}-\d)(?!\d)")


@dataclass
class CaseResult:
    case_id: str
    file: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    actual: dict[str, Any] | None = None


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_valid_cas(cas: str) -> bool:
    if not CAS_RE.fullmatch(cas):
        return False
    digits = cas.replace("-", "")
    return sum(int(value) * weight for weight, value in enumerate(reversed(digits[:-1]), 1)) % 10 == int(digits[-1])


def validate_dataset(dataset: dict[str, Any], pdf_dir: Path) -> list[str]:
    errors: list[str] = []
    if dataset.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if dataset.get("review_status") != "approved":
        errors.append("review_status must be 'approved'")

    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        return errors + ["cases must be a non-empty array"]

    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    for index, case in enumerate(cases, 1):
        prefix = f"cases[{index - 1}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix} must be an object")
            continue
        case_id = str(case.get("id", ""))
        filename = str(case.get("file", ""))
        if not case_id or case_id in seen_ids:
            errors.append(f"{prefix}: missing or duplicate id {case_id!r}")
        if not filename or filename in seen_files:
            errors.append(f"{prefix}: missing or duplicate file {filename!r}")
        seen_ids.add(case_id)
        seen_files.add(filename)

        pdf_path = pdf_dir / filename
        if not pdf_path.is_file():
            errors.append(f"{case_id}: PDF is missing: {filename}")
        else:
            expected_hash = case.get("source_sha256")
            actual_hash = sha256_file(pdf_path)
            if expected_hash != actual_hash:
                errors.append(f"{case_id}: SHA-256 mismatch ({actual_hash})")

        product = case.get("product_name")
        if not isinstance(product, dict) or not str(product.get("expected", "")).strip():
            errors.append(f"{case_id}: product_name.expected is required")

        components = case.get("components")
        if not isinstance(components, list):
            errors.append(f"{case_id}: components must be an array")
            continue
        component_cas: set[str] = set()
        for component_index, component in enumerate(components):
            cas = str(component.get("cas", "")) if isinstance(component, dict) else ""
            content = str(component.get("content_expected", "")) if isinstance(component, dict) else ""
            if not is_valid_cas(cas):
                errors.append(f"{case_id}: components[{component_index}] has invalid CAS {cas!r}")
            if cas in component_cas:
                errors.append(f"{case_id}: duplicate component CAS {cas}")
            component_cas.add(cas)
            if not content:
                errors.append(f"{case_id}: components[{component_index}].content_expected is required")

    marker = str(dataset.get("scope", {}).get("required_filename_marker", "★"))
    required_files = {path.name for path in pdf_dir.glob("*.pdf") if marker and marker in path.name}
    missing_required = sorted(required_files - seen_files)
    if missing_required:
        errors.append("golden cases omit required marked PDFs: " + ", ".join(missing_required))
    return errors


def _clean_product(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def parse_component_chain(value: Any) -> list[dict[str, str]]:
    """Convert the production ``CAS(content); ...`` contract to rows."""
    if isinstance(value, list):
        rows = []
        for item in value:
            if not isinstance(item, dict):
                continue
            cas = str(item.get("cas") or item.get("cas_no") or "").strip()
            content = str(item.get("content") or item.get("percentage") or "").strip()
            if cas:
                rows.append({"cas": cas, "content": content})
        return rows
    if not isinstance(value, str):
        return []
    rows = []
    for part in (piece.strip() for piece in value.split(";")):
        if not part:
            continue
        match = CAS_RE.search(part)
        if not match:
            continue
        suffix = part[match.end() :].strip()
        content_match = re.match(r"^\((.*)\)$", suffix)
        rows.append({"cas": match.group(1), "content": content_match.group(1).strip() if content_match else ""})
    return rows


def normalize_engine_result(raw: dict[str, Any]) -> dict[str, Any]:
    product = raw.get("제품명", raw.get("product_name", ""))
    component_value = raw.get("구성성분", raw.get("함유량", raw.get("components", [])))
    return {"product_name": _clean_product(product), "components": parse_component_chain(component_value)}


def compare_case(case: dict[str, Any], raw_result: dict[str, Any]) -> CaseResult:
    actual = normalize_engine_result(raw_result)
    errors: list[str] = []
    product_spec = case["product_name"]
    allowed_products = [_clean_product(product_spec["expected"])] + [
        _clean_product(value) for value in product_spec.get("allowed_variants", [])
    ]
    if actual["product_name"] not in allowed_products:
        errors.append(
            f"product name mismatch: {actual['product_name']!r} not in {allowed_products!r}"
        )

    expected_rows = [
        {"cas": str(item["cas"]), "content": str(item["content_expected"])}
        for item in case.get("components", [])
    ]
    if actual["components"] != expected_rows:
        errors.append(f"component rows mismatch: actual={actual['components']!r}, expected={expected_rows!r}")

    forbidden = {
        str(item.get("cas"))
        for item in case.get("cas_missing_components", [])
        if isinstance(item, dict) and item.get("cas")
    }
    forbidden.update(
        str(item.get("cas"))
        for item in case.get("excluded_cas_outside_section_3", [])
        if isinstance(item, dict) and item.get("cas")
    )
    hallucinated = [row["cas"] for row in actual["components"] if row["cas"] in forbidden]
    if hallucinated:
        errors.append("forbidden CAS returned: " + ", ".join(hallucinated))

    return CaseResult(str(case["id"]), str(case["file"]), not errors, errors, actual)


def select_cases(dataset: dict[str, Any], case_ids: Iterable[str]) -> list[dict[str, Any]]:
    wanted = set(case_ids)
    cases = list(dataset["cases"])
    if not wanted:
        return cases
    selected = [case for case in cases if str(case["id"]) in wanted]
    missing = wanted - {str(case["id"]) for case in selected}
    if missing:
        raise ValueError("unknown case id(s): " + ", ".join(sorted(missing)))
    return selected


def run_engine(cases: list[dict[str, Any]], pdf_dir: Path) -> dict[str, Any]:
    # The production engine logs emoji while importing. Windows PowerShell may
    # otherwise expose a CP949 stream and fail before extraction begins.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(ROOT))
    import msds_engine_v6  # noqa: PLC0415 - intentionally lazy

    results: dict[str, Any] = {}
    for case in cases:
        case_id = str(case["id"])
        print(f"[{case_id}] running {case['file']} ...", flush=True)
        results[case_id] = msds_engine_v6.process_pdf(str(pdf_dir / case["file"]), log_func=print)
    return results


def print_results(results: list[CaseResult]) -> bool:
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        print(f"[{mark}] {result.case_id} {result.file}")
        for error in result.errors:
            print(f"       - {error}")
    passed = sum(result.passed for result in results)
    print(f"\nGolden regression: {passed}/{len(results)} passed")
    return passed == len(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--case", action="append", default=[], help="case id; repeat to select multiple")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--run-engine", action="store_true", help="run production extraction (may call external APIs)")
    source.add_argument("--results", type=Path, help="compare a saved JSON object keyed by case id")
    parser.add_argument("--save-results", type=Path, help="save raw engine results as JSON")
    args = parser.parse_args(argv)

    try:
        dataset = load_json(args.dataset)
        dataset_errors = validate_dataset(dataset, args.pdf_dir)
        if dataset_errors:
            for error in dataset_errors:
                print(f"[DATASET FAIL] {error}")
            return 2
        print(f"[DATASET PASS] {len(dataset['cases'])} cases and source hashes verified")

        cases = select_cases(dataset, args.case)
        if not args.run_engine and not args.results:
            return 0
        raw_results = run_engine(cases, args.pdf_dir) if args.run_engine else load_json(args.results)
        if args.save_results:
            args.save_results.parent.mkdir(parents=True, exist_ok=True)
            args.save_results.write_text(json.dumps(raw_results, ensure_ascii=False, indent=2), encoding="utf-8")
        compared = []
        for case in cases:
            case_id = str(case["id"])
            raw = raw_results.get(case_id)
            if not isinstance(raw, dict):
                compared.append(CaseResult(case_id, str(case["file"]), False, ["result is missing or not an object"]))
            else:
                compared.append(compare_case(case, raw))
        return 0 if print_results(compared) else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
