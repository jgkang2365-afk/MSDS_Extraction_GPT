import re
import json

# msds_engine_v5.py에서 핵심 함수 복사 (V17.2.2 버전)
def _normalize_single_content(content_str):
    content_str = str(content_str).strip()
    content_str = re.sub(r'([\d\.]+)\s*(<)', r'>\1', content_str)
    content_str = re.sub(r'([\d\.]+)\s*(>)', r'<\1', content_str)
    content_str = re.sub(r'(?i)잔량|balance|remainder|残量', 'Rem.', content_str)
    content_str = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(미만|below|less\s*than|未満)', r'<\1', content_str)
    content_str = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(이하|up\s*to|以下)', r'≤\1', content_str)
    content_str = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(초과|more\s*than|over|超)', r'>\1', content_str)
    content_str = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(이상|above|以上)', r'≥\1', content_str)
    if re.search(r'\d$', content_str): content_str += '%'
    v = content_str.replace(" ", "")
    v = re.sub(r'\([^)]*[A-Za-z가-힣][^)]*\)', '', v)
    v = re.sub(r'(?i)\(w/w\)|\(v/v\)|\(w/v\)|\(weight/weight\)|proprietary|secret', '', v)
    if re.search(r'(?i)(mg/m3|mg/l|g/l|ppm|kg|ml|µg|ug)', v): return "미기재%"
    v = v.replace('＜', '<').replace('＞', '>')
    v = v.replace('<=', '≤').replace('>=', '≥')
    v = re.sub(r'\.0+(?=[^\d]|$)', '', v)
    pm_match = re.match(r'^([0-9.]+)[±\+-]+([0-9.]+)%?$', v)
    if pm_match:
        try:
            val, pm = float(pm_match.group(1)), float(pm_match.group(2))
            return f"{val-pm:g}~{val+pm:g}%"
        except: pass
    weird_range = re.match(r'^([≥>]*)([0-9.]+)(?:%?)([≤<]*)([0-9.]+)(?:%?)$', v)
    if weird_range:
        p1, n1, p2, n2 = weird_range.groups()
        if p1 and p2: return f"{n1}~{n2}%"
    range_m = re.match(r'^([<>≤≥]*)([0-9.]+)[%]*[-~]([<>≤≥]*)([0-9.]+)[%]*$', v)
    if range_m:
        p1, n1, p2, n2 = range_m.groups()
        p1_clean = p1.replace('≥', '').replace('>', '').replace('≤', '').replace('<', '')
        p2_clean = p2.replace('≤', '').replace('≥', '').replace('>', '') 
        return f"{p1_clean}{n1}~{p2_clean}{n2}%"
    if "Rem" in v: return "Rem.%" if "%" not in v else v
    single_m = re.match(r'^([<>≤≥]?)([0-9.]+)%?$', v)
    if single_m:
        p, n = single_m.groups()
        return f"{p}{n}%"
    return "미기재%"

def _clean_content_odl(text):
    t = text.replace(" ", "")
    if any(k in t.lower() for k in ["balance", "잔량", "rem"]): return "Rem.%"
    return t

class MockCell:
    def __init__(self, text):
        self.text = text

class MockRow:
    def __init__(self, texts):
        self.cells = [MockCell(t) for t in texts]

def parse_row_robust_v2_test(row):
    cells = [re.sub(r'\s+', ' ', (c.text or "")).strip() for c in row.cells if (c.text or "").strip()]
    if len(cells) < 2: return None
    header_keywords = {"cas", "casno", "cas번호", "cas-no", "함유량", "함량", "content", "구성성분", "화학물질명", "substance", "물질명", "명칭"}
    cell_lower_set = {re.sub(r'[\s\(\)\.%]', '', c.lower()) for c in cells}
    if cell_lower_set.intersection(header_keywords): return None
    cas_list, name_candidates = [], []
    strong_content = None 
    weak_content = None   
    for c in cells:
        found_cas = re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', c)
        if found_cas:
            cas_list.extend(found_cas)
            c_remain = re.sub(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', '', c).strip()
            if not c_remain: continue
            c = c_remain 
        norm_c = _normalize_single_content(c)
        if norm_c != "미기재%":
            if any(k in c for k in ['%', '~', '-', '<', '>', '≤', '≥', '.', 'Rem', '잔량', 'balance']):
                if not strong_content: strong_content = _clean_content_odl(c)
            else:
                if not weak_content: weak_content = _clean_content_odl(c)
            continue
        if len(c) > 1 and not re.match(r'^[\d\s.,\-~]+$', c):
            name_candidates.append(c)
    if not cas_list: return None
    name = ""
    if name_candidates:
        valid_names = [n for n in name_candidates if len(n) < 50]
        name = max(valid_names, key=len) if valid_names else name_candidates[0]
    final_content = strong_content or weak_content or "미기재%"
    final_comps = []
    for cas in cas_list:
        final_comps.append({"name": name, "cas_no": cas, "content": final_content, "engine": "ODL-v2.2"})
    return final_comps

# 이미지 데이터 테스트
test_rows = [
    ["GERANYL ACETATE", "105-87-3", "203-341-5", "급성 수생 1:H400...", "5 ~ 10"],
    ["HEXAMETHYLINDANOPRYAN", "1222-05-5", "214-946-9", "급성 수생 1:H400...", "5 ~ 10"],
    ["VANILLIN", "121-33-5", "204-465-2", "눈자극성 2(2A):H319", "0 ~ 5"],
    ["BUTYLPHENYL METHYLPROPIONAL", "80-54-6", "201-289-8", "만성 수생 2:H411...", "0 ~ 5"]
]

print("=== V17.2.2 수문장 테스트 결과 ===")
for r_texts in test_rows:
    row = MockRow(r_texts)
    result = parse_row_robust_v2_test(row)
    if result:
        for item in result:
            print(f"물질명: {item['name']} | CAS: {item['cas_no']} | 함량: {item['content']}")
