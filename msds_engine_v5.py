import os
import base64
import sys
import re
import time
from itertools import cycle
import json
import fitz 
import unicodedata
import requests
from opendataloader.pdf import PDFParser
import msds_utils_v3
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

api_keys_raw = [
    os.getenv("MSDS_GOOGLE_API_KEY_1"),
    os.getenv("MSDS_GOOGLE_API_KEY_2"),
    os.getenv("MSDS_GOOGLE_API_KEY_3"),
    os.getenv("MSDS_GOOGLE_API_KEY_4")
]

valid_snipers = []
for i, key in enumerate(api_keys_raw, 1):
    if key:
        valid_snipers.append({"alias": f"스나이퍼-{i}", "key": key})

if not valid_snipers:
    legacy_key = os.getenv("MSDS_GOOGLE_API_KEY")
    if legacy_key:
        valid_snipers = [{"alias": "스나이퍼-L", "key": legacy_key}]
    else:
        print("경고: 장전된 구글 API 키가 없습니다! .env를 확인하세요.")

sniper_pool = cycle(valid_snipers) if valid_snipers else None
_sniper_cooldown = {} 
_sniper_round_robin_idx = 0

def get_next_sniper():
    global _sniper_round_robin_idx
    if not valid_snipers: return None
    now = time.time()
    n = len(valid_snipers)
    for _ in range(n):
        idx = _sniper_round_robin_idx % n
        _sniper_round_robin_idx += 1
        sniper = valid_snipers[idx]
        cooldown_until = _sniper_cooldown.get(sniper["alias"], 0)
        if now >= cooldown_until:
            return sniper
    earliest_alias = min(_sniper_cooldown, key=_sniper_cooldown.get)
    wait_sec = _sniper_cooldown[earliest_alias] - now
    if wait_sec > 0:
        time.sleep(wait_sec + 0.5)
    return next(s for s in valid_snipers if s["alias"] == earliest_alias)

def mark_sniper_cooldown(sniper, cooldown_sec=60):
    if sniper:
        _sniper_cooldown[sniper["alias"]] = time.time() + cooldown_sec

def verify_cas_number(cas_string):
    """[V17.3.0.2] CAS 번호 체크디지트 검증 코어"""
    if not cas_string: return False
    
    # 🚨 [중요] '영업비밀'이나 '-' 등은 검증을 통과시켜야 하므로 예외 처리
    if any(k in cas_string for k in ["영업비밀", "비공개", "Secret", "Proprietary", "빈칸", "-"]):
        return True
        
    # 순수 숫자와 하이픈만 추출
    clean_cas = re.sub(r'[^0-9-]', '', cas_string).strip()
    parts = clean_cas.split('-')
    
    if len(parts) != 3: return False
    
    try:
        check_digit = int(parts[2])
        digits = parts[0] + parts[1]
        # 체크디지트 계산 공식 적용
        total = sum(int(digit) * i for i, digit in enumerate(reversed(digits), 1))
        return (total % 10) == check_digit
    except:
        return False

def _get_sorted_and_normalized_text(page):
    """[V17.3.0.2] PyMuPDF 페이지에서 텍스트를 읽기 순서대로 정렬 및 정규화하여 추출"""
    blocks = page.get_text("blocks")
    # y좌표 -> x좌표 순으로 정렬 (읽기 순서)
    blocks.sort(key=lambda b: (b[1], b[0]))
    text_list = []
    for b in blocks:
        text_list.append(unicodedata.normalize("NFKC", b[4]))
    return "\n".join(text_list)

if not OPENAI_API_KEY:
    print("경고: .env 파일에 OPENAI_API_KEY가 없습니다.")

VERSION = "17.3.0.8"

# [V17.3.0.8] MES 마스터 데이터 로드 (사후 안내를 위한 에러 캡처 방식 적용)
MES_MASTER_MAP = {}
MES_MASTER_LOAD_ERROR = None
try:
    master_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MES_MASTER_LOOKUP.json')
    if not os.path.exists(master_path):
        MES_MASTER_LOAD_ERROR = f"마스터 데이터 파일이 존재하지 않습니다: {master_path}"
    else:
        with open(master_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            items_list = data.get("master_list", []) if isinstance(data, dict) and "master_list" in data else []
            if not items_list:
                MES_MASTER_LOAD_ERROR = "JSON 파일 내에 'master_list' 배열이 없거나 데이터가 비어 있습니다."
            else:
                for info in items_list:
                    cas_raw = str(info.get("CAS번호", "")).strip()
                    cas = re.sub(r'^0+', '', cas_raw)
                    std_name = info.get("물질명") or info.get("상용명")
                    if cas and std_name:
                        MES_MASTER_MAP[cas] = std_name.strip()
except Exception as e:
    MES_MASTER_LOAD_ERROR = f"마스터 DB 초기화 중 오류 발생: {e}"



EXCEPTION_REGISTRY = {
    "CR-13_SERIES": {
        "triggers": ["연강용 피복아크 용접봉", "CS-200", "CR-13"],
        "target_pn": "용접재료(연강용 피복아크 용접봉) CR-13",
        "target_substances": "용접흄; 산화철(분진, 흄); 망간 및 그 무기화합물; 이산화티타늄",
        "components": "13463-67-7(10~15%); 68476-25-5(5~10%); 7439-96-5(1~5%); 1344-09-8(1~5%); 1317-65-3(1~5%); 12001-26-2(1~5%); 7439-89-6(Rem.%)"
    }
}

def call_gemini_with_retry(payload, initial_sniper, max_retries=8, log_func=None):
    current_sniper = initial_sniper
    for attempt in range(max_retries):
        if not current_sniper:
            raise ValueError("🚨 전담 스나이퍼가 배정되지 않았습니다.")
            
        api_key = current_sniper["key"]
        alias = current_sniper["alias"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        try:
            response = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=60)
            if response.status_code != 200:
                if log_func: log_func(f"  🔴 {alias} 사격 실패(HTTP {response.status_code})")
                if response.status_code == 429: mark_sniper_cooldown(current_sniper, 60)
                elif response.status_code == 503: mark_sniper_cooldown(current_sniper, 30)
                
                backoff_time = 1.0 + attempt
                time.sleep(backoff_time)
                current_sniper = get_next_sniper()
                continue
            return response.json()
        except requests.exceptions.RequestException as e:
            mark_sniper_cooldown(current_sniper, 30)
            backoff_time = 1.0 + attempt
            time.sleep(backoff_time)
            current_sniper = get_next_sniper()
            continue
    raise Exception(f"🚨 {max_retries}회 연속 사격 실패. 불도저(GPT) 투입!")

def extract_product_name_hybrid(text_chunk, image_list, current_sniper, log_func=None):
    if not current_sniper or not image_list: return "", "실패"
    first_page_img = image_list[0]
    b64_data = first_page_img.get("data", "") if isinstance(first_page_img, dict) else first_page_img
    mime_type = first_page_img.get("mime_type", "image/jpeg") if isinstance(first_page_img, dict) else "image/jpeg"

    prompt = """
    너는 MSDS의 제품명을 정확히 확정 짓는 전문 판독관이다. 
    1. [구역 격리]: "1. 화학제품과 회사에 관한 정보" 항목을 찾고 그 아래부터 "2. 유해성·위험성" 전까지만 읽어라.
    2. [핵심 타격]: '가. 제품명', '상품명', '품명' 등의 레이블이 가리키는 [순수 제품명]만 정확히 추출하라. 
    불필요한 텍스트는 제거하고 오직 '제품명' 문자열만 딱 한 줄로 출력하라. 못 찾겠으면 아무것도 출력하지 마라.
    """
    payload = {"contents": [{"parts": [{"text": prompt}, {"inlineData": {"mimeType": mime_type, "data": b64_data}}]}]}
    try:
        result = call_gemini_with_retry(payload, current_sniper, log_func=log_func)
        if result:
            pn_ai = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if pn_ai and not any(k in pn_ai for k in ["미추출", "확인"]) and not re.search(r'[PH]\d{3}', pn_ai):
                if log_func: log_func(f" ├─ [제품명 스캔] ✅ 비전 스나이핑 성공: {pn_ai[:30]}")
                return pn_ai.replace('\n', ' ').strip(), "Vision"
    except Exception as e:
        pass
    return "", "실패"

def load_system_prompt():
    prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_system_v5.txt')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return "당신은 MSDS 데이터 추출 전문가입니다."

SYSTEM_PROMPT_TEXT = load_system_prompt()

# 🚨 [수술 1] 찌꺼기 프롬프트 정리 (정책 동기화: CAS 없으면 추출 거부)
PROMPT_GEMINI_FLASH = """
당신은 1차 고속 시각 추출기(Sniper)입니다. 첨부된 MSDS 표 이미지만 보고 데이터를 추출하세요.

[🔥 1차 엔진 절대 원칙]
1. 유효한 CAS 번호(형식: 숫자-숫자-숫자)가 없는 성분(영업비밀, -, 빈칸 등)은 억지로 추출하지 말고 무조건 행 전체를 제외하라.
2. 다중 CAS 단일 문자열화: 한 셀에 여러 CAS가 있다면 슬래시(/)로 묶어서 추출하라.
3. 환각 금지: 표에 없는 숫자를 지어내지 마라. CAS는 있는데 함유량 칸이 비어있다면 함유량을 '미기재%'로 출력하라.
4. 부등호 범위 조작 금지: 원본에 '0.1-1' 이면 '0.1~1%'로, 눈에 보이는 그대로 추출하라.
5. 함유량 포맷: 모든 함유량 뒤에는 반드시 '%'를 붙여라.
"""

PROMPT_GPT_FALLBACK = """당신은 파괴된 표를 긁어모으는 2차 불도저(Bulldozer)입니다. 첨부된 이미지의 표에서 데이터를 '눈에 보이는 그대로' 단순 무식하게 복사하세요. 

[🔥 불도저 단순 추출 4대 원칙]
1. 생각 금지: % 기호 붙이기, 부등호 교정, '잔량'을 'Rem.%'로 바꾸기 등 어떠한 가공이나 번역도 하지 마세요. 후속 엔진이 알아서 합니다. 표에 적힌 글씨를 그대로 타이핑하세요.
2. 영업비밀 및 공란 통과: CAS 번호 칸에 번호가 없고 '영업비밀', '-', '비공개' 등이 적혀있다면, 버리지 말고 그 글자를 그대로 `cas_no`에 적어오세요.
3. 다중 CAS 통합: 한 칸에 CAS 번호가 여러 개 뭉쳐 있으면 행을 나누지 말고, 띄어쓰기나 슬래시(/)로 묶어서 한 줄로 다 퍼 오세요.
4. 페이지 트래킹: 각 성분이 발견된 이미지의 실제 페이지 번호를 'page' 필드에 기재하세요.

[🔥 2차 엔진 절대 원칙]
1. 공간 지각 복구: 표의 선이 투명하거나, 미세하게 틀어졌거나, 비대칭 다중 병합이 있더라도 표의 전체적인 맥락을 입체적으로 읽어 CAS와 함유량을 매칭하세요.
2. 🚨 절대 폐기 및 시각적 팩트 주의: 표에 명시된 숫자로 된 CAS 번호(형식: 숫자-숫자-숫자)만 추출하라. 화학 물질명이나 문맥을 보고 네가 아는 화학 지식을 동원하여 실존하는 CAS 번호를 유추하거나 지어내는(Hallucination) 행위는 절대 금지한다. 눈에 명확히 보이는 번호가 없거나 '영업비밀', '비공개', '-' 등이라면 가차 없이 그 행을 추출 대상에서 폐기하라.
3. 🚨 포맷 통일 및 환각 방지: 추출된 함유량 숫자 뒤에는 반드시 '%' 기호를 붙여라. 단, 원본 표에 함유량이 숫자가 아닌 '잔량', '나머지', 'balance', '적량' 등으로 표기되어 있다면, 절대 본인 마음대로 숫자(예: 10%)를 지어내거나 계산해서 적지 마라. 무조건 영문 대소문자를 맞춰 'Rem.%' 라는 문자열 그대로 출력하라.
   🚨 부등호 훼손 절대 금지: 원본 표의 함유량에 부등호(<, ≤)나 텍스트(미만, 이하)가 포함되어 있다면, 이를 절대 물결표(~) 범위 기호로 바꾸지 마라.
   [올바른 예시]: 원본이 '<1' 이면 '<1%'로 출력, 원본이 '≤1' 이면 '≤1%'로 출력.
   [잘못된 예시]: 원본이 '<1' 인데 '~1%'로 변조하여 출력 (절대 금지).

4. 🚨 페이지 트래킹: 각 성분이 발견된 페이지 번호를 'page' 필드에 기재하라.
 
 JSON 출력 포맷:
 {
   "구성성분": [
     {"cas_no": "123-45-6 / 영업비밀", "content": "10 미만", "page": "3"}
   ],
   "교정_사유": "단순 무식 원본 텍스트 복사 및 심층 복구 완료"
 }"""

def _normalize_single_content(content_str):
    """[V17.3.0.4] 부등호 정밀 복구 및 단위(g) 환각 방지"""
    raw = str(content_str).strip()
    if not raw: return "미기재%"

    # 🚨 [V17.3.0.4] 단위(g, mg 등)가 포함된 수치는 함유량으로 인정하지 않음 (환각 방지)
    # 단, % 기호가 있거나 Rem, Balance 같은 키워드는 허용
    if re.search(r'\d\s*[a-zA-Z]+', raw) and '%' not in raw and not any(k in raw.lower() for k in ["rem", "balance"]):
        return "미기재%"

    # 1. 기초 정규화 (공백 제거 및 전각 -> 반각)
    v = raw.replace(" ", "").replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')
    
    # 🚨 [V17.3.0.5] 전역 키워드 스캔: 기호 정밀 구분 (OCR 오인식 '맊' 등 대응)
    sym_less = "<" if re.search(r'(<|미\s*[만맊먄]|below|less)', v, re.I) else ("≤" if re.search(r'(≤|이\s*[하핚]|up\s*to)', v, re.I) else "")
    sym_more = ">" if re.search(r'(>|초\s*과|more|over)', v, re.I) else ("≥" if re.search(r'(≥|이\s*상|above|from)', v, re.I) else "")


    # 2. 특수 키워드 (잔량 등)
    if any(k in v.lower() for k in ["balance", "잔량", "rem"]): return "Rem.%"
    
    # 3. ± 범위 처리
    pm_match = re.search(r'([0-9.]+)\s*(?:±|\+\s*-\s*|\+/?-)\s*([0-9.]+)', v)
    if pm_match:
        try:
            val, pm = float(pm_match.group(1)), float(pm_match.group(2))
            return f"{val-pm:g}~{val+pm:g}%"
        except: pass

    # 4. 수치 추출 및 부등호 결합
    nums = re.findall(r'(\d+\.?\d*|\.\d+)', v)
    
    if len(nums) >= 2:
        try:
            f1, f2 = float(nums[0]), float(nums[1])
            if f1 > f2: f1, f2 = f2, f1
            n1_s, n2_s = (int(f1) if f1.is_integer() else f1), (int(f2) if f2.is_integer() else f2)
            
            # [규칙] ≥A ≤B 형태는 표준 범위 A~B%로 변환
            if sym_more == "≥" and sym_less == "≤": return f"{n1_s}~{n2_s}%"
            
            # 범위형 부등호 결합 (미만 기호 보존)
            p2 = sym_less if sym_less else ""
            return f"{n1_s}~{p2}{n2_s}%"
        except: pass
    elif len(nums) == 1:
        try:
            f1 = float(nums[0])
            if f1 <= 100:
                n1_s = int(f1) if f1.is_integer() else f1
                prefix = sym_less if sym_less else (sym_more if sym_more else "")
                return f"{prefix}{n1_s}%"
        except: pass

    return "미기재%"

def final_quality_control(components, full_text, is_ai=True, log_func=None):
    """[V17.3.0.2] Fuzzy Shield 3단계 적용 Grounding"""
    refined_dict = {}  
    has_invalid = False
    norm_text = re.sub(r'\s+', '', full_text).upper() if full_text else ""
    
    for comp in components:
        raw_cas_field = str(comp.get("cas", "") or comp.get("cas_no", "")).strip()
        cas_list = re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', raw_cas_field)
        
        if not cas_list: continue

        raw_content = str(comp.get("content", "")).strip()
        content_parts = [_normalize_single_content(c) for c in re.split(r'\s*/\s*', raw_content) if c.strip()]
        page_val = comp.get("page", "")
        origin_engine = comp.get("engine", "Unknown") # DNA 꼬리표 유지
        
        loop_content = content_parts if len(cas_list) == len(content_parts) else [content_parts[0] if content_parts else ""] * len(cas_list)
        
        for cas_raw, cv in zip(cas_list, loop_content):
            cas = re.sub(r'^0+', '', cas_raw)
            if not verify_cas_number(cas):
                has_invalid = True
                continue
                
            if is_ai and norm_text:
                # 1단계: 엄격 매칭 (Strict)
                if cas not in norm_text:
                    # 2단계: 하이픈 제거 매칭 (Soft)
                    cas_no_hyphen = cas.replace('-', '')
                    norm_text_no_hyphen = norm_text.replace('-', '')
                    
                    if cas_no_hyphen not in norm_text_no_hyphen:
                        # 🚨 [수술 2] 3단계: Fuzzy Shield (OCR 노이즈 강제 치환 매칭)
                        fuzzy_trans = str.maketrans('SOIlBZsbo', '501182560')
                        fuzzy_text = norm_text_no_hyphen.translate(fuzzy_trans)
                        fuzzy_cas = cas_no_hyphen.translate(fuzzy_trans)
                        
                        if fuzzy_cas not in fuzzy_text:
                            if log_func: log_func(f" ⚠️ [Grounding 방어] 3단계 퍼지 쉴드 붕괴. 환각 CAS 영구 폐기: {cas}")
                            has_invalid = True
                            continue # 퍼지도 실패하면 사살!

            if cv:
                if cas not in refined_dict:
                    refined_dict[cas] = {"cas": cas, "content": cv, "page": page_val, "engine": origin_engine}

    refined = list(refined_dict.values()) 
    if is_ai:
        try: check_omission(full_text, refined)
        except ValueError as e:
            if log_func: log_func(f" 🟡 [누락 감지] {e}")
            has_invalid = True 
        
    return refined, has_invalid

def find_section3_pages(doc):
    pages = []
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        if re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:구성|성분|함유|COMPOSITION|INGREDIENTS)', text, re.I):
            if i not in pages: pages.append(i)
        if pages and re.search(r'(?:SECTION\s*)?[34][\s.:]*(?:응급|유해성|위험성|FIRST|HAZARDS)', text, re.I):
            if i not in pages: pages.append(i)
            break 
    return pages

def extract_section3_images(pdf_path, current_sniper, log_func=None):
    try:
        doc = fitz.open(pdf_path)
        pages = find_section3_pages(doc)
        
        # 🚨 [수술 3] 지연 정찰(Lazy Recon) 트랩: 텍스트로 못 찾으면 스캔본으로 간주하고 비전 정찰 투입
        if not pages:
            if log_func: log_func(" 🔍 텍스트 탐지 실패 (또는 스캔본). 비전 정찰병(Recon) 가동...")
            recon_images = []
            for i in range(min(5, len(doc))):
                pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.8, 0.8))
                recon_images.append({"mimeType": "image/png", "data": base64.b64encode(pix.tobytes("png")).decode("utf-8")})
            
            recon_res = call_gemini_2_5_flash(recon_images, prompt="이 이미지들 중 '2. 구성성분' 또는 '3. 구성성분' 표가 있는 페이지 번호(0부터 시작)를 찾아라. JSON응답: {\"page_index\": 숫자}", current_sniper=current_sniper, log_func=log_func)
            page_idx = int(recon_res.get("page_index", -1)) if recon_res else -1
                
            if 0 <= page_idx < len(doc):
                pages = [page_idx, page_idx + 1] if page_idx + 1 < len(doc) else [page_idx]
                if log_func: log_func(f" 🎯 정찰병이 페이지를 찾았습니다: {pages}번 바인딩")
            else:
                doc.close()
                return [], "", []

        images, raw_text = [], ""
        for p_idx in pages:
            if p_idx >= len(doc): continue
            page = doc[p_idx]
            raw_text += _get_sorted_and_normalized_text(page) + "\n"
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            images.append({"mimeType": "image/png", "data": base64.b64encode(pix.tobytes("png")).decode("utf-8")})
            if len(images) >= 3: break
            
        doc.close()
        
        section3_text_only = raw_text
        start_m = re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:구성|COMPOSITION)', raw_text, re.I)
        if start_m:
            end_m = re.search(r'(?:SECTION\s*)?[34][\s.:]*(?:응급|유해성|위험성|FIRST|HAZARDS)', raw_text[start_m.end():], re.I)
            section3_text_only = raw_text[start_m.start():start_m.end() + end_m.start()] if end_m else raw_text[start_m.start():]

        return images, section3_text_only, pages 
    except Exception:
        return [], "", []

def call_gemini_2_5_flash(image_list=None, prompt=None, current_sniper=None, log_func=None):
    if not image_list or not current_sniper: return None
    final_prompt = prompt if prompt else PROMPT_GEMINI_FLASH
    parts = [{"text": f"{SYSTEM_PROMPT_TEXT}\n\n{final_prompt}"}]
    for img in image_list:
        parts.append({"inlineData": {"mimeType": "image/png", "data": img.get("data", "")}})
    payload = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}}
    try:
        result = call_gemini_with_retry(payload, current_sniper, log_func=log_func)
        if result:
            text_response = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return json.loads(text_response)
    except: pass
    return None

def check_omission(original_text, extracted_data):
    if not original_text: return 
    cas_pattern = re.compile(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])')
    unique_cas_found = list(set(cas_pattern.findall(original_text)))
    valid_original_cas = [cas for cas in unique_cas_found if verify_cas_number(cas)]
    original_cas_count = len(valid_original_cas)
    
    extracted_cas_set = set()
    for c in (extracted_data if isinstance(extracted_data, list) else extracted_data.get("구성성분", [])):
        found = cas_pattern.findall(str(c.get("cas") or c.get("cas_no") or ""))
        extracted_cas_set.update([f for f in found if verify_cas_number(f)])
    
    if len(extracted_cas_set) < original_cas_count:
        raise ValueError(f"스나이퍼 누락 발생 (원본:{original_cas_count} vs 추출:{len(extracted_cas_set)}). 2차 요원 투입!")

def call_gpt_4o_mini(image_list=None, prompt=None, log_func=None):
    if not image_list or not OPENAI_API_KEY: return None
    final_prompt = prompt if prompt else PROMPT_GPT_FALLBACK
    content_list = [{"type": "text", "text": final_prompt}]
    for img in image_list:
        content_list.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img.get('data', '')}"}})
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "system", "content": SYSTEM_PROMPT_TEXT}, {"role": "user", "content": content_list}], "temperature": 0.0, "response_format": {"type": "json_object"}}
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}, json=payload, timeout=60)
        if response.status_code == 200: return json.loads(response.json()["choices"][0]["message"]["content"])
    except: pass
    return None

def _clean_content_odl(text):
    if any(k in str(text).lower() for k in ["balance", "잔량", "rem"]): return "Rem.%"
    return text

def parse_row_robust_v2(row):
    """[V17.3.0.2] 대청소 통합본 (세포 분열 및 하이픈/소수점 복구)"""
    cells = [re.sub(r'\s*\n\s*', ' __SPLIT__ ', (c.text or "")).strip() for c in row.cells if (c.text or "").strip()]
    if len(cells) < 2: return None

    header_keywords = {"cas", "casno", "cas번호", "cas-no", "함유량", "함량", "content", "구성성분", "화학물질명", "substance", "물질명", "명칭"}
    cell_lower_set = {re.sub(r'[\s\(\)\.%\|_]', '', c.lower()) for c in cells}
    if cell_lower_set.intersection(header_keywords): return None

    cas_list, name_candidates = [], []
    strong_content, weak_content = None, None

    # 🚨 [V17.3.0.2] Backward Scan: 함유량 칸은 보통 뒤쪽에 있으므로 역순 탐색하여 하이재킹 방지
    for raw_cell in reversed(cells):
        sub_cells = raw_cell.split('__SPLIT__')
        
        for c in sub_cells:
            c = c.strip()
            if not c: continue

            # 🚨 [V17.3.0.2] 더 강력한 CAS/관리번호 제거 (자릿수 제한 해제)
            found_cas = re.findall(r'(?<![\d-])(\d+-\d+-\d+)(?![\d-])', c)
            if found_cas:
                cas_list.extend(found_cas)
                c_remain = re.sub(r'(?<![\d-])(\d+-\d+-\d+)(?![\d-])', '', c).strip()
                if not c_remain: continue
                c = c_remain

            # 🚨 [V17.3.0.5] 줄바꿈 유실 방지: 개별 줄에 기호가 없더라도 셀 전체에 부등호가 있다면 합쳐서 재분석
            norm_c = _normalize_single_content(c)
            if norm_c != "미기재%":
                if any(k in c for k in ['%', '~', '∼', '～', '-', '–', '—', '.', '<', '>', '≤', '≥', 'Rem', '잔량', 'balance', '미만', '이하', '초과', '이상']):
                    if not strong_content:
                        # [패치] 숫자와 기호가 줄바꿈으로 분리된 경우(예: 0.1~1 \n 미만) 보정
                        merged_text = raw_cell.replace('__SPLIT__', ' ')
                        if any(k in merged_text for k in ['<', '>', '≤', '≥', '미만', '이하', '초과', '이상']) and not any(k in c for k in ['<', '>', '≤', '≥', '미만', '이하', '초과', '이상']):
                            norm_c = _normalize_single_content(merged_text)
                        strong_content = _clean_content_odl(norm_c)
                else:
                    try:
                        clean_weak = float(re.sub(r'[^\d.]', '', norm_c))
                        if clean_weak <= 100 and not weak_content: 
                            weak_content = _clean_content_odl(norm_c)
                    except: pass
                continue

            if len(c) > 1 and not re.match(r'^[\d\s.,\-~]+$', c):
                name_candidates.append(c)

    if not cas_list: return None

    name = ""
    if name_candidates:
        valid_names = [n for n in name_candidates if len(n) < 50]
        name = max(valid_names, key=len) if valid_names else name_candidates[0]

    final_content = strong_content or weak_content or "미기재%"

    final_comps = []
    for cas in cas_list:
        final_comps.append({
            "name": name,
            "cas_no": cas,
            "content": final_content,
            "engine": "ODL-v2.9_Final" 
        })
    return final_comps

def extract_components_odl_robust(odl_doc, target_pages):
    components = []
    if not target_pages or not odl_doc or not odl_doc.pages: return components

    for p_idx in target_pages:
        if p_idx >= len(odl_doc.pages): continue
        tables = [el for el in getattr(odl_doc.pages[p_idx], 'elements', []) if getattr(el, 'type', '') == "TABLE"]
        for table in tables:
            for row in table.rows:
                parsed_comps = parse_row_robust_v2(row)
                if parsed_comps: components.extend(parsed_comps)
    return components

def process_pdf(pdf_path, log_func=None):
    start_time = time.time()
    current_sniper = get_next_sniper()
    alias = current_sniper["alias"] if current_sniper else "알수없음"
    
    if log_func: log_func(f" 🚀 [{VERSION}] 엔진 가동: {os.path.basename(pdf_path)}")

    image_list, section3_text, pages = extract_section3_images(pdf_path, current_sniper, log_func=log_func)
    
    full_text_for_grounding = ""
    try:
        doc = fitz.open(pdf_path)
        first_page_text = _get_sorted_and_normalized_text(doc[0]) if len(doc) > 0 else ""
        for page in doc: full_text_for_grounding += _get_sorted_and_normalized_text(page)
        pix_cover = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        cover_img = [{"mimeType": "image/png", "data": base64.b64encode(pix_cover.tobytes("png")).decode("utf-8")}]
        doc.close()
    except:
        cover_img, first_page_text, full_text_for_grounding = image_list, "", ""
        
    hybrid_pn, _ = extract_product_name_hybrid(first_page_text, cover_img, current_sniper, log_func=log_func)

    used_engine = ""
    is_ai_extracted = False
    ai_res = None
    
    doc_t = fitz.open(pdf_path)
    target_pages = find_section3_pages(doc_t) 
    doc_t.close()

    try:
        parser = PDFParser()
        odl_doc = parser.parse(pdf_path)
        odl_components = extract_components_odl_robust(odl_doc, target_pages)
    except Exception as e:
        if log_func: log_func(f" ⚠️ ODL 파싱 오류: {e}")
        odl_components = []
    
    pure_odl_cas = sum(1 for c in odl_components if re.search(r'\d-\d', str(c.get("cas", "") or c.get("cas_no", ""))))
    # 🚨 [패치 핵심 1] ODL 함량 유효성 검증 복구 (2.5 Flash 시대에 맞춰 필수)
    valid_odl_contents = sum(1 for c in odl_components if str(c.get("content", "")) not in ["", "미기재%"])
    
    # 🚨 ODL이 CAS와 함량을 모두 정상적으로 찾았을 때만 성공으로 인정 (스마트 폴백)
    if pure_odl_cas > 0 and valid_odl_contents > 0:
        if log_func: log_func(f" 🟢 ODL 정밀 추출 성공 ({len(odl_components)}건). AI 생략.")
        ai_res = {"구성성분": odl_components, "교정_사유": "ODL 정밀 추출 완료"}
        used_engine = "ODL-Regex"
        is_ai_extracted = False
    else:
        if log_func: log_func(f" 🟡 ODL 탐지 0건 또는 함량 누락. AI 비전 스나이퍼({alias}) 투입!")
        # 🚨 [패치 핵심 2] 프롬프트는 2.5 Flash의 파편화 인식에 대응하도록 재전달
        ai_res = call_gemini_2_5_flash(image_list, PROMPT_GEMINI_FLASH, current_sniper, log_func)
        used_engine = "Gemini-2.5-Flash"
        is_ai_extracted = True
        
        # 🚨 [지원군 모드] 스나이퍼(Gemini)가 응답 실패(None)인 경우에만 불도저(GPT) 복구 투입
        if ai_res is None:
            if log_func: log_func(f" ⚠️ {alias} 사망. 비상 지원군(GPT-4o-mini) 복구 투입...")
            ai_res = call_gpt_4o_mini(image_list, PROMPT_GPT_FALLBACK, log_func=log_func)
            used_engine = "GPT-4o-mini"
            is_ai_extracted = True
            
        # 결과 분석 (스나이퍼 또는 불도저의 결과)
        if ai_res and "구성성분" in ai_res:
            for c in ai_res["구성성분"]: c["engine"] = used_engine
            pure_cas_count = sum(1 for c in ai_res.get("구성성분", []) if re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', str(c.get("cas", "") or c.get("cas_no", ""))))
        else:
            pure_cas_count = 0
            
        if not ai_res or "구성성분" not in ai_res:
            if log_func: log_func(" ❌ AI 엔진(지원군 포함) 추출 실패 (수동 검토 대상)")
            return {"error": "전체 추출 실패 (수동 검토 필요)", "제품명": hybrid_pn, "신호등": "🔴"}

    components = ai_res.get("구성성분", [])
    reason = ai_res.get("교정_사유", "사유 없음")
    
    local_grounding_text = str(first_page_text)
    try:
        doc_g = fitz.open(pdf_path)
        for p_idx in pages:
            if p_idx != 0: local_grounding_text += "\n" + _get_sorted_and_normalized_text(doc_g[p_idx])
        doc_g.close()
    except: local_grounding_text += "\n" + str(section3_text)
    
    refined_comps, has_invalid_cas = final_quality_control(components, local_grounding_text, is_ai=is_ai_extracted, log_func=log_func)
    
    comp_parts = [f"{c['cas']}({c['content']})" for c in refined_comps]
    if not comp_parts:
        if log_func: log_func(" ❌ 유효한 성분 데이터가 존재하지 않음")
        return {"error": "AI 추출 완전 실패 (수동 검토 필요)", "제품명": hybrid_pn, "신호등": "🔴"}

    comp_str = "; ".join(comp_parts)
    product_name = hybrid_pn
    target_substances = ""
    
    norm_search_pool = re.sub(r'[\s\-]', '', product_name + " " + first_page_text[:500]).upper()
    for ext_key, ext_data in EXCEPTION_REGISTRY.items():
        if all(re.sub(r'[\s\-]', '', trigger).upper() in norm_search_pool for trigger in ext_data["triggers"]):
            product_name, comp_str, target_substances = ext_data["target_pn"], ext_data["components"], ext_data["target_substances"]
            break

    gui_engine_name = "flash" if "Gemini" in used_engine else "bulldozer" if "GPT" in used_engine else "odl"
    
    res_obj = {
        "구성성분": comp_str, "제품명": product_name, "측정대상": target_substances,
        "교정_사유": reason,
        "신호등": "🟡" if has_invalid_cas or not product_name else "🟢",
        "used_engine": gui_engine_name
    }
    
    if log_func: log_func(f" ✅ [{VERSION}] 완료 (엔진: {used_engine}, 소요시간: {time.time()-start_time:.2f}초)")
    return res_obj

analyze_msds = process_pdf

def self_test_regression():
    print(f"--- [V{VERSION}] 엔진 자가 검증 시작 ---")
    
    # 1. 부등호 및 범위 표준화 테스트
    test_cases = [
        ("0.1~1미만", "0.1~<1%", "미만(Below) 변환 유실"),
        ("0.1 - 1", "0.1~1%", "하이픈 범위 표준화 실패"),
        ("0.1 ~ < 1%", "0.1~<1%", "공백 포함 복합 범위 처리 실패"),
        ("<0.1%", "<0.1%", "단일 부등호 보존 실패"),
        ("≤ 0.1", "≤0.1%", "특수 부등호 및 공백 처리 실패"),
        ("≥95%≤100%", "95~100%", "양방향 부등호(Full Range) 표준화 실패"),
        ("1 ~ 5미만", "1~<5%", "한글 부등호 포함 범위 처리 실패"),
        ("5 ~ 1", "1~5%", "범위 역순 정렬 실패"),
        ("< 5 ~ 1", "1~<5%", "부등호 포함 역순 정렬 및 귀속 실패"),
        ("0.1 ~ < 1 / 1 ~ 5", "0.1~<1%", "다중 범위 혼입 시 첫 번째 수치 추출 실패")
    ]
    
    # 2. 단위 및 노이즈 필터링 테스트 (Hallucination 방지)
    noise_cases = [
        ("77.08g", "미기재%", "단위(g) 환각 필터 작동 실패"),
        ("100 mg/kg", "미기재%", "단위(mg/kg) 환각 필터 작동 실패"),
        ("Ethylene Glycol 50-60%", "50~60%", "Shield-Inversion(텍스트 혼입) 처리 실패"),
        ("95-100% (wt)", "95~100%", "부가 텍스트(wt) 처리 실패")
    ]
    
    # 3. 특수 키워드 테스트
    keyword_cases = [
        ("Rem.", "Rem.%", "Rem. 키워드 표준화 실패"),
        ("balance", "Rem.%", "balance 키워드 표준화 실패"),
        ("잔량", "Rem.%", "한글 '잔량' 키워드 표준화 실패")
    ]

    all_tests = test_cases + noise_cases + keyword_cases
    fail_count = 0
    
    for input_str, expected, msg in all_tests:
        actual = _normalize_single_content(input_str)
        if actual != expected:
            print(f" [FAIL] 입력: '{input_str}' -> 결과: '{actual}' (기대값: '{expected}') | 사유: {msg}")
            fail_count += 1
        else:
            print(f" [PASS] '{input_str}' -> '{actual}'")

    if fail_count > 0:
        print(f"--- [!] 검증 실패: {fail_count}건의 오류 발견 ---")
        sys.exit(1)
    else:
        print(f"--- [OK] 모든 회귀 테스트 통과 (V{VERSION}) ---")

if __name__ == "__main__":
    self_test_regression()
