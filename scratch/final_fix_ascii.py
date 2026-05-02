import os
import re

def final_fix_ascii_only():
    with open('msds_engine_v5_utf8.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 모든 한글 주석 및 문자열을 안전하게 처리
    # 한글 주석 제거
    content = re.sub(r'#.*[가-힣].*', '', content)
    
    # 2. 부등호 및 버전 업데이트
    content = content.replace('VERSION = "15.8.10"', 'VERSION = "17.3.0.5"')
    
    # 3. 새로운 로직 삽입 (영어로 작성된 로직)
    new_norm_func = """
def _normalize_single_content(content_str):
    raw = str(content_str).strip()
    if not raw: return "None%"
    if re.search(r'\\\\d\\\\s*[a-zA-Z]{1,2}(?!\\\\d)', raw) and '%' not in raw:
        return "None%"
    v = raw.replace('\\u2264', '<=').replace('\\u2265', '>=').replace('\\uff5e', '~').replace('-', '~')
    # Use hex/unicode for Korean keywords in internal logic if needed
    if any(k in v.lower() for k in ["balance", "rem"]): return "Rem.%"
    pm_match = re.search(r'([0-9.]+)\\\\s*(?:\\\\u00b1|\\\\+\\\\s*-\\\\s*|\\\\+/?-)\\\\s*([0-9.]+)', v)
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
    return "None%"
"""
    start_marker = 'def _normalize_single_content(raw):'
    end_marker = 'def final_quality_control'
    s_idx = content.find(start_marker)
    e_idx = content.find(end_marker)
    if s_idx != -1 and e_idx != -1:
        content = content[:s_idx] + new_norm_func + "\n" + content[e_idx:]

    # 4. 프롬프트 등 한글 문자열을 유니코드 에스케이프로 변환 (중요!)
    def to_unicode_escape(match):
        s = match.group(0)
        try:
            return s.encode('ascii', 'get_unicode_escape').decode('ascii')
        except:
            # 수동 변환
            res = ""
            for char in s:
                if ord(char) > 127:
                    res += f"\\\\u{ord(char):04x}"
                else:
                    res += char
            return res
            
    # 문자열 내부 한글 변환
    content = re.sub(r'("[^"]*"|\'[^\']*\')', to_unicode_escape, content)

    # 5. 이모지 등 잔여 특수문자 제거
    content = content.replace('\\U0001f6a8', '[ALERT]').replace('\\U0001f534', '[RED]')
    
    # 6. 저장
    with open('msds_engine_v5.py', 'w', encoding='ascii') as f:
        f.write(content)
    
    print("Final Fix (ASCII Only) applied.")

if __name__ == "__main__":
    final_fix_ascii_only()
