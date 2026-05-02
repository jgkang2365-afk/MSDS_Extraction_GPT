import os
import re

def final_perfect_restore():
    # 1. 원본 백업 읽기
    with open('msds_engine_v5_utf8.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 2. 버전 업데이트
    content = content.replace('VERSION = "15.8.10"', 'VERSION = "17.3.0.5"')

    # 3. 새로운 정규화 로직 (부등호 보존형 V17.3.0.5)
    new_norm_func = """
def _normalize_single_content(content_str):
    \"\"\"[V17.3.0.5] 농도 범위 및 부등호(<, <=, 미만 등) 완벽 보존형 정규화\"\"\"
    raw = str(content_str).strip()
    if not raw: return "미기재%"

    # [V17.3.0.4] 단위(g, mg 등)가 포함된 수치는 함량 제외
    if re.search(r'\\d\\s*[a-zA-Z]{1,2}(?!\\d)', raw) and '%' not in raw and not any(k in raw.lower() for k in ["rem", "balance"]):
        return "미기재%"

    # 1. 전처리: 표준화 (원본 기호 최대한 보전)
    v = raw.replace('≤', '<=').replace('≥', '>=').replace('～', '~').replace('-', '~')
    # 텍스트 부등호를 기호로 변환 (엔진 가독성용)
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(미만|below|less\\s*than)', r'<\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(이하|up\\s*to)', r'<=\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(초과|more\\s*than|over)', r'>\\1', v)
    v = re.sub(r'(?i)([0-9.]+)\\s*%?\\s*(이상|above|from)', r'>=\\1', v)
    
    # 2. 특별 키워드 처리
    if any(k in v.lower() for k in ["balance", "잔량", "rem"]): return "Rem.%"
    
    # 3. 오차 범위 처리 (±)
    pm_match = re.search(r'([0-9.]+)\\s*(?:±|\\+\\s*-\\s*|\\+/?-)\\s*([0-9.]+)', v)
    if pm_match:
        try:
            val, pm = float(pm_match.group(1)), float(pm_match.group(2))
            return f"{val-pm:g}~{val+pm:g}%"
        except: pass

    # 4. 범위 및 부등호 보존 조립
    parts = re.split(r'\\s*[~]\\s*', v)
    if len(parts) >= 2:
        p1 = parts[0].strip().replace('%', '')
        p2 = parts[1].strip().replace('%', '')
        try:
            # 정렬을 위한 숫자 추출
            n1 = float(re.sub(r'[^\\d.]', '', p1)) if re.search(r'\\d', p1) else 0
            n2 = float(re.sub(r'[^\\d.]', '', p2)) if re.search(r'\\d', p2) else 0
            if n1 > n2 and n2 != 0: p1, p2 = p2, p1 
            
            if p1 and p2: return f"{p1}~{p2}%"
            elif p2: return f"{p2}%"
        except: pass

    # 5. 단일 값
    if len(parts) == 1 or (len(parts) >= 2 and not parts[1]):
        p = parts[0].strip().replace('%', '')
        if re.search(r'\\d', p):
            return f"{p}%"

    return "미기재%"
"""
    # 기존 함수 교체 (정규표현식 대신 안전하게 문자열 검색으로)
    start_marker = 'def _normalize_single_content(raw):'
    end_marker = 'def final_quality_control'
    s_idx = content.find(start_marker)
    e_idx = content.find(end_marker)
    if s_idx != -1 and e_idx != -1:
        content = content[:s_idx] + new_norm_func + "\n" + content[e_idx:]

    # 4. 자가 테스트 케이스 보강
    test_rebuild = """
def self_test_regression():
    print(f"--- [V{VERSION}] 엔진 자가 검증 시작 ---")
    test_cases = [
        ("0.1~1미만", "0.1~<1%", "미만 보존 실패"),
        ("0.1 - <1", "0.1~<1%", "하이픈 부등호 조합 실패"),
        ("5 ~ 1", "1~5%", "오름차순 정렬 실패"),
        ("<0.1", "<0.1%", "단일 부등호 보존 실패")
    ]
    fail_count = 0
    for i, e, m in test_cases:
        a = _normalize_single_content(i)
        if a != e:
            print(f" [FAIL] {i} -> {a} (Expected: {e}) | {m}")
            fail_count += 1
        else:
            print(f" [PASS] {i} -> {a}")
    
    if fail_count > 0: sys.exit(1)
    print(f"--- [OK] 모든 자가 테스트 통과 ---")

if __name__ == "__main__":
    self_test_regression()
"""
    # 파일 끝부분의 self_test_regression 교체
    st_idx = content.find('def self_test_regression():')
    if st_idx != -1:
        content = content[:st_idx] + test_rebuild

    # 5. 인코딩 오류 방지 (이모지 및 특수문자 제거)
    content = content.replace('🚨', '[ALERT]').replace('🔴', '[RED]').replace('🔄', '[REFRESH]')
    content = content.replace('🎯', '[TARGET]').replace('❌', '[FAIL]').replace('✅', '[PASS]')
    content = content.replace('🚀', '[RUN]').replace('🚜', '[RECOVER]').replace('🔥', '[FIRE]')
    content = content.replace('🔍', '[SEARCH]').replace('🟡', '[YELLOW]').replace('🟢', '[GREEN]')
    content = content.replace('⚠️', '[WARN]').replace('💡', '[IDEA]').replace('🏁', '[FINISH]').replace('➡️', '->')
    content = content.replace('├─', ' |--').replace('━━━━━━━━━', '---------')

    # 6. 최종 저장
    with open('msds_engine_v5.py', 'w', encoding='utf-8') as f:
        f.write(content)

    print("Engine perfectly restored and updated to V17.3.0.5.")

if __name__ == "__main__":
    final_perfect_restore()
