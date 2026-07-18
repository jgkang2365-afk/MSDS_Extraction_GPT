"""Load and query the generated MSDS measurement-factor dataset."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


DATASET_FEATURE_FLAG_ENV = "MSDS_DATASET_V2"
_TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def is_dataset_v2_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return whether the opt-in dataset adapter is enabled (default: off)."""

    source = os.environ if env is None else env
    return str(source.get(DATASET_FEATURE_FLAG_ENV, "")).strip().lower() in _TRUE_VALUES


def normalize_name(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", str(value or "")).lower()


def normalize_cas(value: Any) -> str:
    match = re.search(r"(?<!\d)(\d{2,7}-\d{2}-\d)(?!\d)", str(value or ""))
    return match.group(1) if match else ""


class DatasetIndex:
    """In-memory indexes over generated profiles, relations and rules."""

    def __init__(self, profiles, relations, rules, manifest=None) -> None:
        self.profiles = list(profiles)
        self.relations = list(relations)
        self.rules = list(rules)
        self.manifest = manifest or {}
        self.profiles_by_id = {
            item["profile_id"]: item for item in self.profiles if item.get("profile_id")
        }
        self.active_profiles = [item for item in self.profiles if item.get("active", True)]
        self.active_rules = [item for item in self.rules if item.get("active", False)]
        self._by_cas: dict[str, list[dict[str, Any]]] = {}
        self._by_name: dict[str, list[dict[str, Any]]] = {}
        self._by_sort_code: dict[str, dict[str, Any]] = {}
        for profile in self.active_profiles:
            cas_no = normalize_cas(profile.get("cas_no"))
            if cas_no:
                self._by_cas.setdefault(cas_no, []).append(profile)
            names = [profile.get("canonical_name"), *profile.get("aliases", [])]
            for name in names:
                key = normalize_name(name)
                if key:
                    self._by_name.setdefault(key, []).append(profile)
            sort_code = str(
                profile.get("sort_code") or profile.get("source_sort_code") or ""
            ).strip()
            if sort_code:
                self._by_sort_code[sort_code] = profile
        for values in self._by_cas.values():
            values.sort(key=self.profile_sort_key)

    @classmethod
    def from_directory(cls, directory: str | Path = "data/generated") -> "DatasetIndex":
        base = Path(directory)

        def read_json(name: str) -> Any:
            with (base / name).open("r", encoding="utf-8") as stream:
                return json.load(stream)

        manifest_path = base / "dataset_manifest.json"
        return cls(
            read_json("substance_profiles.json"),
            read_json("substance_relations.json"),
            read_json("recommendation_rules.json"),
            read_json("dataset_manifest.json") if manifest_path.exists() else {},
        )

    @staticmethod
    def profile_sort_key(profile: Mapping[str, Any]) -> tuple[int, int, str, str]:
        return (
            0 if profile.get("selectable") else 1,
            1 if profile.get("is_parent") else 0,
            str(profile.get("sort_code") or profile.get("source_sort_code") or "~"),
            str(profile.get("canonical_name") or ""),
        )

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        return self.profiles_by_id.get(profile_id)

    @staticmethod
    def _dedupe(profiles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result = []
        for profile in profiles:
            profile_id = str(profile.get("profile_id") or "")
            if profile_id and profile_id not in seen:
                seen.add(profile_id)
                result.append(profile)
        return result

    def find_by_cas(self, cas_no: Any) -> list[dict[str, Any]]:
        return list(self._by_cas.get(normalize_cas(cas_no), []))

    def find_by_name(self, name: Any) -> list[dict[str, Any]]:
        return self._dedupe(self._by_name.get(normalize_name(name), []))

    def profile_for_sort_code(self, sort_code: Any) -> dict[str, Any] | None:
        return self._by_sort_code.get(str(sort_code or "").strip())

    def migrate_legacy_codes(self, sort_codes: Iterable[Any]) -> list[str]:
        """Map legacy V24 sort codes to stable profile IDs, preserving order."""

        migrated: list[str] = []
        seen: set[str] = set()
        for code in sort_codes:
            profile = self.profile_for_sort_code(code)
            if profile and profile["profile_id"] not in seen:
                seen.add(profile["profile_id"])
                migrated.append(profile["profile_id"])
        return migrated
