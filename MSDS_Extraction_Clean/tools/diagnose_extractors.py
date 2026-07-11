#!/usr/bin/env python3
"""Print local extractor intermediates without calling external AI services."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure:
        reconfigure(encoding="utf-8", errors="replace")

import fitz
from opendataloader.pdf import PDFParser

from msds_engine_v6 import MSDSEngineV6


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    pdf_path = args.pdf.resolve()

    engine = MSDSEngineV6()
    doc = fitz.open(pdf_path)
    pages = engine.find_section3_pages(doc)
    density = []
    for page_index in pages:
        for item in engine.extract_table_by_density_clustering(doc[page_index]):
            item = dict(item)
            item["page"] = page_index + 1
            density.append(item)
    doc.close()

    odl_doc = PDFParser().parse(str(pdf_path))
    tables = []
    for page_index in pages:
        page_tables = []
        for element in getattr(odl_doc.pages[page_index], "elements", []):
            if getattr(element, "type", "") != "TABLE":
                continue
            priority = -1
            for row in element.rows:
                row_texts = [cell.text or "" for cell in row.cells]
                joined = "".join(
                    __import__("re").sub(r"[\s().%|_]", "", text.lower())
                    for text in row_texts
                )
                if any(key in joined for key in ("함유량", "함량", "content", "conc", "weight")):
                    for index, text in enumerate(row_texts):
                        clean = __import__("re").sub(r"\s+", "", text.lower())
                        if "%" in text or "함량" in clean or "content" in clean:
                            priority = index
                            break
                    if priority >= 0:
                        break
            page_tables.append({
                "priority_col_idx": priority,
                "rows": [
                    {
                        "cells": [cell.text or "" for cell in row.cells],
                        "parsed": engine.parse_row_robust_v2(row, priority_col_idx=priority),
                    }
                    for row in element.rows
                ],
            })
        tables.append({"page": page_index + 1, "tables": page_tables})
    odl = engine.extract_components_odl_robust(odl_doc, pages, str(pdf_path), log_func=print)
    print(json.dumps({"pages": pages, "tables": tables, "odl": odl, "density": density}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
