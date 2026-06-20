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

    print("--- Heading 및 중요 텍스트 목록 ---")
    for elem in all_elements:
        etype = elem.get("type", "").upper()
        content = elem.get("content", "").strip()
        if etype in ["HEADING", "TITLE"]:
            print(f"[{etype}] P.{elem.get('page number')}: {content}")
        elif etype in ["PARAGRAPH", "TEXT"] and any(kw in content for kw in ["항 ", "항3", "3.", "구성성분"]):
            print(f"[{etype}-MATCH] P.{elem.get('page number')}: {content}")

if __name__ == "__main__":
    main()
