import os
import sys
import json

# 모듈 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import MSDSEngineV6

def 디버그_004_자재():
    작업_디렉토리 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    대상_파일 = os.path.join(작업_디렉토리, "TEST_File", "004_(-)SHIKIMIC ACID.PDF")
    
    engine = MSDSEngineV6()
    결과 = engine.process_msds_pipeline(대상_파일, log_func=print)
    print("\n[최종 반환 딕셔너리]:")
    print(json.dumps(결과, ensure_ascii=False, indent=4))

if __name__ == "__main__":
    디버그_004_자재()
