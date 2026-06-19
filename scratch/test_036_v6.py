# -*- coding: utf-8 -*-
import os
import sys
import glob

# 프로젝트 루트를 임포트 경로에 추가
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

import msds_engine_v6

def main():
    test_file_dir = os.path.join(base_dir, "TEST_File")
    files = glob.glob(os.path.join(test_file_dir, "*036*.pdf"))
    if not files:
        print("036 파일을 찾을 수 없습니다.")
        return
        
    pdf_path = files[0]
    print(f"디버그 테스트 파일: {pdf_path}")
    
    # process_pdf 함수를 통해 MSDS 파싱 격발
    try:
        res = msds_engine_v6.process_pdf(pdf_path, log_func=print)
        print("\n================ [결과 리포트] ================")
        print(f"제품명: {res.get('제품명')}")
        print(f"신호등: {res.get('신호등')}")
        print(f"사용 엔진: {res.get('used_engine')}")
        print(f"품질 점수: {res.get('integrity_score')}")
        print(f"구성성분 문자열: {res.get('구성성분')}")
        
        # 고분자 CAS (26636-08-8) 추출 정합성 검증
        comp_str = res.get('구성성분', '')
        if "26636-08-8(1~10%)" in comp_str:
            print("🟢 [성공] 고분자 성분이 1~10% 함량으로 정상 추출되었습니다!")
        else:
            print("❌ [실패] 고분자 성분(26636-08-8) 또는 함량이 누락되었거나 다르게 추출되었습니다.")
            
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    main()
