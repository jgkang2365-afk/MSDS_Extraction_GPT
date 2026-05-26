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

# [V17.3.3.7] 윈도우 터미널 인코딩 노이즈 방어 (안전한 설정 방식)
if sys.platform == 'win32':
    import io
    # 이미 UTF-8이거나 GUI 환경(idna 등)인 경우 재정의하지 않음
    if getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            # reconfigure가 없는 구버전 파이썬 대응
            pass

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

VERSION = "24.4.1.0" # [V24.4.1.0] 비전 정찰병 7장 일괄 비교 폐기 및 순차적 조기 종료(Early Stopping) 알고리즘 도입

def load_prompt(prompt_type, version):
    """[V17.4.2.8] 프롬프트 로드 (Priority: Root(Versionless) -> Root(Versioned) -> archive/)"""
    mapping = {
        "vision_extractor": f"prompt_vision_extractor",
        "product_name": f"prompt_product_name"
    }
    prefix = mapping.get(prompt_type)
    if not prefix: raise ValueError(f"알 수 없는 프롬프트 타입: {prompt_type}")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 🔍 탐색 순서 정의
    search_paths = [
        os.path.join(base_dir, f"{prefix}.txt"),             # 1. 루트 (버전 없는 표준 파일)
        os.path.join(base_dir, f"{prefix}_{version}.txt"),   # 2. 루트 (현재 버전 명시 파일)
        os.path.join(base_dir, "archive", f"{prefix}_{version}.txt") # 3. 아카이브
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
                
    # 모든 경로에서 실패 시
    msg = f"[Version Lock Error] 프롬프트 파일을 찾을 수 없습니다.\n탐색한 경로:\n" + "\n".join([f" - {p}" for p in search_paths])
    raise RuntimeError(msg)

# 프롬프트 초기화 (지휘 체계 단일화)
try:
    VISION_EXTRACTOR_PROMPT = load_prompt("vision_extractor", VERSION)
    PRODUCT_NAME_PROMPT = load_prompt("product_name", VERSION)
    print(f"[*] 프롬프트 엔진 표준화 및 로드 완료 (엔진 버전: {VERSION})")
except Exception as e:
    print(f"[ERROR] 프롬프트 로드 중 치명적 오류: {e}")
    # GUI에서 import 시 sys.exit(1)이 발생하면 GUI가 닫히므로, 
    # 여기서는 예외를 다시 발생시켜 smu_gui.py의 try-except에서 잡도록 함
    raise

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

def call_gemini_with_retry(payload, initial_sniper, max_retries=8, log_func=None, model="gemini-2.5-flash"):
    current_sniper = initial_sniper
    for attempt in range(max_retries):
        if not current_sniper:
            raise ValueError("🚨 전담 스나이퍼가 배정되지 않았습니다.")
            
        api_key = current_sniper["key"]
        alias = current_sniper["alias"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
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
    """[V17.4.0.0] 제품명: 비전 주도(Leader) + 텍스트 참고(Reference) 모델"""
    if not current_sniper or not image_list: return "", "실패"
    first_page_img = image_list[0]
    b64_data = first_page_img.get("data", "") if isinstance(first_page_img, dict) else first_page_img
    mime_type = first_page_img.get("mime_type", "image/jpeg") if isinstance(first_page_img, dict) else "image/jpeg"

    # [V17.4.0.0] 텍스트 레이어는 환각 방지용 힌트로만 제공 (AI에게 자유를 부여)
    combined_prompt = f"{PRODUCT_NAME_PROMPT}\n\n[Text Layer Hint for Verification]:\n{text_chunk[:1000]}"
    payload = {"contents": [{"parts": [{"text": combined_prompt}, {"inlineData": {"mimeType": mime_type, "data": b64_data}}]}]}
    # [V17.4.0.8] 429 에러 대응 및 재시도 로직 강화
    for attempt in range(3):
        try:
            result = call_gemini_with_retry(payload, current_sniper, log_func=log_func, model="gemini-2.5-flash-lite")
            if result:
                pn_ai = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                # [V17.4.0.0] 100자까지 허용하여 제품명 절단 방지
                if pn_ai and not any(k in pn_ai for k in ["미추출", "확인"]) and len(pn_ai) < 100:
                    cleaned_pn = msds_utils_v3.clean_candidate(pn_ai)
                    cleaned_pn = re.sub(r'^(\S)\1(?=[가-힣])', r'\1', cleaned_pn)
                    if log_func: log_func(f" ├─ [제품명 스캔] ✅ 비전 스나이핑 성공(Lite): {cleaned_pn[:40]}")
                    return cleaned_pn, "Vision"
                break # 유효하지 않은 결과인 경우 루프 종료 (Fallback 대기)
        except Exception as e:
            if "429" in str(e):
                if log_func: log_func(f"  ⚠️ [Retry] {attempt+1}차 시도 실패(429). 잠시 대기 중...")
                time.sleep(5 * (attempt + 1))
                current_sniper = get_next_sniper()
                continue
            break
            
    # [V17.4.0.8] 최종 병기(GPT-4o-mini) 투입: Gemini 전담 요원 전멸 시
    if log_func: log_func(" 🚀 [최종 병기] Gemini 쿼터 초과. GPT-4o-mini 긴급 투입...")
    try:
        gpt_prompt = f"{combined_prompt}\n\n[IMPORTANT]: 반드시 JSON 형식으로 응답하라. 예: {{\"제품명\": \"추출된이름\"}}"
        gpt_res = call_gpt_4o_mini(image_list, prompt=gpt_prompt, log_func=log_func)
        if gpt_res:
            # GPT는 JSON 형식을 따를 수 있으므로 텍스트 추출 방식 조정
            pn_gpt = gpt_res.get("제품명", "") if isinstance(gpt_res, dict) else str(gpt_res)
            if pn_gpt and len(pn_gpt) < 100:
                cleaned_pn = msds_utils_v3.clean_candidate(pn_gpt)
                if log_func: log_func(f" ├─ [제품명 스캔] ✅ GPT 긴급 구출 성공: {cleaned_pn[:40]}")
                return cleaned_pn, "GPT-Fallback"
    except Exception as e:
        if log_func: log_func(f"  ❌ GPT Fallback 실패: {e}")

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
    raw_lower = v.lower()
    # [V17.3.5.20] 날짜/연도(YYYY.MM.DD 또는 YYYY) 패턴 사전 제거하여 함량 오인 방지
    v_shield = re.sub(r'\b20[0-2]\d[.\-/]\d{1,2}[.\-/]\d{1,2}\b', ' ', v)
    v_shield = re.sub(r'\b20[0-2]\d년?\b', ' ', v_shield)
    
    nums = re.findall(r'(\d+\.?\d*|\.\d+)', v_shield)
    if not nums: return "미기재%"
    
    # [V17.3.5.14] 부등호 결정 (Boolean -> Char)
    is_less = any(k in raw_lower for k in ["<", "미만", "below", "less"])
    is_le = any(k in raw_lower for k in ["≤", "이하", "max", "upto"])
    is_more = any(k in raw_lower for k in [">", "초과", "over", "above"])
    is_ge = any(k in raw_lower for k in ["≥", "이상", "min", "from", "+"])
    has_range_sep = any(k in raw_lower for k in ["~", "∼", "～", "-", "to"])

    # 후위 부등호 반전 처리 (단일 수치일 때만 적용하여 범위형과 간섭 차단)
    if len(nums) == 1:
        if has_trailing_less: is_more, is_less, is_le, is_ge = True, False, False, False
        if has_trailing_more: is_less, is_more, is_le, is_ge = True, False, False, False
        if has_trailing_le:   is_le, is_ge, is_less, is_more = True, False, False, False
        if has_trailing_ge:   is_ge, is_le, is_less, is_more = True, False, False, False

    pref = "≥" if is_ge else (">" if is_more else ("≤" if is_le else ("<" if is_less else "")))
    suff = "≤" if is_le else ("<" if is_less else "")

    if len(nums) == 1:
        v1 = nums[0]
        try:
            f1 = float(v1)
            n1 = int(f1) if f1.is_integer() else f1
            # [V17.3.5.17] 110% 초과 수치 거부
            if n1 > 110: return "미기재%"
            if (is_ge or is_more) and has_range_sep: return f"≥{n1}%"
            return f"{pref}{n1}%"
        except: return "미기재%"
        
    # [V17.4.0.11] 수치 개수에 따른 분기 처리 (단일 수치 vs 범위 수치)
    if len(nums) == 1:
        f1 = float(nums[0])
        n1 = int(f1) if f1.is_integer() else f1
        if n1 > 110: return "미기재%"
        return f"{pref}{n1}%"

    elif len(nums) >= 2:
        try:
            f1_orig, f2_orig = float(nums[0]), float(nums[1])
            is_swapped = f1_orig > f2_orig
            f1, f2 = (f2_orig, f1_orig) if is_swapped else (f1_orig, f2_orig)
            n1, n2 = (int(f1) if f1.is_integer() else f1), (int(f2) if f2.is_integer() else f2)
            
            # [V17.4.2.0] 부등호 결합형 범위 처리 (양쪽 모두 검사)
            parts = re.split(r'\s*(?:~|∼|～|\-|to|and)\s*', v, maxsplit=1)
            s_sym = ""
            
            if len(parts) == 2:
                v_left, v_right = parts[0], parts[1]
                # 높은 수치(n2)가 원래 어느 쪽에 있었는지 판단하여 부등호 추출
                target_part = v_left if is_swapped else v_right
                
                if any(k in target_part for k in ["<", "≤", "below", "미만"]): 
                    s_sym = "≤" if any(k in target_part for k in ["≤", "이하"]) else "<"
                elif any(k in target_part for k in [">", "≥", "above", "이상", "+"]):
                    s_sym = "≥" if any(k in target_part for k in ["≥", "이상", "+"]) else ">"
            
            # [V17.4.2.1] 1% 앵커 및 예외 케이스: 부등호가 2개 이상이거나 + 기호 중첩 시 단일 수치로 전환
            # 예: (GR) 99.0 +% (EP) 98.0 +% -> 하한선 기준 하이브리드 처리
            if v.count('+') >= 2 or v.count('이상') >= 2:
                return f"≥{n1}%"

            if n2 > 1.0 and s_sym in ["<", "≤"]: 
                if n2 != 1.0: s_sym = ""
            
            if not s_sym: return f"{n1}~{n2}%"
            return f"{n1}~{s_sym}{n2}%"
        except: 
            return "미기재%"
    
    return "미기재%"

def final_quality_control(components, full_text, is_ai=True, log_func=None):
    """[V17.3.2.25] Fuzzy Shield 3단계 적용 Grounding"""
    refined_dict = {}  
    has_invalid = False
    norm_text = re.sub(r'\s+', '', full_text).upper() if full_text else ""
    
    for comp in components:
        raw_cas_field = str(comp.get("cas", "") or comp.get("cas_no", "")).strip()
        clean_cas = re.sub(r'\s+', '', raw_cas_field) # [V17.4.1.3] 공백 제거 후 유효성 검사
        raw_content = str(comp.get("content", "")).strip()
        
        # 🚨 [V17.3.2.29] 후처리 보정 Rule (Rule 1, 2, 4 통합 적용)
        # Rule 4: 하나라도 유효한 CAS가 섞여 있는지 정규식으로 판별
        has_any_valid_cas = bool(re.search(r'\d{2,7}-\d{2}-\d', clean_cas))
        
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
            if any(k in raw_cas_field for k in ["영업비밀", "비공개", "해당없음", "Secret", "Proprietary"]):
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

            if cas in refined_dict:
                # [V17.4.0.12] 중복 처리: 기존 데이터가 '미기재%'이고 새 데이터가 유효하면 업데이트
                old_cont = refined_dict[cas].get("content", "미기재%")
                if old_cont == "미기재%" and cv and cv != "미기재%":
                    refined_dict[cas]["content"] = cv
                    if comp.get("name"): refined_dict[cas]["name"] = comp.get("name")
                
                # 페이지 정보는 더 앞쪽(작은 번호) 페이지로 유지
                try:
                    if page_val:
                        old_p = refined_dict[cas].get("page", 999)
                        if int(page_val) < int(old_p):
                            refined_dict[cas]["page"] = page_val
                except: pass
            else:
                # 신규 등록
                refined_dict[cas] = {
                    "cas": cas,
                    "name": comp.get("name", ""),
                    "content": cv if cv else "미기재%",
                    "page": page_val,
                    "engine": origin_engine
                }

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
    exit_pattern = re.compile(r'^(?:SECTION\s*)?[4-9][항\s.:]*(?:응급|폭발|화재|누출|취급|저장|노출|방지|FIRST|FIRE|ACCIDENTAL|HANDLING|EXPOSURE)', re.I | re.M)
    
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        
        # 1. 섹션 3 시작 확인
        if not found_section3:
            # [V17.4.0.9] 정규식 관용도 극대화: 오타(INFORMAION) 및 변칙 공백 대응 강화
            if re.search(r'(?:SECTION\s*)?[23][\s.:\-\/]*(?:구성성분|성분|성분\s?및\s?함량|COMPOS|INGRED|조성물)', text, re.I):
                found_section3 = True
        
        if found_section3:
            pages.append(i)
            # 🚨 [V17.4.2.3] 주님의 지침: 섹션 3을 찾은 시점부터 최대 2페이지(현재+다음)까지만 읽음
            # 범위를 6페이지로 넓게 잡을 경우 8항(노출기준) 등의 노이즈가 유입되어 정확도가 급락함
            if len(pages) >= 2:
                return sorted(list(set(pages)))
            
            # 🚨 [V17.3.2.25] 조기 종료 가드: 다음 페이지를 보기도 전에 섹션 4가 나오면 즉시 중단
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for line in lines:
                if exit_pattern.match(line) and "Page" not in line:
                    return sorted(list(set(pages)))
                
    return sorted(list(set(pages)))

# [V17.3.2.28] 공용 정규식 패턴: CAS 번호 내 공백 허용 (\s* 추가)
cas_pattern = re.compile(r'(?<![\d-])(\d{2,7}\s*-\s*\d{2}\s*-\s*\d)(?![\d-])')
# [V17.3.3.5] 범위형 정규식 패턴 최종: 단일 수치와 범위 수치를 유연하게 획득 (*)
# [V17.3.4.2] 범위형 정규식 패턴: 숫자 앞뒤에 알파벳이나 하이픈이 붙은 경우(화학명 파편) 제외
# [V17.4.0.9] 특수 대시 및 전각 부등호 대응 강화: –, — (En/Em Dash), \uff1c, \uff1e 및 공백 유연화
cont_pattern = re.compile(r'(?<![a-zA-Z\d-])([<>≤≥= \uff1c\uff1e\uff1d~∼～\-|\u2013|\u2014]*\s*\b\d+(?:\.\d+)?\b(?:\s*[<>≤≥=~∼～\-|\u2013|\u2014|이상|미만|above|below|to|and|%]+\s*)*\b\d*(?:\.\d+)?\b\s*%?(?:\s*(?:이상|미만|above|below|%)\s*)*)(?![a-zA-Z])', re.IGNORECASE)
# 보조 패턴: 단일 수치 및 전각 부등호 대응
cont_pattern_single = re.compile(r'([<>≤≥\uff1c\uff1e~∼～\-\u2013\u2014]?\s*\d+(?:\.\d+)?\s*%?)', re.IGNORECASE)



def extract_from_text_regex(page, log_func=None, inherited_x_range=None):
    """[V24.0.0.0] 분업의 철칙: 블랙홀 차단(엄격한 행 분리) 및 GHS 노이즈 필터링 (AI 토스 최적화)"""
    if log_func: log_func(f"  [마스킹 엔진] 텍스트 기반 정밀 추출(Regex-Recovery) 가동...")
    found = []
    
    try:
        raw_words = page.get_text("words")
        if not raw_words: return [], inherited_x_range

        # 유령 텍스트 사전 병합 (020번 가짜 볼드체 방어)
        merged_words = []
        for w in raw_words:
            font_h = w[3] - w[1]
            merged = False
            for j, u in enumerate(merged_words):
                if u[4] == w[4]:
                    if abs(u[0] - w[0]) < max(12, font_h * 0.8) and abs(u[1] - w[1]) < max(8, font_h * 0.5):
                        merged_words[j] = (min(u[0],w[0]), min(u[1],w[1]), max(u[2],w[2]), max(u[3],w[3]), u[4], u[5], u[6], u[7])
                        merged = True
                        break
            if not merged:
                merged_words.append(w)
        raw_words = merged_words
        
        raw_words.sort(key=lambda w: (w[1], w[0]))

        # 블록 단위로 y_start, y_end 계산
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: b[1])
        
        y_start, y_end = 0.0, 9999.0
        y_start_orig = 0.0
        for b in blocks:
            b_text = re.sub(r'\s+', '', b[4]).upper()
            if y_start_orig == 0.0:
                if any(k in b_text for k in ["구성성분", "성분및", "COMPONENTS", "INGREDIENTS", "COMPOSITION", "조성물"]):
                    y_start_orig = b[1] - 30
                    y_start = y_start_orig
            # y_start_orig가 감지된 상태에서, 그 아래쪽 영역에서만 y_end 탐색 (오염 방지)
            if y_start_orig > 0.0 and b[1] > y_start_orig:
                if any(k in b_text for k in ["응급조치", "FIRSTAID", "FIRSTAIDMEASURES"]):
                    y_end = b[1]
                    break
                    
        if raw_words and y_start > raw_words[-1][1] * 0.75:
            y_start = 0.0
            
        raw_words = [w for w in raw_words if y_start <= w[1] < y_end]

        # 🚨 [V24.0.1.0] 누락되었던 content_x_mid 변수 및 갱신 로직 복구
        is_left_arranged = False
        has_global_percent = False
        content_x_mid = 9999 # 🚨 누락되었던 변수 부활
        
        # y_start가 0.0으로 폴백되더라도 y_start_orig가 존재한다면 그 기준으로 헤더를 감지
        y_header_ref = y_start_orig if y_start_orig > 0.0 else y_start
        header_words = [w for w in raw_words if y_header_ref - 30 <= w[1] <= y_header_ref + 150]
        header_text = " ".join([w[4] for w in header_words]).upper()
        
        if "%" in header_text or "퍼센트" in header_text:
            has_global_percent = True
            
        cas_x_min = 9999
        content_x_min = 9999
        for w in header_words:
            txt = w[4].upper()
            if "CAS" in txt:
                cas_x_min = min(cas_x_min, w[0])
            if any(k in txt for k in ["함유량", "함량", "CONTENT", "CONC", "%", "농도"]):
                content_x_min = min(content_x_min, w[0])
                if content_x_mid == 9999: # 🚨 첫 번째 발견된 헤더의 중앙 좌표 저장 로직 부활
                    content_x_mid = (w[0] + w[2]) / 2
                
        if content_x_min < cas_x_min and cas_x_min != 9999:
            is_left_arranged = True

        words = []
        for w in raw_words:
            text_val = w[4]
            if any(c.isdigit() for c in text_val) and any(c.isalpha() for c in text_val):
                check_val = re.sub(r'\s+', '', text_val)
                if not cas_pattern.search(text_val) and not any(k in check_val for k in ["미만", "이상", "이하", "초과", "%", "~", "∼", "to"]):
                    text_val = re.sub(r'\d', 'X', text_val)
            words.append((w[0], w[1], w[2], w[3], text_val, w[5], w[6], w[7]))

        # 🚨 [V24.0.0.0] 블랙홀 차단: Y축 기준선(Baseline) 강제 고정 (문단이 하나의 줄로 합쳐지는 것 원천 차단)
        physical_lines = []
        if words:
            current_line_words = [words[0]]
            line_top = words[0][1]    
            line_bottom = words[0][3] 
            line_height = line_bottom - line_top

            for i in range(1, len(words)):
                curr_w = words[i]
                curr_top = curr_w[1]
                curr_bottom = curr_w[3]

                overlap = max(0, min(line_bottom, curr_bottom) - max(line_top, curr_top))

                if overlap > (line_height * 0.3) or abs(curr_top - line_top) <= (line_height * 0.5):
                    current_line_words.append(curr_w)
                    # 🚨 선언: line_bottom을 확장하지 않음. 첫 글자의 기준을 엄격히 유지.
                else:
                    current_line_words.sort(key=lambda w: w[0])
                    physical_lines.append({
                        "y": line_top, 
                        "text": " ".join([w[4] for w in current_line_words]),
                        "words": current_line_words
                    })
                    current_line_words = [curr_w]
                    line_top = curr_w[1]
                    line_bottom = curr_w[3]
                    line_height = line_bottom - line_top

            if current_line_words:
                current_line_words.sort(key=lambda w: w[0])
                physical_lines.append({
                    "y": line_top, 
                    "text": " ".join([w[4] for w in current_line_words]),
                    "words": current_line_words
                })

        # physical_lines 빌드 후 y_start 정밀 재검색 및 교정
        y_start_refined = 0.0
        for pl in physical_lines:
            line_text = pl["text"]
            if re.search(r'(?:SECTION\s*)?[23][\s.:\-\/]*(?:구성성분|성분|성분\s?및\s?함량|COMPOS|INGRED|조성물)', line_text, re.I):
                y_start_refined = pl["y"] - 10
                break
                
        if y_start_refined > 0.0:
            y_start_orig = y_start_refined
            if raw_words and y_start_refined > raw_words[-1][1] * 0.75:
                y_start = 0.0
            else:
                y_start = y_start_refined
                
            raw_words = [w for w in raw_words if y_start <= w[1] < y_end]
            y_header_ref = y_start_orig
            header_words = [w for w in raw_words if y_header_ref - 30 <= w[1] <= y_header_ref + 150]
            header_text = " ".join([w[4] for w in header_words]).upper()
            has_global_percent = "%" in header_text or "퍼센트" in header_text

        logical_rows = []
        pending_lines = []
        current_row = None

        for line in physical_lines:
            if line["y"] < y_start: continue # y_start 이전 라인은 행 구성에서 생략 (블랙홀 방어)
            row_text = line["text"]
            cas_list = cas_pattern.findall(row_text)
            
            if cas_list:
                current_row = {"cas_list": cas_list, "words": []}
                for p_line in pending_lines:
                    current_row["words"].extend(p_line["words"])
                pending_lines = []
                current_row["words"].extend(line["words"])
                logical_rows.append(current_row)
            else:
                if current_row:
                    current_row["words"].extend(line["words"])
                else:
                    pending_lines.append(line)

        last_valid_info = None 
        
        for row in logical_rows:
            safe_word_texts = [w[4] for w in row.get("words", [])]
            row_full_text = " ".join(safe_word_texts)
            
            for target_cas in row["cas_list"]:
                clean_text = row_full_text
                for other_cas in row["cas_list"]:
                    if other_cas != target_cas:
                        clean_text = clean_text.replace(other_cas, " [OTHER_CAS] ")
                clean_text = clean_text.replace(target_cas, "[CAS_ANCHOR]")
                
                clean_text = re.sub(r'\b20[0-2]\d[.\-/]\d{1,2}[.\-/]\d{1,2}\b', ' YYYY ', clean_text)
                clean_text = re.sub(r'\b20[0-2]\d년?\b', ' YYYY ', clean_text)
                clean_text = clean_text.replace("미맊", "미만").replace("미먄", "미만")
                clean_text = re.sub(r'(\d)(미만|이상|이하|초과)', r'\1 \2', clean_text)
                clean_text = re.sub(r'(\d)\s*([-~])\s*(\d)', r'\1\2\3', clean_text)

                matches_with_pos = []
                for m in cont_pattern.finditer(clean_text):
                    val = m.group(1).strip()
                    if not val: continue
                    
                    start_idx = m.start()
                    prefix = clean_text[:start_idx]
                    if prefix.count('(') > prefix.count(')'):
                        last_open = prefix.rfind('(')
                        context_window = clean_text[max(0, last_open-30):start_idx]
                        if "[CAS_ANCHOR]" not in context_window:
                            continue
                    matches_with_pos.append((val, start_idx)) 
                    
                content = "미기재%"
                if matches_with_pos:
                    def score_match(match_tuple):
                        m_val, match_pos = match_tuple
                        
                        # 1. 핵심: % 기호 유무 판단
                        has_percent = "%" in m_val
                        
                        # 2. GHS 규제치(SCL) 노이즈 차단 (콜론 법칙 - 27, 28, 29번 우측 열 방어)
                        # % 기호 바로 뒤에 콜론(:)이 오면 무조건 규제 기준치임 (예: >= 0.1 %:)
                        if re.search(r'%\s*:', clean_text[match_pos:match_pos+len(m_val)+5]):
                            return -5000
                            
                        context_area = clean_text[max(0, match_pos-30):min(len(clean_text), match_pos+len(m_val)+30)].lower()
                        tight_context = clean_text[max(0, match_pos-10):min(len(clean_text), match_pos+len(m_val)+10)].lower()
                        
                        # 3. 절대 단위 노이즈 (반경 10글자 타이트)
                        # 퍼센트 기호가 있든 없든 함유량 옆에 바로 붙어있으면 안되는 이종 단위들
                        absolute_noises = ["g/mol", "mg/m3", "ppm", "밀도", "density", "twa", "lel", "oel"]
                        if any(noise in tight_context for noise in absolute_noises):
                            return -5000
                            
                        # 🚨 [V24.3.1.0] % 면책 특권 룰: 퍼센트(%) 기호가 없는 경우에만 강력하게 환각 검사
                        if not has_percent:
                            # 11번(TECA) 구제: 글로벌 헤더에도 %가 없고, 범위 기호(~, -)도 없다면 줄글이 확실하므로 컷
                            if not has_global_percent and not any(k in m_val for k in ['~', '∼', '～', '-', '<', '>', '≤', '≥']):
                                return -5000
                                
                            # %가 없는 숫자는 주변(30글자)에 노이즈가 1개라도 있으면 가짜(섹션번호, EC, 카테고리)로 간주
                            weak_noises = ["ec 번호", "ec번호", "ec-no", "ec number", "einecs", "elincs", 
                                           "tox", "irrit", "corr", "dam", "stot", "분류", "category", "cat.", 
                                           "분자량", "molecular weight", "mw", "항", "section"]
                            if any(noise in context_area for noise in weak_noises):
                                return -5000
                                
                        # --- 이하 공통 로직 ---
                        layout_noises = ["쪽", "page", "페이지"]
                        if any(noise in clean_text[max(0, match_pos-20):match_pos].lower() for noise in layout_noises) and not has_percent: 
                            return -5000 
                            
                        core_m_val = m_val.strip(' -∼~<>\u2013\u2014≤≥=')
                        if core_m_val.count('-') >= 2 or core_m_val.count('\u2013') >= 2: return -5000
                            
                        anchor_pos = clean_text.find("[CAS_ANCHOR]")
                        
                        start_search = min(anchor_pos, match_pos)
                        end_search = max(anchor_pos, match_pos)
                        text_between = clean_text[start_search:end_search]
                        if "[OTHER_CAS]" in text_between:
                            return -10000
                            
                        dist_char = abs(anchor_pos - match_pos)
                        if dist_char > 120: 
                            return -5000

                        score = 0
                        if has_percent: score += 500
                        elif has_global_percent: score += 400 

                        if any(k in m_val for k in ['~', '∼', '～', '-', '<', '>', '≤', '≥', '미만', '이상', '\u2013', '\u2014']): score += 300
                        if '.' in m_val: score += 100
                        
                        if match_pos > anchor_pos: score += 200 
                        else:
                            if is_left_arranged: score += 200 
                            else: score -= 50  
                        
                        score -= (dist_char * 3) 
                        
                        m_nums = re.findall(r'\d+\.?\d*', m_val)
                        if m_nums:
                            for num_str in m_nums:
                                try:
                                    val = float(num_str)
                                    if val > 110: score -= 3000; break 
                                    if 1990 <= val <= 2030: score -= 1000 
                                except: pass
                        return score
                    
                    best_match_tuple = max(matches_with_pos, key=score_match)
                    if score_match(best_match_tuple) > -500:
                        content = _normalize_single_content(best_match_tuple[0])
                
                if content == "미기재%":
                    single_matches = []
                    for m in cont_pattern_single.finditer(clean_text):
                        val = m.group(1).strip()
                        if val: single_matches.append((val, m.start()))
                    if single_matches:
                        valid_singles = [m for m in single_matches if score_match(m) > -500]
                        if valid_singles:
                            best_single = max(valid_singles, key=score_match)
                            content = _normalize_single_content(best_single[0])
                    
                target_word = next((w for w in row["words"] if target_cas in w[4]), None)
                if target_word:
                    curr_x, curr_y = target_word[0], target_word[1]
                    if content == "미기재%" and last_valid_info:
                        prev_x, prev_y, prev_content = last_valid_info
                        if abs(curr_x - prev_x) < 50 and 0 < (curr_y - prev_y) < 150:
                            content = f"{prev_content} (병합추정)"
                            if log_func: log_func(f"   [수직 상속] CAS {target_cas} -> 병합 셀 함량({content}) 상속 완료")
                            
                    if content != "미기재%":
                        base_content = content.replace(" (병합추정)", "")
                        last_valid_info = (curr_x, curr_y, base_content)
                    
                if log_func: log_func(f"   [Regex-Recovery] CAS {target_cas} -> 함량 {content} (신뢰도: 고)")
                found.append({"name": "CAS 기반 자동 매핑", "cas_no": target_cas, "content": content, "engine": "Regex-Recovery"})

    except Exception as e:
        if log_func: log_func(f"  ⚠️ Regex-Recovery 오류: {e}")
        
    return found, inherited_x_range

def extract_section3_images(pdf_path, current_sniper, log_func=None):
    try:
        doc = fitz.open(pdf_path)
        pages = find_section3_pages(doc)
        
        # [V24.4.1.0] 구조적 개편: 7장 일괄 비교를 폐기하고 '순차적 조기 종료(Early Stopping)' 알고리즘 도입
        if not pages:
            if log_func: log_func(" 🔍 텍스트 탐지 실패 (또는 스캔본). 비전 정찰병(Recon) 순차 탐색 가동...")
            
            target_index = None
            max_recon_pages = min(7, len(doc))
            
            for i in range(max_recon_pages):
                if log_func: log_func(f"   ├─ [정찰 진행] 인덱스 {i}번 이미지 검증 중... ({i+1}/{max_recon_pages})")
                
                pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.8, 0.8))
                img_data = base64.b64encode(pix.tobytes("png")).decode("utf-8")
                single_image = {"mimeType": "image/png", "data": img_data}
                
                # 이진 판별(True/False) 초경량 전용 프롬프트 설계
                recon_prompt = """현재 입력된 1장의 이미지(MSDS 문서 페이지)를 분석하여, 이 페이지가 '3. 구성성분의 명칭 및 함유량' (또는 Composition / Information on Ingredients) 표가 시작되는 페이지가 맞는지 판단하라.

[판단 필수 기준]
1. 반드시 화학물질명(Substance Name), CAS 번호, 함유량(%)을 기재하기 위한 가로/세로 '표(Table Grid)' 구조가 시각적으로 보여야 한다.
2. 🚨 [절대 금지 - 함정 차단]: 문서 후반부에 등장하는 '11. 독성에 관한 정보' 섹션 내에서 단순히 '성분 1', '성분 2' 등의 줄글 텍스트나 독성학적 데이터가 나열된 페이지는 절대로 3번 섹션이 아니다. 무조건 false로 답하라.

결과는 반드시 다른 서술 없이 JSON 형식 {"is_section3": true} 또는 {"is_section3": false} 로만 답변하라."""
                
                recon_res = call_gemini_2_5_flash(
                    [single_image], 
                    prompt=recon_prompt, 
                    current_sniper=current_sniper, 
                    log_func=log_func, 
                    model="gemini-2.5-flash-lite"
                )
                
                # 진짜 3번 섹션 표를 발견한 즉시 루프 탈출 (인터셉터 작동)
                if recon_res and recon_res.get("is_section3") is True:
                    if log_func: log_func(f"   🎯 [정찰 성공] 인덱스 {i}번에서 진짜 구성성분 표 확보. 루프 조기 종료(Early Stopping).")
                    target_index = i
                    break
            
            if target_index is not None:
                pages = [target_index, target_index + 1] if target_index + 1 < len(doc) else [target_index]
                if log_func: log_func(f"  🎯 정찰병이 최종 확정 페이지를 찾았습니다: {pages}번 바인딩")
            else:
                if log_func: log_func("  ❌ [정찰 실패] 7페이지 이내에서 유효한 3번 구성성분 표를 인지하지 못함")
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

def call_gemini_2_5_flash(image_list=None, prompt=None, current_sniper=None, log_func=None, model="gemini-2.5-flash"):
    if not image_list or not current_sniper: return None
    final_prompt = prompt if prompt else VISION_EXTRACTOR_PROMPT
    parts = [{"text": final_prompt}]
    for img in image_list:
        parts.append({"inlineData": {"mimeType": "image/png", "data": img.get("data", "")}})
    payload = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}}
    try:
        result = call_gemini_with_retry(payload, current_sniper, log_func=log_func, model=model)
        if result:
            text_response = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            data = json.loads(text_response)
            # [V17.4.0.1] AI가 리스트[]를 반환하면 엔진 규격에 맞게 {"구성성분": []}로 래핑
            if isinstance(data, list):
                return {"구성성분": data}
            return data
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
    # [V17.3.5.18] GPT 호출 재시도 로직 도입 (429 대비)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post("https://api.openai.com/v1/chat/completions", 
                                   headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}, 
                                   json=payload, timeout=60)
            if response.status_code == 200: 
                res_data = json.loads(response.json()["choices"][0]["message"]["content"])
                if isinstance(res_data, list):
                    return {"구성성분": res_data}
                return res_data
            elif response.status_code == 429:
                if log_func: log_func(f"    [GPT Retry] 429 감지. {5*(attempt+1)}초 후 재시도...")
                time.sleep(5 * (attempt + 1))
        except: pass
    return None
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

        # 🚨 [V17.3.3.3] 수술적 정규화: 셀 내 숫자 사이의 하이픈 공백 제거
        c = re.sub(r'(\d)\s*-\s*(\d)', r'\1-\2', c)

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

        # [V17.4.0.3] 페이지 간 함량 열 좌표 계승 변수 (Context Messenger)
        inherited_x_range = None
        
        for p_idx in target_pages:
            if p_idx >= len(odl_doc.pages): continue
            
            page_items = []
            # 1. 테이블 기반 추출
            tables = [el for el in getattr(odl_doc.pages[p_idx], 'elements', []) if getattr(el, 'type', '') == "TABLE"]
            for table in tables:
                priority_col_idx = -1
                for row in table.rows:
                    row_texts = [c.text or "" for c in row.cells]
                    # [V17.4.0.4] 헤더 매칭 시 모든 공백 제거 후 비교 (성  분 -> 성분)
                    row_clean_texts = [re.sub(r'[\s\(\)\.%\|_]', '', t.lower()) for t in row_texts]
                    
                    if any(k in "".join(row_clean_texts) for k in ["함유량", "함량", "content", "conc", "weight"]):
                        for i, t in enumerate(row_texts):
                            clean_t = re.sub(r'\s+', '', t.lower())
                            if '%' in t or '함량' in clean_t or 'content' in clean_t:
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
            
            # 2. 텍스트 기반 보완 (좌표 계승 적용)
            if fitz_doc:
                text_comps, detected_x = extract_from_text_regex(fitz_doc[p_idx], log_func=log_func, inherited_x_range=inherited_x_range)
                # [V17.4.0.3] 다음 페이지를 위해 감지된 좌표 업데이트 (기억의 계승)
                if detected_x:
                    inherited_x_range = detected_x
                
                # [V17.3.2.25] 최종 병합
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

    # [V17.4.0.0] 스캔본(Image-only) 선제 탐지
    is_scanned = False
    try:
        doc_check = fitz.open(pdf_path)
        is_scanned = not any(page.get_text().strip() for page in doc_check)
        doc_check.close()
    except: is_scanned = True

    if is_scanned and log_func: log_func(" 🔍 스캔본(Image-only) 감지. 즉시 AI 스나이퍼 모드 가동.")

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
    odl_components = []
    components = []

    # 🚨 [V17.4.0.9] 진정한 엔진 단일화: ODL(표) + Regex(패턴) 융합 추출
    if not is_scanned and pages:
        target_pages = pages 
        fitz_doc = fitz.open(pdf_path)

        # 1. 표 구조 분석 (ODL)
        try:
            parser = PDFParser()
            odl_doc = parser.parse(pdf_path)
            odl_components = extract_components_odl_robust(odl_doc, target_pages, pdf_path, log_func=log_func)
        except Exception:
            odl_components = []

        # 2. 텍스트 패턴 분석 (Regex-Recovery) - 상시 가동
        regex_components = []
        inherited_x = None
        for p_idx in target_pages:
            if p_idx >= len(fitz_doc): continue
            try:
                page_comps, detected_x = extract_from_text_regex(fitz_doc[p_idx], log_func=log_func, inherited_x_range=inherited_x)
                regex_components.extend(page_comps)
                if detected_x: inherited_x = detected_x
            except Exception as e:
                if log_func: log_func(f" ⚠️ [Regex] 페이지 {p_idx} 분석 오류: {e}")
        
        fitz_doc.close()

        # 3. 데이터 융합 (Merge) - CAS 번호 기준 중복 제거 및 밀도 극대화
        merged_map = {}
        # Regex 결과를 먼저 담고
        for c in regex_components:
            # [V17.4.1.3] CAS 번호 공백 제거하여 키 일치화 (64742 - 54 - 7 -> 64742-54-7)
            cas = str(c.get("cas_no", "")).replace(" ", "").strip()
            if cas: 
                existing = merged_map.get(cas)
                # [회귀 방지] 기존에 '유효한 함량'이 있는데, 새로 들어온 값이 '미기재%'라면 덮어쓰기 무시
                if existing and str(existing.get("content")) != "미기재%" and str(c.get("content")) == "미기재%":
                    continue
                merged_map[cas] = c
        
        # ODL 결과로 병합 (ODL이 구조적으로 더 정확하나, 함량이 '미기재%'인 경우 Regex 데이터 보존)
        for c in odl_components:
            cas = str(c.get("cas_no", "")).replace(" ", "").strip()
            if cas:
                existing = merged_map.get(cas)
                if log_func: log_func(f"   [DEBUG] Merge CAS: {cas} | Existing: {existing.get('content') if existing else 'None'} | New: {c.get('content')}")
                # [V17.4.1.2] Content-Aware Merger: Regex에 유효 함량이 있는데 ODL이 미기재면 Regex 데이터 유지
                if existing and str(existing.get("content")) != "미기재%" and str(c.get("content")) == "미기재%":
                    if log_func: log_func(f"   [DEBUG] Skip Overwrite for {cas} (Keep Regex Content)")
                    if not existing.get("name") and c.get("name"):
                        existing["name"] = c.get("name")
                    continue
                merged_map[cas] = c

        components = list(merged_map.values())
        
        if components:
            if log_func: log_func(f" 🔍 [텍스트 정밀 분석] {len(components)}건의 성분(ODL+Regex) 융합 성공")
            used_engine = "Text-Analytic"
        else:
            components = []
    else:
        components = []
    
    # [V17.4.2.5] 3중 방어망 아키텍처 (주님 지침 반영)
    # 1선(ODL) + 2선(Regex)에서 단 하나라도 추출되었다면 AI를 호출하지 않고 종료 (비용 절감 및 정합성 우선)
    if not is_scanned:
        if components:
            if log_func: log_func(f" ✅ [1-2선 성공] {len(components)}건의 성분(ODL+Regex) 융합 성공. AI 생략.")
            ai_res = {"구성성분": components, "교정_사유": "텍스트 정밀 추출 완료"}
            is_ai_extracted = False
        else:
            if log_func: log_func(f" 🟡 [1-2선 실패] 추출 데이터 0건. AI Sniper({alias}) 긴급 투입!")
            is_ai_extracted = True
    else:
        # 스캔본일 경우 즉시 AI 투입
        if log_func: log_func(f" 🟡 [스캔본] AI Sniper({alias}) 투입! (사유: 이미지 전용 문서)")
        is_ai_extracted = True

    if is_ai_extracted:
        
        # AI 프롬프트에 제공할 원본 텍스트 컨텍스트 구성
        raw_prompt = f"{VISION_EXTRACTOR_PROMPT}\n\n[Raw Text Context for Reference]:\n{section3_text[:2000]}"
        ai_res = call_gemini_2_5_flash(image_list, raw_prompt, current_sniper, log_func)
        used_engine = "Gemini-2.5-Flash"
        is_ai_extracted = True
        
        if ai_res is None:
            if log_func: log_func(f" ⚠️ {alias} 사망. 비상 지원군(GPT-4o-mini) 복구 투입...")
            ai_res = call_gpt_4o_mini(image_list, raw_prompt, log_func=log_func)
            used_engine = "GPT-4o-mini"
            is_ai_extracted = True
            
        if ai_res and "구성성분" in ai_res:
            for c in ai_res["구성성분"]: c["engine"] = used_engine
            pure_cas_count = sum(1 for c in ai_res.get("구성성분", []) if re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', str(c.get("cas", "") or c.get("cas_no", ""))))
        else:
            pure_cas_count = 0
            
        if not ai_res or "구성성분" not in ai_res:
            if log_func: log_func(" ❌ AI 엔진 추출 실패 (수동 검토 대상)")
            return {"error": "추출 실패", "제품명": hybrid_pn, "신호등": "🔴"}

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

    gui_engine_name = "flash" if "Gemini" in used_engine else "bulldozer" if "GPT" in used_engine else "analytic"

    
    res_obj = {
        "구성성분": comp_str, "제품명": product_name, "측정대상": target_substances,
        "교정_사유": reason,
        "신호등": "🟡" if (has_invalid_cas or is_ai_extracted or not product_name) else "🟢",
        "used_engine": gui_engine_name
    }
    
    traffic_light = res_obj.get("신호등", "⚪")
    if log_func: log_func(f" ✅ [{VERSION}] 완료 (엔진: {used_engine}, 신호등: {traffic_light}, 소요시간: {time.time()-start_time:.2f}초)")
    return res_obj

analyze_msds = process_pdf

def self_test_regression():
    """[DEPRECATED] 정답지 기반 검증 제거. 로직의 본질적 견고함에 집중."""
    fail_count = 0
    pass_count = 0
    
    # 1. 부등호 및 범위 표준화 테스트
    test_cases = [
        ("0.1~1미만", "0.1~<1%", "미만(Below) 변환 유실"),
        ("0.01이내", "\u22640.01%", "이내(Within) 변환 실패"),
        ("0.1 - 1", "0.1~1%", "하이픈 범위 표준화 실패"),
        ("0.1 ~ < 1%", "0.1~<1%", "공백 포함 복합 범위 처리 실패"),
        (">=95 - <= 100 %", "95~100%", "Shikimic Acid 복합 부등호 패턴 실패"),
        ("80 - 90", "80~90%", "Cycle Oil 숫자 사이 공백 처리 실패"),
        ("<0.1%", "<0.1%", "단일 부등호 보존 실패"),
        ("≤ 0.1", "\u22640.1%", "특수 부등호 및 공백 처리 실패"),
        ("≥95%≤100%", "95~100%", "양방향 부등호(Full Range) 표준화 실패"),
        ("1 ~ 5미만", "1~5%", "1% 앵커 원칙에 따른 부등호 제거 확인"),
        ("0.1 ~ 1미만", "0.1~<1%", "1% 경계 부등호 보존 확인"),
        ("5 ~ 1", "1~5%", "범위 역순 정렬 실패"),
        ("< 5 ~ 1", "1~5%", "부등호 포함 역순 정렬 및 귀속 실패 (1% 앵커 원칙 적용)"),
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
