# 010번 자재에 대해 extract_from_text_regex의 실행 과정과 매칭 후보들을 상세히 인쇄하는 디버그 스크립트입니다.
import os
import sys
import fitz

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import MSDSEngineV6

def 디버그_실행():
    작업_디렉토리 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    대상_파일 = os.path.join(작업_디렉토리, "TEST_File", "010_포름알데하이드_시그마.pdf")
    
    if os.path.exists(대상_파일):
        엔진 = MSDSEngineV6()
        문서 = fitz.open(대상_파일)
        
        # 3섹션이 있는 3번(0부터 시작하여 3번째 인덱스, 즉 4페이지)을 대상으로 합니다.
        페이지 = 문서[3]
        
        # 엔진 내부 함수를 직접 실행하여 후보군을 출력해 봅니다.
        추출_결과, _ = 엔진.extract_from_text_regex(페이지, log_func=print)
        print("\n=== 최종 정규식 추출 결과 ===")
        for 항목 in 추출_결과:
            print(f"CAS: {항목.get('cas')} | 함량: {항목.get('content')} | 이름: {항목.get('name')}")
            
        문서.close()
    else:
        print("파일이 존재하지 않습니다.")

if __name__ == "__main__":
    디버그_실행()
