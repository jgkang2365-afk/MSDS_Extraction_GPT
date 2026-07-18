"""Benchmark fixed and adaptive reconnaissance OCR on image-based PDFs.

This script is deliberately outside the production path.  It discovers input
files in place, disables the extraction result cache, and never changes the
engine's production default of one 1.5x reconnaissance attempt.
"""

import argparse
import csv
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from msds_engine_v6 import MSDSEngineV6, cas_pattern


LARGE_IMAGE_RATIO = 0.55
PURE_IMAGE_TEXT_LIMIT = 120
DEFAULT_CONFIDENCE_THRESHOLD = 60.0

METHODS = {
    "baseline-1.5": {"scales": (1.5,), "adaptive": False},
    "adaptive-1.0": {"scales": (1.0, 1.5), "adaptive": True},
    "adaptive-1.2": {"scales": (1.2, 1.5), "adaptive": True},
}

CSV_FIELDS = [
    "file_name",
    "original_path",
    "document_classification",
    "method",
    "initial_scale",
    "final_used_scale",
    "low_scale_success",
    "retry_1_5",
    "render_image_size",
    "page_recon_paddle_calls",
    "recon_paddle_calls",
    "total_paddle_calls",
    "page_recon_ocr_seconds",
    "total_recon_ocr_seconds",
    "section3_detected",
    "section3_page",
    "section3_start_y",
    "section4_boundary_y",
    "product_name",
    "components",
    "total_processing_seconds",
    "matches_baseline",
    "product_matches_baseline",
    "components_match_baseline",
    "golden_passed",
    "failure_or_difference_reason",
]


def _non_whitespace_count(text):
    return len(re.sub(r"\s+", "", text or ""))


def _page_large_image_info(page):
    page_area = max(1.0, page.rect.width * page.rect.height)
    max_ratio = 0.0
    for image_info in page.get_images(full=True):
        try:
            rects = page.get_image_rects(image_info[0])
        except Exception:
            rects = []
        for rect in rects:
            ratio = max(0.0, rect.width * rect.height) / page_area
            max_ratio = max(max_ratio, ratio)
    return max_ratio >= LARGE_IMAGE_RATIO, max_ratio


def classify_pdf(path):
    document = fitz.open(path)
    try:
        page_details = []
        for page_index in range(min(3, len(document))):
            page = document[page_index]
            text_count = _non_whitespace_count(page.get_text("text"))
            has_large_image, max_ratio = _page_large_image_info(page)
            page_details.append({
                "page_number": page_index + 1,
                "text_chars": text_count,
                "large_image": has_large_image,
                "max_image_ratio": max_ratio,
            })
    finally:
        document.close()

    page_count = len(page_details)
    large_count = sum(item["large_image"] for item in page_details)
    majority_large = page_count > 0 and large_count >= (page_count + 1) // 2
    total_text = sum(item["text_chars"] for item in page_details)
    if majority_large and total_text < PURE_IMAGE_TEXT_LIMIT:
        classification = "순수 이미지형"
        reason = (
            f"첫 {page_count}페이지 비공백 텍스트 {total_text}자(<{PURE_IMAGE_TEXT_LIMIT})이며 "
            f"큰 이미지가 {large_count}/{page_count}페이지에서 {LARGE_IMAGE_RATIO:.0%} 이상 점유"
        )
    elif majority_large:
        classification = "OCR 레이어가 있는 스캔형"
        reason = (
            f"첫 {page_count}페이지 비공백 텍스트 {total_text}자가 존재하지만 "
            f"큰 이미지가 {large_count}/{page_count}페이지에서 {LARGE_IMAGE_RATIO:.0%} 이상 점유"
        )
    else:
        classification = "디지털 PDF"
        reason = (
            f"큰 이미지가 페이지 대부분을 차지하는 페이지가 {large_count}/{page_count}로 "
            "스캔형 판정 기준 미달"
        )
    return {
        "path": path.resolve(),
        "file_name": path.name,
        "classification": classification,
        "page_details": page_details,
        "reason": reason,
    }


def discover_pdfs(root):
    return [classify_pdf(path) for path in sorted(root.rglob("*.pdf"))]


def print_discovery(records):
    image_records = [record for record in records if record["classification"] != "디지털 PDF"]
    print("\n=== 이미지형 PDF 발견 결과 ===")
    print(f"전체 PDF: {len(records)}개 | 테스트 대상: {len(image_records)}개")
    for record in image_records:
        counts = [item["text_chars"] for item in record["page_details"]]
        occupancy = [
            f"P{item['page_number']}={'Y' if item['large_image'] else 'N'}"
            f"({item['max_image_ratio']:.1%})"
            for item in record["page_details"]
        ]
        print(f"\n파일명: {record['file_name']}")
        print(f"원본 경로: {record['path']}")
        print(f"분류 결과: {record['classification']}")
        print(f"첫 3페이지 텍스트 글자 수: {counts}")
        print(f"페이지별 큰 이미지 점유 여부: {', '.join(occupancy)}")
        print(f"판정 근거: {record['reason']}")
    return image_records


def make_confidence_evaluator(threshold):
    section3_pattern = re.compile(
        r"(?:SECTION\s*)?(?:3|Ⅲ)\s*[.、:\-]?\s*"
        r"(?:구성\s*성분|구성성분의\s*명칭|COMPOSITION|INGREDIENTS?)",
        re.IGNORECASE,
    )
    section4_pattern = re.compile(
        r"(?:SECTION\s*)?(?:4|Ⅳ)\s*[.、:\-]?\s*"
        r"(?:응급\s*조치|FIRST\s*AID)",
        re.IGNORECASE,
    )
    cas_label_pattern = re.compile(r"\bCAS(?:\s*(?:NO|NUMBER)\s*\.?)?\b", re.IGNORECASE)
    content_pattern = re.compile(
        r"함유량|농도|CONTENT|CONCENTRATION|%", re.IGNORECASE
    )

    def evaluate(lines, engine):
        text = "\n".join(str(line.get("text", "")) for line in lines)
        heading = bool(section3_pattern.search(text))
        cas_label = bool(cas_label_pattern.search(text))
        valid_cas_values = []
        for match in cas_pattern.finditer(text):
            candidate = re.sub(r"\s+", "", match.group(0))
            if engine.verify_cas_number(candidate, grounding_text=text):
                valid_cas_values.append(candidate)
        content = bool(content_pattern.search(text))
        section4 = bool(section4_pattern.search(text))
        features = {
            "section3_heading": heading,
            "cas_label": cas_label,
            "valid_cas": bool(valid_cas_values),
            "valid_cas_values": sorted(set(valid_cas_values)),
            "content_expression": content,
            "section4_heading": section4,
        }
        score = (
            35 * heading
            + 15 * cas_label
            + 25 * bool(valid_cas_values)
            + 15 * content
            + 10 * section4
        )
        return {
            "score": float(score),
            "accepted": bool(heading and score >= threshold),
            "features": features,
        }

    return evaluate


def _parse_components(component_text):
    parsed = {}
    for cas, content in re.findall(
        r"(\d{2,7}-\d{2}-\d)\s*\(([^)]*)\)", str(component_text or "")
    ):
        parsed[cas] = re.sub(r"\s+", "", content)
    return dict(sorted(parsed.items()))


def _component_display(components):
    return "; ".join(f"{cas}({content})" for cas, content in components.items())


def load_golden_cases(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return {case["file"]: case for case in data.get("cases", [])}


def _golden_comparison(case, product, components):
    if not case:
        return None, "골든셋 항목 없음"
    expected_product = str(case.get("product_name", {}).get("expected", "")).strip()
    expected_components = {
        item["cas"]: re.sub(r"\s+", "", str(item.get("content_expected", "")))
        for item in case.get("components", [])
        if item.get("cas") and item.get("cas") != "미기재"
    }
    product_ok = product.strip().casefold() == expected_product.casefold()
    components_ok = components == dict(sorted(expected_components.items()))
    reasons = []
    if not product_ok:
        reasons.append(f"골든 제품명: {expected_product!r} != {product!r}")
    if not components_ok:
        reasons.append(
            f"골든 성분: {_component_display(expected_components)!r} != {_component_display(components)!r}"
        )
    return product_ok and components_ok, "; ".join(reasons)


def run_method(pdf_record, method_name, method_config, evaluator, golden_case):
    logs = []
    engine = MSDSEngineV6(
        use_remote_ocr=False,
        recon_attempt_scales=method_config["scales"],
        recon_confidence_evaluator=evaluator if method_config["adaptive"] else None,
    )
    started = time.perf_counter()
    error = ""
    try:
        result = engine.process_msds_pipeline(
            str(pdf_record["path"]), log_func=logs.append, bypass_cache=True
        ) or {}
    except Exception as exc:
        result = {}
        error = f"실행 예외: {exc}"
    total_elapsed = time.perf_counter() - started

    recon_data = engine._last_recon_data or {}
    target_index = recon_data.get("target_page_index")
    selected_page = (recon_data.get("pages") or {}).get(target_index, {})
    attempts = list(engine._recon_attempt_metrics)
    recon_metrics = [
        item for item in engine._paddle_call_metrics
        if item.get("purpose") == "1~3페이지 3항 정찰 OCR"
    ]
    page_counts = Counter(item["page_number"] for item in recon_metrics)
    page_seconds = defaultdict(float)
    for item in recon_metrics:
        page_seconds[item["page_number"]] += item["elapsed_seconds"]

    initial_scale = method_config["scales"][0]
    target_attempts = [
        item for item in attempts if target_index is not None and item["page_index"] == target_index
    ]
    low_success = any(
        abs(item["render_scale"] - initial_scale) < 1e-9 and item["accepted"]
        for item in target_attempts
    )
    retry_1_5 = method_config["adaptive"] and any(
        abs(item["render_scale"] - 1.5) < 1e-9 for item in attempts
    )
    bounds = recon_data.get("section_bounds") or {}
    product = str(result.get("제품명", "")).strip()
    components = _parse_components(result.get("구성성분", ""))
    golden_passed, golden_reason = _golden_comparison(golden_case, product, components)
    if golden_reason:
        error = "; ".join(part for part in [error, golden_reason] if part)

    return {
        "file_name": pdf_record["file_name"],
        "original_path": str(pdf_record["path"]),
        "document_classification": pdf_record["classification"],
        "method": method_name,
        "initial_scale": initial_scale,
        "final_used_scale": selected_page.get("render_scale", ""),
        "low_scale_success": low_success,
        "retry_1_5": retry_1_5,
        "render_image_size": (
            f"{selected_page.get('render_width')}x{selected_page.get('render_height')}"
            if selected_page else ""
        ),
        "page_recon_paddle_calls": json.dumps(dict(sorted(page_counts.items())), ensure_ascii=False),
        "recon_paddle_calls": len(recon_metrics),
        "total_paddle_calls": len(engine._paddle_call_metrics),
        "page_recon_ocr_seconds": json.dumps(
            {page: round(value, 3) for page, value in sorted(page_seconds.items())},
            ensure_ascii=False,
        ),
        "total_recon_ocr_seconds": round(sum(page_seconds.values()), 3),
        "section3_detected": target_index is not None,
        "section3_page": "" if target_index is None else target_index + 1,
        "section3_start_y": "" if not bounds else round(bounds.get("y_start", 0), 2),
        "section4_boundary_y": "" if not bounds else round(bounds.get("y_end", 0), 2),
        "product_name": product,
        "components": _component_display(components),
        "_components_dict": components,
        "total_processing_seconds": round(total_elapsed, 3),
        "matches_baseline": method_name == "baseline-1.5",
        "product_matches_baseline": method_name == "baseline-1.5",
        "components_match_baseline": method_name == "baseline-1.5",
        "golden_passed": golden_passed,
        "failure_or_difference_reason": error,
    }


def compare_with_baseline(rows):
    by_file = defaultdict(list)
    for row in rows:
        by_file[row["file_name"]].append(row)
    for file_rows in by_file.values():
        baseline = next(row for row in file_rows if row["method"] == "baseline-1.5")
        for row in file_rows:
            if row is baseline:
                continue
            differences = []
            product_match = row["product_name"].casefold() == baseline["product_name"].casefold()
            component_match = row["_components_dict"] == baseline["_components_dict"]
            detection_match = (
                row["section3_detected"] == baseline["section3_detected"]
                and row["section3_page"] == baseline["section3_page"]
            )
            if not detection_match:
                differences.append(
                    f"3항 탐지: P{baseline['section3_page']} -> P{row['section3_page']}"
                )
            if not product_match:
                differences.append(
                    f"제품명: {baseline['product_name']!r} -> {row['product_name']!r}"
                )
            if not component_match:
                differences.append(
                    f"CAS·함량: {baseline['components']!r} -> {row['components']!r}"
                )
            row["product_matches_baseline"] = product_match
            row["components_match_baseline"] = component_match
            row["matches_baseline"] = detection_match and product_match and component_match
            if differences:
                existing = row["failure_or_difference_reason"]
                row["failure_or_difference_reason"] = "; ".join(
                    part for part in [existing, *differences] if part
                )


def write_csv(rows, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def _rate(values):
    values = list(values)
    return 0.0 if not values else 100.0 * sum(bool(value) for value in values) / len(values)


def print_results(rows):
    print("\n=== 파일·방식별 결과 ===")
    header = (
        f"{'파일':34} {'방식':14} {'배율':9} {'재시도':6} {'정찰초':8} "
        f"{'호출':5} {'3항':5} {'제품':6} {'CAS·함량':9} {'기준일치':8}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        scales = f"{row['initial_scale']}->{row['final_used_scale']}"
        print(
            f"{row['file_name'][:34]:34} {row['method']:14} {scales:9} "
            f"{str(row['retry_1_5']):6} {row['total_recon_ocr_seconds']:8.3f} "
            f"{row['recon_paddle_calls']:5} {str(row['section3_detected']):5} "
            f"{str(row['product_matches_baseline']):6} "
            f"{str(row['components_match_baseline']):9} {str(row['matches_baseline']):8}"
        )

    differences = [row for row in rows if not row["matches_baseline"]]
    if differences:
        print("\n=== 기준 방식과 다른 항목 ===")
        for row in differences:
            print(f"- {row['file_name']} / {row['method']}: {row['failure_or_difference_reason']}")

    print("\n=== 방식별 요약 ===")
    summary_rows = []
    for method in METHODS:
        method_rows = [row for row in rows if row["method"] == method]
        adaptive = METHODS[method]["adaptive"]
        summary = {
            "method": method,
            "avg_recon": statistics.mean(row["total_recon_ocr_seconds"] for row in method_rows),
            "avg_total": statistics.mean(row["total_processing_seconds"] for row in method_rows),
            "paddle_calls": sum(row["recon_paddle_calls"] for row in method_rows),
            "low_success": _rate(row["low_scale_success"] for row in method_rows) if adaptive else None,
            "retry": _rate(row["retry_1_5"] for row in method_rows) if adaptive else None,
            "section": _rate(row["section3_detected"] for row in method_rows),
            "product": _rate(row["product_matches_baseline"] for row in method_rows),
            "components": _rate(row["components_match_baseline"] for row in method_rows),
            "golden": all(row["golden_passed"] is True for row in method_rows),
            "all_match": all(row["matches_baseline"] for row in method_rows),
        }
        summary_rows.append(summary)
        low = "-" if summary["low_success"] is None else f"{summary['low_success']:.1f}%"
        retry = "-" if summary["retry"] is None else f"{summary['retry']:.1f}%"
        print(
            f"{method:14} | 평균 정찰 {summary['avg_recon']:.3f}초 | "
            f"평균 전체 {summary['avg_total']:.3f}초 | Paddle {summary['paddle_calls']}회 | "
            f"저배율 성공 {low} | 재시도 {retry} | 3항 {summary['section']:.1f}% | "
            f"제품 {summary['product']:.1f}% | CAS·함량 {summary['components']:.1f}% | "
            f"골든 {'PASS' if summary['golden'] else 'FAIL'}"
        )

    eligible = [summary for summary in summary_rows if summary["all_match"] and summary["golden"]]
    recommended = min(eligible, key=lambda item: item["avg_recon"]) if eligible else None
    print("\n=== 추천 ===")
    if recommended:
        print(
            f"{recommended['method']}: 모든 이미지형 PDF에서 기준 결과 및 골든셋과 일치하며 "
            f"평균 정찰 OCR 시간이 {recommended['avg_recon']:.3f}초로 가장 빠릅니다."
        )
    else:
        print("모든 이미지형 PDF에서 기준·골든 결과를 유지한 방식이 없어 운영 변경을 추천하지 않습니다.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPO_ROOT / "TEST_File")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "reports" / "benchmarks" / "adaptive_recon_benchmark.csv",
    )
    parser.add_argument("--threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--classification-only", action="store_true")
    args = parser.parse_args()

    discovered = discover_pdfs(args.root)
    image_records = print_discovery(discovered)
    if args.classification_only:
        return 0
    if not image_records:
        print("이미지형 PDF가 없어 OCR 비교를 실행하지 않습니다.")
        return 0

    golden_cases = load_golden_cases(REPO_ROOT / "golden" / "msds_golden_v1.json")
    evaluator = make_confidence_evaluator(args.threshold)
    rows = []
    for record in image_records:
        for method_name, method_config in METHODS.items():
            print(f"\n[실행] {record['file_name']} | {method_name}")
            row = run_method(
                record,
                method_name,
                method_config,
                evaluator,
                golden_cases.get(record["file_name"]),
            )
            rows.append(row)
            print(
                f"  정찰 {row['total_recon_ocr_seconds']:.3f}초 / "
                f"Paddle {row['recon_paddle_calls']}회 / 전체 {row['total_processing_seconds']:.3f}초"
            )

    compare_with_baseline(rows)
    write_csv(rows, args.output)
    print_results(rows)
    print(f"\nCSV 저장: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
