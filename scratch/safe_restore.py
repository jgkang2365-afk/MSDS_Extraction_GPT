import os

def safe_restore():
    # 1. 원본 백업 읽기
    with open('msds_engine_v5_utf8.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 2. 버전 업데이트
    content = content.replace('VERSION = "15.8.10"', 'VERSION = "17.3.0.5"')

    # 3. 새로운 부등호 보존 로직 (함수 통째로 교체)
    # 기존 함수 찾기
    old_func_start = 'def _normalize_single_content(raw):'
    old_func_end = '    return "미기재%"'
    
    start_idx = content.find(old_func_start)
    # old_func_end는 여러 개일 수 있으므로 start_idx 이후 가장 가까운 곳을 찾음
    # 하지만 V15.8.10 코드를 보면 return "미기재%" 가 함수의 마지막 줄임
    # final_quality_control 함수 바로 앞까지를 범위로 잡는 것이 안전함
    end_marker = 'def final_quality_control'
    end_idx = content.find(end_marker)

    if start_idx != -1 and end_idx != -1:
        new_norm_func = """def _normalize_single_content(content_str):
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
        content = content[:start_idx] + new_norm_func + content[end_idx:]

    # 4. 로그 스타일 복구
    content = content.replace('🚀 [V{VERSION} Vision-Only] 분석 시작 ➡️ 담당: {alias}', ' 🚀 [{VERSION}] 엔진 가동: {os.path.basename(pdf_path)}')
    content = content.replace('🏁 [{VERSION}] 완료 (엔진: {used_engine}, 소요시간: {time.time()-start_time:.2f}초)', ' ✅ [{VERSION}] 완료 (엔진: {used_engine}, 소요시간: {time.time()-start_time:.2f}초)')

    # 5. 이모지 치환 (SyntaxError 방지)
    content = content.replace('🚨', '[ALERT]').replace('🔴', '[RED]').replace('🔄', '[REFRESH]')
    content = content.replace('🎯', '[TARGET]').replace('❌', '[FAIL]').replace('✅', '[PASS]')
    content = content.replace('🚀', '[RUN]').replace('🚜', '[RECOVER]').replace('🔥', '[FIRE]')
    content = content.replace('🔍', '[SEARCH]').replace('🟡', '[YELLOW]').replace('🟢', '[GREEN]')
    content = content.replace('⚠️', '[WARN]').replace('💡', '[IDEA]').replace('🏁', '[FINISH]').replace('➡️', '->')

    # 6. 저장
    with open('msds_engine_v5.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Engine fully restored and upgraded to V17.3.0.5 successfully.")

if __name__ == "__main__":
    safe_restore()
