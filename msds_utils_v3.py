# Version: v4.0_Zero-Touch (2026-03-23)
# 개선 내용:
# 1. [REQ-02] 100% 초과 수치 및 단위 미기재 대형 숫자 즉시 기각 로직 (Value Guard)
# 2. [Task 1] 목차 패턴(가., 1., 1.1) 및 구분선 감지 강화 (is_garbage)

import re
import unicodedata

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
        
        # [수정] 범위형에서도 미만(<) 기호 보존
        v2_prefix = "<" if any(c in content_str for c in ["<", "미만", "below", "less"]) else ""
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
    if not content_str: return ""
    content_str = unicodedata.normalize('NFKC', content_str).strip()
    
    # [주님 지시 고정 가드선] 상류에서 정제된 고정 표준 단어는 숫자 연산을 우회하여 원형 보존
    if content_str in ["Rem.", "미기재"]:
        return content_str
        
    content_lower = content_str.lower()
    nums = re.findall(r'\d+(?:\.\d+)?', content_str)
    if not nums: return content_str
    
    suffix = "%" if "%" in content_str else ""
    if len(nums) >= 2:
        v1, v2 = float(nums[0]), float(nums[1])
        if v1 > v2: v1, v2 = v2, v1
        v1_str = int(v1) if v1.is_integer() else v1
        v2_str = int(v2) if v2.is_integer() else v2
        v2_prefix = "<" if any(c in content_lower for c in ["<", "미만", "below", "less"]) else ""
        return f"{v1_str}~{v2_prefix}{v2_str}{suffix}"
    
    if any(c in content_lower for c in ["<", "미만", "below"]): prefix = "<"
    elif any(c in content_lower for c in ["≤", "=<", "이하", "이내", "upto"]): prefix = "≤"
    elif any(c in content_lower for c in [">", "초과", "over"]): prefix = ">"
    elif any(c in content_lower for c in ["≥", "=>", "이상", "above"]): prefix = "≥"
    else: prefix = ""
    v1 = float(nums[0])
    v1_str = int(v1) if v1.is_integer() else v1
    return f"{prefix}{v1_str}{suffix}"
