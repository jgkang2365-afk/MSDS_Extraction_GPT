import os
import sys
import glob
import fitz

# 상위 디렉토리를 탐색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import MSDSEngineV6
from msds_utils_v3 import sanitize_chemical_formulas

def debug_ocr():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_file_dir = os.path.join(base_dir, "TEST_File")
    pdf_files = glob.glob(os.path.join(test_file_dir, "*049*.pdf")) + glob.glob(os.path.join(test_file_dir, "*049*.PDF"))
    pdf_path = pdf_files[0]
    
    doc = fitz.open(pdf_path)
    engine = MSDSEngineV6()
    
    # 3항 페이지 수색
    target_pages = engine.find_section3_pages(doc)
    print(f"Target pages for Section 3: {target_pages}")
    
    for page_idx in target_pages:
        page = doc[page_idx]
        print(f"\n--- Page {page_idx+1} ---")
        
        # extract_from_text_regex 내부와 유사하게 단어 추출 및 라인 구성
        raw_words = page.get_text("words")
        if not raw_words:
            continue
            
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
        
        physical_lines = []
        current_line_words = [raw_words[0]]
        line_top = raw_words[0][1]
        
        for i in range(1, len(raw_words)):
            curr_w = raw_words[i]
            w_prev = current_line_words[-1]
            h_curr = curr_w[3] - curr_w[1]
            h_prev = w_prev[3] - w_prev[1]
            min_h = min(h_curr, h_prev)
            vertical_threshold = min_h * 0.25
            
            if abs(curr_w[1] - w_prev[1]) <= vertical_threshold:
                current_line_words.append(curr_w)
            else:
                current_line_words.sort(key=lambda w: w[0])
                physical_lines.append({
                    "text": " ".join([w[4] for w in current_line_words])
                })
                current_line_words = [curr_w]
                line_top = curr_w[1]
                
        if current_line_words:
            current_line_words.sort(key=lambda w: w[0])
            physical_lines.append({
                "text": " ".join([w[4] for w in current_line_words])
            })
            
        for idx, pl in enumerate(physical_lines):
            line_text = pl["text"]
            sanitized = sanitize_chemical_formulas(line_text)
            if "7779-88-6" in line_text or "HNO3" in line_text or "NO3" in line_text:
                print(f"Row {idx}: [ORIG] {line_text}")
                print(f"Row {idx}: [SANI] {sanitized}")

if __name__ == "__main__":
    debug_ocr()
