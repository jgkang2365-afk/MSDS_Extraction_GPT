"""MSDSEngineV7: V6 재사용 + Section 1/3 범위 제한 계층."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata

import fitz

import msds_engine_v6 as v6
from section_detector_v7 import SectionDetectorV7, SectionRange


VERSION = "25.0.0.0-v7"
MES_MASTER_MAP = v6.MES_MASTER_MAP
MES_MASTER_LOAD_ERROR = v6.MES_MASTER_LOAD_ERROR
cas_pattern = v6.cas_pattern
normalize_concentration = v6.normalize_concentration
extract_labeled_product_name = v6.extract_labeled_product_name

V7_PRODUCT_PROMPT_SUFFIX = """

[V7 Section 근거 규칙]
- 입력은 전체 SDS 또는 Section 1 일부일 수 있다. 제품명은 원칙적으로 Section 1의 제품 식별 정보에서만 찾아라.
- 제품명, 제품의 명칭, 상품명, Product name, Product identifier, Trade name 라벨에 직접 연결된 원문 값을 우선하라.
- 회사명, 제조사명, 공급자명, 주소, 전화번호, 권고 용도, SAFETY DATA SHEET, 물질안전보건자료를 제품명으로 선택하지 마라.
- Section 1에서 명확한 제품명이 없으면 다른 Section으로 추정하거나 원문에 없는 값을 만들지 마라. 확인할 수 없으면 빈 문자열을 반환하라.
""".strip()

V7_COMPONENT_PROMPT_SUFFIX = """

[V7 Section 및 행 관계 규칙]
- 성분명, CAS 번호, 함유량은 Section 3 Composition/information on ingredients 영역에서만 확인하라.
- 각 값은 같은 표 행 또는 같은 성분 블록에 속한 것끼리만 연결하라. CAS와 가깝다는 이유만으로 숫자를 함유량으로 선택하지 마라.
- EC 번호, Index 번호, REACH 등록번호, 분자량, 분류 코드, 개정일, 전화번호, Section 8 노출기준 수치를 함유량으로 오인하지 마라.
- 범위와 부등호를 보존하고 Trade secret, Proprietary, 영업비밀, Balance, 잔량을 숫자로 변환하지 마라.
- Section 3에서 확인되지 않는 CAS나 함유량을 추정·생성하지 말고 미확인 필드는 빈값으로 반환하라.
- 기존 JSON 객체 스키마를 그대로 유지하고 JSON 이외의 설명이나 마크다운 코드블록을 출력하지 마라.
""".strip()


def load_v7_settings(config_path=None):
    settings = {
        "v7_section_scoped_extraction": True,
        "v7_fallback_to_v6": True,
        "v7_comparison_mode": False,
    }
    path = config_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        for key in settings:
            if key in raw:
                value = raw[key]
                if isinstance(value, str):
                    settings[key] = value.strip().casefold() in {"1", "true", "yes", "on"}
                else:
                    settings[key] = bool(value)
    except (OSError, ValueError, TypeError):
        pass
    return settings


def _component_map(result):
    text = str((result or {}).get("구성성분", ""))
    return {
        match.group(1): match.group(2).strip()
        for match in re.finditer(r"(\d{2,7}-\d{2}-\d)\s*\(([^)]*)\)", text)
    }


def compare_results(v6_result, v7_result, section_meta=None, elapsed_seconds=None):
    v6_components = _component_map(v6_result)
    v7_components = _component_map(v7_result)
    return {
        "v6_product_name": str((v6_result or {}).get("제품명", "")),
        "v7_product_name": str((v7_result or {}).get("제품명", "")),
        "v6_component_count": len(v6_components),
        "v7_component_count": len(v7_components),
        "v6_cas": list(v6_components),
        "v7_cas": list(v7_components),
        "v6_content": v6_components,
        "v7_content": v7_components,
        "sections": section_meta or {},
        "v6_fallback_used": bool((v7_result or {}).get("v7_fallback_used")),
        "ai_called": bool(((v7_result or {}).get("metrics") or {}).get("ai")),
        "elapsed_seconds": elapsed_seconds,
    }


class MSDSEngineV7(v6.MSDSEngineV6):
    """V6의 안정 경로를 상속하고 범위 판정만 앞단에 추가한다."""

    def __init__(self, *args, v7_settings=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.v7_settings = dict(load_v7_settings(), **(v7_settings or {}))
        self.section_detector = SectionDetectorV7()
        self._v7_scope_enabled = bool(self.v7_settings["v7_section_scoped_extraction"])
        self._v7_document_text = ""
        self._v7_sections = {1: SectionRange(1), 3: SectionRange(3)}
        self._v7_section3_text = ""
        self._v7_log_func = None
        self._v7_fallback_used = False
        self._v7_fallback_reasons = []

    def _record_v6_fallback(self, reason):
        self._v7_fallback_used = True
        if reason not in self._v7_fallback_reasons:
            self._v7_fallback_reasons.append(reason)
        if self._v7_log_func:
            self._v7_log_func(f"[ENGINE] V7 결과 불확실 → V6 호환 추출로 복귀: {reason}")

    def _prepare_sections(self, pdf_path, log_func=None):
        self._v7_log_func = log_func
        try:
            with fitz.open(pdf_path) as doc:
                page_texts = [self._get_sorted_and_normalized_text(page) for page in doc]
            self._v7_document_text, self._v7_sections = self.section_detector.detect_document(page_texts)
            self._v7_section3_text = self.section_detector.extract(
                self._v7_document_text, self._v7_sections[3]
            )
        except Exception as exc:
            self._v7_document_text = ""
            self._v7_sections = {1: SectionRange(1), 3: SectionRange(3)}
            self._v7_section3_text = ""
            if log_func:
                log_func(f"[SECTION] Section 탐지 예외: V6 호환 추출로 복귀 ({exc})")

        for number in (1, 3):
            detected = self._v7_sections[number]
            if log_func and detected.usable:
                log_func(
                    f"[SECTION] Section {number} 탐지 성공: 페이지 {detected.page_start + 1}, "
                    f"제목='{detected.title}', 시작={detected.start}, 종료={detected.end}, "
                    f"신뢰도={detected.confidence.value}"
                )
            elif log_func:
                log_func(f"[SECTION] Section {number} 탐지 실패: V6 호환 추출로 복귀")

    def _section_metadata(self):
        return {f"section_{number}": value.to_dict() for number, value in self._v7_sections.items()}

    def extract_section_1(self, pdf_type, raw_pdf_content, log_func=None, recon_data=None):
        detected = self._v7_sections.get(1, SectionRange(1))
        if self._v7_scope_enabled and detected.usable and self._v7_document_text:
            scoped = self.section_detector.extract(self._v7_document_text, detected)
            if scoped:
                if not v6.extract_labeled_product_name(scoped):
                    legacy = super().extract_section_1(
                        pdf_type, raw_pdf_content, log_func=log_func, recon_data=recon_data
                    )
                    if v6.extract_labeled_product_name(legacy):
                        self._record_v6_fallback("Section 1 범위에 명시적 제품명 라벨 없음")
                        return legacy
                if self._v7_log_func:
                    self._v7_log_func("[PRODUCT] Section 1 제한 추출 적용")
                    self._v7_log_func("[AI] AI 입력 범위: Section 1")
                return scoped
        if self._v7_log_func:
            self._v7_log_func("[AI] AI 입력 범위: 전체 문서 (Section 1 탐지 실패)")
        return super().extract_section_1(pdf_type, raw_pdf_content, log_func=log_func, recon_data=recon_data)

    def find_section3_pages(self, doc):
        detected = self._v7_sections.get(3, SectionRange(3))
        if self._v7_scope_enabled and detected.usable:
            pages = list(range(detected.page_start, detected.page_end + 1))
            if pages:
                if self._v7_log_func:
                    self._v7_log_func("[INGREDIENT] Section 3 제한 추출 적용")
                return pages
        return super().find_section3_pages(doc)

    def _filter_components_to_section3(self, components):
        detected = self._v7_sections.get(3, SectionRange(3))
        if not self._v7_scope_enabled or not detected.usable or not self._v7_section3_text:
            return components
        compact_scope = unicodedata.normalize("NFKC", self._v7_section3_text)
        compact_scope = re.sub(r"[‐‑‒–—−]", "-", compact_scope)
        compact_scope = re.sub(r"\s+", "", compact_scope)
        filtered = []
        for component in components or []:
            cas = str(component.get("cas") or component.get("cas_no") or "")
            cas = re.sub(r"[‐‑‒–—−]", "-", cas)
            cas = re.sub(r"\s+", "", cas)
            if cas and cas in compact_scope:
                filtered.append(component)
        if components and not filtered:
            self._record_v6_fallback("Section 3 후보 근거 필터 결과 0건")
            return components
        return filtered

    def extract_components_odl_robust(self, *args, **kwargs):
        return self._filter_components_to_section3(super().extract_components_odl_robust(*args, **kwargs))

    def extract_table_by_density_clustering(self, *args, **kwargs):
        return self._filter_components_to_section3(super().extract_table_by_density_clustering(*args, **kwargs))

    def extract_from_text_regex(self, *args, **kwargs):
        components, inherited = super().extract_from_text_regex(*args, **kwargs)
        return self._filter_components_to_section3(components), inherited

    def _load_cached_v6_result(self, pdf_path):
        try:
            digest = hashlib.sha256()
            with open(pdf_path, "rb") as handle:
                for chunk in iter(lambda: handle.read(4096), b""):
                    digest.update(chunk)
            cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "msds_cache_registry.json")
            with open(cache_path, "r", encoding="utf-8") as handle:
                item = json.load(handle).get(digest.hexdigest(), {})
            return item.get("result") if item.get("engine_version") == v6.VERSION else None
        except (OSError, ValueError, TypeError):
            return None

    def _run_v6_product_fallback(self, result, log_func=None):
        first_page = self._v7_document_text.split("\f", 1)[0] if self._v7_document_text else ""
        if not first_page:
            return result
        legacy_context = v6.MSDSEngineV6.extract_section_1(
            self, "digital", first_page, log_func=None, recon_data=None
        )
        if not legacy_context.strip():
            return result
        if log_func:
            log_func("[AI] AI 입력 범위: 전체 문서 (제품명 V6 호환 우회)")
            log_func("[AI] AI 호출 사유: 제품명 불확실")
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{v6.PRODUCT_NAME_PROMPT}\n\n{legacy_context}"}]}],
            "generationConfig": {"temperature": 0.0},
        }
        try:
            response = self.call_llm_router(
                payload,
                log_func=log_func,
                model="gemini-2.5-flash",
                is_scanned_strict=False,
                purpose="product_name_v6_fallback",
            )
            raw_name = response.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            candidate = v6.msds_utils_v3.clean_candidate(str(raw_name).strip())
            forbidden = ("물질안전", "보건자료", "SAFETY DATA SHEET", "MSDS", "SDS")
            if 1 < len(candidate) < 100 and not any(value.casefold() in candidate.casefold() for value in forbidden):
                result["제품명"] = candidate
                result["product_engine"] = "딥시크" if response.get("actual_engine_label") == "deepseek" else "제미나이"
                result["product_name_source"] = "v6_compatible_ai_fallback"
        except Exception as exc:
            if log_func:
                log_func(f"[AI] 제품명 V6 호환 우회 실패: {exc}")
        return result

    def process_msds_pipeline(self, pdf_path, log_func=None, bypass_cache=False, cancel_check=None, checkpoint_func=None):
        started = time.perf_counter()
        self._v7_fallback_used = False
        self._v7_fallback_reasons = []
        if log_func:
            log_func("[ENGINE] MSDSEngineV7 시작")
        self._prepare_sections(pdf_path, log_func=log_func)

        original_product_prompt = v6.PRODUCT_NAME_PROMPT
        original_component_prompt = v6.VISION_EXTRACTOR_PROMPT
        v6.PRODUCT_NAME_PROMPT = f"{original_product_prompt}\n\n{V7_PRODUCT_PROMPT_SUFFIX}"
        v6.VISION_EXTRACTOR_PROMPT = f"{original_component_prompt}\n\n{V7_COMPONENT_PROMPT_SUFFIX}"
        try:
            result = super().process_msds_pipeline(
                pdf_path,
                log_func=log_func,
                bypass_cache=True,
                cancel_check=cancel_check,
                checkpoint_func=checkpoint_func,
            )
        finally:
            v6.PRODUCT_NAME_PROMPT = original_product_prompt
            v6.VISION_EXTRACTOR_PROMPT = original_component_prompt

        fallback_reason = ""
        if isinstance(result, dict):
            components = _component_map(result)
            section3 = self._v7_sections.get(3, SectionRange(3))
            if section3.usable and not components:
                fallback_reason = "Section 3 제한 결과 성분 0건"
            elif self._v7_sections.get(1, SectionRange(1)).usable and not str(result.get("제품명", "")).strip():
                fallback_reason = "Section 1 제한 결과 제품명 불확실"

        if fallback_reason and self.v7_settings.get("v7_fallback_to_v6", True):
            self._record_v6_fallback(fallback_reason)
            # 제품명만 비어 있고 성분은 정상인 경우에는 추가 AI 호출을 만들지 않는다.
            # 성분 0건일 때만 V6의 기존 성분 우회 함수를 항목 단위로 호출한다.
            if not _component_map(result):
                self._v7_scope_enabled = False
                try:
                    fallback_result = v6.MSDSEngineV6._trigger_ai_extraction(
                        self,
                        pdf_path=pdf_path,
                        log_func=log_func,
                        hybrid_pn=str((result or {}).get("제품명", "")),
                        doc_type=(result or {}).get("doc_type"),
                    )
                    if isinstance(fallback_result, dict) and _component_map(fallback_result):
                        result = fallback_result
                finally:
                    self._v7_scope_enabled = bool(self.v7_settings["v7_section_scoped_extraction"])
            elif not str((result or {}).get("제품명", "")).strip():
                result = self._run_v6_product_fallback(result, log_func=log_func)

        if isinstance(result, dict):
            result.setdefault("metrics", {})
            result["metrics"].update({
                "ai": list(self._ai_call_metrics),
                "ai_text_calls": sum(metric.get("input_mode") == "text" for metric in self._ai_call_metrics),
                "ai_image_calls": sum(metric.get("input_mode") == "image" for metric in self._ai_call_metrics),
            })
            result["v7_fallback_used"] = self._v7_fallback_used
            result["v7_fallback_reason"] = "; ".join(self._v7_fallback_reasons)
            result["engine_version"] = VERSION
            result["section_detection"] = self._section_metadata()
            if self.v7_settings.get("v7_comparison_mode"):
                baseline = self._load_cached_v6_result(pdf_path)
                result["v7_comparison"] = compare_results(
                    baseline,
                    result,
                    section_meta=result["section_detection"],
                    elapsed_seconds=round(time.perf_counter() - started, 4),
                )
                result["v7_comparison"]["baseline_source"] = "v6_cache" if baseline else "unavailable_no_duplicate_ai"
        return result


def process_pdf(pdf_path, log_func=None, bypass_cache=False, cancel_check=None, checkpoint_func=None):
    engine = MSDSEngineV7()
    return engine.process_msds_pipeline(
        pdf_path,
        log_func=log_func,
        bypass_cache=bypass_cache,
        cancel_check=cancel_check,
        checkpoint_func=checkpoint_func,
    )


analyze_msds = process_pdf
