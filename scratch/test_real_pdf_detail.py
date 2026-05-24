import sys
import os
import fitz
import re
import unicodedata

# msds_engine_v5 임포트를 위해 경로 설정
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))
import msds_engine_v5

cas_pattern = re.compile(r'(?<![\d-])(\d{2,7}\s*-\s*\d{2}\s*-\s*\d)(?![\d-])')
# cont_pattern도 복사
cont_pattern = re.compile(r'(?<![a-zA-Z\d-])([<>≤≥= \uff1c\uff1e\uff1d~∼～\-|\u2013|\u2014]*\s*\b\d+(?:\.\d+)?\b(?:\s*[<>≤≥=~∼～\-|\u2013|\u2014|이상|미만|above|below|to|and|%]+\s*)*\b\d*(?:\.\d+)?\b\s*%?(?:\s*(?:이상|미만|above|below|%)\s*)*)(?![a-zA-Z])', re.IGNORECASE)
cont_pattern_single = re.compile(r'([<>≤≥\uff1c\uff1e~∼～\-\u2013\u2014]?\s*\d+(?:\.\d+)?\s*%?)', re.IGNORECASE)

def run_detail_test():
    pdf_path = "TEST_File/(O)011_SDS_ICP-08N-1(Cd).pdf"
    doc = fitz.open(pdf_path)
    
    # msds_engine_v5.find_section3_pages의 행 단위 매칭 개량 버전 시뮬레이션
    pages = []
    found_section3 = False
    exit_pattern = re.compile(r'^(?:SECTION\s*)?[4-9][항\s.:]*(?:응급|폭발|화재|누출|취급|저장|노출|방지|FIRST|FIRE|ACCIDENTAL|HANDLING|EXPOSURE)', re.I | re.M)
    
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        # 헤더 라인 단위 정밀 대조
        if not found_section3:
            for line in lines:
                if re.search(r'(?:SECTION\s*)?[23][\s.:\-\/]*(?:구성성분|성분|성분\s?및\s?함량|COMPOS|INGRED|조성물)', line, re.I):
                    found_section3 = True
                    break
        
        if found_section3:
            pages.append(i)
            if len(pages) >= 2:
                # 2페이지 규칙 준수
                break
            for line in lines:
                if exit_pattern.match(line) and "Page" not in line:
                    break
                    
    print(f"[*] 개량된 섹션 3 발견 페이지: {pages}")
    
    if not pages:
        print("섹션 3 페이지를 찾지 못했습니다.")
        return

    log_path = "scratch/test_detail_output.txt"
    sys.stdout = open(log_path, "w", encoding="utf-8")
    
    # 2페이지 (Water가 있는 페이지) 상세 분석을 위해 강제 지정
    page_idx = 1
    print(f"\n================ [페이지 {page_idx} 상세 분석] ================")
    page = doc[page_idx]
    raw_words = page.get_text("words")
    # y좌표 -> x좌표 순 정렬
    raw_words.sort(key=lambda w: (w[1], w[0]))
    
    # 블록 단위로 y_start, y_end 계산
    blocks = page.get_text("blocks")
    blocks.sort(key=lambda b: b[1])
    
    y_start, y_end = 0.0, 9999.0
    y_start_orig = 0.0
    for b in blocks:
        b_text = re.sub(r'\s+', '', b[4]).upper()
        if y_start_orig == 0.0:
            if any(k in b_text for k in ["구성성분", "성분및", "COMPONENTS", "INGREDIENTS", "COMPOSITION", "조성물"]):
                y_start_orig = b[1] - 30
                y_start = y_start_orig
        if y_start_orig > 0.0 and b[1] > y_start_orig:
            if any(k in b_text for k in ["응급조치", "FIRSTAID", "FIRSTAIDMEASURES"]):
                y_end = b[1]
                break
                
    if raw_words and y_start > raw_words[-1][1] * 0.75:
        y_start = 0.0
        
    filtered_words = [w for w in raw_words if y_start <= w[1] < y_end]
    print(f"[*] 필터링된 단어 범위: y_start={y_start}, y_end={y_end} (원본 y_start_orig={y_start_orig})")
    
    # 텍스트 레이아웃 정보 출력
    print("\n--- [추출된 텍스트 레이아웃] ---")
    for w in filtered_words:
        # (x0, y0, x1, y1, word)
        print(f"[{w[0]:.1f}, {w[1]:.1f}, {w[2]:.1f}, {w[3]:.1f}] -> {w[4]}")
        
    # physical_lines 구성 시뮬레이션
    words = []
    for w in filtered_words:
        text_val = w[4]
        if any(c.isdigit() for c in text_val) and any(c.isalpha() for c in text_val):
            check_val = re.sub(r'\s+', '', text_val)
            if not cas_pattern.search(text_val) and not any(k in check_val for k in ["미만", "이상", "이하", "초과", "%", "~", "∼", "to"]):
                text_val = re.sub(r'\d', 'X', text_val)
        words.append((w[0], w[1], w[2], w[3], text_val, w[5], w[6], w[7]))

    physical_lines = []
    if words:
        current_line_words = [words[0]]
        line_top = words[0][1]    
        line_bottom = words[0][3] 
        line_height = line_bottom - line_top

        for i in range(1, len(words)):
            curr_w = words[i]
            curr_top = curr_w[1]
            curr_bottom = curr_w[3]
            overlap = max(0, min(line_bottom, curr_bottom) - max(line_top, curr_top))

            if overlap > (line_height * 0.3) or abs(curr_top - line_top) <= (line_height * 0.5):
                current_line_words.append(curr_w)
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
                line_height = line_bottom - line_top

        if current_line_words:
            current_line_words.sort(key=lambda w: w[0])
            physical_lines.append({
                "y": line_top, 
                "text": " ".join([w[4] for w in current_line_words]),
                "words": current_line_words
            })

    print("\n--- [구성된 물리적 행(physical_lines)] ---")
    for pl in physical_lines:
        print(f"y={pl['y']:.1f} | {pl['text']}")

    # logical_rows 시뮬레이션
    logical_rows = []
    pending_lines = []
    current_row = None

    for line in physical_lines:
        row_text = line["text"]
        cas_list = cas_pattern.findall(row_text)
        
        if cas_list:
            current_row = {"cas_list": cas_list, "words": []}
            for p_line in pending_lines:
                current_row["words"].extend(p_line["words"])
            pending_lines = []
            current_row["words"].extend(line["words"])
            logical_rows.append(current_row)
        else:
            if current_row:
                current_row["words"].extend(line["words"])
            else:
                pending_lines.append(line)

    print("\n--- [논리적 행(logical_rows) 분석] ---")
    
    # physical_lines 빌드 후 y_start 정밀 재검색
    y_start_refined = 0.0
    for pl in physical_lines:
        line_text = pl["text"]
        if re.search(r'(?:SECTION\s*)?[23][\s.:\-\/]*(?:구성성분|성분|성분\s?및\s?함량|COMPOS|INGRED|조성물)', line_text, re.I):
            y_start_refined = pl["y"] - 10
            break
            
    if y_start_refined > 0.0:
        y_start_orig = y_start_refined
        y_start = y_start_refined
        # filtered_words 재필터링
        filtered_words = [w for w in raw_words if y_start <= w[1] <= y_end]
        
    print(f"[*] 개량된 y_start 적용: y_start={y_start} (y_start_orig={y_start_orig})")

    # has_global_percent 구단 설정 교정
    y_header_ref = y_start_orig if y_start_orig > 0.0 else y_start
    header_words = [w for w in filtered_words if y_header_ref - 30 <= w[1] <= y_header_ref + 150]
    header_text = " ".join([w[4] for w in header_words]).upper()
    has_global_percent = "%" in header_text or "퍼센트" in header_text
    
    print(f"\n[*] 검출된 헤더 텍스트 범위: y_header_ref={y_header_ref - 30} ~ {y_header_ref+150}")
    print(f"[*] 검출된 헤더 텍스트: '{header_text}' (has_global_percent = {has_global_percent})")
    
    # logical_rows 시뮬레이션 복구
    logical_rows = []
    pending_lines = []
    current_row = None

    for line in physical_lines:
        if line["y"] < y_start: continue # y_start 이전 라인은 행 구성에서 생략
        row_text = line["text"]
        cas_list = cas_pattern.findall(row_text)
        
        if cas_list:
            current_row = {"cas_list": cas_list, "words": []}
            for p_line in pending_lines:
                current_row["words"].extend(p_line["words"])
            pending_lines = []
            current_row["words"].extend(line["words"])
            logical_rows.append(current_row)
        else:
            if current_row:
                current_row["words"].extend(line["words"])
            else:
                pending_lines.append(line)

    print("\n--- [논리적 행(logical_rows) 분석] ---")
    for r_idx, row in enumerate(logical_rows):
        row_full_text = " ".join([w[4] for w in row["words"]])
        print(f"행 {r_idx} | CAS: {row['cas_list']} | 텍스트: {row_full_text}")
        
        for target_cas in row["cas_list"]:
            clean_text = row_full_text
            for other_cas in row["cas_list"]:
                if other_cas != target_cas:
                    clean_text = clean_text.replace(other_cas, " [OTHER_CAS] ")
            clean_text = clean_text.replace(target_cas, "[CAS_ANCHOR]")
            
            clean_text = re.sub(r'\b20[0-2]\d[.\-/]\d{1,2}[.\-/]\d{1,2}\b', ' YYYY ', clean_text)
            clean_text = re.sub(r'\b20[0-2]\d년?\b', ' YYYY ', clean_text)
            clean_text = clean_text.replace("미맊", "미만").replace("미먄", "미만")
            clean_text = re.sub(r'(\d)(미만|이상|이하|초과)', r'\1 \2', clean_text)
            clean_text = re.sub(r'(\d)\s*([-~])\s*(\d)', r'\1\2\3', clean_text)

            matches_with_pos = []
            for m in cont_pattern.finditer(clean_text):
                val = m.group(1).strip()
                if not val: continue
                matches_with_pos.append((val, m.start()))
                
            print(f"  -> CAS {target_cas} 에 대한 cont_pattern 매칭 후보들: {matches_with_pos}")
            
            # score_match 시뮬레이션
            for m_val, match_pos in matches_with_pos:
                has_percent = "%" in m_val
                
                # SCL 노이즈 차단
                if re.search(r'%\s*:', clean_text[match_pos:match_pos+len(m_val)+5]):
                    continue
                    
                context_area = clean_text[max(0, match_pos-30):min(len(clean_text), match_pos+len(m_val)+30)].lower()
                tight_context = clean_text[max(0, match_pos-10):min(len(clean_text), match_pos+len(m_val)+10)].lower()
                
                # 절대 단위 노이즈
                absolute_noises = ["g/mol", "mg/m3", "ppm", "밀도", "density", "twa", "lel", "oel"]
                if any(noise in tight_context for noise in absolute_noises):
                    continue
                    
                # % 면책 특권 룰 검사
                if not has_percent:
                    if not has_global_percent and not any(k in m_val for k in ['~', '∼', '～', '-', '<', '>', '≤', '≥']):
                        continue
                    weak_noises = ["ec 번호", "ec번호", "ec-no", "ec number", "einecs", "elincs", 
                                   "tox", "irrit", "corr", "dam", "stot", "분류", "category", "cat.", 
                                   "분자량", "molecular weight", "mw", "항", "section"]
                    if any(noise in context_area for noise in weak_noises):
                        continue
                        
                layout_noises = ["쪽", "page", "페이지"]
                if any(noise in clean_text[max(0, match_pos-20):match_pos].lower() for noise in layout_noises) and not has_percent: 
                    continue
                    
                core_m_val = m_val.strip(' -∼~<>\u2013\u2014≤≥=')
                if core_m_val.count('-') >= 2 or core_m_val.count('\u2013') >= 2: 
                    continue
                    
                anchor_pos = clean_text.find("[CAS_ANCHOR]")
                start_search = min(anchor_pos, match_pos)
                end_search = max(anchor_pos, match_pos)
                text_between = clean_text[start_search:end_search]
                if "[OTHER_CAS]" in text_between:
                    continue
                    
                dist_char = abs(anchor_pos - match_pos)
                if dist_char > 120: 
                    continue

                score = 0
                if has_percent: score += 500
                elif has_global_percent: score += 400 

                if any(k in m_val for k in ['~', '∼', '～', '-', '<', '>', '≤', '≥', '미만', '이상', '\u2013', '\u2014']): score += 300
                if '.' in m_val: score += 100
                
                if match_pos > anchor_pos: score += 200 
                else: score -= 50  
                
                score -= (dist_char * 3) 
                
                m_nums = re.findall(r'\d+\.?\d*', m_val)
                if m_nums:
                    for num_str in m_nums:
                        try:
                            val = float(num_str)
                            if val > 110: score -= 3000; break 
                            if 1990 <= val <= 2030: score -= 1000 
                        except: pass
                        
                print(f"    - 후보 [{m_val}]: 최종 점수 = {score} (거리: {dist_char}자)")
            
    doc.close()
    sys.stdout.close()
    sys.stdout = sys.__stdout__

if __name__ == "__main__":
    run_detail_test()
