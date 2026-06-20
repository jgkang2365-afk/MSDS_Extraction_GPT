# 010번 자재의 clean_text와 cont_pattern 매칭 결과를 상세 인쇄하는 스크립트입니다.
import os
import sys
import fitz
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import MSDSEngineV6

def 분석():
    작업_디렉토리 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    대상_파일 = os.path.join(작업_디렉토리, "TEST_File", "010_포름알데하이드_시그마.pdf")
    
    if os.path.exists(대상_파일):
        엔진 = MSDSEngineV6()
        문서 = fitz.open(대상_파일)
        페이지 = 문서[3]
        
        # 물리적인 행 추출
        words = 페이지.get_text("words")
        words.sort(key=lambda w: (w[1], w[0]))
        
        physical_lines = []
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
            
        # 3섹션 시작부터 파싱
        y_start = 0.0
        for pl in physical_lines:
            line_text = pl["text"]
            if re.search(r'(?:SECTION\s*)?[23][\s.:\-\/]*(?:구성성분|성분|성분\s?및\s?함량|COMPOS|INGRED|조성물)', line_text, re.I):
                y_start = pl["y"] - 10
                break
                
        logical_rows = []
        pending_lines = []
        current_row = None
        cas_pattern = re.compile(r'(?<![\d-])(\d{2,7}\s*-\s*\d{2}\s*-\s*\d)(?![\d-])')
        
        for line in physical_lines:
            if line["y"] < y_start: continue
            row_text = line["text"]
            if re.search(r'SECTION\s*[3456]', row_text, re.I): continue
            cas_list = cas_pattern.findall(row_text)
            if cas_list:
                is_prod = any(k in row_text.lower() for k in ["chemical identification", "product name", "제품식별자", "제품명", "substance identification"])
                current_row = {"cas_list": cas_list, "words": [], "last_y": line["y"], "is_product_id": is_prod}
                for p_line in pending_lines:
                    current_row["words"].extend(p_line["words"])
                pending_lines = []
                current_row["words"].extend(line["words"])
                logical_rows.append(current_row)
            else:
                if current_row and (line["y"] - current_row["last_y"]) < 40:
                    current_row["words"].extend(line["words"])
                    current_row["last_y"] = line["y"]
                else:
                    current_row = None
                    pending_lines.append(line)
                    
        for row in logical_rows:
            row_words = sorted(row["words"], key=lambda w: (w[1], w[0]))
            row_full_text = " ".join([w[4] for w in row_words])
            print("\n------------------------------")
            print(f"로지컬 로우 전체 텍스트:\n{row_full_text}")
            
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
                
                print(f"\n대상 캐스: {target_cas}")
                print(f"정제 텍스트: {clean_text}")
                
                matches_with_pos = []
                cont_pattern = re.compile(r'(?<![a-zA-Z\d-])([<>≤≥= \uff1c\uff1e\uff1d~∼～\-|\u2013|\u2014]*\s*\b\d+(?:\.\d+)?\b(?:\s*[<>≤≥=~∼～\-|\u2013|\u2014|이상|미만|above|below|to|and|%]+\s*)*\b\d*(?:\.\d+)?\b\s*%?(?:\s*(?:이상|미만|above|below|%)\s*)*)(?![a-zA-Z])', re.IGNORECASE)
                for m in cont_pattern.finditer(clean_text):
                    val = m.group(1).strip()
                    if not val: continue
                    matches_with_pos.append((val, m.start(), m.end()))
                    print(f"  매칭 후보: {val} | 시작: {m.start()} | 끝: {m.end()}")
                    
        문서.close()

if __name__ == "__main__":
    분석()
