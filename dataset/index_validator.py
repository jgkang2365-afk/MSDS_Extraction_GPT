from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .models import ValidationReport


CAS_PATTERN = re.compile(r"^\d{2,7}-\d{2}-\d$")
OLD_PATHS = (
    "data/review/same_cas_candidates.csv",
    "data/review/cross_cas_relation_candidates.csv",
    "data/review/gui_hardcoding_inventory.csv",
    "data/review/source_column_mapping.csv",
    "reports/adaptive_recon_benchmark.csv",
)
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".ini", ".cfg", ".yml", ".yaml"}


def _normalize_name(value: Any) -> str:
    return re.sub(r"[\s\-_·,./()\[\]{}]+", "", str(value or "")).lower()


def _scan_old_paths(repo_root: Path) -> list[tuple[Path, str]]:
    matches: list[tuple[Path, str]] = []
    excluded_parts = {".git", "__pycache__", ".venv", "venv", "tmp"}
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        if excluded_parts.intersection(path.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        normalized = content.replace("\\", "/")
        for old_path in OLD_PATHS:
            if old_path in normalized:
                matches.append((path, old_path))
    return matches


def validate_dataset(
    profiles: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    *,
    repo_root: str | Path | None = None,
    source_master_rows: int | None = None,
    expected_source_master_rows: int = 297,
    loaded_review_decisions: int | None = None,
    converted_review_decisions: int | None = None,
    reference_paths: Iterable[str | Path] = (),
    check_old_paths: bool = False,
) -> ValidationReport:
    report = ValidationReport()
    profile_ids = [profile.get("profile_id") for profile in profiles]
    duplicate_ids = [
        profile_id
        for profile_id, count in Counter(profile_ids).items()
        if profile_id and count > 1
    ]
    for profile_id in duplicate_ids:
        report.add(
            "ERROR",
            "DUPLICATE_PROFILE_ID",
            f"profile_id 중복: {profile_id}",
            "profile",
            profile_id,
        )
    for profile in profiles:
        profile_id = profile.get("profile_id")
        if not profile_id:
            report.add("ERROR", "MISSING_PROFILE_ID", "profile_id 누락", "profile")
            continue
        cas_no = profile.get("cas_no")
        cas_raw = str(profile.get("cas_no_raw") or "")
        if cas_no and not CAS_PATTERN.fullmatch(str(cas_no)):
            report.add(
                "ERROR",
                "NONSTANDARD_RUNTIME_CAS",
                f"실행 CAS 형식 오류: {cas_no}",
                "profile",
                profile_id,
            )
        if "등" in str(cas_no or ""):
            report.add(
                "ERROR",
                "CAS_RAW_USED_AS_RUNTIME_KEY",
                "'14808-60-7 등'과 같은 raw CAS가 실행 검색키에 남음",
                "profile",
                profile_id,
            )
        if cas_raw and "등" in cas_raw and cas_no == cas_raw:
            report.add(
                "ERROR",
                "CAS_RAW_NOT_SEPARATED",
                "CAS raw와 normalized 값이 분리되지 않음",
                "profile",
                profile_id,
            )
        if not cas_no and not profile_id:
            report.add(
                "ERROR",
                "CASLESS_PROFILE_WITHOUT_ID",
                "CAS 없는 인자에 profile_id가 없음",
                "profile",
            )
        parent_id = profile.get("parent_profile_id")
        if parent_id and parent_id not in set(profile_ids):
            report.add(
                "ERROR",
                "MISSING_PARENT_PROFILE",
                f"parent_profile_id 대상 없음: {parent_id}",
                "profile",
                profile_id,
            )
        if profile.get("is_parent") and not profile.get("active"):
            report.add(
                "WARNING",
                "INACTIVE_PARENT_PROFILE",
                "부모 profile이 비활성 상태임",
                "profile",
                profile_id,
            )
        if profile.get("default_recommended") and not profile.get("selectable"):
            report.add(
                "WARNING",
                "DEFAULT_RECOMMENDED_NOT_SELECTABLE",
                "기본추천 profile이 선택 불가 상태임",
                "profile",
                profile_id,
            )

    profile_map = {
        profile["profile_id"]: profile for profile in profiles if profile.get("profile_id")
    }
    relation_ids = [relation.get("relation_id") for relation in relations]
    for relation_id, count in Counter(relation_ids).items():
        if relation_id and count > 1:
            report.add(
                "ERROR",
                "DUPLICATE_RELATION_ID",
                f"relation_id 중복: {relation_id}",
                "relation",
                relation_id,
            )
    for relation in relations:
        relation_id = relation.get("relation_id")
        source_id = relation.get("source_profile_id")
        target_id = relation.get("target_profile_id")
        if relation.get("active"):
            for role, profile_id in (("source", source_id), ("target", target_id)):
                if not profile_id or profile_id not in profile_map:
                    report.add(
                        "ERROR",
                        "ACTIVE_RELATION_PROFILE_MISSING",
                        f"활성 관계의 {role} profile 없음: {profile_id}",
                        "relation",
                        relation_id,
                    )
                elif not profile_map[profile_id].get("active"):
                    report.add(
                        "ERROR",
                        "ACTIVE_RELATION_PROFILE_INACTIVE",
                        f"활성 관계가 비활성 {role} profile을 참조함",
                        "relation",
                        relation_id,
                    )
        if source_id and target_id and source_id == target_id:
            report.add(
                "ERROR",
                "SELF_RELATION",
                "source와 target profile이 동일함",
                "relation",
                relation_id,
            )
        if relation.get("review_status") == "REVIEW_REQUIRED" and relation.get("active"):
            report.add(
                "ERROR",
                "REVIEW_RELATION_ACTIVE",
                "보류/검토 필요 관계가 active임",
                "relation",
                relation_id,
            )

    rule_ids = [rule.get("rule_id") for rule in rules]
    for rule_id, count in Counter(rule_ids).items():
        if rule_id and count > 1:
            report.add(
                "ERROR",
                "DUPLICATE_RULE_ID",
                f"rule_id 중복: {rule_id}",
                "rule",
                rule_id,
            )
    for rule in rules:
        rule_id = rule.get("rule_id")
        if rule.get("final_decision") == "제외":
            report.add(
                "ERROR",
                "EXCLUDED_RULE_EMITTED",
                "제외 관계가 recommendation_rules에 생성됨",
                "rule",
                rule_id,
            )
        if rule.get("review_status") == "REVIEW_REQUIRED" and rule.get("active"):
            report.add(
                "ERROR",
                "REVIEW_RULE_ACTIVE",
                "보류/검토 필요 규칙이 active임",
                "rule",
                rule_id,
            )
        if rule.get("final_decision") == "보류" and rule.get("active"):
            report.add(
                "ERROR",
                "HELD_RULE_ACTIVE",
                "보류 규칙이 active임",
                "rule",
                rule_id,
            )
        if rule.get("require_user_confirmation") and rule.get("auto_confirmed"):
            report.add(
                "ERROR",
                "USER_CONFIRMATION_BYPASSED",
                "사용자 확인 필요 규칙이 자동 확정됨",
                "rule",
                rule_id,
            )
        if rule.get("active"):
            for role in ("source_profile_id", "target_profile_id"):
                profile_id = rule.get(role)
                if not profile_id or profile_id not in profile_map:
                    report.add(
                        "ERROR",
                        "ACTIVE_RULE_PROFILE_MISSING",
                        f"활성 규칙의 {role} 대상 없음: {profile_id}",
                        "rule",
                        rule_id,
                    )
                elif not profile_map[profile_id].get("active"):
                    report.add(
                        "ERROR",
                        "ACTIVE_RULE_PROFILE_INACTIVE",
                        f"활성 규칙이 비활성 profile을 참조함: {profile_id}",
                        "rule",
                        rule_id,
                    )
        if rule.get("default_selected") is True and rule.get("allow_multiple") is False:
            report.add(
                "WARNING",
                "DEFAULT_SELECTED_SINGLE_POLICY",
                "기본 선택이지만 복수선택이 N임. 원인자와 추천인자 동시 표시 정책 확인 필요",
                "rule",
                rule_id,
            )
        target_id = rule.get("target_profile_id")
        if target_id in profile_map:
            profile = profile_map[target_id]
            target_cas = rule.get("target_cas")
            if target_cas and profile.get("cas_no") != target_cas:
                report.add(
                    "ERROR",
                    "TARGET_CAS_DIRECTION_MISMATCH",
                    f"추천 CAS와 target profile CAS 불일치: {target_cas} != {profile.get('cas_no')}",
                    "rule",
                    rule_id,
                )
            if _normalize_name(rule.get("target_name")) != _normalize_name(
                profile.get("canonical_name")
            ):
                report.add(
                    "WARNING",
                    "TARGET_NAME_NORMALIZED",
                    "승인 추천명과 target profile 표준명이 다름",
                    "rule",
                    rule_id,
                )

    parents_by_cas: dict[str, list[str]] = defaultdict(list)
    for profile in profiles:
        if profile.get("active") and profile.get("is_parent") and profile.get("cas_no"):
            parents_by_cas[profile["cas_no"]].append(profile["profile_id"])
    for cas_no, parents in parents_by_cas.items():
        if len(parents) > 1:
            report.add(
                "WARNING",
                "MULTIPLE_PARENT_PROFILES",
                f"CAS {cas_no}에 부모·대표가 {len(parents)}개라 parent_profile_id를 자동 확정하지 않음",
                "cas_group",
                cas_no,
            )

    if source_master_rows is not None and source_master_rows != expected_source_master_rows:
        report.add(
            "ERROR",
            "SOURCE_ROW_COUNT_MISMATCH",
            f"V24 staging 행 수 {source_master_rows}, 기대 {expected_source_master_rows}",
            "dataset",
        )
    master_profile_count = sum(
        profile.get("source_version") == "msds_index_V24" for profile in profiles
    )
    if master_profile_count != expected_source_master_rows:
        report.add(
            "ERROR",
            "MASTER_PROFILE_COUNT_MISMATCH",
            f"V24 profile 수 {master_profile_count}, 기대 {expected_source_master_rows}",
            "dataset",
        )
    if (
        loaded_review_decisions is not None
        and converted_review_decisions is not None
        and loaded_review_decisions != converted_review_decisions
    ):
        report.add(
            "ERROR",
            "REVIEW_DECISION_COUNT_MISMATCH",
            f"승인 Excel 결정 {loaded_review_decisions}, 변환 결정 {converted_review_decisions}",
            "dataset",
        )
    for reference in reference_paths:
        path = Path(reference)
        if not path.exists():
            report.add(
                "ERROR",
                "REFERENCE_PATH_MISSING",
                f"참조 파일 누락: {path}",
                "path",
                str(path),
            )
    if check_old_paths and repo_root is not None:
        root = Path(repo_root)
        for path, old_path in _scan_old_paths(root):
            report.add(
                "ERROR",
                "OLD_PATH_REFERENCE",
                f"구경로 참조 잔존: {old_path} ({path.relative_to(root)})",
                "path",
                old_path,
            )
    return report
