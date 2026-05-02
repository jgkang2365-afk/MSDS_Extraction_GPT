import sys
import re
import os

def _normalize_single_content(content_str):
    """[V17.3.0.5] 농도 범위 및 부등호(<, ≤, 미만 등) 완벽 보존형 정규화"""
    raw = str(content_str).strip()
    if not raw: return "미기재%"

    # [V17.3.0.4] 단위(g, mg 등)가 포함된 수치는 함량 제외
    if re.search(r'\d\s*[a-zA-Z]{1,2}(?!\d)', raw) and '%' not in raw and not any(k in raw.lower() for k in ["rem", "balance"]):
        return "미기재%"

    # 1. 전처리: 표준화 (원본 기호 최대한 보전)
    v = raw.replace('≤', '<=').replace('≥', '>=').replace('～', '~').replace('-', '~')
    # 텍스트 부등호를 기호로 변환 (엔진 가독성용)
    v = re.sub(r'(?i)([0-9.]+)\s*%?\s*(미만|below|less\s*than)', r'<\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*%?\s*(이하|up\s*to)', r'<=\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*%?\s*(초과|more\s*than|over)', r'>\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*%?\s*(이상|above|from)', r'>=\1', v)
    
    # 2. 특별 키워드 처리
    if any(k in v.lower() for k in ["balance", "잔량", "rem"]): return "Rem.%"
    
    # 3. 오차 범위 처리 (±)
    pm_match = re.search(r'([0-9.]+)\s*(?:±|\+\s*-\s*|\+/?-)\s*([0-9.]+)', v)
    if pm_match:
        try:
            val, pm = float(pm_match.group(1)), float(pm_match.group(2))
            return f"{val-pm:g}~{val+pm:g}%"
        except: pass

    # 4. 범위 및 부등호 보존 조립
    parts = re.split(r'\s*[~]\s*', v)
    if len(parts) >= 2:
        p1 = parts[0].strip().replace('%', '')
        p2 = parts[1].strip().replace('%', '')
        try:
            # 정렬을 위한 숫자 추출
            n1 = float(re.sub(r'[^\d.]', '', p1)) if re.search(r'\d', p1) else 0
            n2 = float(re.sub(r'[^\d.]', '', p2)) if re.search(r'\d', p2) else 0
            if n1 > n2 and n2 != 0: p1, p2 = p2, p1 
            
            if p1 and p2: return f"{p1}~{p2}%"
            elif p2: return f"{p2}%"
        except: pass

    # 5. 단일 값
    if len(parts) == 1 or (len(parts) >= 2 and not parts[1]):
        p = parts[0].strip().replace('%', '')
        if re.search(r'\d', p):
            return f"{p}%"

    return "미기재%"

def patch_engine(target_file):
    with open(target_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    skip = False
    
    # _normalize_single_content 함수 시작점 찾기 (219라인 근처)
    for i, line in enumerate(lines):
        if 'def _normalize_single_content' in line:
            # 새로운 함수 정의 추가
            import inspect
            func_source = inspect.getsource(_normalize_single_content)
            new_lines.append(func_source + "\n")
            skip = True
            continue
        
        # 함수가 끝나는 지점 (다음 함수 시작) 까지 스킵
        if skip:
            if line.startswith('def ') or line.startswith('class '):
                skip = False
            else:
                continue
        
        if not skip:
            new_lines.append(line)

    with open(target_file, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"Patched {target_file} successfully.")

if __name__ == "__main__":
    patch_engine('msds_engine_v5_utf8_temp.py')
