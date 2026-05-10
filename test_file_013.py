import os
import sys
import json
from msds_engine_v5 import process_pdf

def test_file_13():
    file_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\013_[래디안]달팽이점액여과물(HD2)_영문 GHS MSDS(240429)삼정-씨엔티드림_요청 조성비 서류.pdf"
    
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    print(f"--- 13번 파일 정밀 테스트 시작 ---")
    
    def log_print(msg):
        print(f"[*] {msg}")

    result = process_pdf(file_path, log_func=log_print)
    
    print("\n--- [최종 추출 결과] ---")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_file_13()
