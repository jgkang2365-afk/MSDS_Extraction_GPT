import os

def patch_logic():
    # 1. 원본 백업에서 깨끗한 소스 가져오기
    with open('msds_engine_v5_utf8.py', 'rb') as f:
        content = f.read().decode('utf-8')

    # 2. 버전 업데이트
    content = content.replace('VERSION = "15.8.10"', 'VERSION = "17.3.0.5"')

    # 3. _normalize_single_content 함수 교체
    # V15.8.9 로직의 시작과 끝을 찾아 교체
    old_func_start = 'def _normalize_single_content(raw):'
    # 다음 함수 시작점인 'def final_quality_control' 까지 찾기
    next_func_start = 'def final_quality_control'
    
    new_func = """def _normalize_single_content(content_str):
    \"\"\"[V17.3.0.5] 농도 범위 및 부등호(<, <=, 미만 등) 완벽 보존형 정규화\"\"\"
    raw = str(content_str).strip()
    if not raw: return "미기재%"
    if re.search(r'\\d\\s*[a-zA-Z]{1,2}(?!\\d)', raw) and '%' not in raw and not any(k in raw.lower() for k in ["rem", "balance"]):
        return "미기재%"
    v = raw.replace('≤', '<=').replace('≥', '>=').replace('～', '~').replace('-', '~')
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(미만|below|less\\s*than)', r'<\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(이하|up\\s*to)', r'<=\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(초과|more\\s*than|over)', r'>\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(이상|above|from)', r'>=\\1', v)
    if any(k in v.lower() for k in ["balance", "잔량", "rem"]): return "Rem.%"
    pm_match = re.search(r'([0-9.]+)\\s*(?:±|\\+\\s*-\\s*|\\+/?-)\\s*([0-9.]+)', v)
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
    
    start_idx = content.find(old_func_start)
    end_idx = content.find(next_func_start)
    
    if start_idx != -1 and end_idx != -1:
        new_content = content[:start_idx] + new_func + content[end_idx:]
        
        # 4. SyntaxError 유발하는 이모지 및 깨진 문자 제거
        # 특히 프롬프트 내의 특수문자들
        new_content = new_content.replace('🚨', '[ALERT]').replace('🔴', '[RED]').replace('🔄', '[REFRESH]')
        new_content = new_content.replace('🎯', '[TARGET]').replace('❌', '[FAIL]').replace('✅', '[PASS]')
        new_content = new_content.replace('🚀', '[RUN]').replace('🚜', '[RECOVER]').replace('🔥', '[FIRE]')
        new_content = new_content.replace('🔍', '[SEARCH]').replace('🟡', '[YELLOW]').replace('🟢', '[GREEN]')
        new_content = new_content.replace('⚠️', '[WARN]').replace('💡', '[IDEA]')
        
        # 5. 저장 (UTF-8 with BOM for Windows friendliness)
        with open('msds_engine_v5.py', 'w', encoding='utf-8-sig') as f:
            f.write(new_content)
        print("Successfully patched and sanitized msds_engine_v5.py")
    else:
        print("Failed to find function markers.")

if __name__ == "__main__":
    patch_logic()
