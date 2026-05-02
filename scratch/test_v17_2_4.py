import re

def _normalize_single_content(content_str):
    """[V17.2.4.1] 마이너스 수치 오류 해결 및 키워드(미만/이하) 완벽 보존 (버그 수정판)"""
    orig_raw = str(content_str).strip()
    
    # 1. 기초 정제: 일본식 역순 부등호 및 잔량 표기 통일
    v = re.sub(r'([\d\.]+)\s*(<)', r'>\1', orig_raw)
    v = re.sub(r'([\d\.]+)\s*(>)', r'<\1', v)
    v = re.sub(r'(?i)잔량|balance|remainder|残량|나머지', 'Rem.', v)
    
    # 2. 한글/영문 키워드를 기호로 선치환 (누락 방지)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(미만|below|less\s*than|未満)', r'<\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(이하|up\s*to|以下)', r'≤\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(초과|more\s*than|over|超)', r'>\1', v)
    v = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(이상|above|以上)', r'≥\1', v)

    # 3. 불필요한 단위 및 공백 제거
    v = v.replace(" ", "")
    v = re.sub(r'(?i)\(w/w\)|\(v/v\)|\(w/v\)|\(weight/weight\)|proprietary|secret', '', v)
    if re.search(r'(?i)(mg/m3|mg/l|g/l|ppm|kg|ml|µg|ug)', v): return "미기재%"
    v = v.replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')

    # 4. ± 기호 연산 (오름차순 보장) - [패치] 단일 하이픈(-)은 범위로 양보
    pm_match = re.match(r'^([0-9.]+)\s*(?:±|\+\s*-\s*|\+/?-)\s*([0-9.]+)\s*[%]*$', v)
    if pm_match:
        try:
            val, pm = float(pm_match.group(1)), float(pm_match.group(2))
            n1, n2 = sorted([val-pm, val+pm])
            return f"{n1:g}~{n2:g}%"
        except: pass

    # 5. 범위 패턴 (숫자 ~ 숫자) 추출 - [패치] 구분자가 없는 양방향 부등호(≥95≤100) 지원 및 앵커(^) 적용
    range_m = re.match(r'^([<>≤≥]*)\s*(\d*\.?\d+)\s*[%]*\s*([-~∼～/]?)\s*([<>≤≥]*)\s*(\d*\.?\d+)\s*[%]*$', v)
    if range_m:
        p1, n1, sep, p2, n2 = range_m.groups()
        if not sep and not (p1 and p2):
            pass 
        else:
            try:
                if float(n1) > float(n2):
                    n1, n2 = n2, n1
                    p1, p2 = p2, p1
                if p1 and p2:
                    return f"{n1}~{n2}%"
                res = f"{p1}{n1}~{p2}{n2}"
                return res if '%' in res else res + '%'
            except: pass

    # 6. 단일 수치 패턴 (부등호 포함) - [패치] 앵커(^) 적용으로 단위(g) 환각 차단
    single_m = re.match(r'^([<>≤≥]?)\s*(\d*\.?\d+)\s*[%]*$', v)
    if single_m:
        p, n = single_m.groups()
        return f"{p}{n}%"

    if "Rem" in v: return "Rem.%"
    return "미기재%"

# 테스트 데이터
test_cases = [
    "≥95%≤100%", "45 - 50", "8-0%", "0.1 - 1미만", "10±2", "balance", "77.08g"
]

print(f"{'입력값':<20} | {'결과값':<20}")
print("-" * 45)
for tc in test_cases:
    print(f"{tc:<20} | {_normalize_single_content(tc):<20}")
