"""Resolve MSDS-detected substances into selectable and related factors."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .index_loader import DatasetIndex, normalize_cas, normalize_name


class SubstanceResolver:
    def __init__(self, index: DatasetIndex) -> None:
        self.index = index

    def resolve(
        self,
        name: str = "",
        cas_no: str = "",
        process_context: Mapping[str, Any] | None = None,
        restored_profile_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        context = dict(process_context or {})
        direct = self._dedupe(self.index.find_by_cas(cas_no) + self.index.find_by_name(name))
        selectable = [item for item in direct if item.get("selectable", False)]
        normalized_input_name = normalize_name(name)
        detected = [
            self._candidate(
                profile,
                "msds_detected"
                if normalize_name(profile.get("canonical_name")) == normalized_input_name
                else "same_cas_variant",
            )
            for profile in selectable
        ]

        recommendations = []
        for rule in self.index.active_rules:
            if not self._source_matches(rule, direct, name, cas_no):
                continue
            if not self._condition_matches(rule, context):
                continue
            target = self.index.get_profile(str(rule.get("target_profile_id") or ""))
            if not target or not target.get("active", True) or not target.get("selectable", False):
                continue
            recommendations.append(
                {
                    **self._candidate(target, rule.get("selection_source") or "process_recommended"),
                    "rule_id": rule.get("rule_id"),
                    "relation_type": rule.get("relation_type"),
                    "default_selected": bool(rule.get("default_selected", False)),
                    "allow_multiple": bool(rule.get("allow_multiple", False)),
                    "requires_user_confirmation": bool(
                        rule.get("requires_user_confirmation", rule.get("require_user_confirmation", False))
                    ),
                    "reason": rule.get("reason") or rule.get("review_note") or "",
                }
            )

        restored = []
        for profile_id in restored_profile_ids or []:
            profile = self.index.get_profile(profile_id)
            if profile and profile.get("active", True):
                restored.append(self._candidate(profile, "restored_from_saved_selection"))
        return {
            "detected": detected,
            "same_cas_candidates": detected,
            "related_recommendations": self._dedupe_candidates(recommendations),
            "restored_selections": self._dedupe_candidates(restored),
            "selection_mode": "multiple" if len(selectable) > 1 else "single",
            "requires_user_choice": len(selectable) > 1,
        }

    @staticmethod
    def _candidate(profile: Mapping[str, Any], selection_source: str) -> dict[str, Any]:
        return {
            "profile_id": profile.get("profile_id"),
            "canonical_name": profile.get("canonical_name"),
            "cas_no": profile.get("cas_no"),
            "sort_code": profile.get("sort_code") or profile.get("source_sort_code"),
            "sort_key": profile.get("sort_key"),
            "selection_source": selection_source,
        }

    @staticmethod
    def _source_matches(rule, direct, name, cas_no) -> bool:
        direct_ids = {item.get("profile_id") for item in direct}
        if rule.get("source_profile_id") in direct_ids:
            return True
        rule_cas = normalize_cas(rule.get("source_cas"))
        if rule_cas and rule_cas == normalize_cas(cas_no):
            return True
        source_name = normalize_name(rule.get("source_name"))
        return bool(source_name) and source_name == normalize_name(name)

    @staticmethod
    def _flatten_context(context: Mapping[str, Any]) -> str:
        return " ".join(str(value).lower() for value in context.values())

    def _condition_matches(self, rule, context) -> bool:
        condition = " ".join(
            str(rule.get(key) or "")
            for key in ("trigger_condition", "reason", "review_note", "source_name")
        ).lower()
        context_text = self._flatten_context(context)
        if "석면" in condition and any(token in condition for token in ("불명", "unknown", "포함")):
            status = str(context.get("asbestos_status") or "").lower()
            return status in {"included", "unknown", "포함", "불명"} or any(
                token in context_text for token in ("석면 포함", "석면불명", "unknown")
            )
        heat_tokens = ("용접", "welding", "고열", "열절단", "산화")
        if rule.get("relation_type") == "PROCESS_GENERATED" and any(
            token in condition for token in heat_tokens
        ):
            return any(token in context_text for token in heat_tokens)
        return True

    @staticmethod
    def _dedupe(profiles):
        seen, result = set(), []
        for profile in profiles:
            profile_id = str(profile.get("profile_id") or "")
            if profile_id and profile_id not in seen:
                seen.add(profile_id)
                result.append(profile)
        return result

    @staticmethod
    def _dedupe_candidates(items):
        seen, result = set(), []
        for item in items:
            if item.get("profile_id") not in seen:
                seen.add(item.get("profile_id"))
                result.append(item)
        return result

    @staticmethod
    def serialize_selection(profile_ids, selection_sources=None):
        sources = selection_sources or {}
        return [
            {"profile_id": profile_id, "selection_source": sources.get(profile_id, "manually_added")}
            for profile_id in profile_ids
        ]

    def migrate_legacy_selection(self, sort_codes):
        profile_ids = self.index.migrate_legacy_codes(sort_codes)
        return self.serialize_selection(
            profile_ids,
            {profile_id: "restored_from_saved_selection" for profile_id in profile_ids},
        )
