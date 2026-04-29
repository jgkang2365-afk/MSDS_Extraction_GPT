import os
import base64

import sys
import re
import time
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
GOOGLE_API_KEY = os.getenv("MSDS_GOOGLE_API_KEY")

if not OPENAI_API_KEY:
    print("경고: .env 파일에 OPENAI_API_KEY가 없습니다. 2차 Fallback 엔진이 작동하지 않습니다.")
if not GOOGLE_API_KEY:
    print("경고: .env 파일에 GOOGLE_API_KEY가 없습니다. 1차 메인 엔진(Gemini)이 작동하지 않습니다.")

VERSION = "15.3.1"

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_API_KEY}"

def extract_product_name_hybrid(text_chunk, image_list, api_key, log_func=None):
    """[V12.9.5] 주님의 2.3 시선 이동 알고리즘 이식: 인지적 격리 비전 스나이퍼"""
    if not api_key or not image_list: return "미추출", "실패"

    # 1페이지 사진 데이터 준비
    first_page_img = image_list[0]
    b64_data = first_page_img.get("data", "") if isinstance(first_page_img, dict) else first_page_img
    mime_type = first_page_img.get("mime_type", "image/jpeg") if isinstance(first_page_img, dict) else "image/jpeg"

    # [핵심] 인지적 격리 프롬프트
    prompt = """
    너는 MSDS의 제품명을 정확히 확정 짓는 전문 판독관이다. 사진에서 다음 3단계 수칙을 엄격히 준수하라.

    1. [구역 격리]: "1. 화학제품과 회사에 관한 정보" 항목을 찾고, 그 아래부터 "2. 유해성·위험성" 항목 시작 전까지만 읽어라. 2번 항목의 GHS 그림이나 안전 문구(P305 등)는 네 시야에 없는 것이니 절대 무시하라.
    2. [의미적 레이블 앵커]: '가. 제품명', '상품명', '품명', '제품의 명칭', 'Product Name' 등 제품의 이름을 나타내는 모든 유사 레이블을 앵커로 삼아라. 레이블이 없더라도 1번 항목 바로 아래에 가장 강조된 텍스트를 목표로 한다.
    3. [원본 무삭제 카피]: 모델명, 규격, 괄호 안 영문명까지 토씨 하나 틀리지 말고 그대로 베껴라. 요약은 절대 금지한다. 단, '제조자'나 '나.' 항목이 나오면 그 직전에서 즉시 멈춰라.

    부연 설명 없이 오직 제품명 문자열만 딱 한 줄로 출력하라. 못 찾겠으면 '미추출'.
    """

    payload = {"contents": [{"parts": [{"text": prompt}, {"inlineData": {"mimeType": mime_type, "data": b64_data}}]}]}
    try:
        resp = requests.post(GEMINI_API_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        if resp.status_code == 200:
            pn_ai = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            # GHS 쓰레기 데이터 최종 검열
            if pn_ai and not any(k in pn_ai for k in ["미추출", "확인"]) and not re.search(r'[PH]\d{3}', pn_ai):
                if log_func: log_func(f" ├─ [제품명 스캔] ✅ 비전 스나이핑 성공: {pn_ai[:30]}")
                return pn_ai.replace('\n', ' ').strip(), "Vision"
    except: pass
    return "미추출", "실패"

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
당신은 1차 고속 시각 추출기(Sniper)입니다. 첨부된 MSDS Section 3 표 이미지만 보고 데이터를 추출하세요.

[🔥 1차 엔진 절대 원칙]
1. 엄격한 수평 1:1 매칭: 같은 가로줄(Same Y-axis)에 있는 CAS 번호와 함유량만 연결하세요.
2. 🚨 절대 폐기 원칙: CAS 칸이 비어있거나 '영업비밀', '비공개', '승인번호', '미기재' 등이 적혀있다면 그 행은 쓰레기입니다. 가차 없이 폐기하세요.
3. 유추 금지: 선이 어긋나거나 셀 병합이 복잡해서 수평이 맞지 않으면 억지로 엮지 말고 버리세요. (어려운 표는 2차 요원에게 넘길 것입니다)
4. 🚨 포맷 통일 및 환각 방지: 추출된 함유량 숫자 뒤에는 반드시 '%' 기호를 붙여라. 단, 원본 표에 함유량이 숫자가 아닌 '잔량', '나머지', 'balance', '적량' 등으로 표기되어 있다면, 절대 본인 마음대로 숫자(예: 10%)를 지어내거나 계산해서 적지 마라. 무조건 영문 대소문자를 맞춰 'Rem.%' 라는 문자열 그대로 출력하라.

JSON 출력 포맷:
{
  "구성성분": [
    {"cas_no": "123-45-6", "content": "10~20%"}
  ],
  "교정_사유": "추출 근거 요약"
}
"""

# 🚜 [2차 복구 요원용 프롬프트] GPT-4o-mini 전용
PROMPT_GPT_FALLBACK = """
당신은 2차 심층 복구 요원(Recovery Agent)입니다. 1차 엔진이 이 표의 공간적 구조를 파악하지 못해 당신에게 넘어왔습니다. 첨부된 이미지를 보고 데이터를 추출하세요.

[🔥 2차 엔진 절대 원칙]
1. 공간 지각 복구: 표의 선이 투명하거나, 미세하게 틀어졌거나, 비대칭 다중 병합이 있더라도 표의 전체적인 맥락을 입체적으로 읽어 CAS와 함유량을 매칭하세요.
2. 🚨 유연한 식별 원칙 (1차와 다름): CAS 번호 칸에 다른 식별번호(예: /KE-12345)가 섞여 있더라도, 어떻게든 유효한 CAS 번호(형식: 숫자-숫자-숫자)를 찾아내서 살려내세요. 단, 정말로 '영업비밀', '비공개' 등의 문구만 있어서 CAS를 찾을 수 없는 경우에만 폐기하세요.
3. 🚨 포맷 통일 및 환각 방지: 추출된 함유량 숫자 뒤에는 반드시 '%' 기호를 붙여라. 단, 원본 표에 함유량이 숫자가 아닌 '잔량', '나머지', 'balance', '적량' 등으로 표기되어 있다면, 절대 본인 마음대로 숫자(예: 10%)를 지어내거나 계산해서 적지 마라. 무조건 영문 대소문자를 맞춰 'Rem.%' 라는 문자열 그대로 출력하라.

JSON 출력 포맷:
{
  "구성성분": [
    {"cas_no": "123-45-6", "content": "10~20%"}
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

def minimal_clean(content):
    """[V15.2] 함유량 부등호 치환, 소수점 제거 및 기호 표준화"""
    if not content: return ""
    c = str(content).replace(" ", "")

    # 1. 한글 부등호 위치 변경 및 기호화 (86%미만 -> <86%)
    c = re.sub(r'([0-9.]+)(?:%?)(이하|미만)(?:%?)', r'<\1%', c)
    c = re.sub(r'([0-9.]+)(?:%?)(이상|초과)(?:%?)', r'>\1%', c)

    # 2. 특수기호 표준화
    c = c.replace("≤", "<").replace("≥", ">").replace("＜", "<").replace("＞", ">")

    # 3. 무의미한 소수점(.0) 제거 (1.0~5.0% -> 1~5%, 10.0% -> 10%)
    c = re.sub(r'\.0+(?=[^\d]|$)', '', c)

    # 4. 범위 혼합 기호 깔끔하게 치환 (≥80-≤85% -> 80~85%)
    c = re.sub(r'[><=]*([0-9.]+)[%]*[-~][><=]*([0-9.]+)[%]*', r'\1~\2%', c)

    return c



# =====================================================================
# [2단계] 제미나이 AI 앙상블 (팀장 검수 엔진)
# =====================================================================


def find_section3_pages(doc):
    """[V15.0] 텍스트 스캔을 통한 Section 3(구성성분) 포함 페이지 정밀 탐지"""
    pages = []
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        # 3번 항 시작 지점 탐색
        if re.search(r'3\.\s*구성|SECTION\s*3|3\s*:\s*COMPOSITION', text, re.I):
            pages.append(i)
        # 4번 항이 나오면 해당 페이지까지 포함 후 탐색 종료
        # (Section 3 제목이 이전 페이지, 표 본체가 이 페이지에 있는 경우 대비)
        if pages and re.search(r'4\.\s*응급|SECTION\s*4|4\s*:\s*FIRST', text, re.I):
            if i not in pages:
                pages.append(i)
            break
    return pages

def extract_section3_images(pdf_path, log_func=None):
    """[V14.6] Section 3 영역 고해상도(2.5x) 캡처 및 스캔본 정찰병(Recon)"""
    try:
        doc = fitz.open(pdf_path)
        pages = find_section3_pages(doc)
        
        # [🚨 Plan B: 스캔본 정찰병 가동]
        if not pages:
            if log_func: log_func(" 🔍 텍스트 기반 탐지 실패. 스캔본 정찰병(Recon) 가동...")
            recon_images = []
            for i in range(min(5, len(doc))):
                pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.8, 0.8)) # 정찰용 저해상도
                recon_images.append({
                    "mimeType": "image/png", 
                    "data": base64.b64encode(pix.tobytes("png")).decode("utf-8")
                })
            
            # 정찰병 호출 (숫자만 추출하도록 강제)
            recon_prompt = """
            이 이미지들 중 '3. 구성성분' 표가 있는 페이지의 번호(0부터 시작하는 index)를 찾아라.
            반드시 아래 JSON 형식으로만 응답하라:
            {"page_index": 숫자}
            찾지 못했다면 {"page_index": -1}
            """
            recon_res = call_gemini_2_5_flash(recon_images, prompt=recon_prompt)
            
            try:
                page_idx = int(recon_res.get("page_index", -1))
            except:
                page_idx = -1
                
            if page_idx >= 0 and page_idx < len(doc):
                pages = [page_idx]
                # [수정] 표가 다음 장으로 넘어갈 것을 대비해 N+1 페이지도 바인딩
                if page_idx + 1 < len(doc):
                    pages.append(page_idx + 1)
                if log_func: log_func(f" 🎯 정찰병이 페이지를 찾았습니다: {pages}번 바인딩")
            else:
                if log_func: log_func(" ❌ 정찰병도 표를 찾지 못했습니다.")
                doc.close()
                return []
        
        images = []
        for p_idx in pages:
            page = doc[p_idx]
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
            b64_img = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            images.append({"mimeType": "image/png", "data": b64_img})
            if len(images) >= 3: break
            
        doc.close()
        return images
    except Exception:
        return []

def call_gemini_2_5_flash(image_list=None, prompt=None, log_func=None):
    """[V14.6] 1차 스나이퍼: 고속 시각 추출"""
    if not image_list or not GOOGLE_API_KEY: return None
    
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
        response = requests.post(GEMINI_API_URL, json=payload, timeout=40)
        if response.status_code == 200:
            result = response.json()
            candidate = result.get("candidates", [{}])[0]
            text_response = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
            return json.loads(text_response)
        return None
    except:
        return None

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
        return None
    except:
        return None

def process_pdf(pdf_path, log_func=None):
    start_time = time.time()
    if log_func: log_func(f" 🚀 [V{VERSION} Vision-Only] 비전 전용 파이프라인 가동")

    # 1. Section 3 이미지 추출
    image_list = extract_section3_images(pdf_path, log_func=log_func)
    if not image_list:
        if log_func: log_func(" ❌ Section 3 이미지를 찾을 수 없습니다.")
        return {"error": "AI 추출 완전 실패 (수동 검토 필요)"}

    # 2. 제품명 하이브리드 스캔 (무조건 1페이지 캡처)
    try:
        doc = fitz.open(pdf_path)
        first_page_text = doc[0].get_text() if len(doc) > 0 else ""
        # 제품명 추출 전용 1페이지 렌더링
        pix_cover = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        cover_img = [{"mimeType": "image/png", "data": base64.b64encode(pix_cover.tobytes("png")).decode("utf-8")}]
        doc.close()
    except:
        cover_img = image_list # 실패 시 기존 이미지 폴백
        first_page_text = ""
    
    hybrid_pn, _ = extract_product_name_hybrid(first_page_text, cover_img, GOOGLE_API_KEY, log_func=log_func)

    # ----------------------------------------------------
    # [V15.3] 제품명 노이즈 제거 및 다중 모델 감지 (축약 금지, 원본 보존)
    
    # 1. 앞쪽 쓸데없는 특수기호만 제거 ("- 럭키 Lacquer" -> "럭키 Lacquer")
    hybrid_pn = re.sub(r'^[\s\-_*:#=|]+', '', hybrid_pn)
    is_multi_model = False
    
    # 2. 콤마(,)가 많거나 길면 다중 모델로 판별만 하고(🟡황색불 트리거), 이름은 절대 자르지 마라!
    if hybrid_pn.count(',') >= 2 or len(hybrid_pn) > 60:
        is_multi_model = True
    # ----------------------------------------------------

    # 3. 1차 스나이퍼(Flash) 투입
    if log_func: log_func(" 🎯 1차 고속 스나이퍼(Gemini-Flash) 투입")
    ai_res = call_gemini_2_5_flash(image_list, PROMPT_GEMINI_FLASH)
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
        
        # [황색불 조건] 비공개/빈칸을 버리고 났더니 유효 성분이 0개다? 1차 엔진의 시야 실패!
        if len(valid_components) == 0:
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
    
    comp_parts = []
    for comp in components:
        cas = str(comp.get("cas_no", "")).strip()
        # CAS 번호 정규화: 앞의 0 제거
        if re.match(r'^0+\d+-\d{2}-\d$', cas): cas = re.sub(r'^0+', '', cas)
        
        # CAS 번호 규격 검증 (혼합 표기에서 순수 CAS만 추출)
        cas_match = re.search(r'(\d{1,7}-\d{2}-\d)', cas)
        if not cas_match: 
            continue
        cas = cas_match.group(1)
            
        # 함유량 극단적 단순 정제 (공백 제거만)
        substance_content = minimal_clean(comp.get("content", ""))
        if not substance_content: continue

        # 주님 지시: 물질명 100% 제거하고 오직 CAS(함유량) 포맷으로만 조립
        comp_parts.append(f"{cas}({substance_content})")

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
            "신호등": "🟡"
        }

    # 정상 단일 모델일 경우
    tag = f"[{used_engine}-PASS]"
    
    # [V15.3.1 추가] 제품명이 '미추출'인 경우에도 주의가 필요하므로 황색불(🟡) 반환
    if hybrid_pn == "미추출":
        return {
            "구성성분": comp_str,
            "제품명": hybrid_pn,
            "측정대상": target_substances,
            "교정_사유": "제품명 추출 실패 - 수동 확인 요망",
            "신호등": "🟡"
        }

    return {
        "구성성분": comp_str,
        "제품명": hybrid_pn,
        "측정대상": target_substances,
        "교정_사유": reason,
        "신호등": "🟢"
    }

# [V7.0] GUI 호환성을 위한 별칭 설정
analyze_msds = process_pdf
