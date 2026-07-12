import re

engine_file = r"c:\Users\USER\Desktop\안티그래비티\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v6.py"

with open(engine_file, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
for idx, line in enumerate(lines):
    if "GOLDEN_HASH" in line or "golden_hash" in line.lower():
        print(f"{idx+1}: {line.strip()}")
