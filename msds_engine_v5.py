import os
import base64

import sys
import re
import time
from itertools import cycle
import json
import fitz  # [복구 완료] 텍스트 추출의 핵심 엔진 부활!
import unicodedata
import requests
from opendataloader.pdf import PDFParser
import msds_utils_v3
from dotenv import load_dotenv

# .env 파일 로드 (시스템 환경 변수보다 .env 파일 우선 적용)
load_dotenv(override=True)

# [필수 세팅] API 키 (시스템 변수 충돌 방지를 위해 전용 변수명 사용)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- V15.8.1 API 무한 탄창 로직 (전담 마크 시스템) ---
api_keys_raw = [
    os.getenv("MSDS_GOOGLE_API_KEY_1"),
    os.getenv("MSDS_GOOGLE_API_KEY_2"),
    os.getenv("MSDS_GOOGLE_API_KEY_3"),
    os.getenv("MSDS_GOOGLE_API_KEY_4")
]

# 유효한 키에 별명(alias) 부여
valid_snipers = []
for i, key in enumerate(api_keys_raw, 1):
    if key:
        valid_snipers.append({"alias": f"스나이퍼-{i}", "key": key})

if not valid_snipers:
    # 레거시 키 지원 (하위 호환성)
    legacy_key = os.getenv("MSDS_GOOGLE_API_KEY")
    if legacy_key:
        valid_snipers = [{"alias": "스나이퍼-L", "key": legacy_key}]
    else:
        print("경고: 장전된 구글 API 키가 없습니다! .env를 확인하세요.")

sniper_pool = cycle(valid_snipers) if valid_snipers else None

# [V15.8.8] 스나이퍼 쿨다운 레지스트리: 429를 받은 키는 일정 시간 블랙리스트
_sniper_cooldown = {}  # {alias: timestamp_until}
_sniper_round_robin_idx = 0

def get_next_sniper():
    """[V15.8.8] 쿨다운이 끝난 키 중 라운드로빈으로 배정"""
    global _sniper_round_robin_idx
    if not valid_snipers: return None
    
    now = time.time()
    n = len(valid_snipers)
    
    # 1. 쿨다운이 풀린 키 중에서 라운드로빈
    for _ in range(n):
        idx = _sniper_round_robin_idx % n
        _sniper_round_robin_idx += 1
        sniper = valid_snipers[idx]
        cooldown_until = _sniper_cooldown.get(sniper["alias"], 0)
        if now >= cooldown_until:
            return sniper
    
    # 2. 모든 키가 쿨다운 중 → 가장 빨리 풀리는 키를 대기 후 반환
    earliest_alias = min(_sniper_cooldown, key=_sniper_cooldown.get)
    wait_sec = _sniper_cooldown[earliest_alias] - now
    if wait_sec > 0:
        time.sleep(wait_sec + 0.5)
    return next(s for s in valid_snipers if s["alias"] == earliest_alias)

def mark_sniper_cooldown(sniper, cooldown_sec=60):
    """[V15.8.8] 429를 받은 스나이퍼를 일정 시간 블랙리스트"""
    if sniper:
        _sniper_cooldown[sniper["alias"]] = time.time() + cooldown_sec

if not OPENAI_API_KEY:
    print("경고: .env 파일에 OPENAI_API_KEY가 없습니다. 2차 Fallback 엔진이 작동하지 않습니다.")

VERSION = "15.8.8"

def call_gemini_with_retry(payload, initial_sniper, max_retries=8, log_func=None):
    """[V15.8.8] 쿨다운 레지스트리 연동: 429 키는 60초 블랙리스트, 살아있는 키 자동 배정"""
    current_sniper = initial_sniper
    
    for attempt in range(max_retries):
        if not current_sniper:
            raise ValueError("🚨 전담 스나이퍼가 배정되지 않았습니다.")
            
        api_key = current_sniper["key"]
        alias = current_sniper["alias"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        try:
            response = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=40)
            
            if response.status_code != 200:
                error_msg = response.text
                if log_func: log_func(f"  🔴 {alias} 사격 실패(HTTP {response.status_code}): {error_msg[:60]}...")
                
                # [V15.8.8] 429면 해당 키를 60초 블랙리스트
                if response.status_code == 429:
                    mark_sniper_cooldown(current_sniper, cooldown_sec=60)
                elif response.status_code == 503:
                    mark_sniper_cooldown(current_sniper, cooldown_sec=30)
                
                # 쿨다운 레지스트리가 알아서 살아있는 키를 골라줌
                current_sniper = get_next_sniper()
                if current_sniper:
                    if log_func: log_func(f"  🔄 [{current_sniper['alias']}](으)로 자동 전환")
                continue
                    
            return response.json()
            
        except requests.exceptions.RequestException as e:
            if log_func: log_func(f"  🔴 {alias} 네트워크 끊김: {str(e)[:60]}")
            time.sleep(2 ** min(attempt, 5))
            continue
            
    raise Exception(f"🚨 {max_retries}회 연속 사격 실패. 불도저(GPT) 투입!")

def extract_product_name_hybrid(text_chunk, image_list, current_sniper, log_func=None):
    """[V15.8.2] 족쇄 해제 & 공란(Blank) 반환 패치"""
    if not current_sniper or not image_list: return "", "실패"

    # 1페이지 사진 데이터 준비
    first_page_img = image_list[0]
    b64_data = first_page_img.get("data", "") if isinstance(first_page_img, dict) else first_page_img
    mime_type = first_page_img.get("mime_type", "image/jpeg") if isinstance(first_page_img, dict) else "image/jpeg"

    # [핵심] 주님의 지시로 다이어트된 프롬프트
    prompt = """
    너는 MSDS의 제품명을 정확히 확정 짓는 전문 판독관이다. 사진에서 다음 2단계 수칙을 엄격히 준수하라.

    1. [구역 격리]: "1. 화학제품과 회사에 관한 정보" 항목을 찾고, 그 아래부터 "2. 유해성·위험성" 항목 시작 전까지만 읽어라. 2번 항목의 GHS 그림이나 안전 문구는 철저히 무시하라.
    2. [핵심 타격]: '가. 제품명', '상품명', '품명', '제품의 명칭', 'Product Name' 등의 레이블이 가리키는 [순수 제품명]만 정확히 추출하라. 

    제품 번호, 카탈로그 코드, 권장 용도, 제조사 정보 등 불필요한 텍스트는 스스로 판단하여 제거하고, 오직 '제품명' 문자열만 부연 설명 없이 딱 한 줄로 출력하라. 못 찾겠으면 아무것도 출력하지 마라.
    """

    payload = {"contents": [{"parts": [{"text": prompt}, {"inlineData": {"mimeType": mime_type, "data": b64_data}}]}]}
    try:
        # [V15.8.1] 전담 스나이퍼 탄창 사용
        # [V15.8.5] log_func 전달 파이프 연결
        result = call_gemini_with_retry(payload, current_sniper, log_func=log_func)
        if result:
            pn_ai = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            
            # AI가 공란을 주거나 실패했을 때를 대비한 안전망
            if pn_ai and not any(k in pn_ai for k in ["미추출", "확인"]) and not re.search(r'[PH]\d{3}', pn_ai):
                if log_func: log_func(f" ├─ [제품명 스캔] ✅ 비전 스나이핑 성공: {pn_ai[:30]}")
                return pn_ai.replace('\n', ' ').strip(), "Vision"
    except Exception as e:
        if log_func: log_func(f" ├─ [제품명 스캔] ❌ 실패: {e}")
        
    return "", "실패"  # '미추출' 대신 깔끔한 공란 반환

PATTERN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'patterns.json')

def load_v5_patterns():
    try:
        if os.path.exists(PATTERN_FILE):
            with open(PATTERN_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get("V5_PATTERNS", {})
    except Exception:
        pass
    return {}

P = load_v5_patterns()

# [V5.1 Step 3] AI 시스템 프롬프트 외부 로드
def load_system_prompt():
    prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_system_v5.txt')
    try:
        if not os.path.exists(prompt_path):
            raise FileNotFoundError(f"프롬프트 파일 누락: {prompt_path}")
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        raise RuntimeError(f"[시스템 치명적 오류] AI 프롬프트 로드 실패. prompt_system_v5.txt 파일을 확인하세요!\n상세: {e}")

# 전역 프롬프트 로드
SYSTEM_PROMPT_TEXT = load_system_prompt()

# 🎯 [1차 스나이퍼용 프롬프트] Gemini 2.5 Flash 전용
PROMPT_GEMINI_FLASH = """
당신은 1차 고속 시각 추출기(Sniper)입니다. 첨부된 MSDS 표 이미지만 보고 데이터를 추출하세요.

[🔥 1차 엔진 5대 절대 원칙]
1. 🚨 엄격한 수평(Y-axis) 1:1 매칭: 표에 선이 없거나 칸이 넓어 성분명, CAS 번호, 함유량이 어긋나 있더라도, 반드시 같은 행(Row)의 문맥을 추적하여 1:1로 매칭하라. 한 물질의 CAS가 2줄로 쪼개져 있다면 병합하라.
2. 🚨 환각 금지(가장 중요): 표에 '함유량'이나 '%'가 명시된 컬럼이 없을 경우, 절대 옆에 있는 '분자량'이나 '녹는점' 같은 무관한 숫자를 함유량으로 둔갑시켜 추출하지 마라.
3. 🚨 결측치 처리: CAS 칸이 비어있거나 '영업비밀', '비공개' 등이면 가차 없이 폐기하라. 반대로 CAS는 있는데 함유량 칸이 비어있거나 '-' 처리되어 있다면 함유량을 '미기재%'로 출력하라. 단, '잔량', 'balance' 등으로 명시된 경우만 'Rem.%'로 출력하라.
4. 🚨 1% 부등호 조작 금지: 원본에 '0.1-1' 이라 적혀 있으면 '0.1~1%'로 출력하라. 임의로 '<1%'처럼 부등호를 지어내는 환각을 절대 금지한다.
5. 포맷 통일: 함유량 숫자 뒤에는 반드시 '%'를 붙여라.

6. 🚨 페이지 트래킹: 첨부된 이미지 중 해당 성분이 발견된 이미지의 실제 페이지 번호(이미지 구석에 적힌 번호 등)를 'page' 필드에 기재하라.
 
 JSON 출력 포맷:
 {
   "구성성분": [
     {"cas_no": "123-45-6", "content": "10~20%", "page": "3"}
   ],
   "교정_사유": "시각 추출 완료"
 }
"""

# 🚜 [2차 복구 요원용 프롬프트] GPT-4o-mini 전용
PROMPT_GPT_FALLBACK = """
당신은 2차 심층 복구 요원(Recovery Agent)입니다. 1차 엔진이 이 표의 공간적 구조를 파악하지 못해 당신에게 넘어왔습니다. 첨부된 이미지를 보고 데이터를 추출하세요.

[🔥 2차 엔진 절대 원칙]
1. 공간 지각 복구: 표의 선이 투명하거나, 미세하게 틀어졌거나, 비대칭 다중 병합이 있더라도 표의 전체적인 맥락을 입체적으로 읽어 CAS와 함유량을 매칭하세요.
2. 🚨 절대 폐기 및 시각적 팩트 주의: 표에 명시된 숫자로 된 CAS 번호(형식: 숫자-숫자-숫자)만 추출하라. 화학 물질명이나 문맥을 보고 네가 아는 화학 지식을 도원하여 실존하는 CAS 번호를 유추하거나 지어내는(Hallucination) 행위는 절대 금지한다. 눈에 명확히 보이는 번호가 없거나 '영업비밀', '비공개', '-' 등이라면 가차 없이 그 행을 추출 대상에서 폐기하라.
3. 🚨 포맷 통일 및 환각 방지: 추출된 함유량 숫자 뒤에는 반드시 '%' 기호를 붙여라. 단, 원본 표에 함유량이 숫자가 아닌 '잔량', '나머지', 'balance', '적량' 등으로 표기되어 있다면, 절대 본인 마음대로 숫자(예: 10%)를 지어내거나 계산해서 적지 마라. 무조건 영문 대소문자를 맞춰 'Rem.%' 라는 문자열 그대로 출력하라.
   🚨 부등호 훼손 절대 금지: 원본 표의 함유량에 부등호(<, ≤)나 텍스트(미만, 이하)가 포함되어 있다면, 이를 절대 물결표(~) 범위 기호로 바꾸지 마라.
   [올바른 예시]: 원본이 '<1' 이면 '<1%'로 출력, 원본이 '≤1' 이면 '≤1%'로 출력.
   [잘못된 예시]: 원본이 '<1' 인데 '~1%'로 변조하여 출력 (절대 금지).

4. 🚨 페이지 트래킹: 각 성분이 발견된 페이지 번호를 'page' 필드에 기재하라.
 
 JSON 출력 포맷:
 {
   "구성성분": [
     {"cas_no": "123-45-6", "content": "10~20%", "page": "3"}
   ],
   "교정_사유": "심층 복구 근거 요약"
 }
"""

# [V8.2] MES 마스터 데이터 로드 (Silent Failure 방어 및 Fail-Safe 적용)
MES_MASTER_MAP = {}
try:
    master_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MES_MASTER_LOOKUP.json')
    
    # 1. 파일 존재 여부 물리적 확인
    if not os.path.exists(master_path):
        raise FileNotFoundError(f"마스터 데이터 파일이 존재하지 않습니다: {master_path}")

    with open(master_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        items_list = data.get("master_list", []) if isinstance(data, dict) and "master_list" in data else []
        
        # 2. 데이터 유효성 검증
        if not items_list:
            raise ValueError("JSON 파일 내에 'master_list' 배열이 없거나 데이터가 비어 있습니다.")
            
        for info in items_list:
            cas_raw = str(info.get("CAS번호", "")).strip()
            # CAS 번호 정규화 (앞의 0 제거하여 매칭 확률 증대)
            cas = re.sub(r'^0+', '', cas_raw)
            # [수정] 초산메틸 대신 메틸 아세테이트를 잡도록 '물질명' 최우선 적용
            std_name = info.get("물질명") or info.get("상용명")
            if cas and std_name:
                MES_MASTER_MAP[cas] = std_name.strip()
                
except Exception as e:
    # [치명적 변경] print로 조용히 넘기지 않고 RuntimeError 발생. 
    # GUI의 global_exception_handler가 캐치하여 팝업으로 띄우도록 강제함.
    raise RuntimeError(f"[시스템 치명적 오류] 마스터 DB 초기화에 실패했습니다. DB 파일을 확인하세요!\n상세 원인: {e}")

# [V5.1 성능 최적화] 정규식 사전 컴파일 및 전역 헬퍼 함수 분리
REGEX_LE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|프로)?\s*(?:이하|≤|<=)')
REGEX_LT = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|프로)?\s*(?:미만|＜|<)')
REGEX_GE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|프로)?\s*(?:이상|≥|>=)')
REGEX_GT = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|프로)?\s*(?:초과|＞|>)')
REGEX_PM = re.compile(r'(\d+(?:\.\d+)?)\s*(?:±|\+-)\s*(\d+(?:\.\d+)?)')

def _calc_pm_range(m):
    """정규식 매치 객체를 받아 ± 범위를 계산하는 전역 헬퍼 함수"""
    try:
        val, pm = float(m.group(1)), float(m.group(2))
        return f"{val-pm:g}~{val+pm:g}"
    except:
        return m.group(0)

# =====================================================================
# [1단계] V24 정규식 코어 (안전망 복구 완료)
# =====================================================================
def clean_junk_from_name(name):
    if not name: return name
    name = re.split(r'\s{2,}', str(name))[0]
    junk_keywords = ["Date", "발행일", "개정일", "Revision", "Rev.", "Page", "페이지", "물질안전보건자료", "MSDS", "작성일", "공급자", "식별자", "번호", "CAS"]
    for key in junk_keywords:
        name = re.split(rf'(?i){re.escape(key)}', name)[0]
    name = re.split(r'\d{4}[.\-/]\d{2}[.\-/]\d{2}', name)[0]
    name = re.sub(r'(.+?)\1+', r'\1', name)
    return name.strip(": ").strip()

# [V14.6] 정규식 최적화 및 전역 헬퍼 함수



# [엔진 내장] CAS 검증
def verify_cas_number(cas_string):
    if not cas_string or re.search(r'[가-힣a-zA-Z]', cas_string) or cas_string.strip() == "-": return True
    clean_cas = re.sub(r'[^0-9-]', '', cas_string)
    parts = clean_cas.split('-')
    if len(parts) != 3: return False
    try:
        check_digit = int(parts[2])
        digits = parts[0] + parts[1]
        total = sum(int(digit) * i for i, digit in enumerate(reversed(digits), 1))
        return (total % 10) == check_digit
    except: return False

def clean_number(n_str):
    try:
        f = float(n_str.replace(',', '.')) 
        if f.is_integer(): return str(int(f))
        return str(f)
    except: return n_str

def _normalize_single_content(raw):
    """[V15.8.8] 개별 함유량 문자열 정제 헬퍼"""
    v = raw.strip().replace(" ", "")
    v = re.sub(r'\([^)]*[A-Za-z가-힣][^)]*\)', '', v)
    v = re.sub(r'([0-9.]+)(?:%?)미만(?:%?)', r'<\1', v)
    v = re.sub(r'([0-9.]+)(?:%?)이하(?:%?)', r'≤\1', v)
    v = re.sub(r'([0-9.]+)(?:%?)초과(?:%?)', r'>\1', v)
    v = re.sub(r'([0-9.]+)(?:%?)이상(?:%?)', r'≥\1', v)
    v = v.replace('＜', '<').replace('＞', '>')
    v = v.replace('<=', '≤').replace('>=', '≥')
    v = re.sub(r'\.0+(?=[^\d]|$)', '', v)

    weird_range = re.match(r'^≤([0-9.]+)(?:%?)≤([0-9.]+)(?:%?)$', v)
    if weird_range:
        n1, n2 = weird_range.groups()
        return f"{n1}~{n2}%"
    range_m = re.match(r'^([<>≤≥]?)([0-9.]+)[%]*[-~]([<>≤≥]?)([0-9.]+)[%]*$', v)
    if range_m:
        p1, n1, p2, n2 = range_m.groups()
        return f"{n1}~{p2}{n2}%"
    if "Rem" in v:
        return "Rem.%" if "%" not in v else v
    single_m = re.match(r'^([<>≤≥]?)([0-9.]+)%?$', v)
    if single_m:
        p, n = single_m.groups()
        return f"{p}{n}%"
    return v

def final_quality_control(components, full_text, log_func=None):
    """[V15.8.8] 지능형 다중 CAS ↔ 함유량 1:1 매칭 분리"""
    refined = []
    has_invalid = False
    norm_text = re.sub(r'[\s\-]', '', full_text).upper() if full_text else ""
    for comp in components:
        raw_cas_field = str(comp.get("cas_no", "")).strip()

        # 1. CAS 번호부터 싹쓸이
        cas_list = re.findall(r'(\d{1,7}-\d{2}-\d)', raw_cas_field)
        # 2. 번호가 아예 없고 '영업비밀'만 적힌 경우만 거름
        if not cas_list and any(w in raw_cas_field for w in ["영업비밀", "비공개", "Secret"]):
            continue
        if not cas_list:
            continue

        # 3. 함유량 원본 추출
        raw_content = str(comp.get("content", "")).strip()

        # [V15.8.8 핵심] 함유량도 슬래시(/)로 분리하여 CAS와 1:1 매칭
        content_parts_raw = re.split(r'\s*/\s*', raw_content)
        content_parts = [_normalize_single_content(c) for c in content_parts_raw if c.strip()]

        # CAS 번호 당 하나씩 정제 데이터 생성
        page_val = comp.get("page", "")
        if len(cas_list) == len(content_parts):
            for cas_raw, cv in zip(cas_list, content_parts):
                cas = re.sub(r'^0+', '', cas_raw)
                if not verify_cas_number(cas):
                    has_invalid = True
                    continue
                if cv:
                    refined.append({"cas": cas, "content": cv, "page": page_val})
        else:
            fallback_content = content_parts[0] if content_parts else ""
            for cas_raw in cas_list:
                cas = re.sub(r'^0+', '', cas_raw)
                if not verify_cas_number(cas):
                    has_invalid = True
                    continue
                if fallback_content:
                    refined.append({"cas": cas, "content": fallback_content, "page": page_val})
    try:
        check_omission(full_text, refined)
    except ValueError as e:
        if log_func: log_func(f" 🟡 [누락 감지] {e}")
        has_invalid = True 
    return refined, has_invalid



# =====================================================================
# [2단계] 제미나이 AI 앙상블 (팀장 검수 엔진)
# =====================================================================


def find_section3_pages(doc):
    """[V15.8.3] 2번 항목(비표준) 및 3번 항목 정밀 탐지"""
    pages = []
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        # 2번 또는 3번 항 시작 지점 탐색
        if re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:구성|COMPOSITION)', text, re.I):
            pages.append(i)
        # 3번 또는 4번 항이 나오면 해당 페이지까지 포함 후 탐색 종료
        if pages and re.search(r'(?:SECTION\s*)?[34][\s.:]*(?:응급|유해성|위험성|FIRST|HAZARDS)', text, re.I):
            if i not in pages:
                pages.append(i)
            break
    return pages

def extract_section3_images(pdf_path, current_sniper, log_func=None):
    """[V15.8.3] 표 이미지와 함께 해당 페이지의 텍스트만 국소 추출하여 반환"""
    try:
        doc = fitz.open(pdf_path)
        pages = find_section3_pages(doc)
        
        if not pages:
            if log_func: log_func(" 🔍 텍스트 기반 탐지 실패. 스캔본 정찰병 가동...")
            recon_images = []
            for i in range(min(5, len(doc))):
                pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.8, 0.8))
                recon_images.append({
                    "mimeType": "image/png", 
                    "data": base64.b64encode(pix.tobytes("png")).decode("utf-8")
                })
            
            recon_prompt = """
            이 이미지들 중 '2. 구성성분' 또는 '3. 구성성분' 표가 있는 페이지의 번호(0부터 시작하는 index)를 찾아라.
            반드시 아래 JSON 형식으로만 응답하라: {"page_index": 숫자}
            찾지 못했다면 {"page_index": -1}
            """
            recon_res = call_gemini_2_5_flash(recon_images, prompt=recon_prompt, current_sniper=current_sniper, log_func=log_func)
            
            try:
                page_idx = int(recon_res.get("page_index", -1))
            except:
                page_idx = -1
                
            if page_idx >= 0 and page_idx < len(doc):
                pages = [page_idx]
                if page_idx + 1 < len(doc):
                    pages.append(page_idx + 1)
                if log_func: log_func(f" 🎯 정찰병이 페이지를 찾았습니다: {pages}번 바인딩")
            else:
                if log_func: log_func(" ❌ 정찰병도 표를 찾지 못했습니다.")
                doc.close()
                return [], "" # 빈 튜플 반환

        images = []
        raw_text = ""
        for p_idx in pages:
            page = doc[p_idx]
            raw_text += page.get_text("text") + "\n"
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
            b64_img = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            images.append({"mimeType": "image/png", "data": b64_img})
            if len(images) >= 3: break
            
        doc.close()

        # [V15.8.4] 정밀 슬라이싱: 2/3번 항목 시작부터 3/4번 항목 시작 전까지만 텍스트 칼질
        section3_text_only = raw_text
        start_m = re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:구성|COMPOSITION)', raw_text, re.I)
        if start_m:
            end_m = re.search(r'(?:SECTION\s*)?[34][\s.:]*(?:응급|유해성|위험성|FIRST|HAZARDS)', raw_text[start_m.end():], re.I)
            if end_m:
                section3_text_only = raw_text[start_m.start():start_m.end() + end_m.start()]
            else:
                section3_text_only = raw_text[start_m.start():]

        # ... (중략) ...
        return images, section3_text_only, pages # 👈 이미지, 텍스트, 페이지 번호 목록 반환
    except Exception:
        return [], "", []

def call_gemini_2_5_flash(image_list=None, prompt=None, current_sniper=None, log_func=None):
    """[V14.6] 1차 스나이퍼: 고속 시각 추출"""
    if not image_list or not current_sniper: return None
    
    final_prompt = prompt if prompt else PROMPT_GEMINI_FLASH

    # Google AI API Contents/Parts 구조 구성
    parts = [{"text": f"{SYSTEM_PROMPT_TEXT}\n\n{final_prompt}"}]
    for img in image_list:
        parts.append({
            "inlineData": {
                "mimeType": "image/png",
                "data": img.get("data", "")
            }
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json"
        }
    }

    try:
        # [V15.8.5] 본진 로그 파이프 연결!
        result = call_gemini_with_retry(payload, current_sniper, log_func=log_func)
        if result:
            candidate = result.get("candidates", [{}])[0]
            text_response = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
            return json.loads(text_response)
        return None
    except Exception as e:
        if log_func: log_func(f" ❌ Gemini 호출 에러: {e}")
        return None

def check_omission(original_text, extracted_data):
    """[V15.8.8] 카운트 기반 누락 검증: 중복 출현 CAS까지 정밀하게 체크합니다."""
    if not original_text: return 
    
    # 1. 원본 텍스트에서 CAS 번호 형태를 모두 추출 (중복 허용)
    cas_pattern = re.compile(r'\d{1,7}-\d{2}-\d')
    all_cas_found = cas_pattern.findall(original_text)
    
    # 유효한 CAS만 필터링 (중복 포함)
    valid_original_cas = [cas for cas in all_cas_found if verify_cas_number(cas)]
    original_cas_count = len(valid_original_cas)
    
    # 2. 추출 데이터 개수 계산
    if isinstance(extracted_data, list):
        extracted_cas_count = len(extracted_data)
    else:
        extracted_cas_count = len(extracted_data.get("구성성분", []))
    
    # 3. 누락 적발
    if extracted_cas_count < original_cas_count:
        raise ValueError(f"스나이퍼 누락 발생 (원본:{original_cas_count} vs 추출:{extracted_cas_count}). 2차 불도저(GPT) 요원 투입!")

def call_gpt_4o_mini(image_list=None, prompt=None, log_func=None):
    """[V14.6] 2차 복구 요원: 심층 구조 분석"""
    if not image_list or not OPENAI_API_KEY: return None

    final_prompt = prompt if prompt else PROMPT_GPT_FALLBACK

    content_list = [{"type": "text", "text": final_prompt}]
    for img in image_list:
        content_list.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img.get('data', '')}"}
        })

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_TEXT},
            {"role": "user", "content": content_list}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=40)
        if response.status_code == 200:
            result = response.json()
            text_response = result["choices"][0]["message"]["content"]
            return json.loads(text_response)
        else:
            if log_func: log_func(f" 🔴 불도저(GPT) 서버 에러: HTTP {response.status_code}")
            return None
    except Exception as e:
        if log_func: log_func(f" 🔴 불도저(GPT) 통신 에러: {str(e)[:50]}")
        return None

def process_pdf(pdf_path, log_func=None):
    start_time = time.time()
    
    current_sniper = get_next_sniper()
    alias = current_sniper["alias"] if current_sniper else "알수없음"
    
    if log_func: log_func(f" 🚀 [V{VERSION} Vision-Only] 분석 시작 ➡️ 담당: {alias}")

    # [V15.8.3] 배선 교체: 이미지와 국소 텍스트를 동시에 받음 (1 PDF = 1 스나이퍼 원칙)
    image_list, section3_text_for_omission = extract_section3_images(pdf_path, current_sniper, log_func=log_func)
    if not image_list:
        if log_func: log_func(" ❌ Section 3 이미지를 찾을 수 없습니다.")
        return {"error": "AI 추출 완전 실패 (수동 검토 필요)"}

    # 2. 제품명 하이브리드 스캔 및 전체 텍스트 추출 (Grounding용)
    full_text_for_grounding = ""
    try:
        doc = fitz.open(pdf_path)
        first_page_text = doc[0].get_text() if len(doc) > 0 else ""
        
        for page in doc:
            full_text_for_grounding += page.get_text()
            
        pix_cover = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        cover_img = [{"mimeType": "image/png", "data": base64.b64encode(pix_cover.tobytes("png")).decode("utf-8")}]
        doc.close()
    except:
        cover_img = image_list 
        first_page_text = ""
        full_text_for_grounding = ""
    
    # [V15.8.7 복원] 1 PDF = 1 스나이퍼 원칙: 진입 시 배정된 스나이퍼를 계속 사용
    hybrid_pn, _ = extract_product_name_hybrid(first_page_text, cover_img, current_sniper, log_func=log_func)

    hybrid_pn = re.sub(r'^[\s\-_*:#=|]+', '', hybrid_pn)
    is_multi_model = False
    
    if hybrid_pn.count(',') >= 2 or len(hybrid_pn) > 60:
        is_multi_model = True

    # 3. 1차 스나이퍼(Flash) 투입 (진입 시 배정된 스나이퍼 재사용)
    if log_func: log_func(f" 🎯 1차 고속 스나이퍼({alias}) 투입")
    # [V15.8.5] 누락되었던 log_func 파라미터 강제 주입!
    ai_res = call_gemini_2_5_flash(image_list, PROMPT_GEMINI_FLASH, current_sniper=current_sniper, log_func=log_func)
    used_engine = "Gemini-Flash"

    # 4. 스마트 Gatekeeper (황색불 판별)
    needs_gpt = False
    valid_components = []

    if not ai_res or "구성성분" not in ai_res:
        needs_gpt = True # 구조 붕괴
    else:
        for comp in ai_res.get("구성성분", []):
            cas = str(comp.get("cas_no", "")).strip()
            content_str = str(comp.get("content", "")).replace(" ", "") # 공백만 제거 (최소 정제)
            
            # [필터링] 영업비밀성 키워드면 1차에서도 버림
            if not cas or any(kw in cas for kw in ["영업비밀", "비공개", "승인번호", "미기재", "Secret"]):
                continue

            # [롤백] 1차 엔진(Gemini)은 엄격한 기준 적용 (혼합 표기면 폐기하고 2차로 넘김)
            cas_clean = re.sub(r'^0+', '', cas) # 앞의 0 제거
            is_valid_cas = re.match(r'^\d{1,7}-\d{2}-\d$', cas_clean)
            
            if not is_valid_cas:
                needs_gpt = True # CAS 규격이 깨졌으면 1차 엔진의 시각 오류로 간주, GPT 호출!
                continue
                
            # [황색불 조건] 함유량 오류
            if not re.search(r'\d', content_str) and "Rem" not in content_str:
                needs_gpt = True 
                break
            valid_components.append(comp)
        
        # [V15.8.3] 누락 탐지기: 전체 문서가 아닌 '표가 있는 페이지의 텍스트'만으로 비교!
        if len(valid_components) == 0:
            needs_gpt = True
        else:
            try:
                # full_text_for_grounding 대신 section3_text_for_omission 사용!
                check_omission(section3_text_for_omission, valid_components)
            except ValueError as e:
                if log_func: log_func(f" 🟡 {e}")
                needs_gpt = True

    # 5. 2차 복구 요원(GPT) 투입
    if needs_gpt:
        if log_func: log_func(" 🟡 1차 엔진 추출 불가 판단. 2차 입체 복구 요원(GPT-4o-mini) 투입!")
        ai_res = call_gpt_4o_mini(image_list, PROMPT_GPT_FALLBACK)
        used_engine = "GPT-4o-mini"
        
        # GPT마저 실패하거나 유효 성분이 0개면 깔끔하게 포기 (대안 찾지 마!)
        if not ai_res or not ai_res.get("구성성분") or len(ai_res.get("구성성분", [])) == 0:
            if log_func: log_func(" ❌ 모든 AI 엔진 추출 실패 (수동 검토 대상)")
            return {
                "error": "AI 추출 완전 실패 (수동 검토 필요)",
                "제품명": hybrid_pn,
                "신호등": "🔴"
            }

    final_ai_result = ai_res

    # 6. 데이터 조립 및 Phase 3 단순 후처리 (공백 제거)
    product_name = hybrid_pn # 1페이지에서 스나이핑한 진짜 제품명 강제 적용

    
    # [수정] AI가 찾은 제품명을 인위적으로 정제하지 않음
    
    components = final_ai_result.get("구성성분", [])
    reason = final_ai_result.get("교정_사유", "사유 없음")
    
    # 🚨 [V15.6] 중앙 통제실(후행 교정기)로 데이터 일괄 세탁
    refined_comps, has_invalid_cas = final_quality_control(components, full_text_for_grounding, log_func)
    
    comp_parts = [f"{c['cas']}({c['content']})" for c in refined_comps]

    if not comp_parts:
        if log_func: log_func(" ❌ 유효한 성분 데이터가 존재하지 않음")
        return {
            "error": "AI 추출 완전 실패 (수동 검토 필요)",
            "제품명": hybrid_pn,
            "신호등": "🔴"
        }

    comp_str = "; ".join(comp_parts)
    target_substances = "" # 🚨 측정대상 변수 추가

    # ----------------------------------------------------
    # 🚨 [V15.3] 특정 다중 모델 용접봉(CR-13 시리즈) 하드코딩 예외 처리
    if "연강용 피복아크 용접봉" in hybrid_pn and "CS-200" in hybrid_pn and "CR-13" in hybrid_pn:
        hybrid_pn = "용접재료(연강용 피복아크 용접봉) CR-13"
        comp_str = "13463-67-7(10~15%); 68476-25-5(5~10%); 7439-96-5(1~5%); 1344-09-8(1~5%); 1317-65-3(1~5%); 12001-26-2(1~5%); 7439-89-6(Rem.%)"
        
        # 🚨 주님 지시: 측정대상 텍스트 강제 고정!
        target_substances = "용접흄; 산화철(분진, 흄); 망간 및 그 무기화합물; 이산화티타늄"
        
        is_multi_model = True 
        if log_func: log_func(" ⚠️ [하드코딩 예외] CR-13 감지! 제품명, 성분, 측정대상 강제 치환 완료")
    # ----------------------------------------------------

    # 🚨 [V15.2 핵심] AI 추출은 무사히 끝났으나, 다중 모델이므로 🟡황색불로 강제 변경!
    if is_multi_model:
        return {
            "구성성분": comp_str,
            "제품명": hybrid_pn,
            "측정대상": target_substances, # 👈 강제 삽입!
            "교정_사유": "다중 모델(시리즈) 문서 감지 또는 표준 예외 치환",
            "신호등": "🟡",
            "used_engine": "flash" if used_engine == "Gemini-Flash" else "bulldozer" # 👈 GUI 규격에 맞게 변환하여 추가!
        }

    # 정상 단일 모델일 경우
    tag = f"[{used_engine}-PASS]"
    gui_engine_name = "flash" if used_engine == "Gemini-Flash" else "bulldozer" # 👈 공통 변수 추가
    
    # [V15.8.2 패치] 제품명이 공란('')인 경우 수동 확인을 위해 황색불(🟡) 반환
    if not hybrid_pn:
        return {
            "구성성분": comp_str,
            "제품명": "",
            "측정대상": target_substances,
            "교정_사유": "제품명 추출 실패 - 수동 확인 요망",
            "신호등": "🟡",
            "used_engine": gui_engine_name
        }

    # [V15.5 추가] 가짜 CAS가 탐지된 경우 초록불(🟢) 차단 및 황색불(🟡) 강제 전환
    final_signal = "🟢"
    final_reason = reason
    if has_invalid_cas:
        final_signal = "🟡"
        final_reason = f"{reason} (⚠️ 일부 부적절한 CAS 포맷 감지 및 제외됨)"

    return {
        "구성성분": comp_str,
        "제품명": hybrid_pn,
        "측정대상": target_substances,
        "교정_사유": final_reason,
        "신호등": final_signal,
        "used_engine": gui_engine_name # 👈 추가!
    }

# [V7.0] GUI 호환성을 위한 별칭 설정
analyze_msds = process_pdf
