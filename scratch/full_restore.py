import os
import re

def full_restore():
    # 1. 원본 백업 읽기 (실제 로직이 들어있는 파일)
    with open('msds_engine_v5_utf8.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 2. 버전 업데이트
    content = content.replace('VERSION = "15.8.10"', 'VERSION = "17.3.0.5"')

    # 3. 새로운 부등호 보존 로직 삽입
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
    # 기존 _normalize_single_content 함수 교체
    content = re.sub(r'def _normalize_single_content\(raw\):.*?return "미기재%"', new_norm_func, content, flags=re.DOTALL)

    # 4. 출력 로그 스타일 복구 (v17 스타일로)
    content = content.replace('🚀 [V{VERSION} Vision-Only] 분석 시작 ➡️ 담당: {alias}', ' 🚀 [{VERSION}] 엔진 가동: {os.path.basename(pdf_path)}')
    content = content.replace('🏁 [{VERSION}] 완료 (엔진: {used_engine}, 소요시간: {time.time()-start_time:.2f}초)', ' ✅ [{VERSION}] 완료 (엔진: {used_engine}, 소요시간: {time.time()-start_time:.2f}초)')

    # 5. 인코딩 깨짐 방지를 위한 이모지 치환 (SyntaxError 방어)
    content = content.replace('🚨', '[ALERT]').replace('🔴', '[RED]').replace('🔄', '[REFRESH]')
    content = content.replace('🎯', '[TARGET]').replace('❌', '[FAIL]').replace('✅', '[PASS]')
    content = content.replace('🚀', '[RUN]').replace('🚜', '[RECOVER]').replace('🔥', '[FIRE]')
    content = content.replace('🔍', '[SEARCH]').replace('🟡', '[YELLOW]').replace('🟢', '[GREEN]')
    content = content.replace('⚠️', '[WARN]').replace('💡', '[IDEA]')
    # 추가로 문제될 수 있는 화살표 등 제거
    content = content.replace('➡️', '->').replace('🏁', '[FINISH]').replace('🎯', '[TARGET]')

    # 6. 최종 파일 저장
    with open('msds_engine_v5.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Full restoration to V17.3.0.5 completed.")

if __name__ == "__main__":
    full_restore()
