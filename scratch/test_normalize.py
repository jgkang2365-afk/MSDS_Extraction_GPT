# -*- coding: utf-8 -*-
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from msds_engine_v6 import MSDSEngineV6

def main():
    engine = MSDSEngineV6()
    test_inputs = [
        "1 이상 ~ 10 % 미만",
        "1이상 ~ 10% 미만",
        "1 ~ 10 % 미만",
        "1 ~ 10%",
        "1 이상 ~ 10 % 미만".replace(" ", "")
    ]
    for inp in test_inputs:
        res = engine._normalize_single_content(inp)
        print(f"입력: '{inp}' -> 결과: '{res}'")

if __name__ == "__main__":
    main()
