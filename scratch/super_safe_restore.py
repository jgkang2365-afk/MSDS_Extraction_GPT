import os
import re

def super_safe_restore():
    with open('msds_engine_v5_utf8.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 모든 한글 주석 제거 (비-ASCII 문자 포함된 # 줄 제거)
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if '#' in line:
            # 주석 부분만 떼어내서 한글이 있는지 확인
            parts = line.split('#', 1)
            if any(ord(c) > 127 for c in parts[1]):
                new_lines.append(parts[0]) # 주석 제거
                continue
        new_lines.append(line)
    content = '\n'.join(new_lines)

    # 2. 문자열 내의 한글을 유니코드 에스케이프로 변환
    def to_unicode_escape(match):
        s = match.group(0)
        return s.encode('unicode_escape').decode('ascii')
    
    # 따옴표로 둘러싸인 문자열 내의 한글만 변환
    content = re.sub(r'("[^"]*"|\'[^\']*\')', to_unicode_escape, content)

    # 3. 버전 및 로직 교체 (이전과 동일)
    content = content.replace('VERSION = "15.8.10"', 'VERSION = "17.3.0.5"')
    
    # 새로운 정규화 로직 삽입 (이미 영어 주석으로 되어 있음)
    new_norm_func = """def _normalize_single_content(content_str):
    raw = str(content_str).strip()
    if not raw: return "미기재%"
    if re.search(r'\\\\d\\\\s*[a-zA-Z]{1,2}(?!\\\\d)', raw) and '%' not in raw and not any(k in raw.lower() for k in ["rem", "balance"]):
        return "미기재%"
    v = raw.replace('\\u2264', '<=').replace('\\u2265', '>=').replace('\\uff5e', '~').replace('-', '~')
    v = re.sub(r'(?i)([0-9.]+)\\\\s*%?\\\\s*(\\xeb\\xaf\\xb8\\xeb\\xa7\\x8c|below|less\\\\s*than)', r'<\\\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\\\s*%?\\\\s*(\\xec\\x9d\\xb4\\xed\\x95\\x98|up\\\\s*to)', r'<=\\\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\\\s*%?\\\\s*(\\xec\\xb4\\x88\\xea\\xb3\\xbc|more\\\\s*than|over)', r'>\\\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\\\s*%?\\\\s*(\\xec\\x9d\\xb4\\xec\\x83\\x81|above|from)', r'>=\\\\1', v)
    if any(k in v.lower() for k in ["balance", "rem"]): return "Rem.%"
    pm_match = re.search(r'([0-9.]+)\\\\s*(?:\\u00b1|\\\\+\\\\s*-\\\\s*|\\\\+/?-)\\\\s*([0-9.]+)', v)
    if pm_match:
        try:
            val, pm = float(pm_match.group(1)), float(pm_match.group(2))
            return f"{val-pm:g}~{val+pm:g}%"
        except: pass
    parts = re.split(r'\\\\s*[~]\\\\s*', v)
    if len(parts) >= 2:
        p1 = parts[0].strip().replace('%', '')
        p2 = parts[1].strip().replace('%', '')
        try:
            n1 = float(re.sub(r'[^\\\\d.]', '', p1)) if re.search(r'\\\\d', p1) else 0
            n2 = float(re.sub(r'[^\\\\d.]', '', p2)) if re.search(r'\\\\d', p2) else 0
            if n1 > n2 and n2 != 0: p1, p2 = p2, p1 
            if p1 and p2: return f"{p1}~{p2}%"
            elif p2: return f"{p2}%"
        except: pass
    if len(parts) == 1 or (len(parts) >= 2 and not parts[1]):
        p = parts[0].strip().replace('%', '')
        if re.search(r'\\\\d', p): return f"{p}%"
    return "미기재%"

"""
    start_marker = 'def _normalize_single_content(raw):'
    end_marker = 'def final_quality_control'
    s_idx = content.find(start_marker)
    e_idx = content.find(end_marker)
    if s_idx != -1 and e_idx != -1:
        content = content[:s_idx] + new_norm_func + content[e_idx:]

    # 4. 저장 (BOM 없는 UTF-8)
    with open('msds_engine_v5.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Super safe restoration completed. No more encoding issues.")

if __name__ == "__main__":
    super_safe_restore()
