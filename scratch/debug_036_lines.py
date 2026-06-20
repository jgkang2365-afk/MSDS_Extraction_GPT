import os
import sys
# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import glob
import re
import msds_utils_v3

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
test_file_dir = os.path.join(base_dir, "TEST_File")
files_036 = glob.glob(os.path.join(test_file_dir, "*036*.pdf"))

if not files_036:
    print("No 036 PDF found.")
else:
    pdf_path = files_036[0]
    doc = fitz.open(pdf_path)
    # Page 1 represents index 0
    page = doc[0]
    raw_words = page.get_text("words")
    
    # Same preprocessing logic as msds_engine_v6
    merged_words = []
    for w in raw_words:
        font_h = w[3] - w[1]
        merged = False
        for j, u in enumerate(merged_words):
            if u[4] == w[4]:
                if abs(u[0] - w[0]) < max(12, font_h * 0.8) and abs(u[1] - w[1]) < max(8, font_h * 0.5):
                    merged_words[j] = (min(u[0],w[0]), min(u[1],w[1]), max(u[2],w[2]), max(u[3],w[3]), u[4], u[5], u[6], u[7])
                    merged = True
                    break
        if not merged:
            merged_words.append(w)
    raw_words = merged_words
    raw_words.sort(key=lambda w: (w[1], w[0]))
    
    words = []
    cas_pattern = re.compile(r'(?<![\d-])(\d{2,7}\s*-\s*\d{2}\s*-\s*\d)(?![\d-])')
    for w in raw_words:
        text_val = w[4]
        if any(c.isdigit() for c in text_val) and any(c.isalpha() for c in text_val):
            check_val = re.sub(r'\s+', '', text_val)
            if not cas_pattern.search(text_val):
                text_val = re.sub(r'\d', 'X', text_val)
        words.append((w[0], w[1], w[2], w[3], text_val, w[5], w[6], w[7]))

    physical_lines = []
    if words:
        current_line_words = [words[0]]
        line_top = words[0][1]    
        line_bottom = words[0][3] 

        for i in range(1, len(words)):
            curr_w = words[i]
            w_prev = current_line_words[-1]
            h_curr = curr_w[3] - curr_w[1]
            h_prev = w_prev[3] - w_prev[1]
            min_h = min(h_curr, h_prev)
            vertical_threshold = min_h * 0.25
            
            if abs(curr_w[1] - w_prev[1]) <= vertical_threshold:
                current_line_words.append(curr_w)
                line_top = min(line_top, curr_w[1])
                line_bottom = max(line_bottom, curr_w[3])
            else:
                current_line_words.sort(key=lambda w: w[0])
                physical_lines.append({
                    "y": line_top, 
                    "text": " ".join([w[4] for w in current_line_words]),
                    "words": current_line_words
                })
                current_line_words = [curr_w]
                line_top = curr_w[1]
                line_bottom = curr_w[3]

        if current_line_words:
            current_line_words.sort(key=lambda w: w[0])
            physical_lines.append({
                "y": line_top, 
                "text": " ".join([w[4] for w in current_line_words]),
                "words": current_line_words
            })
        physical_lines.sort(key=lambda pl: pl["y"])

    print("--- PHYSICAL LINES ---")
    for idx, pl in enumerate(physical_lines):
        print(f"[{idx}] (y={pl['y']:.1f}): {pl['text']}")
        
    print("\n--- CAS SEARCH TESTING ---")
    target_cases = ["7732-18-5", "14807-96-6", "1317-65-3"]
    for tc in target_cases:
        found_idx = -1
        for idx, pl in enumerate(physical_lines):
            # Try normal search and clean search
            if tc in pl["text"]:
                found_idx = idx
                print(f"Normal found: {tc} in [{idx}]")
            if tc.replace(" ", "") in pl["text"].replace(" ", ""):
                print(f"Clean found: {tc} in [{idx}]")
