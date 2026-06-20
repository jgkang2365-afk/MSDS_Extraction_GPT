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

    table_index = 1
    for elem in all_elements:
        if elem.get("type", "").upper() == "TABLE" and elem.get("page number") in [3, 4]:
            print(f"--- [Table {table_index} (Page {elem.get('page number')})] ---")
            print(json.dumps(elem, ensure_ascii=False, indent=2))
            print()
            table_index += 1

if __name__ == "__main__":
    main()
