# -*- coding: utf-8 -*-
import os
import sys

gui_path = r"c:\Users\USER\Desktop\프로젝트\MSDS_EXtaction_V3(v24+GUI통합)\smu_gui.py"
if not os.path.exists(gui_path):
    print("smu_gui.py not found at path:", gui_path)
    exit(1)

with open(gui_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

found = False
for idx, line in enumerate(lines):
    if "mes_master_list" in line and "=" in line:
        print(f"Found mes_master_list assignment at line {idx+1}:")
        start = max(0, idx - 5)
        end = min(idx + 30, len(lines))
        for i in range(start, end):
            l = lines[i]
            sys.stdout.buffer.write(l.encode('utf-8'))
        found = True
        # break 하지 않고 전체 다 확인해봄

if not found:
    print("mes_master_list assignment not found")
