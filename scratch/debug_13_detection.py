import sys
import os
import re
import fitz

# sys.stdout encoding fix
import io
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

def debug_find_section3_pages(pdf_path):
    print(f"[*] Debug Start: {pdf_path}")
    doc = fitz.open(pdf_path)
    pages = []
    found_section3 = False
    
    # regex from engine
    section_regex = r'(?:SECTION\s*)?[23][\s.:\-\/]*(?:구성성분|성분|성분\s?및\s?함량|COMPOS|INGRED|조성물)'
    
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        print(f"--- [Page {i}] Text Snippet ---")
        print(text[:200].replace('\n', ' '))
        
        match = re.search(section_regex, text, re.I)
        if match:
            print(f"MATCH SUCCESS! (Page {i}): {match.group()}")
            found_section3 = True
        else:
            print(f"MATCH FAILED (Page {i})")
        
        if found_section3:
            pages.append(i)
    
    doc.close()
    return pages

if __name__ == "__main__":
    pdf_path = r"TEST_File\013_[래디안]달팽이점액여과물(HD2)_영문 GHS MSDS(240429)삼정-씨엔티드림_요청 조성비 서류.pdf"
    res = debug_find_section3_pages(pdf_path)
    print(f"\n[*] Detected Pages: {res}")
