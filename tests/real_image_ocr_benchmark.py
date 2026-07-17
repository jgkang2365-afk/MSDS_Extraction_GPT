import argparse
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from msds_engine_v6 import MSDSEngineV6


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--force-local", action="store_true")
    parser.add_argument("--full-pipeline", action="store_true")
    args = parser.parse_args()

    golden = json.loads(Path("golden/msds_golden_v1.json").read_text(encoding="utf-8"))
    case = next(item for item in golden["cases"] if item["file"] == args.pdf.name)
    expected_cas = sorted(
        component["cas"]
        for component in case["components"]
        if component.get("cas") and component["cas"] != "미기재"
    )

    if args.full_pipeline:
        logs = []
        engine = MSDSEngineV6()
        if args.force_local:
            with patch(
                "msds_engine_v6.requests.post",
                side_effect=ConnectionError("benchmark blocked external OCR"),
            ), patch.object(
                engine,
                "call_llm_router",
                side_effect=ConnectionError("benchmark blocked external AI"),
            ):
                result = engine.process_msds_pipeline(str(args.pdf), log_func=logs.append)
        else:
            result = engine.process_msds_pipeline(str(args.pdf), log_func=logs.append)
        component_text = str(result.get("구성성분", ""))
        actual_by_cas = {
            cas: content.strip()
            for cas, content in re.findall(r"(\d{2,7}-\d{2}-\d)\s*\(([^)]*)\)", component_text)
        }
        expected_by_cas = {
            component["cas"]: component["content_expected"]
            for component in case["components"]
            if component.get("cas")
        }
        product = str(result.get("제품명", ""))
        comparison = {
            cas: {
                "expected": expected_content,
                "actual": actual_by_cas.get(cas),
                "passed": actual_by_cas.get(cas) == expected_content,
            }
            for cas, expected_content in expected_by_cas.items()
        }
        summary = {
            "file": args.pdf.name,
            "product_expected": case["product_name"]["expected"],
            "product_actual": product,
            "product_passed": product.lower() == case["product_name"]["expected"].lower(),
            "content_comparison": comparison,
            "all_golden_fields_passed": (
                product.lower() == case["product_name"]["expected"].lower()
                and all(item["passed"] for item in comparison.values())
            ),
            "engine_result": result,
            "paddle_calls": engine._paddle_call_metrics,
            "local_paddle_call_count": len(engine._paddle_call_metrics),
        }
        print("\n".join(logs))
        print("FULL_PIPELINE_GOLDEN_JSON=" + json.dumps(summary, ensure_ascii=False, indent=2))
        return

    logs = []
    engine = MSDSEngineV6()
    images, section_text, pages, recon_data = engine.extract_section3_images(
        str(args.pdf), log_func=logs.append
    )
    product_text = engine.extract_section_1(
        "scanned", str(args.pdf), log_func=logs.append, recon_data=recon_data
    )

    precision_result = None
    if recon_data and recon_data.get("section_crop"):
        kwargs = {
            "pdf_path": str(args.pdf),
            "paddle_ocr_instance": None,
            "log_func": logs.append,
            "target_page_idx": recon_data["target_page_index"],
            "recon_data": recon_data,
            "pre_rendered_crop": recon_data["section_crop"],
        }
        if args.force_local:
            with patch(
                "msds_engine_v6.requests.post",
                side_effect=ConnectionError("benchmark forced local fallback"),
            ):
                precision_result = engine.run_flexible_sandwich_pipeline(**kwargs)
        else:
            precision_result = engine.run_flexible_sandwich_pipeline(**kwargs)

    combined_text = "\n".join(
        [section_text, product_text, str((precision_result or {}).get("data", "")), str((precision_result or {}).get("raw_data", ""))]
    )
    found_cas = sorted(cas for cas in expected_cas if cas in combined_text)
    target_page_index = None if not recon_data else recon_data.get("target_page_index")
    summary = {
        "file": args.pdf.name,
        "pages": pages,
        "target_page_number": None if target_page_index is None else target_page_index + 1,
        "product_expected": case["product_name"]["expected"],
        "product_text_contains_expected": case["product_name"]["expected"].lower() in product_text.lower(),
        "expected_cas": expected_cas,
        "found_expected_cas": found_cas,
        "precision_status": None if precision_result is None else precision_result.get("status"),
        "paddle_calls": engine._paddle_call_metrics,
        "local_paddle_call_count": len(engine._paddle_call_metrics),
        "crop_size": None if not recon_data or not recon_data.get("section_crop") else [
            recon_data["section_crop"]["image_width"],
            recon_data["section_crop"]["image_height"],
        ],
    }
    print("\n".join(logs))
    print("BENCHMARK_JSON=" + json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
