# Version: v4.0_Zero-Touch (2026-03-23)
# 개선 내용:
# 1. [REQ-02] 100% 초과 수치 및 단위 미기재 대형 숫자 즉시 기각 로직 (Value Guard)
# 2. [Task 1] 목차 패턴(가., 1., 1.1) 및 구분선 감지 강화 (is_garbage)

import re
import unicodedata

def clean_content_text(text: str) -> str:
    """
    한글 혼용 범위어 조건을 표준 물결 기호 형태로 세척합니다.
    [Fuzzy 보강] OCR 스캔 본 깨짐 현상('미맊', '미밖', '밎안', '이핚' 등) 강제 평탄화 가드 가동
    """
    if not text:
        return ""
    
    # 1. 스캔 가루/오타 단어 원천 정류 세척 세트 격발
    text = re.sub(r'미\s*[만맊밖먄내발방안]|밎안|미밖', '미만', text)
    text = re.sub(r'이\s*[하핚내]', '이하', text)
    text = re.sub(r'이\s*[상상ㅇ]', '이상', text)
    
    # 연속된 개행 및 공백 평탄화
    text = re.sub(r'\s+', ' ', text)
    
    # 유럽식/복합 부등호 범위 세척 (예: >= 35 - < 40 % -> 35~<40%)
    pattern_complex = r'>=\s*(\d+(?:\.\d+)?)\s*-\s*<\s*(\d+(?:\.\d+)?)\s*%?'
    text = re.sub(pattern_complex, r'\1~<\2%', text)
    
    pattern_complex2 = r'>=\s*(\d+(?:\.\d+)?)\s*-\s*<=\s*(\d+(?:\.\d+)?)\s*%?'
    text = re.sub(pattern_complex2, r'\1~\2%', text)
    
    # 공백 포함 하이픈 범위 세척 (예: 35 - 40 % -> 35~40%)
    pattern_hyphen = r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*%?'
    text = re.sub(pattern_hyphen, r'\1~\2%', text)
    
    # 🛡️ [역방향 범위 표기어 정류] 1-0%, 1~0% 등 큰 숫자가 앞에 오는 역방향 수치를 사전에 평탄화
    pattern_descending = r'(\d+(?:\.\d+)?)\s*[-~∼～\u2013\u2014]\s*(\d+(?:\.\d+)?)\s*(%?)'
    def fix_descending(m):
        n1_str, n2_str, pct = m.group(1), m.group(2), m.group(3) or ""
        try:
            n1, n2 = float(n1_str), float(n2_str)
            if n1 > n2:
                return f"{n2_str}~{n1_str}{pct}"
        except ValueError:
            pass
        return m.group(0)
    text = re.sub(pattern_descending, fix_descending, text)
    
    # 한글 혼용 범위어 매칭 규칙 적용: 이상 ~ 미만 형태를 물결과 백분율로 평탄화 (미만 무조건 보존)
    pattern = r'(\d+(?:\.\d+)?)\s*이상\s*~\s*(\d+(?:\.\d+)?)\s*%?\s*미만'
    def replace_match(match):
        v1 = match.group(1)
        v2 = match.group(2)
        return f"{v1}~<{v2}%"
    text = re.sub(pattern, replace_match, text)
    return text.strip()

def is_valid_cas(cas):
    """CAS 번호 체크디지트 검증 (유효성 99% 보장)"""
    if not cas or not isinstance(cas, str): return False
    clean_cas = cas.strip()
    if not re.match(r'^\d{2,7}-\d{2}-\d$', clean_cas): return False
    
    try:
        main_part = clean_cas[:-2].replace('-', '')
        reverse_digits = main_part[::-1]
        checksum = sum((i + 1) * int(d) for i, d in enumerate(reverse_digits))
        return (checksum % 10) == int(clean_cas[-1])
    except: return False

def is_garbage(text):
    """
    [Task 1] 목차 헤더 및 쓰레기 텍스트 판독 (정규식 오류 수정 완료)
    """
    if not text or len(text.strip()) < 2: return True
    t = text.strip()
    
    # [수정됨] 런타임 에러를 유발하던 '가-하나-힣' 오타를 '가-힣'으로 정상화
    if re.match(r'^[가-힣a-zA-Z\d\.]+\s*[.)]', t):
        if any(kw in t for kw in ["용도", "제한", "정보", "분류", "성분", "명칭", "Identification", "Section"]):
            return True
            
    if re.search(r'\.{4,}|-{4,}', t): return True # 구분선
    if re.search(r'\d{2,3}-\d{3,4}-\d{4}', t): return True # 연락처
    return False

def format_content(content, log_callback=None):
    if not content: return "함유량미기재"
    # 한글 혼용 범위어 평탄화 적용
    content = clean_content_text(str(content))
    content_str = str(content).lower()
    
    # [수정] 영문 GHS 유해성 코드 추가 방어
    block_keywords = [
        "g/몰", "g/mol", "분자량", "molecular", "m.w", 
        "구분", "category", "독성", "자극성", "수생", "과민성", "h3", "h4",
        "corr", "irrit", "dam", "tox", "sens", "aquatic", "eye", "skin", "flam"
    ]
    if any(kw in content_str for kw in block_keywords):
        if log_callback: log_callback(f"   └─ ⚠️ [Value Guard] 오탐지 키워드 감지 -> 기각: '{content}'")
        return "함유량미기재"

    if any(re.search(p, str(content), re.I) for p in [r'영업비밀', r'Secret', r'Confidential']): 
        return "Trade Secret"

    nums = re.findall(r'\d+(?:\.\d+)?', str(content))
    if not nums: return "함유량미기재"

    valid_nums = [n for n in nums if float(n) <= 100.0]
    if not valid_nums: 
        if log_callback: log_callback(f"   └─ ⚠️ [Value Guard] 100 초과 비정상 수치 감지 -> 기각: '{content}'")
        return "함유량미기재"

    suffix = "%" if "%" in str(content) else ""
    
    if len(valid_nums) >= 2:
        v1, v2 = float(valid_nums[0]), float(valid_nums[1])
        if v1 > v2: v1, v2 = v2, v1
        v1_str = int(v1) if v1.is_integer() else v1
        v2_str = int(v2) if v2.is_integer() else v2
        
        v2_prefix = ""
        if any(c in content_str for c in ["<", "미만", "below", "less"]):
            v2_prefix = "<"
        return f"{v1_str}~{v2_prefix}{v2_str}{suffix}"
    
    # 수학 기호(≤, ≥) 완벽 인식 (공백 제거)
    # 수학 기호(≤, ≥) 및 키워드 정밀 인식
    if any(c in content_str for c in ["<", "미만", "below"]): prefix = "<"
    elif any(c in content_str for c in ["≤", "=<", "이하", "이내", "upto"]): prefix = "≤"
    elif any(c in content_str for c in [">", "초과", "over"]): prefix = ">"
    elif any(c in content_str for c in ["≥", "=>", "이상", "above"]): prefix = "≥"
    else: prefix = ""
    v1 = float(valid_nums[0])
    v1_str = int(v1) if v1.is_integer() else v1
    return f"{prefix}{v1_str}{suffix}"

def clean_candidate(text):
    if not text: return ""
    text = unicodedata.normalize('NFKC', text)
    # [V4.1] '용도', '사용' 등 불필요한 레이블 노이즈 정밀 제거 추가
    prefixes = [
        r'^제품\s*명\s*[:：]\s*', r'^물질\s*명\s*[:：]\s*', r'^상호명\s*[:：]\s*',
        r'^품명\s*[:：]\s*', r'^용도\s*[:：]\s*', r'^사용\s*[:：]\s*'
    ]
    for p in prefixes: text = re.sub(p, '', text, flags=re.I)
    # 선두의 특수기호 및 공백 제거
    text = re.sub(r'^[ \t:：·\-\.\s\(\)>【】\[\]]+', '', text)
    return text.strip()

def normalize_text(text):
    """[V4.1] 유니코드 정규화 및 중점(·) 등 노이즈 문자 치환"""
    if not text: return ""
    try:
        # 1. NFKC 정규화 (전각 -> 반각, 유사 기호 통합)
        t = unicodedata.normalize("NFKC", text)
        
        # 2. 인코딩 깨짐으로 오해받는 특수 중점 및 노이즈 치환
        replacements = {
            "∼": "~", "～": "~", "％": "%", "－": "-", "：": ":",
            "·": " ", "・": " ", "•": " ", "": " " # 불렛 및 중점을 공백으로 치환
        }
        for src, dst in replacements.items(): 
            t = t.replace(src, dst)
            
        return t.strip()
    except Exception: return text

def clean_percentage(content_str):
    """🛡️ [데이터 검증 및 예외 처리] 1~0% 와 같은 역방향 범위어 노이즈 발견 즉시 0~1% 오름차순 평탄화 정류 및 포맷 수선"""
    if not content_str:
        return "미기재%"
    
    # 1. 한글 혼용 범위어 오타 정류 및 유니코드 정규화
    raw = clean_content_text(str(content_str))
    raw = unicodedata.normalize('NFKC', raw).strip()
    
    # 2. [고정 가드선] 상류 정제 고정 단어 원형 보존
    if raw in ["Rem.", "미기재"]:
        return raw
        
    content_lower = raw.lower()
    nums = re.findall(r'\d+(?:\.\d+)?', raw)
    if not nums:
        return raw if "%" in raw else f"{raw}%"
    
    # 3. 정형화된 포맷 조인을 위한 백업
    suffix = "%"
    
    # 4. 수치 2개 이상일 경우 (범위어 역방향 평탄화 스왑 정류)
    if len(nums) >= 2:
        try:
            v1, v2 = float(nums[0]), float(nums[1])
            # 앞 숫자가 뒷 숫자보다 크면 논리적 모순이므로 오름차순 스왑(Swap) 집도
            if v1 > v2:
                v1, v2 = v2, v1
            
            v1_str = int(v1) if v1.is_integer() else v1
            v2_str = int(v2) if v2.is_integer() else v2
            
            v2_prefix = ""
            if any(c in content_lower for c in ["<", "미만", "below", "less"]):
                v2_prefix = "<"
            elif any(c in content_lower for c in ["≤", "=<", "이하", "이내", "upto"]):
                v2_prefix = "≤"
                
            return f"{v1_str}~{v2_prefix}{v2_str}{suffix}"
        except Exception:
            pass
            
    # 5. 수치 1개일 경우 (단일 부등호 및 포맷 정류)
    prefix = ""
    if any(c in content_lower for c in ["<", "미만", "below"]): prefix = "<"
    elif any(c in content_lower for c in ["≤", "=<", "이하", "이내", "upto"]): prefix = "≤"
    elif any(c in content_lower for c in [">", "초과", "over"]): prefix = ">"
    elif any(c in content_lower for c in ["≥", "=>", "이상", "above"]): prefix = "≥"
    
    try:
        v1 = float(nums[0])
        v1_str = int(v1) if v1.is_integer() else v1
        return f"{prefix}{v1_str}{suffix}"
    except Exception:
        return raw


# ==============================================================================
# 🛠️ [Chunk 22] msds_utils.py ➔ 코어 유틸리티: 함량 데이터 보존 로직 추가
# ==============================================================================
def clean_text_for_msds(text, mode="standard"):
    """
    모드 전환형 정제 로직: 
    mode="standard" -> 기존대로 기호 삭제
    mode="concentration" -> 일본식 부동호(>, <, =) 보존
    """
    if mode == "concentration":
        # 수치, %, 그리고 부동호만 남기고 나머지만 제거
        return re.sub(r'[^0-9\.\s%><=≧≦]', '', text)
    
    # 기존 standard 모드 (기존 정제 방식 유지)
    return re.sub(r'[^\w\s]', '', text)
# ==============================================================================

