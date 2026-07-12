# -*- coding: utf-8 -*-
import sys
import os

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

engine_path = r"c:\Users\USER\Desktop\안티그래비티\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v6.py"

print("=== msds_engine_v6.py에서 'gemini-2.5-flash' 검색 ===")
with open(engine_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

count = 0
for idx, line in enumerate(lines):
    if "gemini-2.5-flash" in line:
        count += 1
        print(f"줄 {idx+1}: {line.strip()}")

print(f"총 발견 횟수: {count}")
