import os
import re

def final_rebuild():
    # 1. 원본 백업 읽기
    with open('msds_engine_v5_utf8.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    skip = False
    
    # 버전 정보
    target_version = 'VERSION = "17.3.0.5"\n'
    
    # 삽입할 새로운 함수
    new_func = """
def _normalize_single_content(content_str):
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

    for line in lines:
        # 버전 교체
        if line.startswith('VERSION ='):
            new_lines.append(target_version)
            continue
            
        # 함수 교체 시작
        if 'def _normalize_single_content' in line:
            new_lines.append(new_func)
            skip = True
            continue
        
        # 다음 함수 시작점 찾기
        if skip:
            if line.startswith('def final_quality_control'):
                skip = False
                new_lines.append("\n" + line)
            continue
            
        if not skip:
            # 이모지 제거 (SyntaxError 방지)
            sanitized_line = line.replace('🚨', '[ALERT]').replace('🔴', '[RED]').replace('🔄', '[REFRESH]')\
                                 .replace('🎯', '[TARGET]').replace('❌', '[FAIL]').replace('✅', '[PASS]')\
                                 .replace('🚀', '[RUN]').replace('🚜', '[RECOVER]').replace('🔥', '[FIRE]')\
                                 .replace('🔍', '[SEARCH]').replace('🟡', '[YELLOW]').replace('🟢', '[GREEN]')\
                                 .replace('⚠️', '[WARN]').replace('💡', '[IDEA]')
            new_lines.append(sanitized_line)

    # 2. 파일 쓰기 (BOM 없이 UTF-8)
    with open('msds_engine_v5.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print("Rebuild completed successfully.")

if __name__ == "__main__":
    final_rebuild()
