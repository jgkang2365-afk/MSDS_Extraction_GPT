import os
import re

def strip_and_rebuild():
    with open('msds_engine_v5_utf8.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 버전 및 기본 로직 유지, 한글 주석 제거
    # 정규식으로 한글 주석 (# ...) 제거
    content = re.sub(r'#.*[가-힣].*', '', content)
    
    # 2. 부등호 로직 삽입 (영어로 작성하여 인코딩 방어)
    new_logic = """
def _normalize_single_content(content_str):
    raw = str(content_str).strip()
    if not raw: return "미기재%"
    if re.search(r'\\d\\s*[a-zA-Z]{1,2}(?!\\d)', raw) and '%' not in raw and not any(k in raw.lower() for k in ["rem", "balance"]):
        return "미기재%"
    v = raw.replace('≤', '<=').replace('≥', '>=').replace('～', '~').replace('-', '~')
    # Use hex for Korean text to avoid encoding issues in script
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(\\xeb\\xaf\\xb8\\xeb\\xa7\\x8c|below|less\\s*than)', r'<\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(\\xec\\x9d\\xb4\\xed\\x95\\x98|up\\s*to)', r'<=\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(\\xec\\xb4\\x88\\xea\\xb3\\xbc|more\\s*than|over)', r'>\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(\\xec\\x9d\\xb4\\xec\\x83\\x81|above|from)', r'>=\\1', v)
    if any(k in v.lower() for k in ["balance", "\\xec\\x9a\\xbc\\xeb\\x9f\\x89", "rem"]): return "Rem.%"
    pm_match = re.search(r'([0-9.]+)\\s*(?:\\xc2\\xb1|\\+\\s*-\\s*|\\+/?-)\\s*([0-9.]+)', v)
    if pm_match:
        try:
            val, pm = float(pm_match.group(1)), float(pm_match.group(2))
            return f"{val-pm:g}~{val+pm:g}%"
        except: pass
    parts = re.split(r'\\s*[~]\\s*', v)
    if len(parts) >= 2:
        p1 = parts[0].strip().replace('%', '')
        p2 = parts[1].strip().replace('%', '')
        try:
            n1 = float(re.sub(r'[^\\d.]', '', p1)) if re.search(r'\\d', p1) else 0
            n2 = float(re.sub(r'[^\\d.]', '', p2)) if re.search(r'\\d', p2) else 0
            if n1 > n2 and n2 != 0: p1, p2 = p2, p1 
            if p1 and p2: return f"{p1}~{p2}%"
            elif p2: return f"{p2}%"
        except: pass
    if len(parts) == 1 or (len(parts) >= 2 and not parts[1]):
        p = parts[0].strip().replace('%', '')
        if re.search(r'\\d', p): return f"{p}%"
    return "미기재%"
"""
    # ... (생략) - 파이썬으로 직접 조작하여 완벽한 파일을 만들겠습니다.
    # 현재 이 도구 안에서 코드를 길게 쓰는 것보다, 
    # 파일을 한 번에 덮어쓰는 것이 더 안전합니다.

if __name__ == "__main__":
    strip_and_rebuild()
