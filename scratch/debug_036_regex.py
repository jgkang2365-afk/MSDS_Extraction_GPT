# -*- coding: utf-8 -*-
import os
import sys
import glob
import fitz

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from msds_engine_v6 import MSDSEngineV6

def main():
    test_file_dir = os.path.join(base_dir, "TEST_File")
    files = glob.glob(os.path.join(test_file_dir, "*036*.pdf"))
    if not files:
        print("036 파일을 찾을 수 없습니다.")
        return
        
    pdf_path = files[0]
    doc = fitz.open(pdf_path)
    page = doc[0] # 1페이지
    
    engine = MSDSEngineV6()
    
    # extract_from_text_regex 내부의 physical_lines 빌드 로직 재현
    raw_words = page.get_text("words")
    raw_words.sort(key=lambda w: (w[1], w[0]))
    
    physical_lines = []
    if raw_words:
        current_line_words = [raw_words[0]]
        line_top = raw_words[0][1]    
        line_bottom = raw_words[0][3] 

        for i in range(1, len(raw_words)):
            curr_w = raw_words[i]
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
        
    print("--- 1페이지 physical_lines 목록 ---")
    for pl in physical_lines:
        print(f"y={pl['y']:.1f}: {pl['text']}")
        
    # 디버그: 26636-08-8 탐색
    target_cas = "26636-08-8"
    cas_line_idx = -1
    for idx, pl in enumerate(physical_lines):
        if target_cas in pl["text"]:
            cas_line_idx = idx
            break
            
    print(f"\nCAS 번호 검출 줄 인덱스: {cas_line_idx}")
    if cas_line_idx != -1:
        start_idx = max(0, cas_line_idx - 3)
        end_idx = min(len(physical_lines), cas_line_idx + 4)
        
        target_indices = []
        for idx in range(start_idx, end_idx):
            pl_text = physical_lines[idx]["text"].lower()
            if "polymer" in pl_text or "고분자" in pl_text:
                target_indices.append(idx)
                
        print(f"polymer/고분자 키워드 검출 줄 인덱스들: {target_indices}")
        if target_indices:
            min_idx = min([cas_line_idx] + target_indices)
            max_idx = max([cas_line_idx] + target_indices)
            polymer_lines = physical_lines[min_idx:max_idx+1]
            
            nearby_text = "\n".join([pl["text"] for pl in polymer_lines])
            print(f"\n--- 수집된 nearby_text ---\n{nearby_text}")
            
            import re
            # cont_pattern은 msds_engine_v6에서 정의된 것과 동일
            cont_pattern = re.compile(r'(?<![a-zA-Z\d-])([<>≤≥= \uff1c\uff1e\uff1d~∼～\-|\u2013|\u2014]*\s*\b\d+(?:\.\d+)?\b(?:\s*[<>≤≥=~∼～\-|\u2013|\u2014|이상|미만|above|below|to|and|%]+\s*)*\b\d*(?:\.\d+)?\b\s*%?(?:\s*(?:이상|미만|above|below|%)\s*)*)(?![a-zA-Z])', re.IGNORECASE)
            
            cas_pos = nearby_text.find(target_cas)
            if cas_pos != -1:
                target_text = nearby_text[cas_pos:]
            else:
                target_text = nearby_text
                
            clean_nearby = target_text.replace("미맊", "미만").replace("미먄", "미만").replace("이핚", "이하")
            clean_nearby = re.sub(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', ' ', clean_nearby)
            clean_nearby = re.sub(r'\b20[0-2]\d[.\-/]\d{1,2}[.\-/]\d{1,2}\b', ' ', clean_nearby)
            clean_nearby = re.sub(r'\b20[0-2]\d년?\b', ' ', clean_nearby)
            
            flat_nearby = re.sub(r'\s+', ' ', clean_nearby)
            print(f"\n--- 평탄화된 flat_nearby ---\n{flat_nearby}")
            
            nums = [float(n) for n in re.findall(r'\d+\.?\d*', flat_nearby)]
            valid_nums = []
            for n in nums:
                n_val = int(n) if n.is_integer() else n
                if 0.01 <= n_val <= 100.0:
                    valid_nums.append(n_val)
                    
            print(f"추출된 전체 숫자 목록: {nums}")
            print(f"필터링된 유효 숫자 목록: {valid_nums}")
            
            best_pct = "미기재%"
            if len(valid_nums) == 2:
                n1, n2 = min(valid_nums), max(valid_nums)
                is_less = "미만" in flat_nearby or "<" in flat_nearby
                s_sym = ""
                if is_less:
                    if abs(float(n2) - 1.0) < 1e-9:
                        s_sym = "<"
                if s_sym:
                    best_pct = f"{n1}~{s_sym}{n2}%"
                else:
                    best_pct = f"{n1}~{n2}%"
            elif len(valid_nums) == 1:
                n1 = valid_nums[0]
                is_less = "미만" in flat_nearby or "<" in flat_nearby
                is_more = "이상" in flat_nearby or ">" in flat_nearby or "≥" in flat_nearby
                pref = "<" if is_less else ("≥" if is_more else "")
                best_pct = f"{pref}{n1}%"
                
            print(f"최종 합성 후보: '{best_pct}'")
            
    doc.close()

if __name__ == "__main__":
    main()
