import sys
import os
import json

# 현재 디렉토리를 경로에 추가하여 msds_engine_v5를 불러올 수 있게 함
sys.path.append(os.getcwd())

import msds_engine_v5

def test_015():
    pdf_path = r"TEST_File\015_Bentone Gel ISD V _ MSDS (KO).pdf"
    print(f"[*] 테스트 시작: {pdf_path}")
    
    # 로그 함수 정의
    def log_print(msg):
        print(f"[*] {msg}")
        
    result = msds_engine_v5.process_pdf(pdf_path, log_func=log_print)
    
    print("\n--- [최종 추출 결과] ---")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_015()
