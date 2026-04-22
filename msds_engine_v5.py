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

# .env 파일 로드
load_dotenv()

# [필수 세팅] 구글 제미나이 API 키 (필요 시 requests에서 활용)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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

def extract_product_name_hybrid(pdf_path, P):
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
        # [교체할 코드]
        # '+'는 '이상'으로 처리
        if re.search(r'[≥]|>=|이상|\+', content_str): return f"≥{v1}"
        # '-'는 '이하'로 처리하되, 범위 연결자와 꼬이지 않도록 문자열 끝부분(-%)에 있을 때만 작동
        if re.search(r'[≤]|<=|이하|미만', content_str) or re.search(r'-\s*$', content_str.replace('%','').strip()): 
            return f"≤{v1}"
        if re.search(r'[<]', content_str): return f"<{v1}"
        if re.search(r'[>]|초과', content_str): return f">{v1}"
        return f"{v1}"

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
    product_name = extract_product_name_hybrid(pdf_path, P)
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

    comp_parts = [f"{c['cas_no']}({c['content']})" for c in all_components]
    comp_str = "; ".join(comp_parts) if comp_parts else "함유량미기재%"
    tag = "[PASS]" if all_components and "함유량미기재" not in comp_str else "[REVIEW]"

    return {"제품명": product_name, "함유량": comp_str, "tag": tag}

# =====================================================================
# [2단계] 제미나이 AI 앙상블 (팀장 검수 엔진)
# =====================================================================
def extract_context_for_ai(pdf_path):
    # [복구] ODL이 장님이 될 때를 대비하여 확실한 fitz로 텍스트 5000자 발췌
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        for i in range(min(5, len(doc))):
            full_text += doc[i].get_text("text", sort=True) + "\n"
        doc.close()
        
        sec1 = re.search(r'(?:^|\n|\b)\s*(?:1[\.\s\)]+|항\s*1|1\s*항|SECTION\s*1)[^0-9\n]*(?:화학|Product)', full_text, re.I)
        sec4 = re.search(r'(?:^|\n|\b)\s*(?:4[\.\s\)]+|항\s*4|4\s*항|SECTION\s*4)[^0-9\n]*(?:응급|First)', full_text, re.I)

        if sec1 and sec4 and sec1.start() < sec4.start(): target_text = full_text[sec1.start():sec4.start() + 1000]
        elif sec1: target_text = full_text[sec1.start():sec1.start() + 5000]
        else: target_text = full_text[:5000]
        
        return target_text[:5000]
    except Exception:
        return ""

def extract_section3_images(pdf_path):
    """[V7.0 Multi-Vision] 3번 항목 시작부터 4번 항목 전까지의 모든 페이지 캡처"""
    try:
        doc = fitz.open(pdf_path)
        start_page = -1
        end_page = -1
        
        # 1. 구간 탐색 (최대 7페이지까지 스캔)
        for i in range(min(7, len(doc))):
            text = doc[i].get_text("text")
            if start_page == -1 and re.search(r'3\.\s*구성|SECTION\s*3', text, re.I):
                start_page = i
            if start_page != -1 and re.search(r'4\.\s*응급|SECTION\s*4', text, re.I):
                end_page = i
                break
        
        if start_page == -1: return [] # 시작점 못 찾으면 빈 리스트
        if end_page == -1: end_page = min(start_page + 1, len(doc)-1) # 4번 못 찾으면 다음 장까지만
        
        # 2. 범위 내 모든 페이지 캡처
        images = []
        for p_idx in range(start_page, end_page + 1):
            page = doc[p_idx]
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            b64_img = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            images.append({"mimeType": "image/png", "data": b64_img})
            if len(images) >= 3: break # 최대 3장으로 제한 (성능 방어)
            
        doc.close()
        return images
    except Exception:
        return []

def analyze_with_gemini_ensemble(v24_result, text_chunk, image_list=[], log_func=None, retry_instruction=None):
    if not text_chunk.strip(): return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GEMINI_API_KEY}"
    prod_name_baseline = v24_result.get('제품명', '')
    
    system_prompt = f"""
    당신은 최고 수준의 화학물질 MSDS 검수자입니다.
    아래 [1차 룰베이스 추출 결과]를 검토하고, 제공된 [원본 정보: 텍스트]를 바탕으로 교정하여 JSON으로 출력하세요.

    [1차 추출 결과]
    - 제품명: {prod_name_baseline}
    - 구성성분: {v24_result.get('함유량')}

    [🔥 V5 핵심 데이터 정제 규칙 최종본]
    1. 1차 결과가 문서와 일치하면 그대로 유지하고, 오타만 교정하세요.
    2. [상한선] 101% 등 100%를 초과하는 수치는 '100%'로 보정하세요.
    3. [부등호 및 범위 통일] 함유량 기호는 아래 규칙을 절대적으로 따르세요.
       - [절대 금지] 범위 기호('~')가 쓰일 때는 부등호('≥', '≤', '<', '>')를 절대 함께 쓰지 마세요.
       - [일반 범위 단순화] 2개 이상의 숫자로 이루어진 범위값은 지저분한 부등호를 모두 제거하고 '~'로만 깔끔하게 연결하세요.
       - [민감한 한계농도 보존] 숫자가 1개뿐인 단일 부등호(<, ≤, >, ≥)는 법적 규제 기준이므로 지우지 말고 그대로 유지하세요.
       - [특수 기호 절대 규칙] 숫자 뒤에 꼬리처럼 붙은 기호는 단일 부등호로 변환하세요. '+'는 '이상(≥)', '-'는 '이하(≤)'로 바꿉니다.
       - [시약 등급(GR/EP) 통합 절대 규칙] 여러 CAS 번호가 나열된 경우 가장 낮은(보수적인) 농도 하나로 통일하세요.
       - 오차범위(±): 직접 계산하여 '최소~최대%'로 변환하세요.
       - 'About', '약' 등은 제거하고 숫자와 기호만 남기세요.
    4. [기호 없는 숫자 주의] 표에 '%' 기호 없이 단순 숫자만 적혀 있다면 퍼센트로 간주하되, 문맥상 다른 숫자(항목 번호 등)와 혼동하지 마세요.
    5. [미기재 및 잔여량] 수치가 없거나 '잔량' 등으로 표기된 경우 임의 계산 없이 무조건 '미기재%'로 표기하세요.
    6. [혼합물 CAS 삭제] 혼합물 전체를 지칭하는 CAS 번호가 하위 성분과 중복될 경우 혼합물 CAS는 삭제하세요.
    7. [특수 단위 배제] 단위가 '%'가 아닌 'ppm', 'mg' 등인 경우 무조건 '미기재%'로 처리하세요.
    8. [🚨 표 구조 파괴 대응 (Chaos-Proof)] PDF 텍스트 추출의 한계로 표의 행과 열이 뒤섞여(Chaos) 글자와 숫자가 난잡하게 흩어져 있을 수 있습니다. CAS 번호를 기준으로 주변의 텍스트가 오염되어 있더라도, 가장 가까운 논리적인 함유량 수치나 범위(예: 40 ~ 50, 10 ~ 25)를 문맥상으로 유추하여 정확히 짝지으세요. 1차 추출 결과가 100%로 도배되어 있다면 이는 파싱 오류일 확률이 높으므로, 원본 텍스트를 정밀 분석하여 진짜 함유량을 발굴해내야 합니다.

    [JSON 포맷]
    {{
      "교정_사유": "사유 요약",
      "제품명": "최종 제품명",
      "구성성분": [ {{"cas_no": "13463-67-7", "content": "70~75%"}} ]
    }}
    """
    
    if retry_instruction:
        system_prompt += f"\n\n[🚨 자가 치유(Self-Healing) 요청]\n{retry_instruction}"

    full_prompt = system_prompt + f"\n\n[원본 정보: 텍스트]\n{text_chunk}"
        
    parts = [{"text": full_prompt}]
    for img in image_list:
        parts.append({"inlineData": img}) # [수정] inlineData (CamelCase)

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
    }
    
    try:
        # [V7.0 과속 방지턱] API RPM 제한을 피하기 위해 호출 전 무조건 3초 대기
        time.sleep(3) 
        
        response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload), timeout=40)
        
        if response.status_code == 200:
            result = response.json()
            text_response = result["candidates"][0]["content"]["parts"][0]["text"]
            
            import re
            match = re.search(r'\{.*\}', text_response, re.DOTALL)
            if match:
                clean_json_str = match.group(0)
                return json.loads(clean_json_str)
            else:
                if log_func: log_func(f" ❌ JSON 파싱 실패 원문: {text_response[:200]}...")
                raise ValueError("AI 응답에서 JSON 구조를 찾을 수 없습니다.")
                
        # [신규] 429 에러(할당량 초과) 발생 시 특별 처리: 15초 대기 후 바깥 루프에서 재시도 유도
        elif response.status_code == 429:
            if log_func: log_func(" ⏳ API 호출 한도 초과(429). 15초간 숨을 고른 후 재시도합니다...")
            time.sleep(15)
            return None
            
        else:
            if log_func: log_func(f" ❌ API 통신 에러 ({response.status_code}): {response.text}")
            return None
            
    except Exception as e:
        if log_func: log_func(f" ❌ 시스템 오류 발생: {str(e)}")
        return None


# =====================================================================
# [메인] GUI 연동 마스터 파이프라인
# =====================================================================
def process_pdf(pdf_path, log_func=None):
    start_time = time.time()
    if log_func: log_func(f" 🚀 [앙상블 기동] V24 코어 + Gemini 2.0 Flash-lite 초고속 검증 시작")

    v24_baseline = run_v24_baseline(pdf_path)
    text_chunk = extract_context_for_ai(pdf_path)
    
    if not GEMINI_API_KEY or GEMINI_API_KEY == "여기에_발급받은_API_키를_입력하세요":
        final_ai_result = None
    else:
        max_ai_retries = 2
        retry_count = 0
        final_ai_result = None
        curr_retry_instruction = None
        
        # --- [V7.0 하이브리드 비전 발동 조건 방어막] ---
        v24_content = str(v24_baseline.get("함유량", ""))
        needs_vision = False
        # 100% 도배, 미기재, 1차 정규식 리뷰 필요 시에만 비전 가동
        if "100%" in v24_content or "미기재" in v24_content or v24_baseline.get("tag") == "[REVIEW]":
            needs_vision = True
            
        image_list = []
        if needs_vision:
            if log_func: log_func(" ├─ 👁️ [Vision 가동] 표 구조 파괴 의심. 3번 항목 이미지 캡처 중...")
            image_list = extract_section3_images(pdf_path)
        # ----------------------------------------------
        
        while retry_count <= max_ai_retries:
            try:
                ai_result = analyze_with_gemini_ensemble(v24_baseline, text_chunk, image_list=image_list, log_func=log_func, retry_instruction=curr_retry_instruction)
                
                if not ai_result:
                    if retry_count == 0: 
                        final_ai_result = None
                        break
                    break
                
                if isinstance(ai_result, list) and len(ai_result) > 0: ai_result = ai_result[0]
                if not isinstance(ai_result, dict): 
                    if retry_count == 0: 
                        final_ai_result = None
                        break
                    break

                components = ai_result.get("구성성분", [])
                checksum_errors = []
                for comp in components:
                    cas = str(comp.get("cas_no", "")).strip()
                    if cas not in ["영업비밀", "미기재", "-"] and not verify_cas_number(cas):
                        checksum_errors.append(cas)
                
                if not checksum_errors:
                    final_ai_result = ai_result
                    break
                
                retry_count += 1
                if retry_count <= max_ai_retries:
                    if log_func: log_func(f" ├─ 🔄 [Self-Healing] {retry_count}회차 재시도: 오타 감지({', '.join(checksum_errors)})")
                    curr_retry_instruction = f"당신이 추출한 '{', '.join(checksum_errors)}' 번호들의 수학적 체크섬 검증이 실패했습니다. 제공된 텍스트 원본에서 해당 번호를 다시 정밀하게 확인하여 오타를 수정하십시오."
                else:
                    if log_func: log_func(f" ├─ 🛑 [Self-Healing] {max_ai_retries}회 재시도 실패. 원본 오류 유지.")
                    final_ai_result = ai_result
            except Exception as e:
                if log_func: log_func(f" ❌ AI 검수 중 오류: {e}")
                final_ai_result = None
                break

    if not final_ai_result:
        # [수정] AI 실패 시 조기 리턴하지 않고 1차 결과를 변수에 매핑
        product_name = v24_baseline.get("제품명", "제품명 확인 필요")
        comp_str = v24_baseline.get("함유량", "함유량미기재%")
        tag = v24_baseline.get("tag", "[REVIEW]")
        reason = "AI 응답 실패 (1차 코어 결과로 대체)"
        comp_parts = [c for c in comp_str.split("; ") if c]
    else:
        product_name = final_ai_result.get("제품명", v24_baseline.get("제품명"))
        product_name = clean_junk_from_name(product_name)
        components = final_ai_result.get("구성성분", [])
        reason = final_ai_result.get("교정_사유", "사유 없음")

        comp_parts = []
        for comp in components:
            cas = str(comp.get("cas_no", "")).strip()
            if re.match(r'^0+\d+-\d{2}-\d$', cas): cas = re.sub(r'^0+', '', cas)
            content = str(comp.get("content", ""))
            content = re.sub(r'[～∼〜]', '~', content).replace(" ", "")
            
            is_valid_cas_fmt = re.match(r'^\d{1,7}-\d{2}-\d$', cas)
            if not (is_valid_cas_fmt or cas in ["영업비밀", "미기재"]): continue
                
            if any(u in content.lower() for u in ['g/l', 'mg', 'ppm', 'ug', 'ml']):
                content = "미기재%"
            
            if "~" in content:
                content = re.sub(r'^[≥≤><]+', '', content.strip())
                content = re.sub(r'~[≥≤>]+', '~', content)
            else:
                content = re.sub(r'([0-9.]+)\s*<\s*(%?)$', r'>\1\2', content)
                content = re.sub(r'([0-9.]+)\s*>\s*(%?)$', r'<\1\2', content)
                content = re.sub(r'([0-9.]+)\s*≤\s*(%?)$', r'≥\1\2', content)
                content = re.sub(r'([0-9.]+)\s*≥\s*(%?)$', r'≤\1\2', content)

            if not content or any(kw in content for kw in ["미기재", "함유량미기재", "비밀", "영업비밀"]): 
                content = "미기재%"
            elif "%" not in content:
                content += "%"

            if cas: comp_parts.append(f"{cas}({content})")

        comp_str = "; ".join(comp_parts) if comp_parts else "함유량미기재%"
        v24_str_clean = str(v24_baseline.get("함유량")).replace(" ", "")
        ai_str_clean = comp_str.replace(" ", "")
        tag = "[AUTO-PASS]" if v24_str_clean == ai_str_clean else "[AI-FIXED]"

    if log_func:
        log_func(f" ├─ AI 검수결과: {reason}")
        log_func(f" ✅ 완료 (소요시간: {time.time()-start_time:.2f}초)")

    result_data = {
        "제품명": product_name, 
        "함유량": comp_str, 
        "구성성분 및 함유량": comp_str, 
        "tag": tag, 
        "신뢰도": tag, 
        "추론근거": f"Gemini 2.0 Flash-lite Ensemble ({reason})"
    }

    # [🚀추가] 제품명에 '확인 필요'가 들어있어도 무조건 노란불 켜기!
    traffic_light = "🟢 통과"
    if "확인 필요" in product_name or "미기재" in comp_str or "비밀" in comp_str or not comp_parts:
        traffic_light = "🟡 확인"
    else:
        for cas_item in [c.split("(")[0] for c in comp_parts]:
            if cas_item not in ["영업비밀", "미기재"] and not verify_cas_number(cas_item):
                traffic_light = "🔴 오류"
                break

    result_data["신호등"] = traffic_light
    # [V7.0] GUI 연동을 위한 페이지 정보 추가 (V5는 주로 1페이지에서 제품명 추출)
    result_data["page"] = 1
    return result_data

# [V7.0] GUI 호환성을 위한 별칭 설정
analyze_msds = process_pdf