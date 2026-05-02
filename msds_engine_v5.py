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

if not OPENAI_API_KEY:
    print("경고: .env 파일에 OPENAI_API_KEY가 없습니다.")

VERSION = "17.2.1"

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

PROMPT_GPT_FALLBACK = """
당신은 파괴된 표를 긁어모으는 2차 불도저(Bulldozer)입니다. 첨부된 이미지의 표에서 데이터를 '눈에 보이는 그대로' 복사하세요. 

[🔥 불도저 단순 추출 절대 원칙]
1. 유효한 CAS 번호(형식: 숫자-숫자-숫자)가 없는 성분(영업비밀, -, 빈칸 등)은 억지로 추출하지 말고 무조건 제외하라.
2. 생각 금지: 부등호(<, >, ≤, ≥)를 임의로 범위(~)로 바꾸거나, 그 반대로 조작하지 마세요. 
3. 다중 CAS 통합: 한 칸에 여러 CAS가 뭉쳐 있으면 슬래시(/)로 묶어서 한 줄로 퍼 오세요.
4. 페이지 트래킹: 각 성분이 발견된 이미지의 실제 페이지 번호를 'page' 필드에 기재하세요.

JSON 출력 포맷:
{
  "구성성분": [
    {"cas_no": "123-45-6 / 789-01-2", "content": "10 미만", "page": "3"}
  ],
  "교정_사유": "원본 텍스트 무가공 복사"
}
"""

def _get_sorted_and_normalized_text(page):
    try:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (b[1], b[0]))
        text = "\n".join([b[4] for b in blocks if len(b) >= 5])
        return unicodedata.normalize('NFKC', text)
    except:
        return unicodedata.normalize('NFKC', page.get_text())

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

def _normalize_single_content(content_str):
    content_str = str(content_str).strip()
    content_str = re.sub(r'([\d\.]+)\s*(<)', r'>\1', content_str)
    content_str = re.sub(r'([\d\.]+)\s*(>)', r'<\1', content_str)
    content_str = re.sub(r'(?i)잔량|balance|remainder|残量', 'Rem.', content_str)
    content_str = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(미만|below|less\s*than|未満)', r'<\1', content_str)
    content_str = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(이하|up\s*to|以下)', r'≤\1', content_str)
    content_str = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(초과|more\s*than|over|超)', r'>\1', content_str)
    content_str = re.sub(r'(?i)([0-9.]+)\s*(?:%?)\s*(이상|above|以上)', r'≥\1', content_str)

    if re.search(r'\d$', content_str): content_str += '%'
    v = content_str.replace(" ", "")
    v = re.sub(r'\([^)]*[A-Za-z가-힣][^)]*\)', '', v)
    v = re.sub(r'(?i)\(w/w\)|\(v/v\)|\(w/v\)|\(weight/weight\)|proprietary|secret', '', v)
    if re.search(r'(?i)(mg/m3|mg/l|g/l|ppm|kg|ml|µg|ug)', v): return "미기재%"

    v = v.replace('＜', '<').replace('＞', '>')
    v = v.replace('<=', '≤').replace('>=', '≥')
    v = re.sub(r'\.0+(?=[^\d]|$)', '', v)

    weird_range = re.match(r'^([≥>]*)([0-9.]+)(?:%?)([≤<]*)([0-9.]+)(?:%?)$', v)
    if weird_range:
        p1, n1, p2, n2 = weird_range.groups()
        if p1 and p2: return f"{n1}~{n2}%"
        
    range_m = re.match(r'^([<>≤≥]*)([0-9.]+)[%]*[-~]([<>≤≥]*)([0-9.]+)[%]*$', v)
    if range_m:
        p1, n1, p2, n2 = range_m.groups()
        p1_clean = p1.replace('≥', '').replace('>', '').replace('≤', '').replace('<', '')
        p2_clean = p2.replace('≤', '').replace('≥', '').replace('>', '') 
        return f"{p1_clean}{n1}~{p2_clean}{n2}%"
        
    if "Rem" in v: return "Rem.%" if "%" not in v else v
    single_m = re.match(r'^([<>≤≥]?)([0-9.]+)%?$', v)
    if single_m:
        p, n = single_m.groups()
        return f"{p}{n}%"
    return "미기재%"

def final_quality_control(components, full_text, is_ai=True, log_func=None):
    """[V17.2.1] Fuzzy Shield 3단계 적용 Grounding"""
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
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
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
    t = text.replace(" ", "")
    if any(k in t.lower() for k in ["balance", "잔량", "rem"]): return "Rem.%"
    return t

def parse_row_robust_v2(row):
    cells = [re.sub(r'\s+', ' ', (c.text or "")).strip() for c in row.cells if (c.text or "").strip()]
    if len(cells) < 2: return None

    # 🚨 [수술 4] 헤더 방어막 특수문자 제거 정규식 강화
    header_keywords = {"cas", "casno", "cas번호", "cas-no", "함유량", "함량", "content", "구성성분", "화학물질명", "substance", "물질명", "명칭"}
    cell_lower_set = {re.sub(r'[\s\(\)\.%]', '', c.lower()) for c in cells}
    if cell_lower_set.intersection(header_keywords): return None

    cas_list, content, name_candidates = [], None, []

    for c in cells:
        found_cas = re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', c)
        if found_cas:
            cas_list.extend(found_cas)
            continue
        if re.search(r'\d', c) and (any(k in c for k in ['%', '~', '-', '<', '>', '≤', '≥', 'Rem']) or len(c) <= 7):
            if not content and not re.match(r'^\d{4}[./-]\d{2}[./-]\d{2}$', c):
                content = _clean_content_odl(c)
                continue
        if len(c) > 1 and not re.match(r'^[\d\s.,\-~]+$', c):
            name_candidates.append(c)

    if not cas_list: return None

    name = ""
    if name_candidates:
        valid_names = [n for n in name_candidates if len(n) < 50]
        name = max(valid_names, key=len) if valid_names else name_candidates[0]

    final_comps = []
    for cas in cas_list:
        final_comps.append({
            "name": name,
            "cas_no": cas,
            "content": content or "미기재%",
            "engine": "ODL-v2.1" # 🚨 [수술 5] DNA 꼬리표 부착 (ODL)
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

# 🚨 [수술 6] 쓸모없는 데드 코드(fallback_text_extraction) 완벽 소각 완료!

def process_pdf(pdf_path, log_func=None):
    start_time = time.time()
    current_sniper = get_next_sniper()
    alias = current_sniper["alias"] if current_sniper else "알수없음"
    
    if log_func: log_func(f" 🚀 [V17.2.1] 엔진 가동: {os.path.basename(pdf_path)}")

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
    
    # 🚨 지연 정찰 연계: ODL이 아무것도 못 찾았는데 target_pages는 있었다면 스캔본 확률 높음
    if pure_odl_cas > 0:
        if log_func: log_func(f" 🟢 ODL 정밀 추출 성공 ({len(odl_components)}건). AI 생략.")
        ai_res = {"구성성분": odl_components, "교정_사유": "ODL 정밀 추출 완료"}
        used_engine = "ODL-Regex"
        is_ai_extracted = False
    else:
        if log_func: log_func(f" 🟡 ODL 탐지 0건(표 없음/스캔본). AI 비전 스나이퍼({alias}) 투입!")
        ai_res = call_gemini_2_5_flash(image_list, PROMPT_GEMINI_FLASH, current_sniper, log_func)
        used_engine = "Gemini-Flash"
        is_ai_extracted = True
        
        # 🚨 [수술 5] DNA 꼬리표 부착 (Gemini)
        if ai_res and "구성성분" in ai_res:
            for c in ai_res["구성성분"]: c["engine"] = used_engine
            pure_cas_count = sum(1 for c in ai_res.get("구성성분", []) if re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', str(c.get("cas", "") or c.get("cas_no", ""))))
        else: pure_cas_count = 0
            
        if not ai_res or "구성성분" not in ai_res or pure_cas_count == 0:
            if log_func: log_func(" ├─ [Step 3] AI Bulldozer (GPT-4o-mini) 복구 투입...")
            ai_res = call_gpt_4o_mini(image_list, PROMPT_GPT_FALLBACK, log_func=log_func)
            used_engine = "GPT-4o-mini"
            is_ai_extracted = True
            
            # 🚨 [수술 5] DNA 꼬리표 부착 (GPT)
            if ai_res and "구성성분" in ai_res:
                for c in ai_res["구성성분"]: c["engine"] = used_engine
                pure_cas_count = sum(1 for c in ai_res.get("구성성분", []) if re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', str(c.get("cas", "") or c.get("cas_no", ""))))
            else: pure_cas_count = 0
                
            if not ai_res or "구성성분" not in ai_res or pure_cas_count == 0:
                if log_func: log_func(" ❌ AI 엔진마저 추출 실패 (수동 검토 대상)")
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
    
    if log_func: log_func(f" ✅ [V17.2.1] 완료 (엔진: {used_engine}, 소요시간: {time.time()-start_time:.2f}초)")
    return res_obj

analyze_msds = process_pdf

def self_test_regression():
    assert _normalize_single_content("≥95%≤100%") == "95~100%", "회귀 오류: 양방향 부등호 파괴"
    assert _normalize_single_content("77.08g") == "미기재%", "회귀 오류: 단위(g) 환각 필터 파괴"
    print("[OK] V17.2.1 엔진 자가 검증 완료.")

self_test_regression()
