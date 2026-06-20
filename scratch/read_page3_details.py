# -*- coding: utf-8 -*-
import os
import sys
import json

def print_kid(kid, depth=0):
    indent = "  " * depth
    etype = kid.get("type", "").upper()
    p_num = kid.get("page number", "?")
    content = kid.get("content", "").strip()
    
    # 텍스트가 있는 타입
    if etype in ["PARAGRAPH", "HEADING", "TEXT", "LIST ITEM", "CAPTION"]:
        print(f"{indent}[{etype}] (P.{p_num}): {content}")
    elif etype == "TABLE":
        print(f"{indent}[{etype}] (P.{p_num})")
        for r_idx, row in enumerate(kid.get("rows", [])):
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
            print(f"{indent}  Row {r_idx}: " + " | ".join(row_cells))
    else:
        print(f"{indent}[{etype}] (P.{p_num})")
        
    if "kids" in kid and etype not in ["TABLE", "TABLE ROW", "TABLE CELL"]:
        for child in kid["kids"]:
            print_kid(child, depth + 1)

def main():
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

    json_path = os.path.join("scratch", "010_formaldehyde_odl.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("--- 페이지 3 계층 디테일 ---")
    for kid in data.get("kids", []):
        if kid.get("page number") == 3:
            print_kid(kid, 0)

if __name__ == "__main__":
    main()
