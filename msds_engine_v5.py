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

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GOOGLE_API_KEY}"

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
            cas = str(info.get("CAS번호", "")).strip()
            # [수정] 초산메틸 대신 메틸 아세테이트를 잡도록 '물질명' 최우선 적용
            std_name = info.get("물질명") or info.get("상용명")
            if cas and std_name:
                MES_MASTER_MAP[cas] = std_name.strip()
                
except Exception as e:
    # [치명적 변경] print로 조용히 넘기지 않고 RuntimeError 발생. 
    # GUI의 global_exception_handler가 캐치하여 팝업으로 띄우도록 강제함.
    raise RuntimeError(f"[시스템 치명적 오류] 마스터 DB 초기화에 실패했습니다. DB 파일을 확인하세요!\n상세 원인: {e}")

# [V5.1 성능 최적화] 정규식 사전 컴파일 및 전역 헬퍼 함수 분리
REGEX_LE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|프로)?\s*이하')
REGEX_LT = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|프로)?\s*미만')
REGEX_GE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|프로)?\s*이상')
REGEX_GT = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|프로)?\s*초과')
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

def clean_product_name(raw_name):
    if not raw_name or str(raw_name).strip() in ["Unknown", "제품명 확인 필요"]: return "제품명 확인 필요"
    cleaned = clean_junk_from_name(raw_name)
    cleaned = re.sub(r'^(?:제품명\s*)+', '', cleaned).strip()
    noise_filters = P.get("NOISE_FILTERS", [])
    if any(k in cleaned for k in noise_filters): return "제품명 확인 필요"
    cleaned = re.sub(r'1\.\s*화학제품과\s*회사에\s*관한\s*정보.*', '', cleaned).strip()
    date_regex = P.get("DATE_CLEAN_REGEX", r'^([A-Za-z]{3}\.?\s*\d{1,2},?\s*\d{4}|\d{4}-\d{2}-\d{2}|\d{4}\.\d{2}\.\d{2})$')
    if re.match(date_regex, cleaned) or not cleaned or len(cleaned) < 2: return "제품명 확인 필요"
    cleaned = re.sub(r'^[\-\:\[\]\(\)\s]+', '', cleaned).strip()
    cleaned = re.sub(r'[\-\:\s\.]+$', '', cleaned).strip()
    if not cleaned or len(cleaned) < 2: return "제품명 확인 필요"
    return cleaned

def extract_product_name_v24(pdf_path, P):
    # [복구] 제품명은 fitz로 첫 페이지만 읽는 것이 가장 정확함
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0: return "제품명 확인 필요"
        page0 = doc[0]
        full_text = page0.get_text("text", sort=True)
        doc.close()

        splitter_regex = r'(항\s*2|0?2\s*\.\s*유\s*해|0?2\s*\.\s*위\s*험|0?2\s*\.\s*HAZARD|2\s*항|제\s*2\s*장|Section\s*2)'
        section1_text = re.split(splitter_regex, full_text, flags=re.IGNORECASE)[0]
        all_lines = [line.strip() for line in section1_text.split('\n') if line.strip()]
        lines = all_lines[:40]

        target_keys = ['제품명', '상품명', '물질명', '화학물질명', 'Product Name', 'Product name', '제품 식별자', 'GHS product identifier', 'Trade Name']
        tail_cutter = r'(나\s*\.|b\s*\.|1\.2\s|제품의\s*권고\s*용도|권고\s*용도|제품\s*코드|신고\s*번호|발행일|AA\d+-\d+|Manufacturer|회사명|용도|동의어)'
        target_keys_no_space = [re.sub(r'\s+', '', k).lower() for k in target_keys]

        def is_junk_candidate(cand):
            cand_lower = cand.strip().lower()
            if not cand_lower: return True
            if cand_lower in ['unknown', 'none', ':', '-', '=', '제품명 확인 필요']: return True
            return False

        for i, line in enumerate(lines):
            for key in target_keys:
                regex_key = r'\s*'.join(re.escape(c) for c in key.replace(" ", ""))
                match = re.search(rf'(?:{regex_key})\s*[:\-]?\s*(.+)$', line, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()
                    candidate = re.split(tail_cutter, candidate, flags=re.IGNORECASE)[0].strip()
                    if len(candidate) > 1 and not is_junk_candidate(candidate): return clean_product_name(candidate)

            clean_line = re.sub(r'^([\d\.\-\s]+|[가-마a-eA-E]\s*[\.\)]\s*)+', '', line).strip()
            clean_line = re.sub(r'^[:\-]\s*', '', clean_line).strip()
            line_no_space = re.sub(r'\s+', '', clean_line).lower()
            
            if line_no_space in target_keys_no_space:
                for j in range(1, 6):
                    if i + j < len(lines):
                        candidate = lines[i+j].strip()
                        candidate = re.split(tail_cutter, candidate, flags=re.IGNORECASE)[0].strip()
                        if len(candidate) > 1 and not is_junk_candidate(candidate): return clean_product_name(candidate)

        for k in range(min(15, len(lines))):
            cand = lines[k].strip()
            if len(cand) > 2 and not re.match(r'^[\d\.\-\s]+$', cand) and not is_junk_candidate(cand):
                if any(bad in cand.lower() for bad in ['물질안전보건자료', 'msds', '안전보건']): continue
                return clean_product_name(cand)
        return "제품명 확인 필요"
    except Exception: return "제품명 확인 필요"

def normalize_text(text):
    if not text: return ""
    try:
        src = "０１２３４５6７８９％～∼－：：，ㅡ－＝"
        dst = "0123456789%~~-::,-- -="
        table = str.maketrans(src, dst)
        t = unicodedata.normalize("NFKC", text).translate(table)
        t = re.sub(r"(\d{2,7})[\s\-]+(\d{2})[\s\-]+(\d)(?!\d)", r"\1-\2-\3", t)
        t = re.sub(r'(\d+(?:[\.,]\d+)?)\s*([~-])\s*(\d+(?:[\.,]\d+)?)', r'\1\2\3', t)
        return t
    except: return text

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

def format_content_v3(content_str):
    if not content_str: return "미기재%"
    c = str(content_str).upper()
    if any(kw in c for kw in ["영업비밀", "SECRET", "TRADE", "PROPRIETARY"]): return "영업비밀"
    
    # [V5.8] 숫자 추출 전 오차범위(±) 선제 계산 (예: 10±2 -> 8~12)
    if re.search(r'±|\+-', content_str):
        content_str = REGEX_PM.sub(_calc_pm_range, content_str)
        
    nums_raw = re.findall(r'\d+(?:[\.,]\d+)?', content_str)
    valid_nums = []
    for num in nums_raw:
        clean_n = num.replace(',', '.')
        if clean_n.startswith("00") and "." not in clean_n: continue
        try:
            val = float(clean_n)
            if val > 100.0: clean_n = "100" # 100% 상한선 보정
            valid_nums.append(clean_n)
        except: pass
        
    if not valid_nums: return "미기재%"
    
    # [범위값] 2개 이상의 숫자: 지저분한 부등호 싹 날리고 '~'로만 깔끔하게 결합
    if len(valid_nums) >= 2:
        v1_raw, v2_raw = valid_nums[0], valid_nums[1]
        try:
            if float(v1_raw) > float(v2_raw): v1_raw, v2_raw = v2_raw, v1_raw
        except: pass
        v1, v2 = clean_number(v1_raw), clean_number(v2_raw)
        return f"{v1}~{v2}"
        
    # [단일값] 1개의 숫자: 1이나 0.1 같은 민감한 값의 부등호 철저히 보존!
    elif len(valid_nums) == 1:
        v1 = clean_number(valid_nums[0])
        # [V5.7] AI 앙상블 비교 정합성을 위한 특수기호(≤, ≥, ＜, ＞) 및 위치 통일
        res = ""
        if re.search(r'[≥]|>=|이상|\+', content_str): res = f"≥{v1}"
        elif re.search(r'[≤]|<=|이하', content_str) or re.search(r'-\s*$', content_str.replace('%','').strip()): 
            res = f"≤{v1}"
        elif re.search(r'[＜<]|미만', content_str): res = f"＜{v1}"
        elif re.search(r'[＞>]|초과', content_str): res = f"＞{v1}"
        else: res = f"{v1}"
        
        # [V5.7] 소수점 후행 영(0) 컷오프
        res = re.sub(r'\.0+(\D|$)', r'\1', res)
        res = re.sub(r'(\.[0-9]*[1-9])0+(\D|$)', r'\1\2', res)
        return res

def search_content_in_context(context_str, cas_abs_pos, ctx_start, is_table=False, table_has_percent=False):
    masked = context_str
    cas_regex_blind = r'(?<!\d)[1-9]\d{1,6}-\d{2}-\d(?!\d)'
    masked = re.sub(cas_regex_blind, lambda x: " " * len(x.group()), masked)
    masked = re.sub(r'\b\d{3}-\d{3}-\d{2}-\d\b', lambda x: " " * len(x.group()), masked)
    masked = re.sub(r'\b\d{3}-\d{3}-\d\b', lambda x: " " * len(x.group()), masked)
    
    cas_pos_in_ctx = cas_abs_pos - ctx_start
    best_candidate = ("함유량미기재", sys.maxsize)
    cas_start = cas_pos_in_ctx
    m_cas = re.match(r'(?<!\d)[1-9]\d{1,6}-\d{2}-\d(?!\d)', context_str[cas_start:])
    cas_end = cas_start + len(m_cas.group()) if m_cas else cas_start + 10
    
    content_p = r"((?:[<>=~≥≤]+\s*)?\d+(?:[\.,]\d+)?(?:(?:\s*[\-~–—<>=≥≤]+\s*)+)\d+(?:[\.,]\d+)?\s*(?:%|w/w)?\s*(?:미만|이하|이상|초과)?|(?:[<>=~≥≤]+\s*)?\d+(?:[\.,]\d+)?\s*(?:%|w/w)?\s*(?:미만|이하|이상|초과)?)"

    for mc in re.finditer(content_p, masked):
        c_val = mc.group(1).strip()
        if re.search(r"[\.:]\s*$", c_val): continue
        formatted = format_content_v3(c_val)
        if formatted != "함유량미기재":
            raw_dist = mc.start() - cas_pos_in_ctx
            score = abs(raw_dist)
            if raw_dist < 0: score += abs(raw_dist) * 9.0 
            if score < best_candidate[1]: best_candidate = (formatted, score)
    return best_candidate[0]

# [복구] ODL이 뻗었을 때 살려주는 최강의 텍스트 안전망
def fallback_text_extraction(pdf_path, product_name, P):
    pdf_doc = fitz.open(pdf_path)
    full_text = ""
    for i in range(min(5, len(pdf_doc))): full_text += pdf_doc[i].get_text("text", sort=True) + "\n"
    pdf_doc.close()
    full_text = normalize_text(full_text)
    cas_best_data = {}
    cas_regex = r'(?:^|[^\d])([1-9]\d{1,6}-\d{2}-\d)(?:[^\d]|$)' 
    for m in re.finditer(cas_regex, full_text):
        cas = m.group(1)
        if not verify_cas_number(cas): continue
        start_idx = max(0, m.start(1) - 300)
        end_idx = min(len(full_text), m.end(1) + 300)
        content_val = search_content_in_context(full_text[start_idx:end_idx], m.start(1), start_idx)
        if cas not in cas_best_data or (cas_best_data[cas] == "함유량미기재" and content_val != "함유량미기재"):
            cas_best_data[cas] = content_val
    return [{"cas_no": k, "content": v} for k, v in cas_best_data.items()]

def run_v24_baseline(pdf_path):
    product_name = extract_product_name_v24(pdf_path, P)
    all_components = []
    try:
        parser = PDFParser()
        doc = parser.parse(pdf_path)
        
        # [복구] ODL이 None을 반환(충돌 시)하면 즉시 안전망 가동
        if not doc:
            return {"제품명": product_name, "함유량": "; ".join([f"{c['cas_no']}({c['content']})" for c in fallback_text_extraction(pdf_path, product_name, P)]), "tag": "[REVIEW]"}

        in_section_3 = False
        stop_parsing = False
        has_table_in_sec3 = False
        table_has_percent = False 
        cas_regex = r'(?:^|[^\d])([1-9]\d{1,6}-\d{2}-\d)(?:[^\d]|$)'

        if doc and doc.pages:
            for page in doc.pages:
                if stop_parsing: break
                for element in page.elements:
                    el_type = getattr(element, 'type', '')
                    txt_val = getattr(element, 'text', '').strip()
                    if el_type == "TEXT":
                        sec4_match = re.search(r'4\.\s*응급|SECTION\s*4|First-aid measures', txt_val, re.I)
                        sec3_match = re.search(r'3\.\s*구성|SECTION\s*3|3\s*:\s*COMPOSITION', txt_val, re.I)
                        if sec3_match and sec4_match and sec3_match.start() < sec4_match.start():
                            in_section_3 = True; stop_parsing = True; break
                        if sec4_match: stop_parsing = True; break
                        if not in_section_3 and sec3_match: in_section_3 = True; continue

                    if not in_section_3 and el_type == "TABLE" and element.rows:
                        if re.search(r'성분|물질명|CAS|Composition', " ".join([getattr(c, 'text', '') for c in element.rows[0].cells]), re.I): in_section_3 = True

                    if in_section_3 and el_type == "TABLE":
                        has_table_in_sec3 = True
                        for row in element.rows:
                            row_text = normalize_text(" ".join([getattr(cell, 'text', '').strip() for cell in row.cells]))
                            if re.search(r'%|％|함량|농도', row_text, re.I): table_has_percent = True
                            for m in re.finditer(cas_regex, row_text):
                                cas = m.group(1)
                                if not verify_cas_number(cas): continue
                                best_content = search_content_in_context(row_text, m.start(1), 0, is_table=True, table_has_percent=table_has_percent)
                                existing = next((c for c in all_components if c['cas_no'] == cas), None)
                                if existing:
                                    if existing['content'] == "함유량미기재" and best_content != "함유량미기재": existing['content'] = best_content
                                else: all_components.append({"cas_no": cas, "content": best_content})
        
        # [복구] 표에서 못 찾으면 fallback 실행!
        if not has_table_in_sec3 or len(all_components) == 0:
            all_components = fallback_text_extraction(pdf_path, product_name, P)
            
    except Exception:
        # [복구] 에러나도 fallback 실행!
        all_components = fallback_text_extraction(pdf_path, product_name, P)

    for comp in all_components:
        orig = str(comp.get('content', '')).strip()
        if not orig or orig in ["-", "Unknown", "미기재"]: orig = "함유량미기재"
        if len(all_components) == 1 and orig == "함유량미기재": comp['content'] = "100%"
        else:
            if "%" not in orig and orig != "함유량미기재": comp['content'] = f"{orig}%"
            else: comp['content'] = orig

    comp_parts = []
    for c in all_components:
        comp_parts.append(f"{c['cas_no']}({c['content']})")
            
    comp_str = "; ".join(comp_parts) if comp_parts else ""
    tag = "[PASS]" if all_components and comp_str else "[REVIEW]"

    return {"제품명": product_name, "함유량": comp_str, "tag": tag}

# =====================================================================
# [2단계] 제미나이 AI 앙상블 (팀장 검수 엔진)
# =====================================================================
def extract_context_for_ai(pdf_path):
    """[V7.8 AI Context] 5페이지 최적화 스캔 + 5000자 절삭 로직 철거"""
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        # 속도와 비용 방어를 위해 5페이지만 스캔 (충분함)
        for i in range(min(5, len(doc))):
            full_text += doc[i].get_text("text", sort=True) + "\n"
        doc.close()
        
        sec1 = re.search(r'(?:^|\n|\b)\s*(?:1[\.\s\)]+|항\s*1|1\s*항|SECTION\s*1)[^0-9\n]*(?:화학|Product)', full_text, re.I)
        sec4 = re.search(r'(?:^|\n|\b)\s*(?:4[\.\s\)]+|항\s*4|4\s*항|SECTION\s*4)[^0-9\n]*(?:응급|First)', full_text, re.I)

        if sec1 and sec4 and sec1.start() < sec4.start(): 
            # 4항 시작점까지만 깔끔하게 발췌
            target_text = full_text[sec1.start() : sec4.start() + 500]
        elif sec1: 
            target_text = full_text[sec1.start() : ]
        else: 
            target_text = full_text
        
        # [핵심] 기존의 return target_text[:5000] 삭제. 잘라먹지 말고 그대로 반환.
        return target_text
    except Exception:
        return ""

def extract_section3_images(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        start_page = -1
        end_page = -1
        
        # 1. 텍스트로 구간 탐색
        for i in range(len(doc)):
            text = doc[i].get_text("text")
            if start_page == -1 and re.search(r'3\.\s*구성|SECTION\s*3', text, re.I):
                start_page = i
            if start_page != -1 and re.search(r'4\.\s*응급|SECTION\s*4', text, re.I):
                end_page = i
                break
        
        images = []
        # 🚨 [핵심 수정] 텍스트 기반으로 3항을 못 찾았다면 포기하지 않고 무조건 1~3페이지 캡처!
        if start_page == -1:
            start_page = 0
            end_page = min(2, len(doc) - 1)
        else:
            if end_page == -1: end_page = min(start_page + 1, len(doc)-1)
        
        # 2. 범위 내 페이지 강제 캡처
        for p_idx in range(start_page, end_page + 1):
            page = doc[p_idx]
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            b64_img = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            images.append({"mimeType": "image/png", "data": b64_img})
            if len(images) >= 3: break # API 부하 방지를 위해 최대 3장 제한
            
        doc.close()
        return images
    except Exception:
        return []

def call_gemini_2_5_lite(v24_result, text_chunk, image_list=None, log_func=None, retry_instruction=None):
    """[V12.1] 텍스트/이미지 동시 방어 로직 적용"""
    if image_list is None: image_list = []
    if (not text_chunk.strip() and not image_list) or not GOOGLE_API_KEY: return None

    prod_name_baseline = v24_result.get('제품명', '')

    strict_rules = """
\n\n[🚨 AI Vision 초정밀 데이터 정제 및 추출 7대 절대 규칙 (V12.6) 🚨]
1. [이미지 최우선 및 행(Row) 독립성]: 오직 첨부된 이미지(표)를 기준으로, 동일한 가로줄(Row)에 있는 [물질명-CAS-함유량]만 한 세트로 묶어라. 텍스트에 휘둘려 위아래 줄을 섞지 마라.
2. [부등호 및 범위 기호의 완벽한 통일]:
   - 범위('~') 기호 사용 시 부등호 혼용 금지: '≥95~100%' -> '95~100%'로 단순화.
   - 단일 한계값 보존: '<2', '≤0.1' 등 숫자가 1개인 부등호는 절대 지우거나 유추하지 말고 유지.
   - 특수 기호 변환: 숫자 뒤의 '+'는 '이상(≥)'으로, '-'는 '이하(≤)'로 변환 (예: '99.0 +%' -> '≥99.0%').
   - 오차범위(±): '10 ± 2%'는 '8~12%'로 계산하여 변환.
   - 불필요한 텍스트 제거: 'About', '약' 등은 제거하고 숫자와 기호만 남김.
3. [잔여량 인식]: 함유량에 '나머지', 'Rem.', 'Balance', '잔량' 등이 적혀 있으면 무조건 'Rem.%'로 출력.
4. [단위 필터링]: '%'가 아닌 'ppm', 'mg/kg' 등의 특수 단위는 무조건 '미기재%'로 처리. 단, 기호 없이 숫자만(예: 100.0) 적혀있다면 %로 간주.
5. [상한선 보정]: '101%' 등 100% 초과 수치는 '100%'로 보정.
6. [누락 금지]: 함유량이 있는데 CAS 칸이 비어있거나 '자료없음' 등이면 절대 누락하지 말고 CAS 칸에 '영업비밀'이라고 기재하여 추출.
7. [EC 번호 구분]: '272-028-3'처럼 중간이 3자리인 유럽 EC 번호는 무시하라.
"""

    user_prompt = f"[1차 추출 결과]\n- 제품명: {prod_name_baseline}\n- 구성성분: {v24_result.get('함유량')}\n\n[원본 정보: 텍스트]\n{text_chunk}{strict_rules}"
    if retry_instruction:
        user_prompt += f"\n\n[🚨 자가 치유(Self-Healing) 요청]\n{retry_instruction}"

    # Google AI API Contents/Parts 구조 구성
    parts = [{"text": f"{SYSTEM_PROMPT_TEXT}\n\n{user_prompt}"}]
    if image_list:
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
        else:
            if log_func: log_func(f" ❌ Gemini API 에러 ({response.status_code}): {response.text}")
            return None
    except Exception as e:
        if log_func: log_func(f" ❌ Gemini 시스템 오류: {str(e)}")
        return None

def call_gpt_4o_mini(v24_result, text_chunk, image_list=None, log_func=None, retry_instruction=None):
    """[V12.1] 텍스트/이미지 동시 방어 로직 적용"""
    if image_list is None: image_list = []
    if (not text_chunk.strip() and not image_list) or not OPENAI_API_KEY: return None

    prod_name_baseline = v24_result.get('제품명', '')

    strict_rules = """
\n\n[🚨 AI Vision 초정밀 데이터 정제 및 추출 7대 절대 규칙 (V12.6) 🚨]
1. [이미지 최우선 및 행(Row) 독립성]: 오직 첨부된 이미지(표)를 기준으로, 동일한 가로줄(Row)에 있는 [물질명-CAS-함유량]만 한 세트로 묶어라. 텍스트에 휘둘려 위아래 줄을 섞지 마라.
2. [부등호 및 범위 기호의 완벽한 통일]:
   - 범위('~') 기호 사용 시 부등호 혼용 금지: '≥95~100%' -> '95~100%'로 단순화.
   - 단일 한계값 보존: '<2', '≤0.1' 등 숫자가 1개인 부등호는 절대 지우거나 유추하지 말고 유지.
   - 특수 기호 변환: 숫자 뒤의 '+'는 '이상(≥)'으로, '-'는 '이하(≤)'로 변환 (예: '99.0 +%' -> '≥99.0%').
   - 오차범위(±): '10 ± 2%'는 '8~12%'로 계산하여 변환.
   - 불필요한 텍스트 제거: 'About', '약' 등은 제거하고 숫자와 기호만 남김.
3. [잔여량 인식]: 함유량에 '나머지', 'Rem.', 'Balance', '잔량' 등이 적혀 있으면 무조건 'Rem.%'로 출력.
4. [단위 필터링]: '%'가 아닌 'ppm', 'mg/kg' 등의 특수 단위는 무조건 '미기재%'로 처리. 단, 기호 없이 숫자만(예: 100.0) 적혀있다면 %로 간주.
5. [상한선 보정]: '101%' 등 100% 초과 수치는 '100%'로 보정.
6. [누락 금지]: 함유량이 있는데 CAS 칸이 비어있거나 '자료없음' 등이면 절대 누락하지 말고 CAS 칸에 '영업비밀'이라고 기재하여 추출.
7. [EC 번호 구분]: '272-028-3'처럼 중간이 3자리인 유럽 EC 번호는 무시하라.
"""

    user_prompt = f"[1차 추출 결과]\n- 제품명: {prod_name_baseline}\n- 구성성분: {v24_result.get('함유량')}\n\n[원본 정보: 텍스트]\n{text_chunk}{strict_rules}"
    if retry_instruction:
        user_prompt += f"\n\n[🚨 자가 치유(Self-Healing) 요청]\n{retry_instruction}"

    content_list = [{"type": "text", "text": user_prompt}]
    if image_list:
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
            if log_func: log_func(f" ❌ OpenAI API 에러 ({response.status_code})")
            return None
    except Exception as e:
        if log_func: log_func(f" ❌ GPT 시스템 오류: {str(e)}")
        return None


# =====================================================================
# [메인] GUI 연동 마스터 파이프라인
# =====================================================================
def process_pdf(pdf_path, log_func=None):
    start_time = time.time()
    if log_func: log_func(f" 🚀 [하이브리드 기동] Gemini 2.5(1차) + GPT-4o-mini(2차) 듀얼 엔진 가동")

    v24_baseline = run_v24_baseline(pdf_path)
    text_chunk = extract_context_for_ai(pdf_path)

    # --- [V12.1] 하이브리드 엔진 시력(Vision) 파이프라인 복구 ---
    # AI 호출 직전 이미지 리스트 확보 (3번 섹션 캡처)
    image_list = extract_section3_images(pdf_path)

    # [NEW] 제품명 2중 방어망 (비전 스나이핑) 가동
    hybrid_pn, hybrid_source = extract_product_name_hybrid(text_chunk, image_list, GOOGLE_API_KEY, log_func=log_func)
    
    # [V7.0] 하이브리드 AI 듀얼 엔진 파이프라인 (Gemini 2.5 Flash-Lite -> GPT-4o-mini)
    used_engine = "regex"
    final_ai_result = None
    curr_retry_instruction = None
    max_retries = 2
    
    # 1단계: Gemini 2.5 Flash-Lite (최대 2회 시도)
    for i in range(max_retries):
        if log_func: log_func(f" ├─ [1단계] Gemini 2.5 호출 중... (시도 {i+1}/{max_retries})")
        ai_res = call_gemini_2_5_lite(v24_baseline, text_chunk, image_list=image_list, log_func=log_func, retry_instruction=curr_retry_instruction)
        
        if ai_res:
            # [NEW] 절대 권력 부여: 비전 스나이퍼(hybrid_pn)가 성공했다면 메인 AI 결과는 무조건 폐기
            if hybrid_pn and hybrid_pn != "미추출":
                ai_res["제품명"] = hybrid_pn
                if log_func: log_func(f" ├─ [우선순위 1위] 비전 스나이퍼 결과 강제 적용: {hybrid_pn[:30]}")
            else:
                main_pn = str(ai_res.get("제품명", "")).strip()
                if log_func: log_func(f" ├─ [우선순위 2위] 비전 실패. 메인 AI 결과 채택: {main_pn[:30]}")
            # CAS 번호 검증 (자가 치유 트리거)
            invalid_cas = []
            for comp in ai_res.get("구성성분", []):
                cas = str(comp.get("cas_no", "")).strip()
                if cas and cas not in ["영업비밀", "미기재"] and not verify_cas_number(cas):
                    invalid_cas.append(cas)
            
            if not invalid_cas:
                if not ai_res.get("구성성분", []) or "확인" in str(ai_res.get("제품명", "")):
                    curr_retry_instruction = "구성성분이 비어있거나 제품명을 찾지 못했습니다. 표를 다시 꼼꼼히 확인하여 누락 없이 추출해 주세요."
                    if log_func: log_func(f" ⚠️ Gemini 추출 부실 감지 (성분 0개 또는 제품명 미확인)")
                    continue 

                final_ai_result = ai_res
                used_engine = "flash"
                if log_func: log_func(" └─ ✅ Gemini 추출 성공 (CAS 검증 통과)")
                break
            else:
                curr_retry_instruction = f"다음 CAS 번호들이 유효하지 않습니다: {', '.join(invalid_cas)}. 정확한 CAS 번호를 다시 확인하여 응답해 주세요."
                if log_func: log_func(f" ⚠️ Gemini CAS 오류 발견: {', '.join(invalid_cas)} (재시도 준비)")
        else:
            if log_func: log_func(" ⚠️ Gemini 응답 실패 (Fallback 대기)")
            break

    # 2단계: Fallback to GPT-4o-mini
    if not final_ai_result and OPENAI_API_KEY:
        if log_func: log_func(" ├─ [2단계 Fallback] GPT-4o-mini 전환 호출 중...")
        final_ai_result = call_gpt_4o_mini(v24_baseline, text_chunk, image_list=image_list, log_func=log_func)
        if final_ai_result:
            # [NEW] 상호 검증: 메인 AI가 놓쳤을 때만 하이브리드(Vision) 결과로 심폐소생
            main_pn = str(final_ai_result.get("제품명", "")).strip()
            is_bad = not main_pn or any(k in main_pn.lower() for k in ["none", "확인", "미추출"])
            
            if is_bad and hybrid_pn and hybrid_pn != "미추출":
                final_ai_result["제품명"] = hybrid_pn
                if log_func: log_func(" ├─ [심폐소생] 메인 AI 실패로 비전 스나이핑 결과를 채택합니다.")
            elif not is_bad:
                if log_func: log_func(" ├─ [검증완료] 메인 AI의 제품명을 최종 확정합니다.")
            used_engine = "bulldozer"
            if log_func: log_func(" └─ ✅ GPT-4o-mini 추출 성공 (Fallback 완료)")
    
    # 최종 데이터 조립
    if not final_ai_result:
        product_name = v24_baseline.get("제품명", "제품명 확인 필요")
        comp_str = v24_baseline.get("함유량", "")
        tag = v24_baseline.get("tag", "[REVIEW]")
        reason = "모든 AI 엔진 응답 실패"
        comp_parts = [c for c in comp_str.split("; ") if c]
    else:
        product_name = clean_junk_from_name(final_ai_result.get("제품명", v24_baseline.get("제품명")))
        components = final_ai_result.get("구성성분", [])
        reason = final_ai_result.get("교정_사유", "사유 없음")
        
        comp_parts = []
        for comp in components:
            cas = str(comp.get("cas_no", "")).strip()
            if re.match(r'^0+\d+-\d{2}-\d$', cas): cas = re.sub(r'^0+', '', cas)
            
            # 1. [원칙 1] CAS 번호 규격이 아니면 함유량이 있어도 가차 없이 버림 (버그 원인 제거)
            if not re.match(r'^\d{1,7}-\d{2}-\d$', cas): 
                continue
                
            content = str(comp.get("content", "")).strip()
            
            # 2. [원칙 2] CAS 번호는 정상인데 함유량이 비어있거나 '없음' 등이면 '미기재%'로 보존
            if not content or any(kw in content for kw in ["-", "없음", "자료", "미기재", "비공개", "비밀"]): 
                content = "미기재%"
            else:
                # (기존 정제 로직 유지)
                content = content.replace(" ", "")
                content = REGEX_PM.sub(_calc_pm_range, content)
                content = REGEX_LE.sub(r'≤\1', content)
                content = REGEX_LT.sub(r'＜\1', content)
                content = REGEX_GE.sub(r'≥\1', content)
                content = REGEX_GT.sub(r'＞\1', content)
                content = content.replace("이하", "≤").replace("미만", "＜").replace("이상", "≥").replace("초과", "＞")
                content = content.replace("<=", "≤").replace(">=", "≥").replace("<", "＜").replace(">", "＞")
                content = re.sub(r'([\d\.]+)\s*(?:%)?\s*([≤≥＜＞])(?!\s*[\d])', r'\2\1%', content)
                content = re.sub(r'([≤≥＜＞])\s*([\d\.]+)\s*(?:%)?', r'\1\2%', content)
                content = re.sub(r'[≤≥＜＞]*\s*([\d\.]+)\s*(?:%|~|-)?\s*[≤≥＜＞]+\s*([\d\.]+)\s*(?:%)?', r'\1~\2%', content)
                content = re.sub(r'\.0+(\D|$)', r'\1', content)
                content = re.sub(r'(\.[0-9]*[1-9])0+(\D|$)', r'\1\2', content)
                if "%" not in content: content += "%"

            comp_parts.append(f"{cas}({content})")

        # [V12.3] 최종 문자열 조립 및 끝에 세미콜론(;) 보장
        comp_str = "; ".join(comp_parts)
        if comp_str and not comp_str.endswith(";"):
            comp_str += ";"
        v24_str_clean = str(v24_baseline.get("함유량")).replace(" ", "")
        ai_str_clean = comp_str.replace(" ", "")
        
        # 엔진별 태그 부여
        engine_prefix = "[G2.5" if "Gemini" in used_engine else "[GPT"
        tag = f"{engine_prefix}-PASS]" if v24_str_clean == ai_str_clean else f"{engine_prefix}-FIXED]"

    if log_func:
        log_func(f" ├─ 엔진: {used_engine}")
        log_func(f" ├─ 결과: {reason}")
        log_func(f" ✅ 완료 (소요시간: {time.time()-start_time:.2f}초)")

    result_data = {
        "제품명": product_name, 
        "함유량": comp_str, 
        "구성성분 및 함유량": comp_str, 
        "tag": tag, 
        "신뢰도": tag, 
        "추론근거": f"{used_engine} ({reason})",
        "used_engine": used_engine,
        "page": 1
    }

    # [🚀수정] 신호등 판별 로직 강화 ('미추출', 'none' 원천 차단)
    traffic_light = "🟢 통과"
    prod_check = str(product_name).strip().lower()
    
    if not prod_check or prod_check == "none" or "확인" in prod_check or "미추출" in prod_check:
        traffic_light = "🟡 확인"
    elif "미기재" in comp_str or "비밀" in comp_str or not comp_parts:
        traffic_light = "🟡 확인"
    else:
        for cas_item in [c.split("[")[1].split("(")[0] if "[" in c else c.split("(")[0] for c in comp_parts]:
            if cas_item not in ["영업비밀", "미기재"] and not verify_cas_number(cas_item):
                traffic_light = "🔴 오류"
                break

    result_data["신호등"] = traffic_light
    return result_data

# [V7.0] GUI 호환성을 위한 별칭 설정
analyze_msds = process_pdf
