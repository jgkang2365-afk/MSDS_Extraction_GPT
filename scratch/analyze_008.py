
import fitz
import re

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\008_싸이클오일).pdf"

def analyze_section3():
    doc = fitz.open(pdf_path)
    section3_text = ""
    target_page = -1
    
    # 3번 항목 찾기
    for i, page in enumerate(doc):
        text = page.get_text()
        if "3. 구성성분의" in text or "3. 명칭 및" in text:
            target_page = i
            section3_text = text
            break
            
    print(f"--- [파일 분석: 8번] ---")
    if target_page == -1:
        print("❌ 3번 항목 섹션을 찾지 못했습니다.")
        return

    print(f"✅ 3번 항목 발견 (페이지 {target_page+1})")
    print("\n--- [텍스트 덤프] ---")
    print(section3_text)
    
    # ODL이 테이블을 놓친 이유 추측 (단어 좌표 확인)
    words = doc[target_page].get_text("words")
    print("\n--- [좌표 분석 (상위 20개)] ---")
    for w in words[:20]:
        print(f"X:{w[0]:.1f}, Y:{w[1]:.1f} | Text: {w[4]}")

if __name__ == "__main__":
    analyze_section3()
