import fitz
import sys

# Ensure UTF-8 for printing
sys.stdout.reconfigure(encoding='utf-8')

pdf_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\015_Bentone Gel ISD V _ MSDS (KO).pdf'

try:
    doc = fitz.open(pdf_path)
    print(f"Total Pages: {len(doc)}")
    
    for i in range(len(doc)):
        text = doc[i].get_text()
        print(f"\n--- Page {i+1} ---")
        if "구성성분의 명칭 및 함유량" in text or "3. 조성" in text or "3. 구성" in text:
            print(f"FOUND Section 3 Header on Page {i+1}")
            # Print a snippet
            idx = text.find("구성성분")
            if idx != -1:
                print(text[max(0, idx-50):idx+500])
        else:
            # Check if it's a scanned page by looking at text length
            if len(text.strip()) < 50:
                print(f"Page {i+1} seems to have very little text (possibly scanned or image-based).")
except Exception as e:
    print(f"Error: {e}")
