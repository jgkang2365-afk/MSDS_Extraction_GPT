
import fitz
import re
import sys

# 표준 출력을 UTF-8로 강제 설정 (Windows 인코딩 문제 방지)
sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\008_싸이클오일).pdf"

def analyze_section3():
    doc = fitz.open(pdf_path)
    section3_text = ""
    target_page = -1
    
    # 3번 항목 찾기 (유연한 검색)
    for i, page in enumerate(doc):
        text = page.get_text()
        if "3." in text and ("구성성분" in text or "명칭" in text or "조성" in text):
            target_page = i
            section3_text = text
            break
            
    print(f"--- [Analysis: File 8] ---")
    if target_page == -1:
        print("FAILED: Could not find Section 3.")
        # 전체 텍스트 1페이지라도 출력해서 상태 확인
        print("--- [Page 1 Preview] ---")
        print(doc[0].get_text()[:500])
        return

    print(f"SUCCESS: Found Section 3 at Page {target_page+1}")
    print("\n--- [Text Dump] ---")
    print(section3_text)
    
    # 띄어쓰기 패턴 확인
    print("\n--- [Space/Hidden Character Analysis] ---")
    lines = section3_text.split('\n')
    for line in lines:
        if re.search(r'\d', line):
            # 글자 사이의 간격 확인을 위해 repr 출력
            print(f"Raw Line: {repr(line)}")

if __name__ == "__main__":
    analyze_section3()
