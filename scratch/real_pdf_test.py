import sys
import os
sys.path.append(os.getcwd())

import fitz
import msds_engine_v5

def test_multiple_pdfs():
    pdfs = [
        r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\011_1005_TECA-BIOME™_GHS_MSDS개정_(KOR)_ICBIO.pdf",
        r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\002_MSDS(보통휘발유(Regular Unleaded Gasoline)_SOIL)(O).pdf"
    ]
    
    for pdf_path in pdfs:
        if not os.path.exists(pdf_path):
            print(f"[ERROR] PDF not found: {pdf_path}")
            continue

        print(f"\n\n==================== [{os.path.basename(pdf_path)}] ====================")
        doc = fitz.open(pdf_path)
        target_pages = msds_engine_v5.find_section3_pages(doc)
        
        for p_idx in target_pages:
            print(f"\n--- [Page {p_idx}] 추출 시작 ---")
            page = doc[p_idx]
            results = msds_engine_v5.extract_from_text_regex(page, log_func=print)
            print(f"[*] 최종 결과: {results}")
        doc.close()

if __name__ == "__main__":
    test_multiple_pdfs()
