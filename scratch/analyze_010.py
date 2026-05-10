
import fitz
import re
import sys

# 표준 출력을 UTF-8로 강제 설정
sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\010_세신 카트리지 구리스 MSDS-한글판-CG400.pdf"

def analyze_section3():
    doc = fitz.open(pdf_path)
    section3_text = ""
    target_page = -1
    
    # 3번 항목 찾기
    for i, page in enumerate(doc):
        text = page.get_text()
        if "3." in text and ("구성성분" in text or "명칭" in text):
            target_page = i
            section3_text = text
            break
            
    print(f"--- [Analysis: File 10] ---")
    if target_page == -1:
        print("FAILED: Could not find Section 3.")
        return

    print(f"SUCCESS: Found Section 3 at Page {target_page+1}")
    print("\n--- [Text Dump] ---")
    print(section3_text)
    
    # 띄어쓰기 및 특수 기호 확인
    print("\n--- [Structural Detail Analysis] ---")
    lines = section3_text.split('\n')
    for line in lines:
        if re.search(r'\d', line):
            print(f"Raw Line: {repr(line)}")

if __name__ == "__main__":
    analyze_section3()
