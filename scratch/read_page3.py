# -*- coding: utf-8 -*-
import os
import sys
import json

def main():
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

    json_path = os.path.join("scratch", "010_formaldehyde_odl.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_elements = []
    def collect_elements(kids):
        for kid in kids:
            all_elements.append(kid)
            if "kids" in kid and kid.get("type", "").upper() not in ["TABLE", "TABLE ROW", "TABLE CELL"]:
                collect_elements(kid["kids"])

    collect_elements(data.get("kids", []))

    print("--- 페이지 3의 모든 요소 ---")
    for elem in all_elements:
        p_num = elem.get("page number")
        if p_num == 3:
            etype = elem.get("type", "").upper()
            content = elem.get("content", "").strip()
            
            # Text 추출
            if etype in ["PARAGRAPH", "HEADING", "TEXT", "LIST ITEM"]:
                if "kids" in elem:
                    texts = []
                    def _collect(ks):
                        for k in ks:
                            if "content" in k: texts.append(k["content"])
                            if "kids" in k: _collect(k["kids"])
                    _collect(elem["kids"])
                    if texts:
                        content = (content + " " + " ".join(texts)).strip()
                print(f"[{etype}] {content}")
                
            elif etype == "TABLE":
                print(f"[{etype}]")
                for r_idx, row in enumerate(elem.get("rows", [])):
                    row_cells = []
                    for cell in row.get("cells", []):
                        cell_texts = []
                        def _extract(ks):
                            for k in ks:
                                if "content" in k: cell_texts.append(k["content"])
                                if "kids" in k: _extract(k["kids"])
                        if "kids" in cell:
                            _extract(cell["kids"])
                        row_cells.append(" ".join(cell_texts).strip())
                    print(f"  Row {r_idx}: " + " | ".join(row_cells))
            else:
                print(f"[{etype}]")

if __name__ == "__main__":
    main()
