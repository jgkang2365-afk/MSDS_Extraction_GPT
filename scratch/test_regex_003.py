import fitz
import re
import sys
import os
from opendataloader.pdf import PDFParser

pdf_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\003_(O)018_[K.S.PEARL] MSDS - Iron Oxide Red 3AS (KR).pdf'
doc = fitz.open(pdf_path)
page = doc[0]

parser = PDFParser()
odl_doc = parser.parse(pdf_path)
table_bboxes = []
for el in odl_doc.pages[0].elements:
    if el.type == "TABLE":
        for row in el.rows:
            for cell in row.cells:
                if getattr(cell, 'bbox', None):
                    table_bboxes.append(cell.bbox)

print("All ODL table_bboxes:")
for idx, bbox in enumerate(table_bboxes):
    print(f"Bbox {idx}: {bbox}")

print("\nSome fitz words:")
words = page.get_text("words")
for w in words:
    if "1309" in w[4] or "2943" in w[4] or "97.0" in w[4] or "INCI" in w[4]:
        print(f"Word: '{w[4]}' | bbox: {[w[0], w[1], w[2], w[3]]}")



current_line_words = [raw_words[0]]
line_top = raw_words[0][1]
line_bottom = raw_words[0][3]
physical_lines = []

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

print("\n--- Physical Lines (Filtered) ---")
for idx, pl in enumerate(physical_lines):
    print(f"Line {idx}: y={pl['y']:.2f} | text='{pl['text']}'")

# logical_rows 빌드
logical_rows = []
pending_lines = []
current_row = None

cas_pattern = re.compile(r'(?<![\d-])(\d{2,7}\s*-\s*\d{2}\s*-\s*\d)(?![\d-])')

for line in physical_lines:
    row_text = line["text"]
    cas_list = cas_pattern.findall(row_text)
    if cas_list:
        is_prod = any(k in row_text.lower() for k in ["chemical identification", "product name", "제품식별자", "제품명", "substance identification", "identification of the substance"])
        current_row = {"cas_list": cas_list, "words": [], "last_y": line["y"], "is_product_id": is_prod, "line_text": row_text}
        for p_line in pending_lines:
            current_row["words"].extend(p_line["words"])
        pending_lines = []
        current_row["words"].extend(line["words"])
        logical_rows.append(current_row)
    else:
        is_new_ingredient_line = any(k in row_text.lower() for k in ["ingredient name", "ingredient", "component", "물질명", "성분명", "chemical name"])
        if current_row and (line["y"] - current_row["last_y"]) < 40 and not is_new_ingredient_line:
            current_row["words"].extend(line["words"])
            current_row["last_y"] = line["y"]
        else:
            current_row = None
            pending_lines.append(line)

print("\n--- Logical Rows (Filtered) ---")
for idx, row in enumerate(logical_rows):
    row_full_text = " ".join([w[4] for w in sorted(row["words"], key=lambda w: (w[1], w[0]))])
    print(f"Row {idx}: cas_list={row['cas_list']} | full_text='{row_full_text}'")

# has_global_percent 확인
y_header_ref = 0.0
for pl in physical_lines:
    if re.search(r'(?:SECTION\s*)?[23][\s.:\-\/]*(?:구성성분|성분|성분\s?및\s?함량|COMPOS|INGRED|조성물)', pl["text"], re.I):
        y_header_ref = pl["y"] - 10
        break

header_words = [w for w in raw_words if y_header_ref - 30 <= w[1] <= y_header_ref + 150]
header_text = " ".join([w[4] for w in header_words]).upper()
has_global_percent = "%" in header_text or "퍼센트" in header_text
print(f"\ny_header_ref: {y_header_ref:.2f}")
print(f"header_text: '{header_text}'")
print(f"has_global_percent: {has_global_percent}")

content_x_mid = 9999
cas_x_min = 9999
content_x_min = 9999
for w in header_words:
    txt = w[4].upper()
    if "CAS" in txt:
        cas_x_min = min(cas_x_min, w[0])
    if any(k in txt for k in ["함유량", "함량", "CONTENT", "CONC", "%", "농도"]):
        content_x_min = min(content_x_min, w[0])
        if content_x_mid == 9999:
            content_x_mid = (w[0] + w[2]) / 2

print(f"content_x_mid: {content_x_mid:.2f}")

for row in logical_rows:
    row_full_text = " ".join([w[4] for w in sorted(row["words"], key=lambda w: (w[1], w[0]))])
    for target_cas in row["cas_list"]:
        clean_text = row_full_text
        for other_cas in row["cas_list"]:
            if other_cas != target_cas:
                clean_text = clean_text.replace(other_cas, " [OTHER_CAS] ")
        clean_text = clean_text.replace(target_cas, "[CAS_ANCHOR]")
        clean_text = re.sub(r'\b20[0-2]\d[.\-/]\d{1,2}[.\-/]\d{1,2}\b', ' YYYY ', clean_text)
        clean_text = re.sub(r'\b20[0-2]\d년?\b', ' YYYY ', clean_text)
        clean_text = clean_text.replace("미맊", "미만").replace("미먄", "미만").replace("이핚", "이하")
        clean_text = re.sub(r'(\d)(미만|이상|이하|초과)', r'\1 \2', clean_text)
        clean_text = re.sub(r'(\d)\s*([-~])\s*(\d)', r'\1\2\3', clean_text)
        
        cont_pattern = re.compile(r'(?<![a-zA-Z\d-])([<>≤≥= \uff1c\uff1e\uff1d~∼～\-|\u2013|\u2014]*\s*\b\d+(?:\.\d+)?\b(?:\s*[<>≤≥=~∼～\-|\u2013|\u2014|이상|미만|above|below|to|and|%]+\s*)*\b\d*(?:\.\d+)?\b\s*%?(?:\s*(?:이상|미만|above|below|%)\s*)*)(?![a-zA-Z])', re.IGNORECASE)
        matches_with_pos = []
        for m in cont_pattern.finditer(clean_text):
            val = m.group(1).strip()
            if not val: continue
            matches_with_pos.append((val, m.start()))
            
        print(f"\nTarget CAS: {target_cas}")
        print(f"clean_text: '{clean_text}'")
        
        def score_match(match_tuple):
            m_val, match_pos = match_tuple
            has_percent = "%" in m_val
            if re.search(r'%\s*:', clean_text[match_pos:match_pos+len(m_val)+5]):
                return -5000, "percent colon noise"
                
            context_area = clean_text[max(0, match_pos-30):min(len(clean_text), match_pos+len(m_val)+30)].lower()
            tight_context = clean_text[max(0, match_pos-10):min(len(clean_text), match_pos+len(m_val)+10)].lower()
            
            absolute_noises = ["g/mol", "mg/m3", "ppm", "밀도", "density", "twa", "lel", "oel"]
            if any(noise in tight_context for noise in absolute_noises):
                return -5000, "absolute noise"
                
            if not has_percent:
                if not has_global_percent and not any(k in m_val for k in ['~', '∼', '～', '-', '<', '>', '≤', '≥']):
                    return -5000, "no percent and no range indicator"
                    
            core_m_val = m_val.strip(' -∼~<>\u2013\u2014≤≥=')
            if core_m_val.count('-') >= 2 or core_m_val.count('\u2013') >= 2:
                return -5000, "too many hyphens"
                
            anchor_pos = clean_text.find("[CAS_ANCHOR]")
            start_search = min(anchor_pos, match_pos)
            end_search = max(anchor_pos, match_pos)
            text_between = clean_text[start_search:end_search]
            if "[OTHER_CAS]" in text_between:
                return -10000, "other cas between"
                
            dist_char = abs(anchor_pos - match_pos)
            if dist_char > 120:
                return -5000, "too far"

            score = 0
            if has_percent: score += 500
            elif has_global_percent: score += 400
            
            if any(k in m_val for k in ['~', '∼', '～', '-', '<', '>', '≤', '≥', '미만', '이상', '\u2013', '\u2014']):
                score += 300
            if '.' in m_val: score += 100
            
            if match_pos > anchor_pos: score += 200 
            else: score -= 50  
            
            score -= (dist_char * 3) 
            return score, "valid"
            
        for m in matches_with_pos:
            score, reason = score_match(m)
            print(f"  Match: {m} -> Score: {score} | Reason/Status: {reason}")
