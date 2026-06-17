# -*- coding: utf-8 -*-
import os
import sys
import re
import fitz

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import msds_engine_v5
import msds_utils_v3

pdf_path = os.path.join("TEST_File", "040_Giemsa SDS.pdf")
doc = fitz.open(pdf_path)

# 2페이지(인덱스 1) 및 3페이지(인덱스 2)에 대해 밀도 클러스터링 결과 관찰
for page_idx in [1, 2]:
    if page_idx >= len(doc):
        continue
    page = doc[page_idx]
    print(f"\n--- Page {page_idx+1} Density Clustering Debug ---")
    
    words = page.get_text("words")
    if not words:
        continue
        
    def _get_median(lst):
        if not lst: return 0.0
        sorted_lst = sorted(lst)
        n = len(sorted_lst)
        if n % 2 == 1: return sorted_lst[n // 2]
        return (sorted_lst[n // 2 - 1] + sorted_lst[n // 2]) / 2.0

    heights = [w[3] - w[1] for w in words]
    base_scale = _get_median(heights)

    words.sort(key=lambda w: w[1])
    temp_rows = []
    current_row = []
    for w in words:
        if not current_row:
            current_row.append(w)
        else:
            w_prev = current_row[-1]
            h_curr = w[3] - w[1]
            h_prev = w_prev[3] - w_prev[1]
            min_h = min(h_curr, h_prev)
            vertical_threshold = min_h * 0.25
            if abs(w[1] - w_prev[1]) <= vertical_threshold:
                current_row.append(w)
            else:
                temp_rows.append(current_row)
                current_row = [w]
    if current_row:
        temp_rows.append(current_row)

    all_gaps = []
    for r in temp_rows:
        r_sorted = sorted(r, key=lambda w: w[0])
        for i in range(len(r_sorted) - 1):
            gap = r_sorted[i+1][0] - r_sorted[i][2]
            if gap > 0: all_gaps.append(gap)

    median_gap = _get_median(all_gaps) if all_gaps else base_scale * 0.5
    horizontal_ratio = median_gap / base_scale if base_scale > 0 else 0.5

    rows = temp_rows
    rows.sort(key=lambda r: _get_median([w[1] for w in r]))

    for row in rows:
        row_words = sorted(row, key=lambda w: w[0])
        cells = []
        current_cell = []
        for w in row_words:
            if not current_cell:
                current_cell.append(w)
            else:
                w_prev = current_cell[-1]
                char_height = w_prev[3] - w_prev[1]
                gap = w[0] - w_prev[2]
                if gap > char_height * horizontal_ratio:
                    cells.append(current_cell)
                    current_cell = [w]
                else:
                    current_cell.append(w)
        if current_cell:
            cells.append(current_cell)
            
        cell_texts = []
        for cell in cells:
            cell.sort(key=lambda w: w[0])
            cell_text = " ".join([w[4] for w in cell]).strip()
            cell_texts.append(cell_text)
            
        # CAS 매칭이 존재하는 행만 출력해봅니다.
        has_cas = False
        for txt in cell_texts:
            clean_txt = txt.replace(" ", "")
            if re.findall(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', clean_txt):
                has_cas = True
                break
                
        if has_cas:
            print(f"Row (y={row_words[0][1]:.1f}): {cell_texts}")

doc.close()
