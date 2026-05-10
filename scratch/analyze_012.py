
import fitz
import re
import sys

# 표준 출력을 UTF-8로 강제 설정
sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\012_[SFG] SinoWhite NCA(CG) MSDS Kor. (Rev.03) 2025-06-09.pdf"

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
            
    print(f"--- [Analysis: File 12] ---")
    if target_page == -1:
        print("FAILED: Could not find Section 3.")
        return

    print(f"SUCCESS: Found Section 3 at Page {target_page+1}")
    print("\n--- [Text Dump] ---")
    print(section3_text)
    
    # 전체 텍스트에서 CAS 패턴 검색
    cas_list = re.findall(r'(\d{2,7}-\d{2}-\d)', section3_text)
    print(f"\n[실제 발견된 CAS 개수]: {len(cas_list)}개")
    print(f"CAS 목록: {cas_list}")

if __name__ == "__main__":
    analyze_section3()
