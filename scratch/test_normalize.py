import sys
import os
sys.path.append(os.getcwd())
from msds_engine_v5 import _normalize_single_content


test_str = "＞  85 ％"
result = _normalize_single_content(test_str)
print(f"Input: '{test_str}'")
print(f"Normalized: '{result}'")

test_str2 = "Concentration : ＞  85 ％"
result2 = _normalize_single_content(test_str2)
print(f"Input: '{test_str2}'")
print(f"Normalized: '{result2}'")
