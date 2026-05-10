import os
import sys
import json
import fitz
from msds_engine_v5 import extract_from_text_regex

def test_011_regex():
    file_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\011_1005_TECA-BIOME™_GHS_MSDS개정_(KOR)_ICBIO.pdf"
    doc = fitz.open(file_path)
    page = doc[0]
    
    def log_print(msg):
        print(msg)

    print("--- [V17.3.5.15] 011번 Regex-Recovery 테스트 ---")
    results = extract_from_text_regex(page, log_func=log_print)
    
    for r in results:
        print(f"CAS: {r['cas_no']} -> 함량: {r['content']}")

if __name__ == "__main__":
    test_011_regex()
