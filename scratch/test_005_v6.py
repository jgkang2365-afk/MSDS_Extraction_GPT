# 005번 자재 단독 디버깅용 스크립트
import os
import sys
import json
import re

# 상위 경로를 모듈 패스에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import msds_engine_v6

def run_debug():
    pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\005_★SUPER WAY LUBE 32.pdf"
    
    print("[*] 005번 자재 분석 시작...")
    try:
        engine = msds_engine_v6.MSDSEngineV6()
        
        # log_func에 print를 전달하여 상세 로그를 화면에 출력
        res = engine.process_msds_pipeline(pdf_path, log_func=print)
        print("\n[+] 분석 성공:")
        print(json.dumps(res, ensure_ascii=False, indent=2))
    except Exception as e:
        print("\n[-] 분석 에러 크래시 발생:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_debug()
