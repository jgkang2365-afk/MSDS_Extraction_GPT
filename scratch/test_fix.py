import re

def _normalize_single_content_old(content_str):
    v = str(content_str).strip()
    v = re.sub(r'[–—]', '-', v)
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
    v = re.sub(r'(?i)proprietary|secret', '', v)
    if re.search(r'(?i)(mg/m3|mg/l|g/l|ppm|kg|ml|µg|ug|g$|g[^a-z])', v): return "미기재%"
    if "Rem" in v: return "Rem.%"
    v = v.replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')
    
    # Hijacking Shield
    letters = re.sub(r'[^a-zA-Z가-힣]', '', v)
    has_explicit_symbol = any(sym in v for sym in ['%', '~', '<', '>', '≤', '≥'])
    if len(letters) > 2 and not has_explicit_symbol:
        return "미기재%"

    # Range Regex (Old)
    range_m = re.search(r'([<>≤≥]*)\s*(\d*\.?\d+)\s*[%]*\s*([-~∼～/]?)\s*([<>≤≥]*)\s*(\d*\.?\d+)', v)
    if range_m:
        p1, n1, sep, p2, n2 = range_m.groups()
        try:
            f1, f2 = float(n1), float(n2)
            if f1 <= 100 and f2 <= 100:
                if f1 > f2: n1, n2 = n2, n1; p1, p2 = p2, p1 
                if p1 and p2 and not sep: return f"{n1}~{n2}%"
                res = f"{p1}{n1}~{p2}{n2}"
                return res if '%' in res else res + '%'
        except: pass

    single_m = re.search(r'([<>≤≥]?)\s*(\d*\.?\d+)', v)
    if single_m:
        if float(single_m.group(2)) <= 100: return f"{single_m.group(1)}{single_m.group(2)}%"
    return "미기재%"

def _normalize_single_content_new(content_str):
    v = str(content_str).strip()
    v = re.sub(r'[–—]', '-', v)
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
    v = re.sub(r'(?i)proprietary|secret', '', v)
    if re.search(r'(?i)(mg/m3|mg/l|g/l|ppm|kg|ml|µg|ug|g$|g[^a-z])', v): return "미기재%"
    if "Rem" in v: return "Rem.%"
    v = v.replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')
    
    # Hijacking Shield (New: added '-' and '~' to symbols)
    letters = re.sub(r'[^a-zA-Z가-힣]', '', v)
    has_explicit_symbol = any(sym in v for sym in ['%', '~', '-', '<', '>', '≤', '≥'])
    if len(letters) > 2 and not has_explicit_symbol:
        return "미기재%"

    # Range Regex (New: sep mandatory OR p2 mandatory)
    # Group 1: p1, Group 2: n1, Group 3: sep, Group 4: p2_1, Group 5: p2_2, Group 6: n2
    range_m = re.search(r'([<>≤≥]*)\s*(\d+\.?\d*|\.\d+)\s*[%]*\s*(?:([-~∼～/])\s*([<>≤≥]*)|([<>≤≥]+))\s*(\d+\.?\d*|\.\d+)', v)
    if range_m:
        groups = range_m.groups()
        p1 = groups[0] or ""
        n1 = groups[1]
        sep = groups[2] or ""
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

    single_m = re.search(r'([<>≤≥]?)\s*(\d*\.?\d+)', v)
    if single_m:
        if float(single_m.group(2)) <= 100: return f"{single_m.group(1)}{single_m.group(2)}%"
    return "미기재%"

test_cases = [
    "45 - 50",
    "≤ 0.1",
    "≤ 0.01",
    "0.1 - 1",
    "다이메틸 카르보네이트 45 - 50", # Hijacking scenario
    "0.1", # Single value decimal
    "10 - 20%",
    "≥95%≤100%",
    "77.08g"
]

print(f"{'Input':<35} | {'Old Result':<15} | {'New Result':<15}")
print("-" * 75)
for tc in test_cases:
    old_res = _normalize_single_content_old(tc)
    new_res = _normalize_single_content_new(tc)
    print(f"{tc:<35} | {old_res:<15} | {new_res:<15}")
