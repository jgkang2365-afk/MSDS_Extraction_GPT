#!/usr/bin/env python
"""승인된 골든 후보의 선택 케이스만 원본 골든에 반영한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = ROOT / "golden" / "msds_golden_v1.json"
DEFAULT_PDF_DIR = ROOT / "TEST_File"


class GoldenUpdateError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_pdf(case: dict[str, Any], pdf_dir: Path) -> Path:
    names = [str(case.get("file") or ""), *[str(value) for value in case.get("aliases", [])]]
    for name in names:
        path = pdf_dir / name
        if path.is_file():
            return path
    raise GoldenUpdateError(f"GOLDEN_PDF_MISSING:{case.get('id')}")


def apply_approved_candidate(
    golden: dict[str, Any], candidate: dict[str, Any], selected_ids: set[str],
    pdf_dir: Path,
) -> dict[str, Any]:
    if not selected_ids:
        raise GoldenUpdateError("GOLDEN_UPDATE_IDS_REQUIRED")
    candidate_by_id = {str(item.get("id")): item for item in candidate.get("cases", [])}
    golden_by_id: dict[str, list[dict[str, Any]]] = {}
    for case in golden.get("cases", []):
        golden_by_id.setdefault(str(case.get("id")), []).append(case)
    for case_id in selected_ids:
        item = candidate_by_id.get(case_id)
        if not item:
            raise GoldenUpdateError(f"GOLDEN_CANDIDATE_ID_MISSING:{case_id}")
        if item.get("approved") is not True:
            raise GoldenUpdateError(f"GOLDEN_APPROVAL_MISSING:{case_id}")
        expected = item.get("user_expected")
        if not isinstance(expected, dict) or not expected:
            raise GoldenUpdateError(f"GOLDEN_EXPECTED_VALUE_MISSING:{case_id}")
        matches = golden_by_id.get(case_id, [])
        if len(matches) != 1:
            raise GoldenUpdateError(f"GOLDEN_ID_NOT_UNIQUE:{case_id}")
        case = matches[0]
        pdf = _find_pdf(case, pdf_dir)
        actual_hash = _sha256(pdf)
        candidate_hash = str(item.get("pdf_sha256") or "").lower()
        golden_hash = str(case.get("source_sha256") or "").lower()
        if not candidate_hash or actual_hash != candidate_hash or actual_hash != golden_hash:
            raise GoldenUpdateError(f"GOLDEN_SOURCE_HASH_MISMATCH:{case_id}")
        allowed_keys = {"product_name", "components", "cas_missing_components"}
        unknown = set(expected) - allowed_keys
        if unknown:
            raise GoldenUpdateError(f"GOLDEN_EXPECTED_FIELD_NOT_ALLOWED:{case_id}:{','.join(sorted(unknown))}")
        for key in allowed_keys:
            if key in expected:
                case[key] = expected[key]
    return golden


def _run_regressions(selected_ids: set[str], runner: Callable[..., Any] = subprocess.run) -> None:
    commands = [
        [sys.executable, str(ROOT / "run_production_race.py"), "--ids", ",".join(sorted(selected_ids))],
        [sys.executable, str(ROOT / "run_production_race.py"), "--tier", "core"],
        [sys.executable, str(ROOT / "run_production_race.py"), "--all"],
    ]
    for command in commands:
        completed = runner(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            scope = "focused" if "--ids" in command else ("core" if "core" in command else "full")
            raise GoldenUpdateError(f"GOLDEN_POST_UPDATE_REGRESSION_FAILED:{scope}")


def update_golden_file(
    candidate_path: Path, golden_path: Path, selected_ids: set[str], pdf_dir: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    original_bytes = golden_path.read_bytes()
    golden = json.loads(original_bytes.decode("utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    updated = apply_approved_candidate(golden, candidate, selected_ids, pdf_dir)
    golden_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        _run_regressions(selected_ids, runner=runner)
    except Exception:
        golden_path.write_bytes(original_bytes)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="승인된 선택 케이스만 골든에 반영")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--ids", required=True, help="쉼표로 구분한 승인 대상 ID")
    parser.add_argument("--approved", action="store_true", help="명시적 사용자 승인 확인")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.approved:
        print("GOLDEN_APPROVAL_FLAG_REQUIRED", file=sys.stderr)
        return 1
    selected_ids = {value.strip() for value in args.ids.split(",") if value.strip()}
    try:
        update_golden_file(args.candidate, args.golden, selected_ids, args.pdf_dir)
    except (OSError, ValueError, GoldenUpdateError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"GOLDEN_UPDATED ids={','.join(sorted(selected_ids))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
