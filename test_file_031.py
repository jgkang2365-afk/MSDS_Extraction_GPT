import os
import sys
import json
from msds_engine_v5 import process_pdf

def test_file_031():
    file_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\031_용접봉CR-13 CSW-0001_MSDS_용접재료(연강용 피복아크 용접봉)_(국문)v5_2023.08.22 (2).pdf"
    
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    print(f"--- [V17.3.5.16] 031번 파일(용접봉) 검증 테스트 ---")
    
    def log_print(msg):
        print(f"[*] {msg}")

    result = process_pdf(file_path, log_func=log_print)
    print("\n--- [최종 결과] ---")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_file_031()
