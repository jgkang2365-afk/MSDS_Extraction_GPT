# -*- coding: utf-8 -*-
"""순차적 조기 종료(Early Stopping) 비전 정찰 기능 검증 스크립트"""
import os
import sys
import fitz

# 상위 폴더를 모듈 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import msds_engine_v5

# 텍스트 탐지를 무조건 실패하게 하여 비전 정찰(Recon)이 가동되도록 임시 모킹(Mocking)
msds_engine_v5.find_section3_pages = lambda doc: []

# 테스트할 파일 경로 지정 (015번 PDF 사용)
pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\015_Bentone Gel ISD V _ MSDS (KO).pdf"

def main():
    print("=== [검증 스크립트 실행] ===")
    if not os.path.exists(pdf_path):
        print(f"오류: 테스트용 PDF 파일이 존재하지 않습니다: {pdf_path}")
        return
        
    current_sniper = msds_engine_v5.get_next_sniper()
    print(f"선택된 AI Sniper: {current_sniper.get('alias') if current_sniper else '없음'}")
    
    def log_func(msg):
        print(f"[로그] {msg}")
        
    print("\n--- extract_section3_images 호출 시작 ---")
    try:
        images, text, pages = msds_engine_v5.extract_section3_images(
            pdf_path=pdf_path,
            current_sniper=current_sniper,
            log_func=log_func
        )
        print("\n--- 호출 완료 결과 ---")
        print(f"최종 매핑된 페이지 번호 리스트 (pages): {pages}")
        print(f"추출된 이미지 개수: {len(images)}")
    except Exception as e:
        print(f"실행 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
