import re

def _normalize_single_content(content_str):
    orig_raw = str(content_str).strip()
    v = re.sub(r'[–—]', '-', orig_raw)
    v = re.sub(r'(\d),(\d)', r'\1.\2', v)
    v = re.sub(r'\((?:max|최대|이하|미만|w/w|v/v|w/v)[^\)]*\)', '', v, flags=re.I)
    v = re.sub(r'([\d\.]+)\s*(<)', r'>\1', v)
    v = re.sub(r'([\d\.]+)\s*(>)', r'<\1', v)
    v = re.sub(r'(?i)잔량|balance|remainder|残량|나머지', 'Rem.', v)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(미만|below|less\s*than|未満)', r'<\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(이하|up\s*to|以下)', r'≤\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(초과|more\s*than|over|超)', r'>\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(이상|above|以上)', r'≥\1', v)
    
    v = v.replace(" ", "")
    v = v.replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')
    
    range_m = re.search(r'([<>≤≥]*)\s*(\d+\.?\d*|\.\d+)\s*[%]*\s*(?:([-–—~∼～/])\s*([<>≤≥]*)|([<>≤≥]+))\s*(\d+\.?\d*|\.\d+)', v)
    if range_m:
        groups = range_m.groups()
        p1, n1, sep = groups[0] or "", groups[1], groups[2] or ""
        p2 = (groups[3] or "") if groups[2] else (groups[4] or "")
        n2 = groups[5]
        try:
            f1, f2 = float(n1), float(n2)
            if f1 <= 100 and f2 <= 100:
                if f1 > f2: n1, n2 = n2, n1; p1, p2 = p2, p1
                if p1 and p2 and not sep: return f"{n1}~{n2}%"
                res = f"{p1}{n1}~{p2}{n2}"
                return res if '%' in res else res + '%'
        except: pass
    return "Failed"

print(f"Test 0.1~1미만: {_normalize_single_content('0.1~1미만')}")
