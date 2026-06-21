# -*- coding: utf-8 -*-
import os
import glob

def search_all_files():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 모든 py 및 txt 파일
    files = glob.glob(os.path.join(base_dir, "*.py")) + glob.glob(os.path.join(base_dir, "*.txt"))
    for filename in files:
        if "find_concentration.py" in filename: continue
        print(f"[*] Searching in {os.path.basename(filename)}...")
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            for idx, line in enumerate(f, 1):
                if "concentration" in line.lower() or "update_regex" in line.lower():
                    print(f"  [FOUND] Line {idx}: {line.strip()}")

if __name__ == "__main__":
    search_all_files()
