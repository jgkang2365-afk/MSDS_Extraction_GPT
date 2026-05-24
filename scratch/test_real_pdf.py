import sys
import os
import fitz

# msds_engine_v5 임포트를 위해 경로 설정
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))
import msds_engine_v5

def run_real_test():
    pdf_path = "TEST_File/(O)018_[K.S.PEARL] MSDS - Iron Oxide Red 3AS (KR).pdf"
    if not os.path.exists(pdf_path):
        print(f"파일을 찾을 수 없습니다: {pdf_path}")
        return
        
    doc = fitz.open(pdf_path)
    # 섹션 3 페이지 찾기
    pages = msds_engine_v5.find_section3_pages(doc)
    print(f"[*] 섹션 3 발견 페이지: {pages}")
    
    if not pages:
        print("섹션 3 페이지를 찾지 못했습니다.")
        return
        
    page = doc[pages[0]]
    
    # words 정보 추출 및 디버깅 출력
    raw_words = page.get_text("words")
    print(f"[*] 총 추출된 단어 개수: {len(raw_words)}")
    
    # 디버깅을 위해 extract_from_text_regex 실행
    print("\n--- extract_from_text_regex 디버깅 시작 ---")
    extracted, inherited_x = msds_engine_v5.extract_from_text_regex(page, log_func=print)
    
    print("\n--- 추출된 결과 ---")
    for item in extracted:
        print(item)
        
    doc.close()

if __name__ == "__main__":
    run_real_test()
