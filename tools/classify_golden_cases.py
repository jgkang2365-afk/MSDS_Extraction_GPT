"""골든 PDF를 무과금 로컬 신호로 분류하고 검토용 초안을 생성한다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from copy import deepcopy
from pathlib import Path

try:
    import fitz
except ImportError:  # pragma: no cover - 호출 환경 진단
    fitz = None


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "golden"
TAG_GROUPS = ("document", "section", "layout", "content", "failure_modes", "product")
REVIEW_COLUMNS = [
    "ID", "파일명", "PDF 존재 여부", "SHA-256 일치 여부", "페이지 수", "문서 유형",
    "Section 1 페이지", "Section 3 시작 페이지", "Section 3 종료 페이지", "OCR 필요 여부",
    "AI fallback 이력", "CAS 수", "표 유형", "함유량 유형", "failure_modes", "제품 유형",
    "regression_tier", "분류 신뢰도", "검토 필요 여부", "자동 판정 근거", "사용자 수정란", "사용자 승인 상태",
]


def _read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {} if default is None else default


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_taxonomy(path=GOLDEN_DIR / "regression_taxonomy.json"):
    taxonomy = _read_json(path)
    for group in TAG_GROUPS:
        if not isinstance(taxonomy.get(group), list):
            raise ValueError(f"taxonomy 그룹 누락: {group}")
    return taxonomy


def validate_tags(tags, taxonomy):
    normalized = {}
    for group in TAG_GROUPS:
        values = list(dict.fromkeys(tags.get(group) or []))
        invalid = [value for value in values if value not in taxonomy[group]]
        if invalid:
            raise ValueError(f"taxonomy 외 태그: {group}={invalid}")
        normalized[group] = values
    return normalized


def _find_section_pages(page_texts, section_number):
    if section_number == 1:
        pattern = re.compile(r"(?:^|\n)\s*(?:section\s*)?(?:1|i|제\s*1\s*항)[\s.:·-]*(?:화학제품|제품|identification)", re.I)
        fallback = None
    else:
        pattern = re.compile(r"(?:^|\n)\s*(?:section\s*)?(?:3|iii|제\s*3\s*항)[\s.:·-]*(?:구성|성분|composition|ingredients)", re.I)
        fallback = re.compile(r"구성\s*성분(?:의)?\s*명칭\s*및\s*함유량|composition\s*(?:/|and)?\s*ingredients", re.I)
    return [index for index, text in enumerate(page_texts) if pattern.search(text) or (fallback and fallback.search(text))]


def _section3_end(page_texts, start):
    if start is None:
        return None
    boundary = re.compile(r"(?:^|\n)\s*(?:section\s*)?(?:4|iv|제\s*4\s*항)[\s.:·-]*(?:응급|first\s*aid)", re.I)
    for index in range(start, len(page_texts)):
        if boundary.search(page_texts[index]):
            return index
    return min(len(page_texts) - 1, start + 2)


def _content_tags(values):
    tags = []
    joined = " ; ".join(str(value or "") for value in values)
    rules = (
        ("content-less-equal", r"≤|<=|이하"), ("content-greater-equal", r"≥|>=|이상"),
        ("content-less-than", r"(?<![<])<(?![=])|미만"), ("content-greater-than", r"(?<![>])>(?![=])|초과"),
        ("content-range", r"\d\s*(?:~|∼|～|\s-\s|\bto\b)\s*[<>≤≥]?\s*\d"),
        ("content-text-secret", r"영업비밀|trade\s*secret|비공개"),
        ("content-balance", r"\bbalance\b|\brem\.?\b|잔량|나머지"),
        ("content-ppm", r"\bppm\b"), ("content-missing", r"미기재|자료없음"),
    )
    for tag, pattern in rules:
        if re.search(pattern, joined, re.I):
            tags.append(tag)
    if not tags and re.search(r"\d", joined):
        tags.append("content-single")
    units = set(re.findall(r"%|ppm|mg\s*/\s*(?:kg|m3|㎥)", joined, re.I))
    if len(units) > 1:
        tags.append("content-mixed-unit")
    return tags


def _product_tags(expected):
    text = str(expected or "").lower()
    groups = (
        ("product-standard-solution", ("standard", "표준액", "표준용액")),
        ("product-metal-polish", ("metal polish", "금속광택")),
        ("product-cleaner", ("세정", "cleaner", "wash", "비누")),
        ("product-paint", ("도료", "paint", "stain", "primer")),
        ("product-solvent", ("solvent", "acetone", "methanol", "acetonitrile")),
        ("product-acid", ("acid", "산 ", "산,")),
        ("product-alkali", ("hydroxide", "수산화")),
        ("product-fragrance", ("향", "fragrance", "perfume")),
        ("product-adhesive", ("접착", "adhesive")),
    )
    return [tag for tag, keywords in groups if any(keyword in text for keyword in keywords)] or ["product-other"]


def _history_flags(file_name, logs_root):
    flags = {"ocr": False, "ai": False, "fallback": False, "reason_codes": []}
    if not Path(logs_root).exists():
        return flags
    for path in list(Path(logs_root).glob("runs/*/files/*/diagnostic.json"))[-300:]:
        data = _read_json(path)
        context_name = str(data.get("file_name") or (data.get("context") or {}).get("file_name") or "")
        if context_name and context_name != file_name:
            continue
        text = json.dumps(data, ensure_ascii=False)
        flags["ocr"] = flags["ocr"] or bool(re.search(r'"(?:recon|precision)_ocr_calls"\s*:\s*[1-9]', text))
        flags["ai"] = flags["ai"] or bool(re.search(r'"ai_(?:text|image)_calls"\s*:\s*[1-9]', text))
        flags["fallback"] = flags["fallback"] or "fallback" in text.lower()
        flags["reason_codes"].extend(re.findall(r'"reason_code"\s*:\s*"([A-Z0-9_]+)"', text))
    flags["reason_codes"] = list(dict.fromkeys(flags["reason_codes"]))
    return flags


def classify_pdf(pdf_path, golden_case, taxonomy, history=None, override=None):
    history = history or {"ocr": False, "ai": False, "fallback": False, "reason_codes": []}
    override = override or {}
    reasons = []
    tags = {group: [] for group in TAG_GROUPS}
    page_texts = []
    page_count = 0
    read_error = ""
    if fitz is None:
        read_error = "PyMuPDF unavailable"
    else:
        try:
            with fitz.open(pdf_path) as document:
                page_count = len(document)
                page_texts = [page.get_text("text") or "" for page in document]
        except Exception as exc:
            read_error = f"{type(exc).__name__}: {exc}"
    char_counts = [len(re.sub(r"\s+", "", text)) for text in page_texts]
    text_pages = sum(count >= 80 for count in char_counts)
    low_pages = sum(count < 20 for count in char_counts)
    if page_count and text_pages == page_count:
        document_type = "digital"
    elif page_count and low_pages == page_count:
        document_type = "scanned"
    else:
        document_type = "mixed"
    tags["document"].append(document_type)
    if document_type in {"scanned", "mixed"} or history.get("ocr"):
        tags["document"].append("ocr-required")
    if history.get("ai") or history.get("fallback"):
        tags["document"].append("ai-fallback")
    elif document_type == "digital":
        tags["document"].append("local-only")

    section1_pages = _find_section_pages(page_texts, 1)
    section3_pages = _find_section_pages(page_texts, 3)
    section1 = section1_pages[0] if section1_pages else None
    section3_start = section3_pages[0] if section3_pages else None
    section3_end = _section3_end(page_texts, section3_start)
    tags["section"].append("section1-standard" if section1 is not None else "section1-nonstandard")
    if section3_start is None:
        tags["failure_modes"].append("section3-not-found")
        tags["section"].append("section3-heading-damaged")
    else:
        tags["section"].append("section3-standard")
        if section3_end is not None and section3_end > section3_start:
            tags["section"].append("section3-multipage")
        if section3_start >= 2:
            tags["section"].append("section3-late-page")
    section_text = "\n".join(page_texts[section3_start:section3_end + 1]) if section3_start is not None else ""
    cas_values = re.findall(r"(?<![\d-])\d{2,7}-\d{2}-\d(?![\d-])", section_text)
    if section3_start is not None and not cas_values:
        tags["section"].append("section3-no-cas")
    lower_section = section_text.lower()
    if re.search(r"cas\s*(?:no|번호)", lower_section, re.I):
        tags["layout"].append("table-basic")
    if sum(bool(re.search(word, lower_section, re.I)) for word in ("cas", "함유량|함량|content|concentration", "화학|chemical|성분")) >= 3:
        tags["layout"].append("table-multicolumn")
    if re.search(r"구분|분류|category|classification", lower_section) and re.search(r"함유량|함량|content|concentration", lower_section):
        tags["layout"].append("table-classification-column")
    if document_type != "digital" and section3_start is not None:
        tags["section"].append("section3-image-table")
        tags["layout"].append("table-image")
    expected_contents = [item.get("content_expected") for item in (golden_case or {}).get("components", [])]
    tags["content"].extend(_content_tags(expected_contents or [section_text]))
    tags["product"].extend(_product_tags(((golden_case or {}).get("product_name") or {}).get("expected")))
    reason_to_failure = {
        "COMPONENT_IMAGE_PAGE_MISMATCH": "section3-page-image-mismatch",
        "DUPLICATE_COMPONENT_AI_RETRY_BLOCKED": "duplicate-ai-retry",
        "CLASSIFICATION_COLUMN_MISREAD_AS_CONCENTRATION": "content-classification-column-confusion",
    }
    tags["failure_modes"].extend(reason_to_failure[code] for code in history.get("reason_codes", []) if code in reason_to_failure)

    override_tags = override.get("tags") or {}
    for group in TAG_GROUPS:
        if group in override_tags:
            tags[group] = list(override_tags.get(group) or [])
    tags = validate_tags(tags, taxonomy)
    if override.get("reasons"):
        reasons.extend(override["reasons"])
    if read_error:
        reasons.append(read_error)
    if section3_start is None:
        reasons.append("Section 3 제목을 디지털 텍스트에서 확인하지 못함")
    if not golden_case:
        reasons.append("골든 미등록 PDF")
    confidence = "HIGH"
    needs_review = False
    if read_error or not golden_case or document_type != "digital" or section3_start is None:
        confidence, needs_review = "LOW", True
    elif history.get("ocr") or history.get("ai"):
        confidence, needs_review = "MEDIUM", True
    tier = override.get("regression_tier") or ("core" if "★" in Path(pdf_path).name else "full")
    return {
        "regression_tier": tier,
        "tags": tags,
        "classification": {"source": "auto", "confidence": confidence, "needs_review": needs_review, "reasons": reasons},
        "metadata": {
            "page_count": page_count, "text_character_count": sum(char_counts), "document_type": document_type,
            "section1_page": section1, "section3_start_page": section3_start, "section3_end_page": section3_end,
            "cas_count": len(set(cas_values)), "ocr_history": bool(history.get("ocr")),
            "ai_fallback_history": bool(history.get("ai") or history.get("fallback")),
        },
    }


def _match_case_pdf(case, pdfs, hashes):
    names = [case.get("file"), *(case.get("aliases") or [])]
    exact = [path for path in pdfs if path.name in names]
    if len(exact) == 1 and hashes[exact[0]] == case.get("source_sha256"):
        return exact[0], "MATCH"
    by_hash = [path for path in pdfs if hashes[path] == case.get("source_sha256")]
    if len(by_hash) == 1 and by_hash[0].name in names:
        return by_hash[0], "MATCH"
    if exact:
        return exact[0], "HASH_MISMATCH"
    return None, "MISSING"


def _review_row(case_id, file_name, pdf_path, match_status, classification):
    meta = classification["metadata"]
    tags = classification["tags"]
    return {
        "ID": case_id, "파일명": file_name, "PDF 존재 여부": "예" if pdf_path else "아니오",
        "SHA-256 일치 여부": "예" if match_status == "MATCH" else ("아니오" if match_status == "HASH_MISMATCH" else "확인 불가"),
        "페이지 수": meta.get("page_count", 0), "문서 유형": ", ".join(tags["document"]),
        "Section 1 페이지": "" if meta.get("section1_page") is None else meta["section1_page"] + 1,
        "Section 3 시작 페이지": "" if meta.get("section3_start_page") is None else meta["section3_start_page"] + 1,
        "Section 3 종료 페이지": "" if meta.get("section3_end_page") is None else meta["section3_end_page"] + 1,
        "OCR 필요 여부": "예" if "ocr-required" in tags["document"] else "아니오",
        "AI fallback 이력": "예" if meta.get("ai_fallback_history") else "아니오", "CAS 수": meta.get("cas_count", 0),
        "표 유형": "\n".join(tags["layout"]), "함유량 유형": "\n".join(tags["content"]),
        "failure_modes": "\n".join(tags["failure_modes"]), "제품 유형": "\n".join(tags["product"]),
        "regression_tier": classification["regression_tier"], "분류 신뢰도": classification["classification"]["confidence"],
        "검토 필요 여부": "예" if classification["classification"]["needs_review"] else "아니오",
        "자동 판정 근거": "\n".join(classification["classification"]["reasons"]), "사용자 수정란": "", "사용자 승인 상태": "",
    }


def classify_cases(golden_path, pdf_dir, taxonomy_path, overrides_path, logs_root):
    golden = _read_json(golden_path)
    if not isinstance(golden.get("cases"), list):
        raise ValueError("올바른 골든 cases가 없습니다.")
    taxonomy = load_taxonomy(taxonomy_path)
    overrides = (_read_json(overrides_path).get("cases") or {})
    pdfs = sorted({*Path(pdf_dir).glob("*.pdf"), *Path(pdf_dir).glob("*.PDF")}, key=lambda path: path.name)
    hashes = {path: _sha256(path) for path in pdfs}
    draft = deepcopy(golden)
    rows = []
    matched_paths = set()
    match_counts = Counter()
    document_types = []
    for draft_case in draft["cases"]:
        pdf_path, status = _match_case_pdf(draft_case, pdfs, hashes)
        match_counts[status] += 1
        if pdf_path:
            matched_paths.add(pdf_path)
            history = _history_flags(pdf_path.name, logs_root)
            classification = classify_pdf(pdf_path, draft_case, taxonomy, history, overrides.get(hashes[pdf_path]))
            document_types.append(classification["metadata"]["document_type"])
        else:
            classification = {
                "regression_tier": "full", "tags": {group: [] for group in TAG_GROUPS},
                "classification": {"source": "auto", "confidence": "LOW", "needs_review": True, "reasons": ["PDF 누락"]},
                "metadata": {},
            }
        draft_case.update(classification)
        rows.append(_review_row(draft_case.get("id", ""), draft_case.get("file", ""), pdf_path, status, classification))
    unregistered = []
    for pdf_path in pdfs:
        if pdf_path in matched_paths:
            continue
        file_id_match = re.match(r"^(\d+)", pdf_path.name)
        case_id = file_id_match.group(1).zfill(3) if file_id_match else ""
        classification = classify_pdf(pdf_path, None, taxonomy, _history_flags(pdf_path.name, logs_root), overrides.get(hashes[pdf_path]))
        document_types.append(classification["metadata"]["document_type"])
        item = {"id": case_id, "file": pdf_path.name, "source_sha256": hashes[pdf_path], **classification}
        unregistered.append(item)
        rows.append(_review_row(case_id, pdf_path.name, pdf_path, "UNREGISTERED", classification))
    draft["classification_generated"] = True
    draft["unregistered_pdfs"] = unregistered
    summary = {
        "pdf_total": len(pdfs), "golden_registered": len(golden["cases"]), "matched": match_counts["MATCH"],
        "missing": match_counts["MISSING"], "hash_mismatch": match_counts["HASH_MISMATCH"],
        "unregistered": len(unregistered),
        "document_counts": dict(Counter(document_types)),
        "core_suggested": sum(row["regression_tier"] == "core" for row in rows),
        "needs_review": sum(row["검토 필요 여부"] == "예" for row in rows),
    }
    return draft, rows, summary


def _write_review_xlsx(rows, output_path):
    script = Path(__file__).with_name("build_golden_review.mjs")
    Path(output_path).unlink(missing_ok=True)
    node = os.environ.get("CODEX_BUNDLED_NODE", "")
    candidates = [node, *[str(path) for path in (Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/node/bin/node.exe")], "node"]
    with tempfile.TemporaryDirectory(prefix="golden-review-") as temp_dir:
        payload_path = Path(temp_dir) / "review.json"
        payload_path.write_text(json.dumps({"columns": REVIEW_COLUMNS, "rows": rows}, ensure_ascii=False), encoding="utf-8")
        errors = []
        for executable in filter(None, candidates):
            try:
                env = os.environ.copy()
                executable_path = Path(executable)
                if executable_path.exists():
                    modules = executable_path.parent.parent / "node_modules"
                    if modules.exists():
                        env["NODE_PATH"] = str(modules)
                command = [executable, str(script), str(payload_path), str(output_path)]
                verify_dir = os.environ.get("GOLDEN_REVIEW_VERIFY_DIR")
                if verify_dir:
                    command.append(verify_dir)
                completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, env=env)
                output = Path(output_path)
                if output.exists() and output.read_bytes()[:4] == b"PK\x03\x04":
                    output.with_suffix(output.suffix + ".inspect.ndjson").unlink(missing_ok=True)
                    return
                errors.append(completed.stderr or completed.stdout)
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(str(exc))
    raise RuntimeError("Excel 검토표 생성 실패: " + "; ".join(errors[-2:]))


DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "golden_classification"


def write_outputs(draft, rows, summary, output_dir=DEFAULT_OUTPUT_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    draft_path = output_dir / "msds_golden_v1.classification_draft.json"
    csv_path = output_dir / "golden_classification_review.csv"
    xlsx_path = output_dir / "golden_classification_review.xlsx"
    summary_path = output_dir / "golden_classification_summary.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    _write_review_xlsx(rows, xlsx_path)
    return [draft_path, csv_path, xlsx_path, summary_path]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "msds_golden_v1.json")
    parser.add_argument("--pdf-dir", type=Path, default=ROOT / "TEST_File")
    parser.add_argument("--taxonomy", type=Path, default=GOLDEN_DIR / "regression_taxonomy.json")
    parser.add_argument("--overrides", type=Path, default=GOLDEN_DIR / "regression_case_overrides.json")
    parser.add_argument("--logs", type=Path, default=ROOT / "logs")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    draft, rows, summary = classify_cases(args.golden, args.pdf_dir, args.taxonomy, args.overrides, args.logs)
    outputs = write_outputs(draft, rows, summary, args.output_dir)
    print(json.dumps({"summary": summary, "outputs": [str(path) for path in outputs]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
