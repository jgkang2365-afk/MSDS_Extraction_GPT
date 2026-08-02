#!/usr/bin/env python
"""선택형 MSDS 골든 PDF 회귀 실행기.

골든 원본을 자동 수정하지 않으며, 제품명 AI는 명시적 옵션에서만 실행한다.
"""

from __future__ import annotations

import argparse
import csv
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_GOLDEN = ROOT / "golden" / "msds_golden_v1.json"
DEFAULT_PDF_DIR = ROOT / "TEST_File"
OVERRIDES_FILE = ROOT / "golden" / "regression_case_overrides.json"
BASELINE_OUTPUT_DIR = ROOT / "artifacts" / "product_name_baseline"
REGRESSION_OUTPUT_DIR = ROOT / "artifacts" / "regression_reports"
PRODUCT_NAME_MODEL = "gemini-2.5-flash"
PRODUCT_NAME_PROMPT_VERSION = "24.4.3.22"
PRODUCT_NAME_RESULT_PARSER_VERSION = "1.0"
SECTION1_EVIDENCE_BUILDER_VERSION = "v6-section1"


class GoldenValidationError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_content(value: Any) -> str:
    """공백·범위 기호만 정규화하고 부등호 의미는 보존한다."""
    text = str(value or "").strip().replace("％", "%")
    text = text.replace("～", "~").replace("–", "~").replace("—", "~")
    text = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "~", text)
    text = re.sub(r"\s+", "", text)
    return text


def normalize_product_name_for_golden(value: str) -> str:
    """안전한 표기 차이만 제거하고 정규화 결과를 정확 일치 비교에 사용한다."""
    # NFKC가 ™를 연속 문자열 TM으로 바꾸기 전에 원래 상표 기호를 제거한다.
    text = unicodedata.normalize("NFKC", str(value or "").replace("™", "")).strip().casefold()
    text = re.sub(r"\(\s*tm\s*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<![0-9a-z])tm(?![0-9a-z])", "", text, flags=re.IGNORECASE)
    return re.sub(r"[\s\-_()./]+", "", text)


def _flatten_tags(case: dict[str, Any]) -> set[str]:
    tags: set[str] = set(case.get("regression_tags") or [])
    for values in (case.get("tags") or {}).values():
        tags.update(values or [])
    return tags


def _apply_override(case: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(case)
    override = overrides.get(str(case.get("source_sha256", "")).lower())
    if override:
        for key in ("regression_tier", "tags", "reasons"):
            if key in override:
                merged[key] = copy.deepcopy(override[key])
    return merged


def _file_number(name: str) -> str:
    match = re.match(r"^(\d+)", str(name or ""))
    return match.group(1) if match else ""


def build_inventory(
    golden_path: Path, pdf_dir: Path,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    if not golden_path.exists():
        raise GoldenValidationError("GOLDEN_FILE_MISSING", str(golden_path))
    data = json.loads(golden_path.read_text(encoding="utf-8"))
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        raise GoldenValidationError("GOLDEN_FILE_INVALID", "cases 배열이 없습니다")
    overrides: dict[str, Any] = {}
    if OVERRIDES_FILE.exists():
        overrides = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8")).get("cases", {})

    draft_path = golden_path.with_name(golden_path.stem + ".classification_draft.json")
    classified_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    draft_unregistered: dict[str, dict[str, Any]] = {}
    if draft_path.exists():
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        for item in draft.get("cases", []):
            classified_by_key[(str(item.get("file", "")), str(item.get("source_sha256", "")).lower())] = item
        draft_unregistered = {str(item.get("source_sha256", "")).lower(): item for item in draft.get("unregistered_pdfs", [])}

    warnings: list[str] = []
    cases = []
    for raw_case in raw_cases:
        case = copy.deepcopy(raw_case)
        classified = classified_by_key.get((str(case.get("file", "")), str(case.get("source_sha256", "")).lower()))
        if classified:
            for key in ("regression_tier", "tags", "classification"):
                if key in classified:
                    case[key] = copy.deepcopy(classified[key])
        cases.append(_apply_override(case, overrides))
    pdfs = sorted(p for p in pdf_dir.glob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    by_name = {p.name: p for p in pdfs}
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path in pdfs:
        by_hash[sha256_file(path)].append(path)

    matched_paths: set[Path] = set()
    direct_matches = 0
    alias_matches = 0
    name_matches = 0
    hash_mismatches = 0
    filename_mismatches = 0
    for case in cases:
        names = [str(case.get("file", "")), *[str(v) for v in case.get("aliases", [])]]
        matched_name = next((name for name in names if name in by_name), None)
        named = by_name.get(matched_name) if matched_name else None
        if named is not None:
            physical_id = _file_number(named.name)
            golden_id = str(case.get("id", ""))
            if physical_id and golden_id and physical_id != golden_id:
                filename_mismatches += 1
                warnings.append(
                    f"GOLDEN_FILENAME_MISMATCH:{golden_id}:{case.get('file')}:{named.name}"
                )
                named = None
        if named is None:
            warnings.append(f"GOLDEN_PDF_MISSING:{case.get('id')}:{case.get('file')}")
            same_number = [path for path in pdfs if _file_number(path.name) == str(case.get("id", ""))]
            if same_number:
                filename_mismatches += 1
                warnings.append(
                    f"GOLDEN_FILENAME_MISMATCH:{case.get('id')}:{case.get('file')}:{same_number[0].name}"
                )
            case["_inventory_status"] = "pdf_missing"
            continue
        case["_pdf_path"] = str(named)
        case["_match_kind"] = "file" if matched_name == str(case.get("file", "")) else "alias"
        name_matches += 1
        matched_paths.add(named.resolve())
        actual_hash = sha256_file(named)
        if actual_hash.lower() != str(case.get("source_sha256", "")).lower():
            case["_hash_mismatch"] = actual_hash
            case["_registered_match"] = False
            hash_mismatches += 1
            warnings.append(
                f"GOLDEN_SOURCE_HASH_MISMATCH:{case.get('id')}:{case.get('source_sha256')}:{actual_hash}"
            )
        else:
            case["_registered_match"] = True
            direct_matches += case["_match_kind"] == "file"
            alias_matches += case["_match_kind"] == "alias"

    # 승인 전 골든에 기록할 수 없는 사용자 검토 사례도 해시 기반 override로 부분 회귀한다.
    registered_hashes = {str(c.get("source_sha256", "")).lower() for c in cases}
    for digest, override in overrides.items():
        if digest.lower() in registered_hashes:
            continue
        matches = by_hash.get(digest.lower(), [])
        if len(matches) == 1 and matches[0].resolve() not in matched_paths:
            path = matches[0]
            cases.append({
                "id": re.match(r"^(\d+)", path.name).group(1) if re.match(r"^(\d+)", path.name) else path.stem,
                "file": path.name,
                "source_sha256": digest.lower(),
                "components": [],
                "product_name": {},
                "_pdf_path": str(path),
                "_review_only": True,
                "_registered_match": False,
                **copy.deepcopy(override),
            })

    for path in pdfs:
        digest = sha256_file(path)
        if path.resolve() not in matched_paths and not any(
            str(case.get("_pdf_path", "")) == str(path) for case in cases
        ):
            warnings.append(f"PDF_NOT_REGISTERED:{path.name}")
            classified = draft_unregistered.get(digest, {})
            cases.append({
                "id": re.match(r"^(\d+)", path.name).group(1) if re.match(r"^(\d+)", path.name) else path.stem,
                "file": path.name,
                "source_sha256": digest,
                "components": [],
                "product_name": {},
                "_pdf_path": str(path),
                "_review_only": True,
                "_registered_match": False,
                "regression_tier": classified.get("regression_tier", "full"),
                "tags": copy.deepcopy(classified.get("tags", {})),
                "classification": copy.deepcopy(classified.get("classification", {})),
            })

    id_counts = Counter(str(c.get("id", "")) for c in raw_cases)
    hash_counts = Counter(str(c.get("source_sha256", "")).lower() for c in raw_cases)
    number_counts = Counter((re.match(r"^(\d+)", p.name).group(1) if re.match(r"^(\d+)", p.name) else "") for p in pdfs)
    warnings.extend(f"DUPLICATE_ID:{value}" for value, count in id_counts.items() if value and count > 1)
    warnings.extend(f"DUPLICATE_SHA256:{value}" for value, count in hash_counts.items() if value and count > 1)
    warnings.extend(f"DUPLICATE_FILE_NUMBER:{value}" for value, count in number_counts.items() if value and count > 1)
    for digest, paths in by_hash.items():
        if len(paths) > 1:
            warnings.append(f"DUPLICATE_PHYSICAL_PDF:{digest}:{'|'.join(path.name for path in paths)}")

    summary = {
        "physical_pdf_count": len(pdfs),
        "golden_case_count": len(raw_cases),
        "direct_match_count": direct_matches,
        "alias_match_count": alias_matches,
        "matched_case_count": direct_matches + alias_matches,
        "filename_or_alias_match_count": name_matches,
        "golden_pdf_missing_count": sum(value.startswith("GOLDEN_PDF_MISSING:") for value in warnings),
        "unregistered_pdf_count": sum(value.startswith("PDF_NOT_REGISTERED:") for value in warnings),
        "filename_mismatch_count": filename_mismatches,
        "hash_mismatch_count": hash_mismatches,
        "duplicate_id_count": sum(count > 1 for count in id_counts.values()),
        "duplicate_file_number_count": sum(count > 1 for value, count in number_counts.items() if value),
        "duplicate_sha256_count": sum(count > 1 for value, count in hash_counts.items() if value),
        "duplicate_physical_pdf_count": sum(len(paths) > 1 for paths in by_hash.values()),
    }
    return cases, sorted(set(warnings)), summary


def load_cases(golden_path: Path, pdf_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    cases, warnings, _ = build_inventory(golden_path, pdf_dir)
    return cases, warnings


def select_cases(
    cases: Iterable[dict[str, Any]], *, ids: set[str] | None = None,
    tags: list[str] | None = None, failure_modes: list[str] | None = None,
    tier: str | None = None, select_all: bool = False, match_all: bool = False,
    registered_only: bool = False,
) -> list[dict[str, Any]]:
    ids = ids or set()
    tags = tags or []
    failure_modes = failure_modes or []
    selected: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    seen_hashes: set[str] = set()
    for case in cases:
        # PDF가 없는 골든은 인벤토리 결과로만 보고하고 엔진 실행 대상에서 제외한다.
        if case.get("_inventory_status") == "pdf_missing":
            continue
        if registered_only and (not case.get("_registered_match") or case.get("_hash_mismatch")):
            continue
        checks: list[bool] = []
        if ids:
            checks.append(str(case.get("id", "")) in ids)
        flat_tags = _flatten_tags(case)
        if tags:
            checks.append(all(tag in flat_tags for tag in tags) if match_all else any(tag in flat_tags for tag in tags))
        if failure_modes:
            case_modes = set((case.get("tags") or {}).get("failure_modes") or [])
            checks.append(all(mode in case_modes for mode in failure_modes) if match_all else any(mode in case_modes for mode in failure_modes))
        if tier and tier != "product-core":
            checks.append(case.get("regression_tier") == tier)
        elif tier == "product-core":
            product = str((case.get("product_name") or {}).get("expected") or "")
            flat = _flatten_tags(case)
            checks.append(bool(
                re.search(r"[가-힣]", product)
                or re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", product)
                or "™" in product or "®" in product
                or "section1-nonstandard" in flat
                or "product-name-company-confusion" in flat
                or "ocr-required" in flat
            ))
        if select_all or (checks and all(checks)):
            path = str(Path(case["_pdf_path"]).resolve()) if case.get("_pdf_path") else ""
            digest = str(case.get("source_sha256", "")).lower()
            if path and (path in seen_paths or (digest and digest in seen_hashes)):
                continue
            if path:
                seen_paths.add(path)
            if digest:
                seen_hashes.add(digest)
            selected.append(case)
    return selected


def _parse_component_list(value: Any) -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)
    if not isinstance(value, list):
        return {}
    for item in value:
        if not isinstance(item, dict):
            continue
        cas = str(item.get("cas") or item.get("cas_no") or "").strip()
        if cas:
            values[cas].append(normalize_content(item.get("content") or item.get("percentage")))
    return dict(values)


def parse_components_with_source(result: dict[str, Any]) -> tuple[dict[str, list[str]], str]:
    """빈 필드를 건너뛰고 CAS를 실제로 제공하는 첫 대표 필드만 선택한다."""
    for field in ("components", "함유량", "구성성분"):
        parsed = _parse_component_list(result.get(field))
        if parsed:
            return parsed, field
    components = result.get("구성성분")
    if isinstance(components, str):
        values: dict[str, list[str]] = defaultdict(list)
        for cas, content in re.findall(r"(\d{2,7}-\d{2}-\d)[^;]*?\(([^()]*)\)", components):
            values[cas.strip()].append(normalize_content(content))
        if values:
            return dict(values), "구성성분"
    return {}, ""


def _parse_components(result: dict[str, Any]) -> dict[str, list[str]]:
    return parse_components_with_source(result)[0]


def compare_case(
    case: dict[str, Any], result: dict[str, Any], *, verify_product_name: bool = True,
) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    if case.get("_review_only"):
        return differences
    product_name = case.get("product_name") or {}
    expected_name = str(product_name.get("expected") or "").strip()
    allowed_variants = [str(value).strip() for value in product_name.get("allowed_variants", [])]
    normalized_expected = normalize_product_name_for_golden(expected_name)
    normalized_allowed = {
        normalize_product_name_for_golden(value)
        for value in (expected_name, *allowed_variants)
        if normalize_product_name_for_golden(value)
    }
    actual_name = str(result.get("제품명") or result.get("product_name") or "").strip()
    normalized_actual = normalize_product_name_for_golden(actual_name)
    if verify_product_name and expected_name and normalized_actual not in normalized_allowed:
        differences.append({
            "field": "product_name",
            "reason_code": "GOLDEN_PRODUCT_NAME_MISMATCH",
            "expected": expected_name,
            "allowed_variants": allowed_variants,
            "actual": actual_name,
            "normalized_expected": normalized_expected,
            "normalized_actual": normalized_actual,
        })

    expected_components = {
        str(component.get("cas") or "").strip(): normalize_content(
            component.get("content_expected") or component.get("content_raw")
        )
        for component in case.get("components") or []
        if str(component.get("cas") or "").strip()
    }
    actual_components = _parse_components(result)
    expected_cas = set(expected_components)
    actual_cas = set(actual_components)

    for cas in sorted(expected_cas - actual_cas):
        differences.append({
            "field": "missing_component",
            "reason_code": "GOLDEN_MISSING_CAS",
            "cas": cas,
        })
    for cas in sorted(actual_cas - expected_cas):
        differences.append({
            "field": "unexpected_component",
            "reason_code": "GOLDEN_UNEXPECTED_CAS",
            "cas": cas,
            "actual": actual_components[cas][0],
        })
    for cas in sorted(actual_cas):
        actual_values = actual_components[cas]
        if len(actual_values) > 1:
            differences.append({
                "field": "duplicate_component",
                "reason_code": "GOLDEN_DUPLICATE_CAS",
                "cas": cas,
                "actual_values": actual_values,
            })
    for cas in sorted(expected_cas & actual_cas):
        expected = expected_components[cas]
        actual = actual_components[cas][0]
        if actual != expected:
            differences.append({
                "field": "component_content",
                "reason_code": "GOLDEN_CONTENT_MISMATCH",
                "cas": cas,
                "expected": expected,
                "actual": actual,
            })
    return differences


def _metric_value(value: Any, key: str) -> int:
    if isinstance(value, dict):
        direct = value.get(key)
        if isinstance(direct, (int, float)) and not isinstance(direct, bool):
            return int(direct)
        return max((_metric_value(child, key) for child in value.values()), default=0)
    if isinstance(value, list):
        return max((_metric_value(child, key) for child in value), default=0)
    return 0


def _ai_metrics(result: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = (result.get("metrics") or {}).get("ai") if isinstance(result, dict) else []
    return [item for item in (metrics or []) if isinstance(item, dict)]


def _product_name_differences(case: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in compare_case(case, result, verify_product_name=True)
        if item.get("reason_code") == "GOLDEN_PRODUCT_NAME_MISMATCH"
    ]


def _run_engine_once(
    path_value: str, *, with_product_ai: bool,
    process_pdf_func: Callable[..., Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    process_pdf_func = process_pdf_func
    if process_pdf_func is None:
        from msds_engine_v6 import process_pdf as process_pdf_func
    previous_disabled = os.environ.get("ANTIGRAVITY_DISABLE_PAID_AI")
    previous_product_only = os.environ.get("ANTIGRAVITY_PRODUCT_NAME_AI_ONLY")
    os.environ["ANTIGRAVITY_GOLDEN_VALIDATION"] = "1"
    if with_product_ai:
        os.environ.pop("ANTIGRAVITY_DISABLE_PAID_AI", None)
        os.environ["ANTIGRAVITY_PRODUCT_NAME_AI_ONLY"] = "1"
    else:
        os.environ["ANTIGRAVITY_DISABLE_PAID_AI"] = "1"
        os.environ.pop("ANTIGRAVITY_PRODUCT_NAME_AI_ONLY", None)
    try:
        result = process_pdf_func(path_value, bypass_cache=True)
    finally:
        if previous_disabled is None:
            os.environ.pop("ANTIGRAVITY_DISABLE_PAID_AI", None)
        else:
            os.environ["ANTIGRAVITY_DISABLE_PAID_AI"] = previous_disabled
        if previous_product_only is None:
            os.environ.pop("ANTIGRAVITY_PRODUCT_NAME_AI_ONLY", None)
        else:
            os.environ["ANTIGRAVITY_PRODUCT_NAME_AI_ONLY"] = previous_product_only
    if not isinstance(result, dict):
        raise TypeError(f"엔진 결과 타입: {type(result).__name__}")
    runtime_context = getattr(result, "runtime_shadow_context", {})
    return result, dict(runtime_context) if isinstance(runtime_context, dict) else {}


def run_case(
    case: dict[str, Any], *, with_product_ai: bool = False,
    product_name_baseline: bool = False,
    process_pdf_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if case.get("_hash_mismatch"):
        raise GoldenValidationError(
            "GOLDEN_SOURCE_HASH_MISMATCH",
            f"{case.get('id')} expected={case.get('source_sha256')} actual={case['_hash_mismatch']}",
        )
    path_value = case.get("_pdf_path")
    if not path_value:
        return {"status": "pdf_missing", "result": {}, "differences": []}
    try:
        result, context = _run_engine_once(
            path_value, with_product_ai=with_product_ai, process_pdf_func=process_pdf_func,
        )
        actual_components, component_source_field = parse_components_with_source(result)
        component_differences = [
            item for item in compare_case(case, result, verify_product_name=False)
            if item.get("reason_code", "").startswith("GOLDEN_")
        ]
        evidence_text = str(context.get("product_name_evidence_text") or "").strip()
        evidence_page = context.get("product_name_evidence_page")
        evidence_error = ""
        if "product_name_evidence_text" not in context:
            evidence_error = "PRODUCT_NAME_EVIDENCE_MISSING"
        elif not evidence_text:
            evidence_error = "PRODUCT_NAME_AI_INPUT_EMPTY"
        elif not isinstance(evidence_page, int) or evidence_page < 0:
            evidence_error = "PRODUCT_NAME_SECTION1_PAGE_INVALID"

        product_differences: list[dict[str, Any]] = []
        second_result: dict[str, Any] | None = None
        product_status = "product_name_not_verified_ai_disabled"
        if evidence_error:
            product_status = "product_name_evidence_missing"
        elif with_product_ai:
            product_differences = _product_name_differences(case, result)
            product_calls = sum(item.get("purpose") == "product_name" for item in _ai_metrics(result))
            if product_calls == 0 or not str(result.get("제품명") or result.get("product_name") or "").strip():
                product_status = "product_name_ai_failed"
            elif product_differences and product_name_baseline:
                second_result, second_context = _run_engine_once(
                    path_value, with_product_ai=True, process_pdf_func=process_pdf_func,
                )
                second_differences = _product_name_differences(case, second_result)
                if not second_differences:
                    product_status = "product_name_unstable_warning"
                    product_differences = []
                else:
                    product_status = "product_name_mismatch"
            elif product_differences:
                product_status = "product_name_mismatch"
            else:
                product_status = "product_name_complete"

        if evidence_error:
            product_differences.append({
                "field": "product_name_evidence",
                "reason_code": evidence_error,
            })
        differences = component_differences + product_differences
        components_status = "components_mismatch" if component_differences else "components_complete"
        if case.get("_review_only"):
            status = "partial"
            components_status = "components_partial"
        elif evidence_error or product_status == "product_name_ai_failed":
            status = "extraction_failed"
        elif differences:
            status = "golden_mismatch"
        elif product_status in {"product_name_not_verified_ai_disabled", "product_name_unstable_warning"}:
            status = "partial"
        else:
            status = "complete"
        if result.get("status") in {"ERROR", "error", "partial_timeout"}:
            status = "extraction_failed" if result.get("status") != "partial_timeout" else "partial"
        metric_results = [result, second_result] if second_result else [result]
        all_metrics = [metric for item in metric_results for metric in _ai_metrics(item or {})]
        return {
            "status": status,
            "result": result,
            "differences": differences,
            "product_name_status": product_status,
            "components_status": components_status,
            "component_source_field": component_source_field,
            "product_name_evidence_text": evidence_text,
            "product_name_evidence_page": evidence_page,
            "product_name_evidence_error": evidence_error,
            "ai_first_result": str(result.get("제품명") or result.get("product_name") or ""),
            "ai_second_result": str((second_result or {}).get("제품명") or (second_result or {}).get("product_name") or ""),
            "ai_not_run": not with_product_ai,
            "ai_product_name_calls": sum(item.get("purpose") == "product_name" for item in all_metrics),
            "ai_component_calls": sum(item.get("purpose") != "product_name" for item in all_metrics),
            "duplicate_ocr_calls": _metric_value(result, "duplicate_ocr_calls"),
            "duplicate_ai_calls": _metric_value(result, "duplicate_ai_calls"),
        }
    except GoldenValidationError:
        raise
    except Exception as exc:
        return {
            "status": "extraction_failed", "result": {}, "differences": [],
            "error": f"{type(exc).__name__}: {exc}", "ai_not_run": not with_product_ai,
            "product_name_status": "product_name_ai_failed" if with_product_ai else "product_name_evidence_missing",
            "components_status": "components_partial", "component_source_field": "",
            "ai_product_name_calls": 0, "ai_component_calls": 0,
        }


def write_candidate(selected: list[dict[str, Any]], results: list[dict[str, Any]]) -> Path:
    output_dir = ROOT / "artifacts" / "golden_candidates"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = output_dir / f"golden_candidate_{stamp}.json"
    entries = []
    for case, run in zip(selected, results):
        entries.append({
            "id": case.get("id"),
            "file": case.get("file"),
            "pdf_sha256": case.get("source_sha256"),
            "existing_expected": {"product_name": case.get("product_name"), "components": case.get("components", [])},
            "current_extraction": run.get("result", {}),
            "differences": run.get("differences", []),
            "change_reason": "",
            "user_expected": None,
            "tags": case.get("tags", {}),
            "approved": False,
            "user_approval_required": True,
        })
    output.write_text(json.dumps({"schema_version": "1.0", "created_at": datetime.now().isoformat(), "cases": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _engine_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def write_product_name_baseline(
    selected: list[dict[str, Any]], results: list[dict[str, Any]],
) -> tuple[Path, Path]:
    BASELINE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = BASELINE_OUTPUT_DIR / f"product_name_baseline_{stamp}.json"
    csv_path = BASELINE_OUTPUT_DIR / f"product_name_baseline_review_{stamp}.csv"
    cases = []
    providers: set[str] = set()
    for case, run in zip(selected, results):
        for metric in _ai_metrics(run.get("result", {})):
            provider = str(metric.get("provider") or metric.get("actual_engine_label") or "").strip()
            if provider:
                providers.add(provider)
        cases.append({
            "id": case.get("id"),
            "file": case.get("file"),
            "golden_product_name": (case.get("product_name") or {}).get("expected", ""),
            "ai_first_result": run.get("ai_first_result", ""),
            "ai_second_result": run.get("ai_second_result", ""),
            "evidence_text": run.get("product_name_evidence_text", ""),
            "evidence_page": run.get("product_name_evidence_page"),
            "model": PRODUCT_NAME_MODEL,
            "prompt_version": PRODUCT_NAME_PROMPT_VERSION,
            "result_parser_version": PRODUCT_NAME_RESULT_PARSER_VERSION,
            "status": run.get("product_name_status"),
            "user_decision": "",
            "keep_golden": False,
            "modify_golden": False,
            "defer_decision": False,
        })
    payload = {
        "verified_at": datetime.now().astimezone().isoformat(),
        "engine_commit": _engine_commit(),
        "engine_version": "v6",
        "model_provider": ",".join(sorted(providers)) or "unknown",
        "model_name": PRODUCT_NAME_MODEL,
        "prompt_version": PRODUCT_NAME_PROMPT_VERSION,
        "result_parser_version": PRODUCT_NAME_RESULT_PARSER_VERSION,
        "section1_evidence_builder_version": SECTION1_EVIDENCE_BUILDER_VERSION,
        "total_pdf_count": len(selected),
        "matched_count": sum(run.get("product_name_status") == "product_name_complete" for run in results),
        "mismatch_count": sum(run.get("product_name_status") == "product_name_mismatch" for run in results),
        "unstable_count": sum(run.get("product_name_status") == "product_name_unstable_warning" for run in results),
        "failed_count": sum(run.get("product_name_status") in {"product_name_ai_failed", "product_name_evidence_missing"} for run in results),
        "cases": cases,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fieldnames = [
        "id", "file", "golden_product_name", "ai_first_result", "ai_second_result",
        "evidence_text", "evidence_page", "model", "prompt_version",
        "result_parser_version", "status", "user_decision", "keep_golden",
        "modify_golden", "defer_decision",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cases)
    return json_path, csv_path


def write_regression_report(
    *, mode: str, inventory: dict[str, Any], warnings: list[str],
    selected: list[dict[str, Any]], results: list[dict[str, Any]], counts: Counter,
) -> Path:
    REGRESSION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = REGRESSION_OUTPUT_DIR / f"regression_{mode}_{stamp}.json"
    cases = []
    for case, run in zip(selected, results):
        cases.append({
            "id": case.get("id"),
            "file": case.get("file"),
            "source_sha256": case.get("source_sha256"),
            "status": run.get("status"),
            "product_name_status": run.get("product_name_status"),
            "components_status": run.get("components_status"),
            "component_source_field": run.get("component_source_field"),
            "differences": run.get("differences", []),
            "ai_product_name_calls": run.get("ai_product_name_calls", 0),
            "ai_component_calls": run.get("ai_component_calls", 0),
            "duplicate_ocr_calls": run.get("duplicate_ocr_calls", 0),
            "duplicate_ai_calls": run.get("duplicate_ai_calls", 0),
        })
    output.write_text(json.dumps({
        "created_at": datetime.now().astimezone().isoformat(),
        "engine_commit": _engine_commit(),
        "mode": mode,
        "inventory": inventory,
        "warnings": warnings,
        "summary": dict(counts),
        "cases": cases,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="선택형 MSDS 골든 PDF 회귀")
    parser.add_argument("--ids", help="쉼표로 구분한 골든 ID")
    parser.add_argument("--tag", action="append", default=[], help="태그(여러 번 지정 가능)")
    parser.add_argument("--failure-mode", action="append", default=[], help="failure_modes 태그")
    parser.add_argument("--tier")
    parser.add_argument("--all", action="store_true", dest="select_all")
    parser.add_argument("--match-all", action="store_true", help="여러 태그를 AND로 선택")
    parser.add_argument("--strict", action="store_true", help="미등록·중복 경고도 실패 처리")
    parser.add_argument("--registered-only", action="store_true", help="파일명/alias와 SHA-256이 모두 일치하는 PDF만 실행")
    parser.add_argument("--inventory-only", action="store_true", help="엔진 실행 없이 인벤토리만 검사")
    ai_group = parser.add_mutually_exclusive_group()
    ai_group.add_argument("--no-paid-ai", action="store_true", help="외부 AI를 차단하고 제품명 비교를 미검증 처리(기본값)")
    ai_group.add_argument("--with-product-ai", action="store_true", help="제품명 AI만 명시적으로 실행")
    parser.add_argument("--product-name-baseline", action="store_true", help="제품명 불일치만 한 번 재확인하고 기준선 산출")
    parser.add_argument("--write-golden-candidate", action="store_true")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.product_name_baseline and not args.with_product_ai:
        print("PRODUCT_NAME_BASELINE_REQUIRES_WITH_PRODUCT_AI", file=sys.stderr)
        return 1
    if not any((args.ids, args.tag, args.failure_mode, args.tier, args.select_all)):
        args.tier = "core"
    ids = {value.strip() for value in (args.ids or "").split(",") if value.strip()}
    try:
        cases, warnings, inventory = build_inventory(args.golden, args.pdf_dir)
        print("INVENTORY " + json.dumps(inventory, ensure_ascii=False, sort_keys=True))
        for warning in warnings:
            print(f"WARNING {warning}")
        if warnings and args.strict:
            raise GoldenValidationError("GOLDEN_INVENTORY_STRICT_FAILURE", f"warnings={len(warnings)}")
        if args.inventory_only:
            return 0
        if args.product_name_baseline and warnings:
            raise GoldenValidationError("PRODUCT_NAME_BASELINE_INVENTORY_INVALID", f"warnings={len(warnings)}")
        if args.with_product_ai and not (
            os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("NOVITA_API_KEY")
            or (ROOT / "vertex_key.json").exists()
        ):
            raise GoldenValidationError(
                "PRODUCT_NAME_AI_CREDENTIALS_MISSING",
                "DEEPSEEK_API_KEY 또는 NOVITA_API_KEY 또는 vertex_key.json 필요",
            )
        selected = select_cases(
            cases, ids=ids, tags=args.tag, failure_modes=args.failure_mode,
            tier=args.tier, select_all=args.select_all, match_all=args.match_all,
            registered_only=args.registered_only,
        )
        if not selected:
            raise GoldenValidationError("GOLDEN_SELECTION_EMPTY")
        print(f"SELECTED_COUNT={len(selected)}")
        print("REGRESSION_MODE=" + ("with_product_ai" if args.with_product_ai else "no_paid_ai"))
        if args.with_product_ai:
            print(f"EXPECTED_PRODUCT_AI_CALLS={len(selected)}")
            print(f"MAX_PRODUCT_AI_CALLS_WITH_MISMATCH_RECHECK={len(selected) * 2}")
            print("PRODUCT_AI_ROUTING=deepseek/deepseek-v4-flash -> vertex/gemini-2.5-flash")
        for case in selected:
            print(f"SELECTED {case.get('id')} {case.get('file')}")
        results = []
        for index, case in enumerate(selected, 1):
            print(f"RUN {index}/{len(selected)} {case.get('id')}")
            run = run_case(
                case, with_product_ai=args.with_product_ai,
                product_name_baseline=args.product_name_baseline,
            )
            results.append(run)
            print(f"RESULT {case.get('id')} {run['status']}")
            print(
                f"RESULT_STATE {case.get('id')} product={run.get('product_name_status')} "
                f"components={run.get('components_status')} source={run.get('component_source_field') or '-'}"
            )
            if run.get("differences"):
                print("DIFFERENCES " + json.dumps(run["differences"], ensure_ascii=False))
            if run.get("error"):
                print(f"ERROR_DETAIL {run['error']}")
        counts = Counter(run["status"] for run in results)
        counts["pdf_missing"] += inventory["golden_pdf_missing_count"]
        counts["inventory_error"] = len(warnings)
        counts["ai_not_run"] = sum(bool(run.get("ai_not_run")) for run in results)
        counts["ai_product_name_calls"] = sum(int(run.get("ai_product_name_calls", 0)) for run in results)
        counts["ai_component_calls"] = sum(int(run.get("ai_component_calls", 0)) for run in results)
        counts["duplicate_ocr_calls"] = sum(int(run.get("duplicate_ocr_calls", 0)) for run in results)
        counts["duplicate_ai_calls"] = sum(int(run.get("duplicate_ai_calls", 0)) for run in results)
        for key in (
            "product_name_complete", "product_name_not_verified_ai_disabled",
            "product_name_unstable_warning", "product_name_mismatch",
            "product_name_ai_failed", "product_name_evidence_missing",
            "components_complete", "components_mismatch", "components_partial",
        ):
            counts[key] = sum(run.get("product_name_status") == key or run.get("components_status") == key for run in results)
        for run in results:
            for difference in run.get("differences", []):
                reason_code = difference.get("reason_code")
                if reason_code:
                    counts[reason_code] += 1
        for key in (
            "complete", "partial", "extraction_failed", "pdf_missing", "inventory_error",
            "GOLDEN_MISSING_CAS", "GOLDEN_UNEXPECTED_CAS", "GOLDEN_DUPLICATE_CAS",
            "GOLDEN_CONTENT_MISMATCH", "duplicate_ocr_calls", "duplicate_ai_calls",
            "ai_product_name_calls", "ai_component_calls",
        ):
            counts.setdefault(key, 0)
        print("SUMMARY " + json.dumps(dict(counts), ensure_ascii=False, sort_keys=True))
        report_path = write_regression_report(
            mode="with_product_ai" if args.with_product_ai else "no_paid_ai",
            inventory=inventory, warnings=warnings, selected=selected, results=results, counts=counts,
        )
        print(f"REGRESSION_REPORT={report_path}")
        if args.write_golden_candidate:
            print(f"GOLDEN_CANDIDATE={write_candidate(selected, results)}")
        if args.product_name_baseline:
            baseline_path, review_path = write_product_name_baseline(selected, results)
            print(f"PRODUCT_NAME_BASELINE={baseline_path}")
            print(f"PRODUCT_NAME_REVIEW={review_path}")
        return 1 if any((
            counts["golden_mismatch"], counts["extraction_failed"], counts["pdf_missing"],
            counts["duplicate_ocr_calls"], counts["duplicate_ai_calls"],
        )) else 0
    except GoldenValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
