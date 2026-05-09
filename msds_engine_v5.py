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

def verify_cas_number(cas_string, grounding_text=None):
    """[V17.3.2.25] CAS 번호 검증 (Grounding 우선 원칙: 문서에 적혀 있으면 체크섬 무관하게 통과)"""
    if not cas_string: return False
    
    # 🚨 [V17.3.2.2] 날짜 형식(YYYY-MM-DD)인 경우 CAS로 인정하지 않음 (오탐 방지)
    if re.match(r'^\d{4}-\d{2}-\d{2}$', cas_string):
        return False

    # 🚨 [V17.3.2.25] 문서 원본(Grounding)에 이 번호가 그대로 있다면, 오타가 있어도 수용
    if grounding_text and cas_string in grounding_text:
        return True
        
    # 🚨 [중요] '영업비밀'이나 '-' 등은 검증을 통과시켜야 하므로 예외 처리
    if any(k in cas_string for k in ["영업비밀", "비공개", "Secret", "Proprietary", "빈칸", "-", "해당없음", "None"]):
        return True
        
    # 🚨 [V17.3.2.28] 문서 원본(Grounding) 대조 시 공백 제거 후 비교 (64742 - 54 - 7 대응)
    if grounding_text:
        clean_cas = cas_string.replace(" ", "")
        clean_grounding = grounding_text.replace(" ", "")
        if clean_cas in clean_grounding:
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
    """[V17.3.2.25] PyMuPDF 페이지에서 텍스트를 읽기 순서대로 정렬 및 정규화하여 추출"""
    blocks = page.get_text("blocks")
    # y좌표 -> x좌표 순으로 정렬 (읽기 순서)
    blocks.sort(key=lambda b: (b[1], b[0]))
    text_list = []
    for b in blocks:
        text_list.append(unicodedata.normalize("NFKC", b[4]))
    return "\n".join(text_list)

if not OPENAI_API_KEY:
    print("경고: .env 파일에 OPENAI_API_KEY가 없습니다.")

VERSION = "17.3.2.30" # [V17.3.2.30] 프롬프트 관리 폴더(prompts/) 도입 버전

def load_prompt(prompt_type, version):
    """[V17.3.2.30] 프롬프트 로드 (Hierarchy Search: Root -> archive/)"""
    mapping = {
        "vision_extractor": f"prompt_vision_extractor_{version}.txt",
        "product_name": f"prompt_product_name_{version}.txt"
    }
    filename = mapping.get(prompt_type)
    if not filename: raise ValueError(f"알 수 없는 프롬프트 타입: {prompt_type}")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 🔍 탐색 순서 정의 (최신은 루트, 구버전은 archive)
    search_paths = [
        os.path.join(base_dir, filename),             # 1. 루트 (최신 버전 위치)
        os.path.join(base_dir, "archive", filename)   # 2. 아카이브 폴더 (구버전 보관)
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
                
    # 모든 경로에서 실패 시
    print(f"\n[Version Lock Error] 프롬프트 파일({filename})을 찾을 수 없습니다.")
    print(f"   현재 엔진 요구 버전: {version}")
    print(f"   탐색한 경로:")
    for p in search_paths:
        print(f"     - {p}")
    sys.exit(1)

# 프롬프트 초기화 (지휘 체계 단일화)
try:
    VISION_EXTRACTOR_PROMPT = load_prompt("vision_extractor", VERSION)
    PRODUCT_NAME_PROMPT = load_prompt("product_name", VERSION)
    print(f"[*] 프롬프트 엔진 통폐합 및 버전 동기화 완료 (버전: {VERSION})")
except Exception as e:
    print(f"[ERROR] 프롬프트 로드 중 치명적 오류: {e}")
    sys.exit(1)

# [V17.3.2.25] MES 마스터 데이터 로드 (사후 안내를 위한 에러 캡처 방식 적용)
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

    payload = {"contents": [{"parts": [{"text": PRODUCT_NAME_PROMPT}, {"inlineData": {"mimeType": mime_type, "data": b64_data}}]}]}
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

def _normalize_single_content(content_str):
    """[V17.3.2.25] 부등호 정밀 복구 및 단위(g) 환각 방지"""
    raw = str(content_str).strip()
    if not raw: return "미기재%"

    # 🚨 [V17.3.2.25] 단위(g, mg 등)가 포함된 수치는 함유량으로 인정하지 않음 (환각 방지)
    if re.search(r'\d\s*[a-zA-Z]+', raw) and '%' not in raw and not any(k in raw.lower() for k in ["rem", "balance"]):
        return "미기재%"

    # 1. 기초 정규화 (공백 제거 및 전각 -> 반각)
    v = raw.replace(" ", "").replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')
    # [V17.3.2.25] 약어 뒤의 마침표가 숫자 추출(.)을 방해하지 않도록 사전에 제거
    v = re.sub(r'(min|max)\.', r'\1', v, flags=re.I)
    
    # 🚨 [V17.3.2.25] 후위 부등호 감지 및 반전 (일본식 표현 대응: 99 < -> >99)
    has_trailing_less = re.search(r'\d\s*(<|미\s*[만맊먄]|below|less)$', v, re.I)
    has_trailing_more = re.search(r'\d\s*(>|초\s*과|more|over)$', v, re.I)
    has_trailing_le = re.search(r'\d\s*(≤|이\s*[하핚내]|up\s*to|max)$', v, re.I)
    has_trailing_ge = re.search(r'\d\s*(≥|이\s*상|above|from|min|\+)$', v, re.I)

    # 🚨 [V17.3.2.25] 전역 키워드 스캔: 기호 정밀 구분
    sym_less = "<" if re.search(r'(<|미\s*[만맊먄]|below|less)', v, re.I) else ("≤" if re.search(r'(≤|이\s*[하핚내]|up\s*to|max)', v, re.I) else "")
    sym_more = "≥" if re.search(r'(≥|이\s*상|above|from|min|\+)', v, re.I) else (">" if re.search(r'(>|초\s*과|more|over)', v, re.I) else "")

    # 2. 특수 키워드 (잔량 등)
    if any(k in v.lower() for k in ["balance", "잔량", "rem"]): return "Rem.%"
    
    # 3. ± 범위 처리
    pm_match = re.search(r'([0-9.]+)\s*(?:±|\+\s*-\s*|\+/?-)\s*([0-9.]+)', v)
    if pm_match:
        try:
            val, pm = float(pm_match.group(1)), float(pm_match.group(2))
            return f"{val-pm:g}~{val+pm:g}%"
        except: pass

    # 4. 숫자 추출
    nums = re.findall(r'(\d+\.?\d*|\.\d+)', v)
    if not nums: return raw # 숫자 없으면 원본 반환

    # 🚨 [V17.3.2.25] 후위 부등호 감지 및 반전 (일본식 표현 대응)
    if len(nums) == 1:
        if re.search(r'\d\s*<$', v): sym_less, sym_more = "", ">"
        elif re.search(r'\d\s*>$', v): sym_less, sym_more = "<", ""
        elif re.search(r'\d\s*≤$', v): sym_less, sym_more = "", "≥"
        elif re.search(r'\d\s*≥$', v): sym_less, sym_more = "≤", ""
    else:
        pass

    # 4. 수치 추출 및 부등호 결합
    if len(nums) >= 2:
        try:
            f1, f2 = float(nums[0]), float(nums[1])
            if f1 > f2: f1, f2 = f2, f1
            n1_s, n2_s = (int(f1) if f1.is_integer() else f1), (int(f2) if f2.is_integer() else f2)
            
            # [V17.3.2.25] 사용자 요청: 복수 수치가 모두 '이상' 기호(+)와 결합된 경우, 최솟값 기준 단일 '이상'으로 통합
            if sym_more and not sym_less and ("+" in v or "min" in v.lower()):
                return f"{sym_more}{n1_s}%"

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
    """[V17.3.2.25] Fuzzy Shield 3단계 적용 Grounding"""
    refined_dict = {}  
    has_invalid = False
    norm_text = re.sub(r'\s+', '', full_text).upper() if full_text else ""
    
    for comp in components:
        raw_cas_field = str(comp.get("cas", "") or comp.get("cas_no", "")).strip()
        raw_content = str(comp.get("content", "")).strip()
        
        # 🚨 [V17.3.2.29] 후처리 보정 Rule (Rule 1, 2, 4 통합 적용)
        # Rule 4: 하나라도 유효한 CAS가 섞여 있는지 정규식으로 판별
        has_any_valid_cas = bool(re.search(r'\d{2,7}-\d{2}-\d', raw_cas_field))
        
        if not has_any_valid_cas:
            # Rule 1: 무효 CAS(해당없음, 영업비밀 등)의 경우 함유량 강제 제거 (GUI AUTO-PASS 보완)
            raw_content = ""
        elif not raw_content or raw_content.strip() in ["-", "", "None", "N/A"]:
            # Rule 2: 유효 CAS가 존재함에도 함유량이 누락된 경우 '미기재%' 강제 할당
            raw_content = "미기재%"

        # 🚨 [V17.3.2.28] CAS 필드에서 공백을 제거한 뒤 정규식 적용 (64742 - 54 - 7 -> 64742-54-7)
        clean_cas_field = re.sub(r'\s+', '', raw_cas_field)
        cas_list = re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', clean_cas_field)
        
        # 🚨 [V17.3.2.28] CAS 번호가 없더라도 '영업비밀', '해당없음' 등이 있다면 행 보존 (DNA 규칙 준수)
        if not cas_list:
            if any(k in raw_cas_field for k in ["영업비밀", "비공개", "해당없음", "-", "Secret", "Proprietary"]):
                cas_list = [raw_cas_field] # 키워드 자체를 CAS로 취급하여 보존
            else:
                continue
        
        content_parts = [_normalize_single_content(c) for c in re.split(r'\s*/\s*', raw_content) if c.strip()]
        # content_parts가 비어있을 경우(Rule 1 적용 등)를 대비한 보정
        if not content_parts: content_parts = [""]
        page_val = comp.get("page", "")
        origin_engine = comp.get("engine", "Unknown") # DNA 꼬리표 유지
        
        loop_content = content_parts if len(cas_list) == len(content_parts) else [content_parts[0] if content_parts else ""] * len(cas_list)
        
        # 🚨 [V17.3.2.25] 문서 전체를 대조군으로 활용하여 누락/오타 성분 원천 방어 (노이즈 세척 포함)
        full_text = full_text.replace('̻', '').replace('̸', '')
        norm_text = re.sub(r'\s+', '', full_text).upper()
        
        for cas_raw, cv in zip(cas_list, loop_content):
            cas = re.sub(r'^0+', '', cas_raw)
            
            # 🚨 [V17.3.2.25] AI 환각 구출 작전: 체크섬 통과 전에 원본 텍스트와 대조하여 교정
            if is_ai and not verify_cas_number(cas, grounding_text=full_text):
                # 텍스트 원본에서 유효한 CAS들 추출
                valid_text_cas = re.findall(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', full_text)
                valid_text_cas = [v for v in valid_text_cas if verify_cas_number(v, grounding_text=full_text)]
                
                for v_cas in valid_text_cas:
                    # 1글자만 틀린 경우 (AI 오타 방어)
                    diff_count = sum(1 for a, b in zip(cas, v_cas) if a != b) if len(cas) == len(v_cas) else 99
                    if diff_count <= 1:
                        cas = v_cas
                        break
                else:
                    if log_func: log_func(f" 🔴 [Fuzzy 방어] 3단계 퍼지 쉴드 붕괴. 환각 CAS 영구 폐기: {cas}")
                    has_invalid = True
                    continue 

            if cv:
                if cas not in refined_dict:
                    refined_dict[cas] = {
                        "cas": cas, 
                        "name": comp.get("name", ""), 
                        "content": cv, 
                        "page": page_val, 
                        "engine": origin_engine
                    }
                else:
                    # [V17.3.2.25] 함유량 업데이트 로직 강화: 기존 데이터가 없거나 미기재%인 경우 무조건 갱신
                    is_current_empty = not refined_dict[cas]["content"] or refined_dict[cas]["content"] == "미기재%"
                    if is_current_empty and cv and cv != "미기재%":
                        refined_dict[cas]["content"] = cv
                        if comp.get("name"): refined_dict[cas]["name"] = comp.get("name")
                    # 페이지 정보도 더 앞쪽(보통 3번 항목이 앞임) 페이지로 유지
                    try:
                        if page_val and (not refined_dict[cas]["page"] or int(page_val) < int(refined_dict[cas]["page"])):
                            refined_dict[cas]["page"] = page_val
                    except: pass

    refined = list(refined_dict.values()) 
    if is_ai:
        try: check_omission(full_text, refined)
        except ValueError as e:
            if log_func: log_func(f" 🟡 [누락 감지] {e}")
            has_invalid = True 
        
    return refined, has_invalid

def find_section3_pages(doc):
    """[V17.3.2.25] 섹션 탐색 조기 종료 가드 강화 (Page 번호 노이즈 차단)"""
    pages = []
    found_section3 = False
    
    # 섹션 4~9 종료 키워드 (행 시작 부분에 숫자와 함께 나타날 때만 인정)
    exit_pattern = re.compile(r'^(?:SECTION\s*)?[4-9][\s.:]*(?:응급|폭발|화재|누출|취급|저장|노출|방지|FIRST|FIRE|ACCIDENTAL|HANDLING|EXPOSURE)', re.I | re.M)
    
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        
        # 1. 섹션 3 시작 확인
        if not found_section3:
            if re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:구성성분|성분|성분\s?및\s?함량|COMPOSITION|INGREDIENTS)', text, re.I):
                found_section3 = True
        
        if found_section3:
            pages.append(i)
            # 🚨 [V17.3.2.25] 조기 종료 가드: 단순 '위험' 단어 등이 아니라, 행의 시작에서 섹션 번호가 명확할 때만 중단
            # 'Page 4 / 10' 같은 텍스트에 의한 오탐 방지를 위해 행 단위 스캔
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for line in lines:
                # 페이지 번호(Page 4...)는 제외하고 진짜 섹션 제목인 경우만
                if exit_pattern.match(line) and "Page" not in line:
                    return sorted(list(set(pages)))[:6]
                
    return sorted(list(set(pages)))[:6]

# [V17.3.2.28] 공용 정규식 패턴: CAS 번호 내 공백 허용 (\s* 추가)
cas_pattern = re.compile(r'(?<![\d-])(\d{2,7}\s*-\s*\d{2}\s*-\s*\d)(?![\d-])')
cont_pattern = re.compile(r'([<>≤≥~∼～-]?\s?\d+(?:\.\d+)?(?:\s*(?:이상|미만|~|∼|～|-|above|below|to|and|%)\s*)*[<>≤≥~∼～-]?\s?\d*(?:\.\d+)?\s*%?)', re.IGNORECASE)

def extract_from_text_regex(table_rows, log_func=None):
    """[V17.3.2.27] ODL 파싱 실패 시 정규식 기반 텍스트 추출 (보조장치)"""
    if log_func: log_func(f"  [마스킹 엔진] 텍스트 기반 정밀 추출(Regex-Recovery) 가동...")
    found = []
    
    for row in table_rows:
        if not row["cas_list"] or not row["combined_text"]: continue
        
        # [V17.3.2.25] CAS 마스킹: 함량 추출 전 CAS 번호를 숨겨서 정규식의 간섭 차단
        protected_text = row["combined_text"]
        for cas in row["cas_list"]:
            protected_text = protected_text.replace(cas, "[CAS_ANCHOR]")
            
        # [V17.3.2.27] 괄호 내 노이즈 배제 원칙 강화
        all_conts = cont_pattern.findall(protected_text)
        content = "미기재%"
        if all_conts:
            # 괄호 밖에 있는 깨끗한 후보군 추출
            outside_conts = []
            for c in all_conts:
                # 텍스트 내에서 해당 함량의 위치를 찾고, 그 주변이 괄호로 감싸여 있는지 확인
                start_idx = protected_text.find(c)
                prefix = protected_text[:start_idx]
                suffix = protected_text[start_idx + len(c):]
                # 열린 괄호가 닫힌 괄호보다 많으면 괄호 내부로 간주
                if prefix.count('(') > prefix.count(')'):
                    continue
                outside_conts.append(c)
            
            target_list = outside_conts if outside_conts else all_conts
            content = _normalize_single_content(target_list[-1])
            
        for cas in row["cas_list"]:
            if log_func: log_func(f"  [마스킹 엔진] CAS {cas} -> 함량 {content}")
            found.append({"name": "CAS 기반 자동 매핑", "cas_no": cas, "content": content, "engine": "마스킹 엔진"})
            
    return found

def extract_section3_images(pdf_path, current_sniper, log_func=None):
    try:
        doc = fitz.open(pdf_path)
        pages = find_section3_pages(doc)
        
        # 🚨 [V17.3.2.25] 지연 정찰(Lazy Recon) 트랩: 텍스트로 못 찾으면 스캔본으로 간주하고 비전 정찰 투입
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
            # [V17.3.1.7] 3페이지 제한 제거 (주님 지침: 정확한 롤백 및 누락 방지)
            if len(images) >= 6: break 
            
        doc.close()
        
        section3_text_only = raw_text
        start_m = re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:구성|COMPOSITION)', raw_text, re.I)
        if start_m:
            # [V17.3.1.7] 섹션 4 탐지 시 finditer를 사용하여 '가장 마지막' 섹션 4 위치를 찾아 데이터 유실 차단
            ends = list(re.finditer(r'(?:SECTION\s*)?[34][\s.:]*(?:응급|유해성|위험성|FIRST|HAZARDS)', raw_text[start_m.end():], re.I))
            if ends:
                last_end = ends[-1]
                section3_text_only = raw_text[start_m.start():start_m.end() + last_end.start()]
            else:
                section3_text_only = raw_text[start_m.start():]

        return images, section3_text_only, pages 
    except Exception:
        return [], "", []

def call_gemini_2_5_flash(image_list=None, prompt=None, current_sniper=None, log_func=None):
    if not image_list or not current_sniper: return None
    final_prompt = prompt if prompt else VISION_EXTRACTOR_PROMPT
    parts = [{"text": final_prompt}]
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
    # [V17.3.2.28] 누락 체크 시에도 공백 허용 패턴 사용 및 정규화 비교
    unique_cas_found = list(set(cas_pattern.findall(original_text)))
    valid_original_cas = [re.sub(r'\s+', '', cas) for cas in unique_cas_found if verify_cas_number(cas, grounding_text=original_text)]
    original_cas_count = len(valid_original_cas)
    
    extracted_cas_set = set()
    for c in (extracted_data if isinstance(extracted_data, list) else extracted_data.get("구성성분", [])):
        found = cas_pattern.findall(str(c.get("cas") or c.get("cas_no") or ""))
        extracted_cas_set.update([f for f in found if verify_cas_number(f)])
    
    if len(extracted_cas_set) < original_cas_count:
        raise ValueError(f"스나이퍼 누락 발생 (원본:{original_cas_count} vs 추출:{len(extracted_cas_set)}). 2차 요원 투입!")

def call_gpt_4o_mini(image_list=None, prompt=None, log_func=None):
    if not image_list or not OPENAI_API_KEY: return None
    final_prompt = prompt if prompt else VISION_EXTRACTOR_PROMPT
    content_list = [{"type": "text", "text": final_prompt}]
    for img in image_list:
        content_list.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img.get('data', '')}"}})
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": content_list}], "temperature": 0.0, "response_format": {"type": "json_object"}}
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}, json=payload, timeout=60)
        if response.status_code == 200: return json.loads(response.json()["choices"][0]["message"]["content"])
    except: pass
    return None

def _clean_content_odl(text):
    if any(k in str(text).lower() for k in ["balance", "잔량", "rem"]): return "Rem.%"
    return text

def parse_row_robust_v2(row, priority_col_idx=-1):
    """[V17.3.1.6] 열 우선순위(priority_col_idx) 반영 로직"""
    header_keywords = {"cas", "casno", "cas번호", "cas-no", "함유량", "함량", "content", "구성성분", "화학물질명", "substance", "물질명", "명칭", "chemicalname", "weight"}
    # [V17.3.1.8] 8번 항목(노출기준) 오인 방지를 위한 차단 키워드
    noise_keywords = {"twa", "stel", "pel", "tlv", "mg/m", "mg/㎥", "노출기준", "exposure"}
    
    raw_cells = [c.text or "" for c in row.cells]
    cell_lower_set = {re.sub(r'[\s\(\)\.%\|_]', '', c.lower()) for c in raw_cells}
    
    # 헤더이거나 노출기준 데이터라면 스킵
    if cell_lower_set.intersection(header_keywords): return None
    if any(k in "".join(raw_cells).lower() for k in noise_keywords): return None

    # [V17.3.1.5] 열 우선순위(priority_col_idx) 반영 로직
    # cells를 (index, cell_text) 튜플 리스트로 변환
    indexed_cells = []
    for i, c in enumerate(row.cells):
        # 🚨 [V17.3.2.1] 두 줄 방어: 줄바꿈을 분할이 아닌 '공백'으로 통합하여 범위(1~10%) 유실 방지
        text = re.sub(r'\s*\n\s*', ' ', (c.text or "")).strip()
        if text: indexed_cells.append((i, text))
    
    if len(indexed_cells) < 2: return None

    # 우선순위 열이 있다면 리스트의 맨 앞으로 보내서 먼저 처리되게 함
    if priority_col_idx >= 0:
        indexed_cells.sort(key=lambda x: 0 if x[0] == priority_col_idx else 1)
    else:
        # 우선순위 열이 없으면 기존처럼 뒤에서부터(CAS 우선 탐색 위해)
        indexed_cells.reverse()

    cas_list, name_candidates = [], []
    strong_content, weak_content = None, None

    for col_idx, raw_cell in indexed_cells:
        # 🚨 [V17.3.2.1] 통합된 셀 텍스트를 그대로 처리 (분할 루프 제거)
        c = raw_cell.strip()
        if not c: continue

        # 🚨 [V17.3.2.3] CAS 정규식 엄격화 (날짜 4-2-2 차단)
        found_cas = re.findall(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', c)
        if found_cas:
            cas_list.extend(found_cas)
            c_remain = re.sub(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', '', c).strip()
            if not c_remain: continue
            c = c_remain

        norm_c = _normalize_single_content(c)
        if norm_c != "미기재%" and re.search(r'\d', norm_c):
            # 🚨 [V17.3.1.2] 함유량 우선순위 서열 (주님 지침 반영)
            is_percent = '%' in c
            is_pure_num = re.match(r'^[\d\s.]+$', c.strip()) 
            is_symbol = any(k in c for k in ['~', '∼', '～', '<', '>', '≤', '≥', 'Rem', '잔량', 'balance', '미만', '이하', '초과', '이상'])
            is_range = ('-' in c or '–' in c or '—' in c) and not re.search(r'[a-zA-Z가-힣]', c)

            # 1. % 기호가 있거나 순수 숫자(99.0)면 무조건 최우선 (Strong Content)
            if is_percent or is_pure_num:
                # [V17.3.2.27] 헤더 우선순위 잠금: 현재 열이 헤더에서 지정한 함유량 열(priority_col_idx)이라면 무조건 채택
                # 다른 열(명칭 열 등)에서 나오는 데이터는 이 데이터가 없을 때만 차선책으로 사용
                is_priority_cell = (col_idx == priority_col_idx)
                
                if is_priority_cell:
                    strong_content = _clean_content_odl(norm_c)
                    break # 우선순위 열에서 찾았다면 더 이상 다른 열을 볼 필요 없음 (잠금)
                elif not strong_content:
                    strong_content = _clean_content_odl(norm_c)
            # 2. %는 없지만 확실한 부등호나 범위 기호가 있는 경우 (차선순위)
            elif not strong_content and (is_symbol or is_range):
                strong_content = _clean_content_odl(norm_c)
            else:
                try:
                    clean_val = float(re.sub(r'[^\d.]', '', norm_c))
                    if clean_val <= 100 and not weak_content: 
                        weak_content = _clean_content_odl(norm_c)
                except: pass
            continue

        if len(c) > 1 and not re.match(r'^[\d\s.,\-~]+$', c) and col_idx != priority_col_idx:
            name_candidates.append(c)

    if not cas_list: return None

    name = ""
    if name_candidates:
        valid_names = [n for n in name_candidates if len(n) < 50]
        name = max(valid_names, key=len) if valid_names else name_candidates[0]

    # 최종 함유량 결정 (Strong -> Weak -> 미기재)
    final_content = strong_content or weak_content or "미기재%"

    final_comps = []
    for cas in cas_list:
        final_comps.append({
            "name": name,
            "cas_no": cas,
            "content": final_content,
            "engine": "ODL-v3.0_Priority" 
        })
    return final_comps

def extract_components_odl_robust(odl_doc, target_pages, pdf_path, log_func=None):
    components = []
    if not target_pages or not odl_doc or not odl_doc.pages: return components

    header_keywords = {"cas", "casno", "cas번호", "cas-no", "함유량", "함량", "content", "구성성분", "화학물질명", "substance", "물질명", "명칭", "chemicalname", "weight"}
    
    # 텍스트 기반 추출을 위해 원본 문서 열기
    try:
        fitz_doc = fitz.open(pdf_path)
    except:
        fitz_doc = None

    for p_idx in target_pages:
        if p_idx >= len(odl_doc.pages): continue
        
        page_items = []
        # 1. 테이블 기반 추출
        tables = [el for el in getattr(odl_doc.pages[p_idx], 'elements', []) if getattr(el, 'type', '') == "TABLE"]
        for table in tables:
            priority_col_idx = -1
            for row in table.rows:
                row_texts = [c.text or "" for c in row.cells]
                row_lower_set = {re.sub(r'[\s\(\)\.%\|_]', '', t.lower()) for t in row_texts}
                if row_lower_set.intersection(header_keywords):
                    for i, t in enumerate(row_texts):
                        if '%' in t:
                            priority_col_idx = i
                            break
                    if priority_col_idx >= 0: break
            
            for row in table.rows:
                parsed_comps = parse_row_robust_v2(row, priority_col_idx=priority_col_idx)
                if parsed_comps:
                    page_items.extend(parsed_comps)
                elif page_items and page_items[-1]["content"] == "미기재%":
                    row_raw_texts = [c.text for c in row.cells if c.text]
                    for txt in row_raw_texts:
                        norm = _normalize_single_content(txt)
                        if norm != "미기재%" and re.search(r'\d', norm):
                            idx = len(page_items) - 1
                            while idx >= 0 and page_items[idx]["content"] == "미기재%":
                                page_items[idx]["content"] = norm
                                idx -= 1
                            break
        
        # 2. 텍스트 기반 보완 (좌표 기반 행 복원)
        if fitz_doc:
            text_comps = extract_from_text_regex(fitz_doc[p_idx], log_func=log_func)
            
            # [V17.3.2.25] 최종 병합: ODL 결과에 Regex 보조장치의 함량을 덧씌우거나 누락 성분 추가
            for tc in text_comps:
                target_cas = tc["cas_no"]
                existing_item = next((item for item in page_items if item.get("cas_no") == target_cas), None)
                if existing_item:
                    if existing_item.get("content") in ["", "미기재%"] and tc.get("content") != "미기재%":
                        existing_item["content"] = tc["content"]
                        existing_item["engine"] = "Regex-Recovery"
                else:
                    page_items.append(tc)
                    
        components.extend(page_items)

    if fitz_doc: fitz_doc.close()
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
        odl_components = extract_components_odl_robust(odl_doc, target_pages, pdf_path, log_func=log_func)
    except Exception as e:
        if log_func: log_func(f" ⚠️ ODL 파싱 오류: {e}")
        odl_components = []
    
    # 🚨 [V17.3.2.25] ODL 추출 결과의 완전성 검증 (누락 체크)
    # 텍스트 원본에 존재하는 CAS 번호 목록과 대조
    expected_cas_list = re.findall(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', section3_text)
    # [V17.3.2.25] 진행률 판단 시에도 문서 원본(section3_text) 대조하여 오타 CAS 수용
    unique_expected_cas = set(c for c in expected_cas_list if verify_cas_number(c, grounding_text=section3_text))
    found_cas_set = set(str(c.get("cas_no", "")) for c in odl_components if verify_cas_number(str(c.get("cas_no", "")), grounding_text=section3_text))
    
    is_omitted = any(cas not in found_cas_set for cas in unique_expected_cas)
    valid_odl_contents = sum(1 for c in odl_components if str(c.get("content", "")) not in ["", "미기재%"])
    all_have_content = (valid_odl_contents == len(odl_components)) if odl_components else False
    
    # 🚨 ODL+보조장치가 모든 CAS를 찾았고, 함량도 완벽할 때만 AI 생략
    if not is_omitted and all_have_content and len(odl_components) > 0:
        if log_func: log_func(f" 🔍 [Raw ODL Search] {len(odl_components)}건 발견 (보조장치 가동 전)")
        # [Debug] ODL이 찾은 원본 리스트 출력
        for idx, c in enumerate(odl_components, 1):
            if log_func: log_func(f"   └─ {idx}. {c.get('cas_no')} | {c.get('content')} | {c.get('name')[:15]}")
        
        if log_func: log_func(f" 🟢 ODL+보조장치 정밀 추출 성공 ({len(odl_components)}건). AI 생략.")
        ai_res = {"구성성분": odl_components, "교정_사유": "ODL 정밀 추출 완료"}
        used_engine = "ODL-Regex"
        is_ai_extracted = False
    else:
        reason_msg = "누락 감지" if is_omitted else "함량 미기재"
        if not odl_components: reason_msg = "탐지 실패"
        
        if log_func: 
            if is_omitted:
                log_func(f" 🟡 ODL 추출 누락 (텍스트:{len(unique_expected_cas)} vs 추출:{len(found_cas_set)}). AI 비전 스나이퍼({alias}) 투입!")
            else:
                log_func(f" 🟡 ODL 결과 불완전 ({reason_msg}). AI 비전 스나이퍼({alias}) 투입!")
        
        ai_res = call_gemini_2_5_flash(image_list, None, current_sniper, log_func)
        used_engine = "Gemini-2.5-Flash"
        is_ai_extracted = True
        
        # 🚨 [지원군 모드] 스나이퍼(Gemini)가 응답 실패(None)인 경우에만 불도저(GPT) 복구 투입
        if ai_res is None:
            if log_func: log_func(f" ⚠️ {alias} 사망. 비상 지원군(GPT-4o-mini) 복구 투입...")
            ai_res = call_gpt_4o_mini(image_list, None, log_func=log_func)
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
    
    # 🚨 [V17.3.1.23] 특정 구역이 아닌 문서 전체(full_text_for_grounding)를 대조군으로 전달
    grounding_pool = full_text_for_grounding if full_text_for_grounding else local_grounding_text
    refined_comps, has_invalid_cas = final_quality_control(components, grounding_pool, is_ai=is_ai_extracted, log_func=log_func)
    
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
        "신호등": "🟡" if (has_invalid_cas or is_ai_extracted or not product_name) else "🟢",
        "used_engine": gui_engine_name
    }
    
    if log_func: log_func(f" ✅ [{VERSION}] 완료 (엔진: {used_engine}, 소요시간: {time.time()-start_time:.2f}초)")
    return res_obj

analyze_msds = process_pdf

def self_test_regression():
    """[V17.3.2.27] 부등호 및 함량 정규화 자가 검증 모듈"""
    print(f"\n--- [{VERSION}] 엔진 자가 검증 시작 ---")
    fail_count = 0
    pass_count = 0
    
    # 1. 부등호 및 범위 표준화 테스트
    test_cases = [
        ("0.1~1미만", "0.1~<1%", "미만(Below) 변환 유실"),
        ("0.01이내", "\u22640.01%", "이내(Within) 변환 실패"),
        ("0.1 - 1", "0.1~1%", "하이픈 범위 표준화 실패"),
        ("0.1 ~ < 1%", "0.1~<1%", "공백 포함 복합 범위 처리 실패"),
        ("<0.1%", "<0.1%", "단일 부등호 보존 실패"),
        ("≤ 0.1", "\u22640.1%", "특수 부등호 및 공백 처리 실패"),
        ("≥95%≤100%", "95~100%", "양방향 부등호(Full Range) 표준화 실패"),
        ("1 ~ 5미만", "1~<5%", "한글 부등호 포함 범위 처리 실패"),
        ("5 ~ 1", "1~5%", "범위 역순 정렬 실패"),
        ("< 5 ~ 1", "1~<5%", "부등호 포함 역순 정렬 및 귀속 실패"),
        ("min. 99.5%", "\u226599.5%", "min. 약어 표준화 실패"),
        ("max 10", "\u226410%", "max 약어 표준화 실패"),
        ("99.0 <", ">99%", "일본식 후위 부등호 처리 실패"),
        ("98.0 +%", "\u226598%", "플러스(+) 기호 이상(More than) 처리 실패"),
        ("(GR) 99.0 +% (EP) 98.0 +%", "\u226598%", "복합 등급 함량 하한선 통합 실패"),
        ("0.1 ~ < 1 / 1 ~ 5", "0.1~<1%", "다중 범위 혼입 시 첫 번째 수치 추출 실패")
    ]
    
    # 2. 복합 컨텍스트(Row Context) 테스트 (V17.3.2.27)
    print(f"[*] 행 컨텍스트(명칭 내 % 노이즈) 방어 테스트...")
    row_text = "뷰테인(부타디엔 함량 0%) 106-97-8 11 ~ 14"
    # 실제 엔진처럼 CAS 마스킹
    protected_row = row_text.replace("106-97-8", "[CAS_ANCHOR]")
    
    all_conts = cont_pattern.findall(protected_row)
    outside_conts = []
    for c in all_conts:
        start_idx = protected_row.find(c)
        prefix = protected_row[:start_idx]
        suffix = protected_row[start_idx+len(c):]
        # 괄호 밸런스 체크 (괄호 안에 있으면 스킵)
        if prefix.count('(') > prefix.count(')'): continue
        outside_conts.append(c)
    
    row_res = _normalize_single_content(outside_conts[-1]) if outside_conts else "미기재%"
    if row_res != "11~14%":
        print(f" [FAIL] 행 컨텍스트 방어 실패: 결과 '{row_res}' (기대값 '11~14%')")
        fail_count += 1
    else:
        print(f" [PASS] 행 컨텍스트 방어 성공 (0% 무시)")
        pass_count += 1
    
    # 2. 단위 및 노이즈 필터링 테스트 (Hallucination 방지)
    noise_cases = [
        ("77.08g", "미기재%", "단위(g) 환각 필터 작동 실패"),
        ("100 mg/kg", "미기재%", "단위(mg/kg) 환각 필터 작동 실패"),
        ("Ethylene Glycol 50-60%", "50~60%", "Shield-Inversion(텍스트 혼입) 처리 실패"),
        ("95-100% (wt)", "95~100%", "부가 텍스트(wt) 처리 실패")
    ]
    
    # 0. CAS 검증기 테스트 (날짜 오탐 방지 및 공백/키워드 대응)
    print(f"[*] CAS 검증기 테스트 가동...")
    cas_tests = [
        ("13463-67-7", True, "정상 CAS 통과 실패"),
        ("2014-12-16", False, "날짜 형식 차단 실패"),
        ("2025-03-17", False, "날짜 형식 차단 실패"),
        ("7732-18-5", True, "정상 CAS 통과 실패"),
        ("64742 - 54 - 7", True, "공백 포함 CAS 통과 실패"),
        ("해당없음", True, "'해당없음' 키워드 통과 실패")
    ]
    for c_str, expected, msg in cas_tests:
        # [V17.3.2.28] Grounding 시나리오 재현: 64742-54-7(추출값) vs 64742 - 54 - 7(문서 원본)
        g_text = "기타 성분: 64742 - 54 - 7 함유" if "64742" in c_str else None
        if verify_cas_number(c_str, grounding_text=g_text) != expected:
            print(f" [FAIL] CAS: {c_str} -> 결과: {not expected} | 사유: {msg}")
            fail_count += 1
        else:
            print(f" [PASS] CAS: {c_str}")

    # 1. 함유량 정규화 테스트
    keyword_cases = [
        ("Rem.", "Rem.%", "Rem. 키워드 표준화 실패"),
        ("balance", "Rem.%", "balance 키워드 표준화 실패"),
        ("잔량", "Rem.%", "한글 '잔량' 키워드 표준화 실패")
    ]

    all_tests = test_cases + noise_cases + keyword_cases
    fail_count = 0
    
    for input_str, expected, msg in all_tests:
        actual = _normalize_single_content(input_str)
        # [V17.3.2.25] 유니코드 기호(≤, ≥)의 환경별 표현 차이 방어를 위해 정규화 비교 수행
        if unicodedata.normalize("NFKC", actual) != unicodedata.normalize("NFKC", expected):
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
