#!/usr/bin/env python
"""선택형 MSDS 골든 PDF 회귀 실행기.

골든 원본을 자동 수정하지 않으며, 외부 유료 AI 호출은 항상 차단한다.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_GOLDEN = ROOT / "golden" / "msds_golden_v1.json"
DEFAULT_PDF_DIR = ROOT / "TEST_File"
OVERRIDES_FILE = ROOT / "golden" / "regression_case_overrides.json"


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


def load_cases(golden_path: Path, pdf_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
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

    for case in cases:
        names = [str(case.get("file", "")), *[str(v) for v in case.get("aliases", [])]]
        named = next((by_name[name] for name in names if name in by_name), None)
        if named is None:
            warnings.append(f"GOLDEN_PDF_MISSING:{case.get('id')}:{case.get('file')}")
            continue
        case["_pdf_path"] = str(named)
        actual_hash = sha256_file(named)
        if actual_hash.lower() != str(case.get("source_sha256", "")).lower():
            case["_hash_mismatch"] = actual_hash

    # 승인 전 골든에 기록할 수 없는 사용자 검토 사례도 해시 기반 override로 부분 회귀한다.
    registered_hashes = {str(c.get("source_sha256", "")).lower() for c in cases}
    for digest, override in overrides.items():
        if digest.lower() in registered_hashes:
            continue
        matches = by_hash.get(digest.lower(), [])
        if len(matches) == 1:
            path = matches[0]
            cases.append({
                "id": re.match(r"^(\d+)", path.name).group(1) if re.match(r"^(\d+)", path.name) else path.stem,
                "file": path.name,
                "source_sha256": digest.lower(),
                "components": [],
                "product_name": {},
                "_pdf_path": str(path),
                "_review_only": True,
                **copy.deepcopy(override),
            })

    registered_names = {str(c.get("file", "")) for c in raw_cases}
    for path in pdfs:
        digest = sha256_file(path)
        if path.name not in registered_names and digest not in overrides:
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
    return cases, sorted(set(warnings))


def select_cases(
    cases: Iterable[dict[str, Any]], *, ids: set[str] | None = None,
    tags: list[str] | None = None, failure_modes: list[str] | None = None,
    tier: str | None = None, select_all: bool = False, match_all: bool = False,
) -> list[dict[str, Any]]:
    ids = ids or set()
    tags = tags or []
    failure_modes = failure_modes or []
    selected: list[dict[str, Any]] = []
    for case in cases:
        checks: list[bool] = []
        if ids:
            checks.append(str(case.get("id", "")) in ids)
        flat_tags = _flatten_tags(case)
        if tags:
            checks.append(all(tag in flat_tags for tag in tags) if match_all else any(tag in flat_tags for tag in tags))
        if failure_modes:
            case_modes = set((case.get("tags") or {}).get("failure_modes") or [])
            checks.append(all(mode in case_modes for mode in failure_modes) if match_all else any(mode in case_modes for mode in failure_modes))
        if tier:
            checks.append(case.get("regression_tier") == tier)
        if select_all or (checks and all(checks)):
            selected.append(case)
    return selected


def _parse_components(result: dict[str, Any]) -> dict[str, list[str]]:
    """대표 성분 필드 하나를 읽어 동일 CAS의 모든 행을 순서대로 보존한다."""
    values: dict[str, list[str]] = defaultdict(list)
    structured = result.get("components")
    if not isinstance(structured, list):
        structured = result.get("함유량")
    if not isinstance(structured, list):
        structured = result.get("구성성분")
    if isinstance(structured, list):
        for item in structured:
            if not isinstance(item, dict):
                continue
            cas = str(item.get("cas") or item.get("cas_no") or "").strip()
            if cas:
                values[cas].append(normalize_content(item.get("content") or item.get("percentage")))
        return dict(values)

    components = result.get("구성성분")
    if isinstance(components, str):
        for cas, content in re.findall(r"(\d{2,7}-\d{2}-\d)[^;]*?\(([^()]*)\)", components):
            values[cas.strip()].append(normalize_content(content))
    return dict(values)


def compare_case(case: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
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
    if expected_name and normalized_actual not in normalized_allowed:
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


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    if case.get("_hash_mismatch"):
        raise GoldenValidationError(
            "GOLDEN_SOURCE_HASH_MISMATCH",
            f"{case.get('id')} expected={case.get('source_sha256')} actual={case['_hash_mismatch']}",
        )
    path_value = case.get("_pdf_path")
    if not path_value:
        return {"status": "pdf_missing", "result": {}, "differences": []}
    os.environ["ANTIGRAVITY_DISABLE_PAID_AI"] = "1"
    os.environ["ANTIGRAVITY_GOLDEN_VALIDATION"] = "1"
    try:
        from msds_engine_v6 import process_pdf
        result = process_pdf(path_value, bypass_cache=True)
        if not isinstance(result, dict):
            raise TypeError(f"엔진 결과 타입: {type(result).__name__}")
        differences = compare_case(case, result)
        status = "partial" if case.get("_review_only") else ("golden_mismatch" if differences else "complete")
        if result.get("status") in {"ERROR", "error", "partial_timeout"}:
            status = "extraction_failed" if result.get("status") != "partial_timeout" else "partial"
        return {
            "status": status, "result": result, "differences": differences, "ai_not_run": True,
            "duplicate_ocr_calls": _metric_value(result, "duplicate_ocr_calls"),
            "duplicate_ai_calls": _metric_value(result, "duplicate_ai_calls"),
        }
    except GoldenValidationError:
        raise
    except Exception as exc:
        return {"status": "extraction_failed", "result": {}, "differences": [], "error": f"{type(exc).__name__}: {exc}", "ai_not_run": True}


def write_candidate(selected: list[dict[str, Any]], results: list[dict[str, Any]]) -> Path:
    output_dir = ROOT / "golden" / "candidates"
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="선택형 MSDS 골든 PDF 회귀")
    parser.add_argument("--ids", help="쉼표로 구분한 골든 ID")
    parser.add_argument("--tag", action="append", default=[], help="태그(여러 번 지정 가능)")
    parser.add_argument("--failure-mode", action="append", default=[], help="failure_modes 태그")
    parser.add_argument("--tier", choices=("focused", "core", "full"))
    parser.add_argument("--all", action="store_true", dest="select_all")
    parser.add_argument("--match-all", action="store_true", help="여러 태그를 AND로 선택")
    parser.add_argument("--strict", action="store_true", help="미등록·중복 경고도 실패 처리")
    parser.add_argument("--write-golden-candidate", action="store_true")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not any((args.ids, args.tag, args.failure_mode, args.tier, args.select_all)):
        args.tier = "core"
    ids = {value.strip() for value in (args.ids or "").split(",") if value.strip()}
    try:
        cases, warnings = load_cases(args.golden, args.pdf_dir)
        for warning in warnings:
            print(f"WARNING {warning}")
        if warnings and args.strict:
            raise GoldenValidationError("GOLDEN_INVENTORY_STRICT_FAILURE", f"warnings={len(warnings)}")
        selected = select_cases(
            cases, ids=ids, tags=args.tag, failure_modes=args.failure_mode,
            tier=args.tier, select_all=args.select_all, match_all=args.match_all,
        )
        if not selected:
            raise GoldenValidationError("GOLDEN_SELECTION_EMPTY")
        print(f"SELECTED_COUNT={len(selected)}")
        for case in selected:
            print(f"SELECTED {case.get('id')} {case.get('file')}")
        results = []
        for index, case in enumerate(selected, 1):
            print(f"RUN {index}/{len(selected)} {case.get('id')}")
            run = run_case(case)
            results.append(run)
            print(f"RESULT {case.get('id')} {run['status']}")
            if run.get("differences"):
                print("DIFFERENCES " + json.dumps(run["differences"], ensure_ascii=False))
            if run.get("error"):
                print(f"ERROR_DETAIL {run['error']}")
        counts = Counter(run["status"] for run in results)
        counts["ai_not_run"] = sum(bool(run.get("ai_not_run")) for run in results)
        counts["duplicate_ocr_calls"] = sum(int(run.get("duplicate_ocr_calls", 0)) for run in results)
        counts["duplicate_ai_calls"] = sum(int(run.get("duplicate_ai_calls", 0)) for run in results)
        for run in results:
            for difference in run.get("differences", []):
                reason_code = difference.get("reason_code")
                if reason_code:
                    counts[reason_code] += 1
        print("SUMMARY " + json.dumps(dict(counts), ensure_ascii=False, sort_keys=True))
        if args.write_golden_candidate:
            print(f"GOLDEN_CANDIDATE={write_candidate(selected, results)}")
        return 1 if any((
            counts["golden_mismatch"], counts["extraction_failed"], counts["pdf_missing"],
            counts["duplicate_ocr_calls"], counts["duplicate_ai_calls"],
        )) else 0
    except GoldenValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
