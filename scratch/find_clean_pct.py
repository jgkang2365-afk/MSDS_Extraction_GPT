# -*- coding: utf-8 -*-
with open("msds_engine_v6.py", "r", encoding="utf-8") as f:
    for idx, line in enumerate(f, 1):
        if "clean_percentage" in line:
            print(f"{idx}: {line.strip()}")
