"""V6 운영 결과를 보존하면서 공유 문맥으로 V7 규칙 결과를 비교한다."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import traceback
import unicodedata

from section_detector_v7 import SectionDetectorV7, SectionRange


COMPLETENESS = {"FULL", "PARTIAL_AI_PATH", "PARTIAL_OCR_PATH", "COMPARISON_FAILED"}
JUDGMENTS = {
    "SAME", "V7_IMPROVEMENT_CANDIDATE", "V7_ERROR_CANDIDATE",
    "MANUAL_REVIEW_REQUIRED", "PARTIAL_COMPARISON", "COMPARISON_FAILED",
}


@dataclass
class ComponentDiff:
    cas: str
    v6_name: str = ""
    v7_name: str = ""
    v6_content: str = ""
    v7_content: str = ""
    status: str = ""
    reason_code: str = ""
    reason_text: str = ""


@dataclass
class EngineComparisonResult:
    file_name: str
    file_path: str
    primary_engine: str = "v6"
    comparison_engine: str = "v7"
    comparison_status: str = "SAME"
    comparison_completeness: str = "FULL"
    v6_product_name: str = ""
    v7_product_name: str = ""
    product_name_different: bool = False
    product_name_reason: str = ""
    v6_component_count: int = 0
    v7_component_count: int = 0
    added_in_v7: list[ComponentDiff] = field(default_factory=list)
    removed_in_v7: list[ComponentDiff] = field(default_factory=list)
    changed_in_v7: list[ComponentDiff] = field(default_factory=list)
    unchanged_components: list[ComponentDiff] = field(default_factory=list)
    section_1_meta: dict = field(default_factory=dict)
    section_3_meta: dict = field(default_factory=dict)
    v7_fallback_used: bool = False
    v7_fallback_reasons: list[str] = field(default_factory=list)
    ocr_reused: bool = True
    ai_reused: bool = True
    duplicate_ocr_calls: int = 0
    duplicate_ai_calls: int = 0
    auto_judgment: str = "SAME"
    auto_judgment_reason: str = ""
    difference_summary: str = "동일"
    v6_result_saved: bool = True
    limitation_reason: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\s‐‑‒–—−_-]+", "", value)


def _norm_content(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    value = re.sub(r"[‐‑‒–—−]", "-", value)
    return re.sub(r"\s+", "", value)


def parse_components(result) -> list[dict]:
    """원문 표현을 보존한다. 구조화 입력과 기존 CAS(함유량) 문자열을 모두 받는다."""
    if isinstance(result, list):
        source = result
    elif isinstance(result, dict) and isinstance(result.get("components"), list):
        source = result["components"]
    else:
        source = None
    if source is not None:
        return [{
            "cas": str(item.get("cas") or item.get("cas_no") or "").strip(),
            "name": str(item.get("name") or item.get("chemical_name") or "").strip(),
            "content": str(item.get("content") or item.get("concentration") or "").strip(),
            "row": index,
        } for index, item in enumerate(source) if isinstance(item, dict)]

    raw = str((result or {}).get("구성성분", "") if isinstance(result, dict) else result or "")
    parsed = []
    for index, segment in enumerate(part for part in raw.split(";") if part.strip()):
        match = re.search(r"(?P<cas>\d{2,7}-\d{2}-\d)\s*\((?P<content>.*)\)\s*$", segment.strip())
        if match:
            prefix = segment[:match.start()].strip(" :-")
            parsed.append({"cas": match.group("cas"), "name": prefix, "content": match.group("content"), "row": index})
        else:
            parsed.append({"cas": "", "name": segment.strip(), "content": "", "row": index})
    return parsed


def _component_key(item: dict) -> str:
    if item.get("cas"):
        return f"cas:{item['cas']}"
    if item.get("name"):
        return f"name:{_norm_text(item['name'])}"
    return f"row:{item.get('row', -1)}"


def compare_engine_results(
    file_name: str,
    file_path: str,
    v6_result: dict,
    v7_result: dict,
    *,
    completeness: str = "FULL",
    section_1_meta: dict | None = None,
    section_3_meta: dict | None = None,
    fallback_used: bool = False,
    fallback_reasons: list[str] | None = None,
    limitation_reason: str = "",
) -> EngineComparisonResult:
    v6_product = str((v6_result or {}).get("제품명", ""))
    v7_product = str((v7_result or {}).get("제품명", ""))
    product_diff = _norm_text(v6_product) != _norm_text(v7_product)
    v6_items, v7_items = parse_components(v6_result), parse_components(v7_result)
    v6_map = {_component_key(item): item for item in v6_items}
    v7_map = {_component_key(item): item for item in v7_items}
    added, removed, changed, unchanged = [], [], [], []
    uncertain = any(not item.get("cas") for item in v6_items + v7_items)

    for key in sorted(v6_map.keys() | v7_map.keys()):
        old, new = v6_map.get(key), v7_map.get(key)
        if old is None:
            added.append(ComponentDiff(new["cas"], v7_name=new["name"], v7_content=new["content"], status="V7 추가", reason_code="ADDED_IN_V7", reason_text="V7 결과에만 존재"))
        elif new is None:
            removed.append(ComponentDiff(old["cas"], v6_name=old["name"], v6_content=old["content"], status="V7 제거", reason_code="REMOVED_IN_V7", reason_text="V7 결과에서 제외"))
        else:
            name_diff = _norm_text(old["name"]) != _norm_text(new["name"])
            content_diff = _norm_content(old["content"]) != _norm_content(new["content"])
            status_parts = []
            if content_diff:
                status_parts.append("함유량 변경")
            if name_diff:
                status_parts.append("성분명 변경")
            diff = ComponentDiff(old["cas"], old["name"], new["name"], old["content"], new["content"], ", ".join(status_parts) or "동일", "VALUE_CHANGED" if status_parts else "", "원문 값 비교" if status_parts else "")
            (changed if status_parts else unchanged).append(diff)

    is_different = product_diff or bool(added or removed or changed)
    status = "DIFFERENT" if is_different else "SAME"
    reason_bits = []
    if product_diff:
        reason_bits.append("제품명 차이")
    if added:
        reason_bits.append(f"CAS/성분 {len(added)}개 추가")
    if removed:
        reason_bits.append(f"CAS/성분 {len(removed)}개 제거")
    if changed:
        reason_bits.append(f"값 {len(changed)}개 변경")

    if completeness == "COMPARISON_FAILED":
        judgment, judgment_reason = "COMPARISON_FAILED", limitation_reason or "V7 비교 실패"
    elif completeness != "FULL":
        judgment, judgment_reason = "PARTIAL_COMPARISON", limitation_reason or "공유 중간 결과 범위 내 부분 비교"
    elif uncertain and is_different:
        judgment, judgment_reason = "MANUAL_REVIEW_REQUIRED", "CAS 없는 성분의 매칭이 불확실함"
    elif not is_different:
        judgment, judgment_reason = "SAME", "제품명·성분·함유량이 실질적으로 동일"
    else:
        judgment, judgment_reason = "MANUAL_REVIEW_REQUIRED", ", ".join(reason_bits)

    return EngineComparisonResult(
        file_name=file_name, file_path=file_path,
        comparison_status=status, comparison_completeness=completeness,
        v6_product_name=v6_product, v7_product_name=v7_product,
        product_name_different=product_diff,
        product_name_reason="Section 1 라벨 원문 비교" if product_diff else "실질적으로 동일",
        v6_component_count=len(v6_items), v7_component_count=len(v7_items),
        added_in_v7=added, removed_in_v7=removed, changed_in_v7=changed,
        unchanged_components=unchanged, section_1_meta=section_1_meta or {},
        section_3_meta=section_3_meta or {}, v7_fallback_used=fallback_used,
        v7_fallback_reasons=list(fallback_reasons or []),
        auto_judgment=judgment, auto_judgment_reason=judgment_reason,
        difference_summary=", ".join(reason_bits) if reason_bits else "동일",
        limitation_reason=limitation_reason,
    )


def build_shadow_comparison(file_path: str, v6_result: dict, context: dict | None) -> EngineComparisonResult:
    """추가 PDF/OCR/AI 호출 없이 V6의 공유 문맥에 V7 범위 규칙만 적용한다."""
    context = context or {}
    page_texts = list(context.get("page_texts") or [])
    section3_fallback_text = str(context.get("section3_text") or "")
    detector = SectionDetectorV7()
    document_text, sections = detector.detect_document(page_texts)
    section1, section3 = sections[1], sections[3]
    fallback_reasons = []

    v6_components = parse_components(v6_result)
    if section3.usable:
        scoped3 = detector.extract(document_text, section3)
        compact3 = _norm_text(scoped3)
        v7_components = [item for item in v6_components if not item["cas"] or _norm_text(item["cas"]) in compact3]
    elif section3_fallback_text:
        compact3 = _norm_text(section3_fallback_text)
        v7_components = [item for item in v6_components if not item["cas"] or _norm_text(item["cas"]) in compact3]
        fallback_reasons.append("Section 3 범위 탐지 실패: 기존 3항 OCR/텍스트 범위 재사용")
    else:
        compact3 = ""
        v7_components = list(v6_components)
        fallback_reasons.append("Section 3 공유 문맥 없음: V6 결과 유지")

    v7_product = str((v6_result or {}).get("제품명", ""))
    if section1.usable:
        scoped1 = detector.extract(document_text, section1)
        label = re.search(
            r"(?:제품명|제품의\s*명칭|상품명|product\s*name|product\s*identifier|trade\s*name)\s*[:：]?\s*([^\r\n]+)",
            scoped1, re.I,
        )
        if label and label.group(1).strip():
            v7_product = label.group(1).strip()
        else:
            fallback_reasons.append("Section 1 명시적 제품명 라벨 없음")
    else:
        fallback_reasons.append("Section 1 범위 탐지 실패")

    metrics = (v6_result or {}).get("metrics") or {}
    ai_calls = int(metrics.get("ai_text_calls", 0) or 0) + int(metrics.get("ai_image_calls", 0) or 0)
    doc_type = str((v6_result or {}).get("doc_type", "")).casefold()
    if ai_calls:
        completeness = "PARTIAL_AI_PATH"
        limitation = "AI 프롬프트별 재호출을 금지하여 공유 AI 결과와 규칙 기반 결과까지만 비교함"
    elif not page_texts and ("스캔" in doc_type or doc_type in {"image", "mixed"}):
        completeness = "PARTIAL_OCR_PATH"
        limitation = "일부 OCR 중간 결과만 공유했으며 중복 OCR은 수행하지 않음"
    else:
        completeness, limitation = "FULL", ""

    v7_result = {"제품명": v7_product, "components": v7_components}
    compared = compare_engine_results(
        os.path.basename(file_path), file_path, v6_result, v7_result,
        completeness=completeness, section_1_meta=section1.to_dict(),
        section_3_meta=section3.to_dict(), fallback_used=bool(fallback_reasons),
        fallback_reasons=fallback_reasons, limitation_reason=limitation,
    )
    if completeness == "FULL" and compared.removed_in_v7:
        if section3.end_reason == "max_chars" or any(_norm_text(item.cas) in compact3 for item in compared.removed_in_v7 if item.cas):
            compared.auto_judgment = "V7_ERROR_CANDIDATE"
            compared.auto_judgment_reason = "V6의 유효 Section 3 후보가 V7 범위에서 누락되었을 가능성"
        else:
            for item in compared.removed_in_v7:
                item.reason_code = "OUTSIDE_SECTION_3"
                item.reason_text = "Section 3 범위 밖 후보"
            compared.auto_judgment = "V7_IMPROVEMENT_CANDIDATE"
            compared.auto_judgment_reason = f"V6 후보 {len(compared.removed_in_v7)}개가 Section 3 범위 밖에서 제외됨"
    return compared


def failed_comparison(file_path: str, exc: BaseException) -> EngineComparisonResult:
    result = EngineComparisonResult(
        file_name=os.path.basename(file_path), file_path=file_path,
        comparison_status="FAILED", comparison_completeness="COMPARISON_FAILED",
        auto_judgment="COMPARISON_FAILED", auto_judgment_reason="V7 shadow 비교 예외",
        difference_summary="비교 실패", limitation_reason=f"{type(exc).__name__}: {exc}",
        error="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    return result


def comparison_rows(results: list[dict], filter_name: str = "전체", include_same: bool = False) -> list[dict]:
    rows = [item for item in results if include_same or item.get("comparison_status") != "SAME" or item.get("comparison_completeness") != "FULL"]
    checks = {
        "제품명 차이": lambda x: x.get("product_name_different"),
        "CAS 추가": lambda x: x.get("added_in_v7"),
        "CAS 제거": lambda x: x.get("removed_in_v7"),
        "함유량 변경": lambda x: any("함유량 변경" in d.get("status", "") for d in x.get("changed_in_v7", [])),
        "V7 개선 추정": lambda x: x.get("auto_judgment") == "V7_IMPROVEMENT_CANDIDATE",
        "V7 오류 가능": lambda x: x.get("auto_judgment") == "V7_ERROR_CANDIDATE",
        "수동 확인 필요": lambda x: x.get("auto_judgment") == "MANUAL_REVIEW_REQUIRED",
        "부분 비교": lambda x: str(x.get("comparison_completeness", "")).startswith("PARTIAL_"),
        "비교 실패": lambda x: x.get("comparison_completeness") == "COMPARISON_FAILED",
    }
    return rows if filter_name == "전체" else [item for item in rows if checks.get(filter_name, lambda _x: True)(item)]


def comparison_summary(results: list[dict]) -> dict:
    return {
        "total_documents": len(results),
        "same": sum(item.get("comparison_status") == "SAME" and item.get("comparison_completeness") == "FULL" for item in results),
        "different": sum(item.get("comparison_status") == "DIFFERENT" for item in results),
        "partial_comparison": sum(str(item.get("comparison_completeness", "")).startswith("PARTIAL_") for item in results),
        "comparison_failed": sum(item.get("comparison_completeness") == "COMPARISON_FAILED" for item in results),
        "v7_improvement_candidate": sum(item.get("auto_judgment") == "V7_IMPROVEMENT_CANDIDATE" for item in results),
        "v7_error_candidate": sum(item.get("auto_judgment") == "V7_ERROR_CANDIDATE" for item in results),
        "manual_review_required": sum(item.get("auto_judgment") == "MANUAL_REVIEW_REQUIRED" for item in results),
        "duplicate_ocr_calls": sum(int(item.get("duplicate_ocr_calls", 0)) for item in results),
        "duplicate_ai_calls": sum(int(item.get("duplicate_ai_calls", 0)) for item in results),
    }


def export_comparison_report(results: list[dict], output_path: str) -> str:
    """artifact-tool 기반 4시트 비교 보고서를 별도 파일로 생성한다."""
    payload = {"summary": comparison_summary(results), "results": results}
    script = Path(__file__).with_name("shadow_comparison_report.mjs")
    node = os.environ.get("CODEX_BUNDLED_NODE", "")
    bundled_candidates = list(
        (Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/node/bin/node.exe")
    )
    candidates = [node, *[str(path) for path in bundled_candidates], "node"]
    last_error = None
    with tempfile.TemporaryDirectory(prefix="msds-shadow-report-") as temp_dir:
        input_path = Path(temp_dir) / "comparison.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        for executable in filter(None, candidates):
            try:
                env = os.environ.copy()
                executable_path = Path(executable)
                if executable_path.exists():
                    bundled_modules = executable_path.parent.parent / "node_modules"
                    if bundled_modules.exists():
                        env["NODE_PATH"] = str(bundled_modules)
                command = [executable, str(script), str(input_path), str(output_path)]
                verify_dir = os.environ.get("SHADOW_REPORT_VERIFY_DIR", "")
                if verify_dir:
                    command.append(verify_dir)
                completed = subprocess.run(
                    command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=90, env=env,
                )
                if completed.returncode == 0 and Path(output_path).exists():
                    return str(output_path)
                last_error = RuntimeError((completed.stderr or "").strip() or (completed.stdout or "").strip() or "artifact-tool report failed")
            except (OSError, subprocess.SubprocessError) as exc:
                last_error = exc
    raise RuntimeError(f"비교 엑셀 생성 실패: {last_error}")
