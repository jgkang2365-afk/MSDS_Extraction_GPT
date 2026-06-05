import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))
import fitz
import re
import unicodedata
from msds_engine_v5 import find_section3_pages, _get_sorted_and_normalized_text

pdf_path = r"TEST_File/035_아이생각수성내부프로 (M-BASE)_GHS국문.pdf"
doc = fitz.open(pdf_path)
pages = find_section3_pages(doc)
print("섹션3 페이지 목록:", pages)

for p_idx in pages:
    page = doc[p_idx]
    raw_words = page.get_text("words")
    raw_words.sort(key=lambda w: (w[1], w[0]))
    
    # physical_lines 구성 재현
    physical_lines = []
    if raw_words:
        current_line_words = [raw_words[0]]
        line_top = raw_words[0][1]    
        line_bottom = raw_words[0][3] 
        line_height = line_bottom - line_top

        for i in range(1, len(raw_words)):
            curr_w = raw_words[i]
            curr_top = curr_w[1]
            curr_bottom = curr_w[3]
            overlap = max(0, min(line_bottom, curr_bottom) - max(line_top, curr_top))

            if overlap > (line_height * 0.2) or abs(curr_top - line_top) <= (line_height * 0.8) or abs(curr_bottom - line_bottom) <= (line_height * 0.8):
                current_line_words.append(curr_w)
                line_bottom = max(line_bottom, curr_bottom)
                line_top = min(line_top, curr_top)
                line_height = line_bottom - line_top
            else:
                current_line_words.sort(key=lambda w: w[0])
                physical_lines.append({
                    "y": line_top, 
                    "text": " ".join([w[4] for w in current_line_words]),
                })
                current_line_words = [curr_w]
                line_top = curr_w[1]
                line_bottom = curr_w[3]
                line_height = line_bottom - line_top

        if current_line_words:
            current_line_words.sort(key=lambda w: w[0])
            physical_lines.append({
                "y": line_top, 
                "text": " ".join([w[4] for w in current_line_words]),
            })

    print(f"\n--- [Page {p_idx}] Physical Lines ---")
    for pl in physical_lines:
        print(f"Y={pl['y']:.1f} | {pl['text']}")
doc.close()
