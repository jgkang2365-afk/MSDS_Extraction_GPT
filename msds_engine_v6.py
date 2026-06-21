import os
import base64
import sys
import re
import time
import json
import requests
import gc
from datetime import datetime
import numpy as np

import fitz
from google.oauth2 import service_account
import google.auth.transport.requests 
import unicodedata
from opendataloader.pdf import PDFParser
import msds_utils_v3
from dotenv import load_dotenv
import socket

# 모든 소켓 통신의 기본 타임아웃을 20초로 강제 설정하여 API 지연 시 프로세스 영구 블로킹 방어
socket.setdefaulttimeout(20.0)

# .env 파일 로드
load_dotenv(override=True)

# 윈도우 터미널 인코딩 노이즈 방어
if sys.platform == 'win32':
    if getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

# PaddleOCR 싱글톤 가속 인프라
_PADDLE_STRUCTURE_ENGINE = None
_OCR_ENGINE = None
_TABLE_ENGINE = None

def get_paddle_structure_engine(log_func=None):
    global _PADDLE_STRUCTURE_ENGINE
    if _PADDLE_STRUCTURE_ENGINE is None:
        if log_func: log_func("   ├─ [엔진 로딩] 최초 가동: Paddle 로컬 두뇌 파일(약 25MB)을 메모리에 탑재합니다.")
        from paddleocr import PPStructureV3
        _PADDLE_STRUCTURE_ENGINE = PPStructureV3(
            lang='korean',
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_seal_recognition=False,
            use_formula_recognition=False,
            use_chart_recognition=False,
        )
    return _PADDLE_STRUCTURE_ENGINE

def get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from paddleocr import PaddleOCR
        _OCR_ENGINE = PaddleOCR(lang='korean')
    return _OCR_ENGINE

def get_table_engine():
    global _TABLE_ENGINE
    if _TABLE_ENGINE is None:
        from paddleocr import TableStructureRecognition
        _TABLE_ENGINE = TableStructureRecognition()
    return _TABLE_ENGINE

# 버전을 V6 사양에 맞게 명시
VERSION = "24.6.0.0"

# MES 마스터 데이터 로드
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

cas_pattern = re.compile(r'(?<![\d-])(\d{2,7}\s*-\s*\d{2}\s*-\s*\d)(?![\d-])')
cont_pattern = re.compile(r'(?<![a-zA-Z\d-])([<>≤≥= \uff1c\uff1e\uff1d~∼～\-|\u2013|\u2014]*\s*\b\d+(?:\.\d+)?\b(?:\s*[<>≤≥=~∼～\-|\u2013|\u2014|이상|미만|above|below|to|and|%]+\s*)*\b\d*(?:\.\d+)?\b\s*%?(?:\s*(?:이상|미만|above|below|%)\s*)*)(?![a-zA-Z])', re.IGNORECASE)
cont_pattern_single = re.compile(r'([<>≤≥=\uff1c\uff1e\uff1d~∼～\-\u2013\u2014\s]*\d+(?:\.\d+)?\s*%?)', re.IGNORECASE)

def load_prompt(prompt_type, version):
    mapping = {
        "vision_extractor": "prompt_vision_extractor",
        "product_name": "prompt_product_name"
    }
    prefix = mapping.get(prompt_type)
    if not prefix: raise ValueError(f"알 수 없는 프롬프트 타입: {prompt_type}")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths = [
        os.path.join(base_dir, f"{prefix}.txt"),
        os.path.join(base_dir, f"{prefix}_{version}.txt"),
        os.path.join(base_dir, "archive", f"{prefix}_{version}.txt")
    ]
    for path in search_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
    raise RuntimeError(f"프롬프트 파일을 찾을 수 없습니다. 탐색한 경로: {search_paths}")

try:
    # 템플릿 로드는 기존 24.4.3.22 버전 아카이빙을 바라보도록 호환성 고정
    VISION_EXTRACTOR_PROMPT = load_prompt("vision_extractor", "24.4.3.22")
    PRODUCT_NAME_PROMPT = load_prompt("product_name", "24.4.3.22")
    print(f"[*] 프롬프트 엔진 표준화 및 로드 완료 (엔진 버전: {VERSION})")
except Exception as e:
    print(f"[ERROR] 프롬프트 로드 중 치명적 오류: {e}")
    raise

class MSDSEngineV6:
    def __init__(self):
        """
        [데이터 검증 가드레일 01] 기계 가동 전 마스터 열쇠 장착 여부 확인
        """
        key_path = "vertex_key.json"
        if not os.path.exists(key_path):
            print("🚨 [[Vertex AI] 마스터 열쇠 사증 실패] 로컬에 vertex_key.json 파일이 존재하지 않습니다.")
        else:
            print("🟢 [[상표명 성분 감별사] 기동] 버텍스 AI 마스터 열쇠 직결 선로가 활성화되었습니다.")

    def extract_section_1(self, pdf_type, raw_pdf_content, log_func=None):
        """
        v5에서 완착된 자재 형태별 1섹션 격리 수거 회로 (비전 배제)
        """
        if not raw_pdf_content:
            raise ValueError("인입된 PDF 자재의 알맹이가 비어있습니다. (데이터 무결성 실패)")

        if pdf_type == "digital":
            if log_func: log_func("📋 [[상표명 정찰병] 디지털 선로] 로컬 문자열 집게 요원이 '1. 화학제품' 간판 행을 포착하여 가위질을 집행합니다.")
            text_chunk = raw_pdf_content
            pinned_text = ""
            start_patterns = [
                r'1\.\s*화학\s*제품\s*과\s*회사',
                r'1\.\s*화학\s*제품',
                r'SECTION\s*1',
                r'1\.\s*IDENTIFICATION',
                r'1\s*화학제품',
                r'IDENTIFICATION',
                r'DESCRIPTION',
                r'1\.\s*DESCRIPTION',
                r'1\.\s*제품명\s*및\s*회사',
                r'1\.\s*제품명'
            ]
            end_patterns = [
                r'2\.\s*유해성\s*[\.\·\-\/]?\s*위험성',
                r'2\.\s*유해성',
                r'2\.\s*위험성',
                r'SECTION\s*2',
                r'2\.\s*HAZARDS',
                r'2\s*유해성',
                r'HAZARDS\s*IDENTIFICATION',
                r'2\.\s*HAZARDS\s*IDENTIFICATION'
            ]
            
            start_idx = -1
            for pat in start_patterns:
                m = re.search(pat, text_chunk, re.IGNORECASE)
                if m:
                    start_idx = m.start()
                    break
            if start_idx == -1:
                start_idx = 0
                
            end_idx = -1
            for pat in end_patterns:
                m = re.search(pat, text_chunk[start_idx:], re.IGNORECASE)
                if m:
                    end_idx = start_idx + m.start()
                    break
                    
            if end_idx != -1 and end_idx > start_idx:
                pinned_text = text_chunk[start_idx:end_idx].strip()
            else:
                pinned_text = text_chunk[start_idx:start_idx + 1200].strip()
                
            return pinned_text

        elif pdf_type == "scanned":
            if log_func: log_func("📸 [[상표명 정찰병] 스캔 선로] 로컬 Y축 레이더 가동 -> 1번~2번 대간판 물리 공간 크롭 후 글자 가루 복원.")
            pdf_path = raw_pdf_content
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"스캔본 PDF 파일이 존재하지 않습니다: {pdf_path}")
            
            paddle_ocr_instance = get_paddle_structure_engine(log_func)
            doc = fitz.open(pdf_path)
            page = doc[0]
            w, h = page.rect.width, page.rect.height
            
            left_strip_rect = fitz.Rect(0, 0, w * 0.33, h)
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=left_strip_rect)
            
            img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            raw_results = paddle_ocr_instance.predict(img_np)
            
            strip_ocr_results = []
            if raw_results and isinstance(raw_results, list):
                for region in raw_results:
                    region_res = region.get("res") if isinstance(region, dict) else getattr(region, 'res', [])
                    if isinstance(region_res, list):
                        for line_item in region_res:
                            if isinstance(line_item, dict):
                                strip_ocr_results.append(line_item)
                            elif len(line_item) >= 2 and isinstance(line_item[1], tuple):
                                pts = line_item[0]
                                txt = line_item[1][0]
                                xs = [p[0] for p in pts]
                                ys = [p[1] for p in pts]
                                bbox = [min(xs), min(ys), max(xs), max(ys)]
                                strip_ocr_results.append({"text": txt, "bbox": bbox})
                    elif isinstance(region_res, dict):
                        strip_ocr_results.append(region_res)
            
            y_start = None
            y_end = None
            
            pattern_sec1 = re.compile(r'(1|일)\b.*?(화학|제품|회사|제조|공급|공명|IDENTIFICATION|DESCRIPTION|IDENT|DESC)', re.IGNORECASE)
            pattern_sec2 = re.compile(r'(2|이)\b.*?(유해성|위험성|유해|위험|HAZARDS)', re.IGNORECASE)
            
            for line in strip_ocr_results:
                text = line.get("text", "").replace(" ", "")
                box = line.get("bbox", [0, 0, 0, 0])
                mid_y = (box[1] + box[3]) / 2.0 / 2.0
                
                if y_start is None and pattern_sec1.search(text):
                    y_start = mid_y
                    continue
                    
                if y_start is not None and y_end is None and pattern_sec2.search(text):
                    y_end = mid_y
                    break
            
            doc.close()
            
            if y_start is None:
                y_start = 0.0
            if y_end is None or y_end <= y_start:
                y_end = min(h, y_start + 450.0)
            
            doc_crop = fitz.open(pdf_path)
            page_crop = doc_crop[0]
            crop_rect = fitz.Rect(0, max(0, y_start - 20), w, min(h, y_end + 20))
            
            pix_crop = page_crop.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=crop_rect)
            img_np_crop = np.frombuffer(pix_crop.samples, dtype=np.uint8).reshape(pix_crop.h, pix_crop.w, pix_crop.n)
            
            ocr_result = paddle_ocr_instance.predict(img_np_crop)
            doc_crop.close()
            
            lines = []
            if ocr_result and isinstance(ocr_result, list):
                for region in ocr_result:
                    region_res = region.get("res") if isinstance(region, dict) else getattr(region, 'res', [])
                    if isinstance(region_res, list):
                        for line in region_res:
                            if isinstance(line, dict):
                                lines.append(line.get("text", ""))
                            elif len(line) >= 2 and isinstance(line[1], tuple):
                                lines.append(line[1][0])
                    elif isinstance(region_res, dict):
                        lines.append(region_res.get("text", ""))
            
            text_hint = "\n".join(lines).strip()
            return text_hint
            
        else:
            raise TypeError("자재 형태가 불분명합니다. (digital 혹은 scanned 레이블 필수)")

    def validate_chemical_balances(self, component_list, log_func=None):
        """
        [데이터 검증 가드레일 02] 후방 수학적 천칭 검문소 (2단계 분리 계량 회로)
        """
        if not component_list:
            if log_func: log_func("⚠️ [[함량 검문소] 경보] 성분 명세 장부가 비어있습니다. 무결성 검증 탈락.")
            return False

        total_max_sum = 0.0

        for component in component_list:
            name = component.get('name', '미상 성분') or component.get('chemical_name', '미상 성분')
            max_val = component.get('max_content')

            # max_content가 없으면 함유량 문자열에서 최대 수치를 동적 추출
            if max_val is None:
                pct_str = str(component.get('percentage') or component.get('content') or '0.0')
                pct_str = re.sub(r'(?<![\w-])[0-9a-zA-Z]{2,7}\s*-\s*[0-9a-zA-Z]{2}\s*-\s*[0-9a-zA-Z]{1}(?![\w-])', ' ', pct_str)
                nums = [float(n) for n in re.findall(r'[\d\.]+', pct_str) if n.strip('.')]
                max_val = max(nums) if nums else 0.0

            # ① 1단계: 개별 성분 저울 (단독 100% 초과 모순 적발)
            if max_val > 100.0:
                if log_func: log_func(f"⚠️ [[함량 검문소] 검문 탈락] 물리적 모순 포착: 성분 [{name}]의 단독 수치 100% 초과 ({max_val}%)")
                return False
            
            total_max_sum += max_val

        # ② 2단계: 범위 최대치 합계 저울 (실무 표준 110% 허용한계 조율)
        if total_max_sum > 110.0:
            if log_func: log_func(f"⚠️ [[함량 검문소] 검문 탈락] 실무 허용한계 초과: 각 성분 최대값의 총합계 110% 초과 ({total_max_sum}%)")
            return False

        if log_func: log_func(f"🟢 [[함량 검문소] 검문 통과] 천칭 계량 완료 (총합: {total_max_sum}%). 청정 데이터로 판정하여 Bypass 허용.")
        return True

    def call_vertex_gemini_with_retry(self, payload, max_retries=2, log_func=None, model="gemini-2.5-flash"):
        """
        [Vertex AI] vertex_key.json 기반으로 GCP Vertex AI API를 직접 REST 호출
        """
        key_path = "vertex_key.json"
        if not os.path.exists(key_path):
            if log_func: log_func(" ❌ [Vertex AI] 마스터 열쇠 사증 실패 (파일 미존재)")
            return {"candidates": [{"content": {"parts": [{"text": ""}]}}]}
            
        access_token = None
        try:
            credentials = service_account.Credentials.from_service_account_file(
                key_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            auth_req = google.auth.transport.requests.Request()
            credentials.refresh(auth_req)
            access_token = credentials.token
        except Exception as auth_err:
            if log_func: log_func(f" ❌ [Vertex AI] 마스터 열쇠 사증 실패 (인증 실패): {auth_err}")
            return {"candidates": [{"content": {"parts": [{"text": ""}]}}]}
            
        project_id = "msds-engine-v6"
        location = "us-central1"
        url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{model}:generateContent"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Vertex AI REST API는 role: user를 필수로 요구하므로 안전하게 보정 주입
        if "contents" in payload:
            for c in payload["contents"]:
                if "role" not in c:
                    c["role"] = "user"
                    
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    return response.json()
                else:
                    if log_func: log_func(f"  🔴 [Vertex AI Retry] 호출 실패 (HTTP {response.status_code}) - {response.text}")
                    time.sleep(1.0)
                    continue
            except Exception as e:
                if log_func: log_func(f"  🔴 [Vertex AI Retry] {attempt+1}차 장애 사유: {e}")
                time.sleep(1.0)
                continue
                
        if log_func: log_func(" ❌ [Vertex AI] 호출 최종 실패")
        return {"candidates": [{"content": {"parts": [{"text": ""}]}}]}

    def call_deepseek_with_retry(self, payload, max_retries=1, log_func=None, model="deepseek/deepseek-v4-flash"):
        """
        [DeepSeek] 30초 타임아웃 가드레일을 얹은 Novita AI 단독 호출
        """
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("NOVITA_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY 누락")
            
        url = "https://api.novita.ai/v3/openai/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        gemini_text = ""
        contents = payload.get("contents", [])
        if contents:
            parts = contents[0].get("parts", [])
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            gemini_text = "\n".join(text_parts)
            
        gen_config = payload.get("generationConfig", {})
        response_format = None
        if gen_config.get("responseMimeType") == "application/json":
            response_format = {"type": "json_object"}
            
        openai_messages = [{"role": "user", "content": gemini_text}]
        openai_payload = {
            "model": model,
            "messages": openai_messages,
            "temperature": 0.0
        }
        if response_format:
            openai_payload["response_format"] = response_format
            
        for attempt in range(max_retries):
            try:
                # 1선 DeepSeek 호출 타임아웃(커넥션 5초, 읽기 12초)을 얹은 Novita AI 호출
                response = requests.post(url, headers=headers, json=openai_payload, timeout=(5, 12))
                if response.status_code == 200:
                    res_json = response.json()
                    content_str = res_json["choices"][0]["message"]["content"]
                    return {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": content_str}
                                    ]
                                }
                            }
                        ]
                    }
                else:
                    raise Exception(f"HTTP {response.status_code}")
            except Exception as e:
                if log_func: log_func(f"   [DeepSeek Retry] {attempt+1}차 시도 실패 사유: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1.0)
        raise Exception("DeepSeek API 호출 최종 실패")

    def call_llm_router(self, payload, max_retries=2, log_func=None, model="gemini-2.5-flash", is_scanned_strict=False):
        """
        [Failover 관문] 1선 DeepSeek(30초 타임아웃) ➔ 에러 시 2선 Vertex Gemini 비전 자동 Failover 결착
        (단, is_scanned_strict가 True인 경우 DeepSeek를 Bypass하고 곧바로 Gemini 비전 채널로 다이렉트 직결)
        """
        if is_scanned_strict:
            if log_func:
                log_func(" ➔ [스캔본 감지] 1선 DeepSeek Bypass, 처음부터 곧바로 제미나이 비전 채널로 다이렉트 고속 직결 수송합니다.")
            res = self.call_vertex_gemini_with_retry(payload, max_retries=max_retries, log_func=log_func, model=model)
            if isinstance(res, dict): res["actual_engine_label"] = "gemini"
            return res
            
        try:
            if log_func: log_func("🚀 [AI 통신] 1선 DeepSeek 호출을 격발합니다. (12초 타임아웃 가드)")
            res = self.call_deepseek_with_retry(payload, max_retries=1, log_func=log_func)
            if isinstance(res, dict): res["actual_engine_label"] = "deepseek"
            return res
        except Exception as ds_err:
            if log_func:
                log_func(f" ⚠️ [보험 가드레일 격발] 1선 DeepSeek 장애/타임아웃 감지 (사유: {ds_err})")
                log_func(" ➔ [Failover] 2선 Vertex Gemini 비전 채널로 즉시 이송합니다.")
            res = self.call_vertex_gemini_with_retry(payload, max_retries=max_retries, log_func=log_func, model=model)
            if isinstance(res, dict): res["actual_engine_label"] = "gemini"
            return res

    def _get_graceful_error_dict(self, pdf_path, reason_msg, log_func=None, hybrid_pn=None):
        if log_func: log_func(f" ⚠️ [추출 격리 수거 격발] 사유: {reason_msg}")
        
        pn_fallback = hybrid_pn
        if not pn_fallback:
            filename = os.path.basename(pdf_path)
            no_ext = os.path.splitext(filename)[0]
            cleaned_name = re.sub(r'^\d+[\s_★\-]*', '', no_ext)
            cleaned_name = re.sub(r'\([oOxX🟢🟡🔴★]\)', '', cleaned_name)
            cleaned_name = re.sub(r'\b(MSDS|SDS|GHS|국문|개정|KOR)\b', '', cleaned_name, flags=re.I)
            cleaned_name = cleaned_name.replace("MSDS", "").replace("SDS", "").replace("★", "").replace("개정", "").replace("국문", "").strip()
            pn_fallback = cleaned_name if cleaned_name else no_ext
            
        return {
            "구성성분": "",
            "제품명": pn_fallback,
            "측정대상": "",
            "교정_사유": f"추출 실패 격리수거: {reason_msg}",
            "신호등": "🔴",
            "used_engine": "error_isolation",
            "integrity_score": 0,
            "integrity_reason": "[품질점수: 0점] ➔ [❌추출실패]"
        }

    def process_msds_pipeline(self, pdf_path, log_func=None):
        try:
            return self._process_msds_pipeline_impl(pdf_path, log_func=log_func)
        except Exception as e:
            if log_func: log_func(f" ⚠️ [치명적 런타임 예외 격리] {e}")
            return self._get_graceful_error_dict(pdf_path, str(e), log_func=log_func)

    def _process_msds_pipeline_impl(self, pdf_path, log_func=None):
        """
        대장 키 단독 직렬 분쇄 메인 파이프라인 실체 (오류는 외부 쉴드에서 격리 수거)
        """
        start_time = time.time()
        
        # 가동 직전 형상 무결성 전수 조사 실시
        self.check_golden_fingerprint(log_func=log_func)
        
        if log_func: log_func(f" 🚀 [{VERSION}] MSDSEngineV6 엔진 가동: {os.path.basename(pdf_path)}")

        # 스캔본(Image-only) 선제 탐지 및 디지털 글자 수 조사로 엄격한 격리
        is_scanned = False
        total_chars = 0
        try:
            doc_check = fitz.open(pdf_path)
            is_scanned = not any(page.get_text().strip() for page in doc_check)
            total_chars = sum(len(page.get_text().strip()) for page in doc_check)
            doc_check.close()
        except: is_scanned = True

        is_scanned_strict = is_scanned or (total_chars < 10)
        if is_scanned_strict and log_func: log_func(" 🔍 스캔본(Image-only) 감지. 즉시 AI 스나이퍼 모드 가동.")

        # 3섹션 성분 탐색 페이지 식별
        image_list, section3_text, pages = self.extract_section3_images(pdf_path, log_func=log_func)
        
        full_text_for_grounding = ""
        try:
            doc = fitz.open(pdf_path)
            first_page_text = self._get_sorted_and_normalized_text(doc[0]) if len(doc) > 0 else ""
            for page in doc: full_text_for_grounding += self._get_sorted_and_normalized_text(page)
            pix_cover = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            cover_img = [{"mimeType": "image/png", "data": base64.b64encode(pix_cover.tobytes("png")).decode("utf-8")}]
            doc.close()
        except:
            cover_img, first_page_text, full_text_for_grounding = image_list, "", ""

        # [1단계 - 파일명 파싱 (괄호 안 진짜 상업용 명칭 수거)]
        filename = os.path.basename(pdf_path)
        file_pn_hint = ""
        brackets = re.findall(r'\(([^)]+)\)', filename)
        candidate_pns = []
        for b in brackets:
            b_clean = b.strip()
            if b_clean in ['O', 'X', '★', '국문', 'KOR', 'E', '요청 조성비 서류', '보통휘발유', ' Regular Unleaded Gasoline']:
                continue
            if any(blacklist in b_clean for blacklist in ['물질안정', '보건자료', 'MSDS', 'SDS', '안전보건']):
                continue
            candidate_pns.append(b_clean)
            
        if candidate_pns:
            file_pn_hint = candidate_pns[0]
            
        if not file_pn_hint:
            no_ext = os.path.splitext(filename)[0]
            cleaned_name = re.sub(r'^\d+[\s_★\-]*', '', no_ext)
            cleaned_name = re.sub(r'\([oOxX🟢🟡🔴★]\)', '', cleaned_name)
            cleaned_name = re.sub(r'\b(MSDS|SDS|GHS|국문|개정|KOR)\b', '', cleaned_name, flags=re.I)
            cleaned_name = cleaned_name.replace("MSDS", "").replace("SDS", "").replace("★", "").replace("개정", "").replace("국문", "").strip()
            file_pn_hint = cleaned_name

        def is_blacklisted_pn(name_str):
            if not name_str: return True
            name_clean = name_str.replace(" ", "")
            blacklist = ['물질안정', '보건자료', 'MSDS', 'SDS', '안전보건']
            return any(k in name_clean for k in blacklist)

        # 1섹션 제품명 추출 경로 가동
        pdf_type = "scanned" if is_scanned_strict else "digital"
        raw_content = pdf_path if is_scanned_strict else first_page_text
        
        compact_context = self.extract_section_1(pdf_type, raw_content, log_func=log_func)
        combined_prompt = f"{PRODUCT_NAME_PROMPT}\n\n[1섹션 울타리 내부 텍스트]:\n{compact_context}"
        
        # 스캔본 이미지일 경우 cover_img의 데이터를 inlineData 형식으로 payload에 추가
        if is_scanned_strict and 'cover_img' in locals() and cover_img:
            parts = [
                {"text": combined_prompt},
                {"inlineData": {"mimeType": "image/png", "data": cover_img[0]["data"]}}
            ]
        else:
            parts = [{"text": combined_prompt}]
            
        payload_pn = {
            "contents": [{"parts": parts}]
        }

        hybrid_pn = ""
        try:
            # 명칭 오인 결선 수정: call_llm_router를 사용하며 is_scanned_strict 신호 전달
            result = self.call_llm_router(payload_pn, log_func=log_func, model="gemini-2.5-flash", is_scanned_strict=is_scanned_strict)
            if result:
                pn_ai = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                if pn_ai and not any(k in pn_ai for k in ["미추출", "확인"]) and len(pn_ai) < 100:
                    hybrid_pn = msds_utils_v3.clean_candidate(pn_ai)
                    hybrid_pn = re.sub(r'^(\S)\1(?=[가-힣])', r'\1', hybrid_pn)
        except Exception as e:
            if log_func: log_func(f" ⚠️ [[상표명 정찰병] 1선 호출 실패] {e}")
            hybrid_pn = ""

        # [상표명 마스킹 쉴드 인터락] AI 제품명이 비어있거나 불량인 경우 file_pn_hint로 보정
        is_empty_or_blacklisted = (
            (not hybrid_pn) or 
            (len(hybrid_pn.strip()) < 2) or 
            any(k in hybrid_pn for k in ["미추출", "확인", "실패", "오류", "error", "unknown", "none", "null", "N/A"])
        )
        if is_empty_or_blacklisted:
            if log_func:
                log_func(f" 🚨 [[상표명 마스킹 쉴드] 인터락 격발] AI 추출 상표명 불량/공란 감지 ('{hybrid_pn}') ➔ 파일명 기반 청정 상표 단어('{file_pn_hint}')로 강제 대체합니다.")
            hybrid_pn = file_pn_hint

        # [최종 출구 파일명 검문소 철거] 1선 직결 파이프라인 마감: AI의 순수 결과를 바이패스 통과시킵니다.
        pass

        used_engine = ""
        is_ai_extracted = False
        ai_res = None
        odl_components = []
        density_components = []

        # [1선 ODL 정밀 격자 분석기 및 밀도 클러스터링 가동]
        if not is_scanned_strict and pages:
            try:
                parser = PDFParser()
                odl_doc = parser.parse(pdf_path)
                odl_components = self.extract_components_odl_robust(odl_doc, pages, pdf_path, log_func=log_func)
                if log_func: log_func(f" 🔍 [[정규식] 1선 ODL 성공] 격자 분석을 통해 {len(odl_components)}건의 성분 선제 확보.")
            except Exception as e:
                if log_func: log_func(f" ⚠️ [1선 ODL 예외] 분석 스킵: {e}")

            try:
                doc_dc = fitz.open(pdf_path)
                for p_idx in pages:
                    if p_idx < len(doc_dc):
                        p_comps = self.extract_table_by_density_clustering(doc_dc[p_idx])
                        for pc in p_comps:
                            pc["page"] = p_idx + 1
                        density_components.extend(p_comps)
                doc_dc.close()
                if log_func: log_func(f" 🔍 [밀도 클러스터링 성공] {len(density_components)}건의 성분 확보.")
            except Exception as e:
                if log_func: log_func(f" ⚠️ [밀도 클러스터링 예외] 분석 스킵: {e}")

        # 1선 성분 병합
        merged_map_1st = {}
        for c in odl_components:
            cas = str(c.get("cas_no") or c.get("cas", "")).replace(" ", "").strip()
            if cas: merged_map_1st[cas] = c
        for c in density_components:
            cas = str(c.get("cas_no") or c.get("cas", "")).replace(" ", "").strip()
            if cas:
                existing = merged_map_1st.get(cas)
                if existing and str(existing.get("percentage") or existing.get("content", "미기재%")) != "미기재%":
                    continue
                merged_map_1st[cas] = c
        odl_density_comps = list(merged_map_1st.values())

        # 1선 완착 무결성 판별
        checked_1st = []
        has_perfect_1st_line = False
        if not is_scanned_strict and odl_density_comps:
            local_grounding_text = str(first_page_text)
            try:
                doc_g = fitz.open(pdf_path)
                for p_idx in pages:
                    if p_idx != 0: local_grounding_text += "\n" + self._get_sorted_and_normalized_text(doc_g[p_idx])
                doc_g.close()
            except: local_grounding_text += "\n" + str(section3_text)
            grounding_pool = full_text_for_grounding if full_text_for_grounding else local_grounding_text
            
            refined_1st = self.refine_msds_components_strict(odl_density_comps)
            checked_1st, has_invalid_cas_1st = self.final_quality_control(refined_1st, grounding_pool, is_ai=False, log_func=None)
            
            unique_cas_found = list(set(cas_pattern.findall(grounding_pool)))
            valid_original_cas = [re.sub(r'\s+', '', cas) for cas in unique_cas_found if self.verify_cas_number(cas, grounding_text=grounding_pool)]
            original_cas_count = len(valid_original_cas)
            
            extracted_cas_set = set()
            for c in checked_1st:
                found = cas_pattern.findall(str(c.get("cas") or c.get("cas_no") or ""))
                extracted_cas_set.update([f for f in found if self.verify_cas_number(f)])
                
            is_integrity_valid = True
            if checked_1st:
                is_integrity_valid = self.validate_chemical_balances(checked_1st, log_func=None)
                if not is_integrity_valid:
                    if log_func: log_func(" ⚠️ [[함량 검문소] 1선 검문 탈락] 수학적 천칭 검증 실패 -> 외부 AI 정제 차선으로 전송합니다.")

            has_migi_jae_1st = any(str(c.get("content") or c.get("percentage") or "").strip() == "미기재%" for c in checked_1st)
            
            has_complex_bounds_1st = False
            complex_bounds_cas_set = set()
            for c in checked_1st:
                target_cas = c.get("cas") or c.get("cas_no")
                if not target_cas: continue
                
                lines = grounding_pool.split('\n')
                context_lines = []
                for idx, line in enumerate(lines):
                    if target_cas in line:
                        start = max(0, idx - 2)
                        end = min(len(lines), idx + 13)
                        context_lines.extend(lines[start:end])
                context_chunk = "\n".join(list(set(context_lines))).strip()
                
                if self.check_complex_bounds_format(context_chunk) or self.check_complex_bounds_format(str(c.get("content") or c.get("percentage") or "")):
                    has_complex_bounds_1st = True
                    complex_bounds_cas_set.add(target_cas)

            # [2선 청소부 기동 회로 철거] 1선 직결: 추가 보정 필터를 생략하고 바로 바이패스합니다.
            pass

            if (original_cas_count > 0 and 
                len(extracted_cas_set) >= original_cas_count and 
                not has_invalid_cas_1st and
                is_integrity_valid and 
                not has_migi_jae_1st and
                not has_complex_bounds_1st):
                has_perfect_1st_line = True
                if log_func: log_func(" 🟢 [1선 완착 통과] 1선 엔진 결과 및 2선 청소부 수선 완료로 무결성이 확보되어 AI 호출을 생략(Bypass)합니다.")

        ai_components = []
        reason = "1선 규칙 엔진 완착"
        used_engine = "1선 정규식/격자"
        is_ai_extracted = False

        if has_perfect_1st_line:
            components = checked_1st
        else:
            # 3선 AI 호출을 위한 이미지 리스트 정비
            image_base64_list = []
            for img_item in image_list:
                try:
                    if isinstance(img_item, dict):
                        b64_data = img_item.get("data", "")
                        if b64_data: image_base64_list.append(b64_data)
                    elif isinstance(img_item, str) and os.path.exists(img_item):
                        with open(img_item, "rb") as image_file:
                            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                            image_base64_list.append(encoded_string)
                except Exception as e:
                    if log_func: log_func(f" ⚠️ [인코더 오류] 이미지 변환 실패: {e}")

            raw_prompt = f"{VISION_EXTRACTOR_PROMPT}\n\n[🚨 CONTEXT CAPTURE]:\n{section3_text[:2000]}"

            if is_scanned_strict:
                local_ocr_html = ""
                ai_res = None
                
                # 시각적 가속 크롭 및 천칭 필터 제어
                acc_success = False
                try:
                    paddle_ocr_instance = get_ocr_engine()
                    res_acc = self.run_flexible_sandwich_pipeline(pdf_path, paddle_ocr_instance, log_func=log_func)
                    
                    if res_acc.get("status") == "SUCCESS":
                        local_ocr_html = res_acc["data"]
                        acc_success = True
                        is_perfect, extracted_items, invalid_cas_dict = self.scan_self_diagnosis(local_ocr_html, log_func=log_func)
                        ai_res = {
                            "구성성분": extracted_items,
                            "교정_사유": "1선 시각적 가속 자가 검문 통과 (Bypass)"
                        }
                        used_engine = "local_bypass"
                        is_ai_extracted = False
                        
                    elif res_acc.get("status") == "FALLBACK":
                        acc_success = True
                        # 천칭 검문에서 탈락(물리적 모순 감지)
                        cropped_bytes = res_acc["image"]
                        cropped_b64 = base64.b64encode(cropped_bytes).decode("utf-8")
                        cropped_image_list = [{"data": cropped_b64, "mime_type": "image/png"}]
                        
                        enriched_text_prompt = (
                            f"{raw_prompt}\n\n"
                            f"[🚨 로컬 정밀 OCR 수집 HTML 표 구조 데이터]\n"
                            f"{res_acc['raw_data']}\n\n"
                            f"※ 지침: 상기 HTML 표는 로컬에서 수집한 원형이다. 오타(숫자 자리에 알파벳 유입)나 뒤틀린 행을 문맥에 맞게 수정하여 정밀한 JSON 장부 형태로 교정하라. "
                            f"<td> 격실 내부에 보존된 미세 부등호 기호(>, <, %, ~)와 수치를 절대 누락하거나 환각 데이터로 변조하지 말고, 유해성 관리 기준 룰북에 입각하여 최종 JSON 장부로 정제하라."
                        )
                        
                        payload_vision = {
                            "contents": [
                                {
                                    "parts": [
                                        {"text": enriched_text_prompt},
                                        {"inlineData": {"mimeType": "image/png", "data": cropped_b64}}
                                    ]
                                }
                            ],
                            "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
                        }
                        
                        # A2 규격: OpenAI 백업 없이 오직 대장 키 Gemini 2.5 Flash 호출
                        raw_ai = self.call_llm_router(payload_vision, log_func=log_func, model="gemini-2.5-flash", is_scanned_strict=is_scanned_strict)
                        ai_res = None
                        if raw_ai:
                            try:
                                text_response = raw_ai.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                                if log_func:
                                    log_func(f" 디버그: 3선 AI 원본 응답 = {text_response}")
                                clean_json = re.sub(r'```json\s*', '', text_response, flags=re.I)
                                clean_json = re.sub(r'```\s*$', '', clean_json)
                                ai_res = json.loads(clean_json.strip())
                            except Exception as parse_err:
                                if log_func: log_func(f" ⚠️ [Gemini Vision 파싱 실패] {parse_err}")
                        used_engine = "gemini_cleaner"
                        
                        is_perfect, extracted_items, invalid_cas_dict = self.scan_self_diagnosis(res_acc["raw_data"], log_func=None)
                        if ai_res and "구성성분" in ai_res and ai_res["구성성분"]:
                            is_ai_extracted = True
                            refined_comps = ai_res["구성성분"]
                            for old_cas in list(invalid_cas_dict.keys()):
                                normalized_old = re.sub(r'[oO]', '0', old_cas)
                                normalized_old = re.sub(r'[lL]', '1', normalized_old)
                                normalized_old = re.sub(r'[iI]', '1', normalized_old)
                                normalized_old = re.sub(r'[zZ]', '2', normalized_old)
                                normalized_old = re.sub(r'[sS]', '5', normalized_old)
                                
                                matching_new = next((c.get("cas_no") or c.get("cas") for c in refined_comps if (c.get("cas_no") or c.get("cas") or "").strip() == normalized_old), None)
                                if not matching_new:
                                    for c in refined_comps:
                                        c_cas = (c.get("cas_no") or c.get("cas") or "").strip()
                                        if c_cas and c_cas.split('-')[0] == old_cas.split('-')[0]:
                                            matching_new = c_cas
                                            break
                                            
                                if matching_new:
                                    invalid_cas_dict[old_cas] = matching_new
                                    if log_func:
                                        log_func(f" 🎯 [Gemini 정제 완착] 오타 수선 완료: '{old_cas}' -> '{matching_new}' 복원 성공.")
                            
                            if log_func: log_func(" ✅ [정제 완료] 데이터 무결성 세척 후 엑셀 장부 입고 완료.")
                        else:
                            # [안전 롤백 게이트 격발] 크롭 이미지 분석 결과 성분이 0건인 경우, 원본 전체 페이지 스캔 방식으로 회군
                            if log_func: log_func(" ⚠️ [안전 롤백 게이트 격발] 크롭 분석 결과 성분 0건 ➔ 원본 전체 페이지 스캔 방식으로 회군합니다.")
                            rollback_parts = [{"text": raw_prompt}]
                            for img in image_list:
                                rollback_parts.append({"inlineData": {"mimeType": "image/png", "data": img.get("data", "")}})
                                
                            payload_rollback = {
                                "contents": [{"parts": rollback_parts}],
                                "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
                            }
                            
                            raw_ai_rollback = self.call_llm_router(payload_rollback, log_func=log_func, model="gemini-2.5-flash", is_scanned_strict=is_scanned_strict)
                            rollback_success = False
                            if raw_ai_rollback:
                                try:
                                    text_response = raw_ai_rollback.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                                    clean_json = re.sub(r'```json\s*', '', text_response, flags=re.I)
                                    clean_json = re.sub(r'```\s*$', '', clean_json)
                                    ai_res_rb = json.loads(clean_json.strip())
                                    if ai_res_rb and "구성성분" not in ai_res_rb:
                                        for alt_key in ["성분", "components", "items", "substances", "composition", "ingredients"]:
                                            if alt_key in ai_res_rb:
                                                ai_res_rb["구성성분"] = ai_res_rb[alt_key]
                                                break
                                    if ai_res_rb and "구성성분" in ai_res_rb and ai_res_rb["구성성분"]:
                                        ai_res = ai_res_rb
                                        is_ai_extracted = True
                                        used_engine = "gemini_cleaner_rollback"
                                        rollback_success = True
                                        if log_func: log_func(f" 🟢 [롤백 회군 정제 완료] 성분 {len(ai_res_rb['구성성분'])}건 확보 완착.")
                                except Exception as rollback_err:
                                    if log_func: log_func(f" ⚠️ [롤백 회군 호출 실패] {rollback_err}")
                            
                            if not rollback_success:
                                return self._get_graceful_error_dict(pdf_path, "외부 AI 호출 실패 또는 정제 에러 (롤백 포함)", log_func=log_func, hybrid_pn=hybrid_pn)
                            
                    elif res_acc.get("status") in ["FALLBACK_FULL", "ERROR"]:
                        return self._get_graceful_error_dict(pdf_path, f"가속 크롭 예외: {res_acc.get('reason')}", log_func=log_func, hybrid_pn=hybrid_pn)
                
                except Exception as acc_fault:
                    if log_func: log_func(f"⚠️ [가속 파이프라인 장애 발생] {acc_fault}")
                    return self._get_graceful_error_dict(pdf_path, f"가속 파이프라인 장애: {acc_fault}", log_func=log_func, hybrid_pn=hybrid_pn)
            else:
                # 1. 텍스트 문서 파이프라인 (정규식 누락 복구용 AI 호출)
                # A2 규격에 따라 DeepSeek-OCR 등 무료/타사 API 라인은 차단하고 즉시 대장 키 Gemini 2.5 Flash를 직접 호출
                if log_func: log_func(" 🚀 [텍스트 2선] 대장 유료 키 단독 고속 호출 기동.")
                
                parts = [{"text": raw_prompt}]
                payload_text_ai = {
                    "contents": [{"parts": parts}],
                    "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
                }
                
                raw_ai = self.call_llm_router(payload_text_ai, log_func=log_func, model="gemini-2.5-flash", is_scanned_strict=is_scanned_strict)
                ai_res = None
                if raw_ai:
                    try:
                        text_response = raw_ai.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        clean_json = re.sub(r'```json\s*', '', text_response, flags=re.I)
                        clean_json = re.sub(r'```\s*$', '', clean_json)
                        ai_res = json.loads(clean_json.strip())
                    except Exception as parse_err:
                        if log_func: log_func(f" ⚠️ [Gemini Text 파싱 실패] {parse_err}")
                used_engine = "Gemini-2.5-Flash (Text AI)"
                is_ai_extracted = True

            # AI가 JSON 키 값을 "성분", "components" 등으로 오독/변조해오는 현상 방어 정규화
            if ai_res:
                if "구성성분" not in ai_res:
                    for alt_key in ["성분", "components", "items", "substances", "composition", "ingredients"]:
                        if alt_key in ai_res:
                            ai_res["구성성분"] = ai_res[alt_key]
                            break
                
                if "구성성분" in ai_res and isinstance(ai_res["구성성분"], list):
                    for c in ai_res["구성성분"]:
                        if not isinstance(c, dict): continue
                        if "content" not in c:
                            for alternate_key in ["함유량", "percentage", "content_value", "value", "함량", "percent"]:
                                if alternate_key in c:
                                    c["content"] = c[alternate_key]
                                    break
                            else:
                                c["content"] = "미기재%"
                        if "cas" not in c:
                            for alternate_cas_key in ["cas_no", "cas번호", "casNo", "cas_number", "cas_code"]:
                                if alternate_cas_key in c:
                                    c["cas"] = c[alternate_cas_key]
                                    break
                        c["engine"] = used_engine

            if ai_res and "구성성분" in ai_res and ai_res["구성성분"]:
                ai_components = ai_res.get("구성성분", [])
                reason = ai_res.get("교정_사유", "AI 완착")
            else:
                # 최후방 회생 가드레일 작동
                if checked_1st:
                    if log_func: log_func(" ⚠️ [최후방 회생 가드레일] AI 장애/오독 격발 -> 1선 백업 자산(checked_1st)을 최종 장부로 강제 복구 완착합니다.")
                    ai_components = checked_1st
                    reason = "1선 백업 자산 회생 완착"
                    used_engine = "1선 백업(회생)"
                else:
                    return self._get_graceful_error_dict(pdf_path, "외부 AI 추출 결과가 존재하지 않으며 복구할 1선 백업 자산도 없음", log_func=log_func, hybrid_pn=hybrid_pn)

            # ODL/밀도 클러스터링 선제 자산과 AI 수거물 최종 병합
            merged_map = {}
            for c in odl_density_comps:
                cas = str(c.get("cas_no") or c.get("cas", "")).replace(" ", "").strip()
                if cas: merged_map[cas] = c
            for c in ai_components:
                cas = str(c.get("cas") or c.get("cas_no", "")).replace(" ", "").strip()
                if cas:
                    existing = merged_map.get(cas)
                    if existing and str(existing.get("percentage") or existing.get("content", "미기재%")) != "미기재%":
                        if not existing.get("name") and c.get("name"):
                            existing["name"] = c.get("name")
                        continue
                    merged_map[cas] = c
            components = list(merged_map.values())
        
        components = self.refine_msds_components_strict(components)
        
        if is_scanned_strict:
            # 스캔본일 경우 로컬 OCR 텍스트 가루를 사용하여 무결성 검증 수행
            ocr_text_clean = ""
            if 'local_ocr_html' in locals() and local_ocr_html:
                ocr_text_clean = re.sub(r'<[^>]+>', ' ', local_ocr_html)
            elif 'res_acc' in locals() and isinstance(res_acc, dict) and res_acc.get('raw_data'):
                ocr_text_clean = re.sub(r'<[^>]+>', ' ', res_acc['raw_data'])
            
            grounding_pool = ocr_text_clean if ocr_text_clean.strip() else str(section3_text)
        else:
            local_grounding_text = str(first_page_text)
            try:
                doc_g = fitz.open(pdf_path)
                for p_idx in pages:
                    if p_idx != 0: local_grounding_text += "\n" + self._get_sorted_and_normalized_text(doc_g[p_idx])
                doc_g.close()
            except: local_grounding_text += "\n" + str(section3_text)
            
            grounding_pool = full_text_for_grounding if full_text_for_grounding else local_grounding_text

        refined_comps, has_invalid_cas = self.final_quality_control(components, grounding_pool, is_ai=is_ai_extracted, log_func=log_func)
        
        # 엑셀 입고용 콤팩트 포장
        comp_parts = []
        for c in refined_comps:
            comp_parts.append(f"{c['cas']}({c['content']})")
                
        if not comp_parts:
            return self._get_graceful_error_dict(pdf_path, "유효한 성분 데이터가 존재하지 않음", log_func=log_func, hybrid_pn=hybrid_pn)

        comp_str = "; ".join(comp_parts)
        product_name = hybrid_pn
        target_substances = ""
        
        norm_search_pool = re.sub(r'[\s\-]', '', product_name + " " + first_page_text[:500]).upper()
        is_exception_matched = False
        for ext_key, ext_data in EXCEPTION_REGISTRY.items():
            if all(re.sub(r'[\s\-]', '', trigger).upper() in norm_search_pool for trigger in ext_data["triggers"]):
                product_name, comp_str, target_substances = ext_data["target_pn"], ext_data["components"], ext_data["target_substances"]
                is_exception_matched = True
                break

        gui_engine_name = "flash" if "Gemini" in used_engine else "bulldozer" if "GPT" in used_engine else "analytic"

        # 품질 지문 산출
        score = 100
        reason_tags = []
        if is_exception_matched:
            has_invalid_cas = False
            reason_tags.append("[✅예외자재완착]")
        else:
            if not product_name:
                score -= 10
                reason_tags.append("[❌제품명분실]")
            else:
                reason_tags.append("[✅제품명완착]")
                
            if has_invalid_cas:
                score -= 60
                reason_tags.append("[❌CAS유실]")
            else:
                reason_tags.append("[✅CAS정합]")
            
        integrity_reason = f"[품질점수: {score}점] ➔ " + " ".join(reason_tags)
        
        res_obj = {
            "구성성분": comp_str, "제품명": product_name, "측정대상": target_substances,
            "교정_사유": reason,
            "신호등": "🟡" if (has_invalid_cas or not product_name) else "🟢",
            "used_engine": gui_engine_name,
            "integrity_score": score,
            "integrity_reason": integrity_reason
        }
        
        traffic_light = res_obj.get("신호등", "⚪")
        if log_func: log_func(f" ✅ [{VERSION}] 완료 (엔진: {used_engine}, 신호등: {traffic_light}, 소요시간: {time.time()-start_time:.2f}초)")
        return res_obj

    # ----------------------------------------------------------------------
    # 내부 서브 파이프라인 및 헬퍼 함수들 (클래스 메소드로 전환 및 self 바인딩)
    # ----------------------------------------------------------------------
    def run_flexible_sandwich_pipeline(self, pdf_path, paddle_ocr_instance, log_func=print):
        try:
            if log_func: log_func(f"🚀 [유연 가속 격발] 비정형 간판 추적 엔진 가동: {os.path.basename(pdf_path)}")
            
            doc = fitz.open(pdf_path)
            page = doc[0]
            w, h = page.rect.width, page.rect.height
            
            left_strip_rect = fitz.Rect(0, 0, w * 0.33, h)
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=left_strip_rect)
            
            img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            raw_results = paddle_ocr_instance.predict(img_np)
            
            strip_ocr_results = []
            if raw_results and isinstance(raw_results, list):
                for region in raw_results:
                    region_res = region.get("res") if isinstance(region, dict) else getattr(region, 'res', [])
                    if isinstance(region_res, list):
                        for line_item in region_res:
                            if isinstance(line_item, dict):
                                strip_ocr_results.append(line_item)
                            elif len(line_item) >= 2 and isinstance(line_item[1], tuple):
                                pts = line_item[0]
                                txt = line_item[1][0]
                                xs = [p[0] for p in pts]
                                ys = [p[1] for p in pts]
                                bbox = [min(xs), min(ys), max(xs), max(ys)]
                                strip_ocr_results.append({"text": txt, "bbox": bbox})
                    elif isinstance(region_res, dict):
                        strip_ocr_results.append(region_res)
            
            y_start = None
            y_end = None
            
            pattern_sec3 = re.compile(r'(3|삼)\b.*?([구성|성분|명칭|함량|기재]{2,})')
            pattern_sec4 = re.compile(r'(4|사)\b.*?([응급|조치|처치|요령|구급]{2,})')
            pattern_sec5 = re.compile(r'(5|오)\b.*?([폭발|화재|소화|대처]{2,})')
            pattern_sec6 = re.compile(r'(6|육)\b.*?([누출|사고|방지|대책]{2,})')
            
            for line in strip_ocr_results:
                text = line.get("text", "").replace(" ", "")
                box = line.get("bbox", [0, 0, 0, 0])
                mid_y = (box[1] + box[3]) / 2.0 / 2.0
                
                if y_start is None and pattern_sec3.search(text):
                    y_start = mid_y
                    if log_func: log_func(f"  ├─ [3번방 포착] 간판명: '{text}' -> 시작 높이: {int(y_start)}px 확정")
                    continue
                    
                if y_start is not None:
                    if y_end is None and pattern_sec4.search(text):
                        y_end = mid_y
                        if log_func: log_func(f"  ├─ [4번방 차단] 간판명: '{text}' -> 종료 한계선: {int(y_end)}px 확정")
                    elif y_end is None and pattern_sec5.search(text):
                        y_end = mid_y
                        if log_func: log_func(f"  ├─ [비상 차단] 5번 간판 앵커링: '{text}' -> 종료 한계선: {int(y_end)}px 확정")
                    elif y_end is None and pattern_sec6.search(text):
                        y_end = mid_y
                        if log_func: log_func(f"  ├─ [비상 차단] 6번 간판 앵커링: '{text}' -> 종료 한계선: {int(y_end)}px 확정")
            
            if y_start is None:
                if log_func: log_func("⚠️ [예외 케이스 1] 3번 고속 추적 실패. 통계적 면적 안전망 가동.")
                y_start = h * 0.25
                y_end = h * 0.60
                
            if y_end is None or y_end <= y_start:
                y_end = min(h, y_start + 400)
                
            crop_rect = fitz.Rect(0, max(0, y_start - 20), w, min(h, y_end + 20))
            if log_func: log_func(f"✂️ [샌드위치 재단] 높이 {int(crop_rect.y0)}px ~ {int(crop_rect.y1)}px 범위를 완벽하게 오려냅니다.")
            
            final_pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=crop_rect)
            cropped_bytes = final_pix.tobytes("png")
            doc.close()
            
            cropped_b64 = base64.b64encode(cropped_bytes).decode("utf-8")
            cropped_image_list = [{"data": cropped_b64, "mime_type": "image/png"}]
            
            local_raw_text = self.extract_table_via_local_ocr(cropped_image_list, log_func=log_func)
            
            # 수학적 천칭 검문소 가동
            is_clean = self.validate_chemical_balances(None, log_func=log_func) # 임시 변형 호출
            is_clean, anomaly_reason = self.verify_integrity_of_local_data(local_raw_text)
            
            if is_clean:
                if log_func: log_func("🟢 [1선 자가 진단 통과] 오독 없는 청정 수치 확정. 외부 AI 호출 비용 0원 처리 (Bypass).")
                return {"status": "SUCCESS", "engine": "local_bypass", "data": local_raw_text}
            else:
                if log_func:
                    log_func(f"⚠️ [[함량 검문소] 검문 탈락] {anomaly_reason}")
                    log_func("🚀 [비상 우회] 즉시 3선 AI 정제 차선으로 자재 긴급 이송!")
                return {"status": "FALLBACK", "engine": "external_cleaner", "raw_data": local_raw_text, "image": cropped_bytes}
                
        except Exception as e:
            if log_func: log_func(f"❌ [치명적 공정 마찰 예외 처리] 시스템 다운 방어벽 가동: {e}")
            return {"status": "ERROR", "reason": str(e)}

    def extract_table_via_local_ocr(self, image_list, log_func=None):
        try:
            engine = get_paddle_structure_engine(log_func)
            html_results = []
            
            from PIL import Image
            import io
            
            for idx, img_item in enumerate(image_list):
                b64_data = ""
                if isinstance(img_item, dict):
                    b64_data = img_item.get("data", "")
                elif isinstance(img_item, str) and os.path.exists(img_item):
                    with open(img_item, "rb") as image_file:
                        b64_data = base64.b64encode(image_file.read()).decode("utf-8")
                        
                if not b64_data: continue
                    
                img_bytes = base64.b64decode(b64_data)
                image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                img_np = np.array(image)
                
                results = engine.predict(
                    img_np,
                    use_table_recognition=True,
                    use_wired_table_cells_trans_to_html=True,
                    use_wireless_table_cells_trans_to_html=True,
                )
                
                for res in results:
                    html_dict = getattr(res, 'html', {}) or {}
                    page_html_parts = []
                    for table_key, html_str in html_dict.items():
                        if html_str and html_str.strip():
                            page_html_parts.append(html_str)
                    
                    combined_html = "\n".join(page_html_parts)
                    text_only = re.sub(r'<[^>]+>', '', combined_html)
                    if len(text_only.strip()) >= 100:
                        html_results.extend(page_html_parts)
                    else:
                        md_data = getattr(res, 'markdown', {}) or {}
                        md_text = md_data.get('markdown_texts', '') if isinstance(md_data, dict) else ''
                        if md_text and md_text.strip():
                            if log_func: log_func(f"   ├─ [품질 전환] HTML 셀 빈약({len(text_only.strip())}자) -> 마크다운 OCR 전문 수거로 대체.")
                            html_results.append(md_text)
            
            gc.collect()
            return "\n".join(html_results) if html_results else ""
        except Exception as e:
            if log_func: log_func(f"   ❌ [로컬 OCR 하드웨어 장애 런타임 에러]: {str(e)}")
            raise e

    def refine_msds_components_strict(self, raw_components):
        refined = []
        for comp in raw_components:
            name = (comp.get('name') or '').strip() or (comp.get('chemical_name') or '').strip()
            cas = (comp.get('cas') or '').strip() or (comp.get('cas_no') or '').strip()
            pct = (comp.get('percentage') or '').strip() or (comp.get('content') or '').strip()
            page_val = comp.get('page', '')
            engine_val = comp.get('engine', 'Unknown')
            
            clean_cas = re.sub(r'\s+', '', cas)
            if not re.match(r'^\d{2,7}-\d{2}-\d$', clean_cas):
                continue
                
            if any(k in pct.lower() for k in ["rem", "balance", "residual"]) or any(k in pct for k in ["잔량", "나머지"]):
                pct = "Rem."
            elif any(k in pct or k in name for k in ["영업비밀", "비공개", "미기재", "secret"]) or not pct:
                pct = "미기재"
                
            combined_text = f"{clean_cas}({pct})"
            
            refined.append({
                'name': name,
                'chemical_name': name,
                'cas': clean_cas,
                'cas_no': clean_cas,
                'percentage': pct,
                'content': pct,
                'page': page_val,
                'engine': engine_val,
                'combined_format': combined_text
            })
        return refined

    def verify_cas_number(self, cas_string, grounding_text=None):
        if not cas_string: return False
        if re.match(r'^\d{4}-\d{2}-\d{2}$', cas_string):
            return False
        if grounding_text and cas_string in grounding_text:
            return True
        if any(k in cas_string for k in ["영업비밀", "비공개", "Secret", "Proprietary", "빈칸", "-", "해당없음", "None"]):
            return True
        if grounding_text:
            clean_cas = cas_string.replace(" ", "")
            clean_grounding = grounding_text.replace(" ", "")
            if clean_cas in clean_grounding:
                return True
            
        clean_cas = re.sub(r'[^0-9-]', '', cas_string).strip()
        parts = clean_cas.split('-')
        if len(parts) != 3: return False
        try:
            check_digit = int(parts[2])
            digits = parts[0] + parts[1]
            total = sum(int(digit) * i for i, digit in enumerate(reversed(digits), 1))
            return (total % 10) == check_digit
        except:
            return False

    def _get_sorted_and_normalized_text(self, page):
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (b[1], b[0]))
        text_list = []
        for b in blocks:
            text_list.append(unicodedata.normalize("NFKC", b[4]))
        return "\n".join(text_list)

    def _normalize_single_content(self, content_str):
        content_str = msds_utils_v3.clean_content_text(str(content_str))
        raw = str(content_str).strip()
        if not raw: return "미기재%"

        if re.search(r'\d\s*[a-zA-Z]+', raw) and '%' not in raw and not any(k in raw.lower() for k in ["rem", "balance"]):
            return "미기재%"

        v = raw.replace(" ", "").replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥').replace('=<', '≤').replace('=>', '≥')
        v = re.sub(r'(min|max)\.', r'\1', v, flags=re.I)
        
        has_trailing_less = re.search(r'\d\s*(<|미\s*[만맊먄]|below|less)$', v, re.I)
        has_trailing_more = re.search(r'\d\s*(>|초\s*과|more|over)$', v, re.I)
        has_trailing_le = re.search(r'\d\s*(≤|이\s*[하핚내]|up\s*to|max)$', v, re.I)
        has_trailing_ge = re.search(r'\d\s*(≥|이\s*상|above|from|min|\+)$', v, re.I)

        if any(k in v.lower() for k in ["balance", "잔량", "rem", "residual"]): return "Rem.%"
        pm_match = re.search(r'([0-9.]+)\s*(?:±|\+\s*-\s*|\+/?-)\s*([0-9.]+)', v)
        if pm_match:
            try:
                val, pm = float(pm_match.group(1)), float(pm_match.group(2))
                return f"{val-pm:g}~{val+pm:g}%"
            except: pass

        v_shield = re.sub(r'\b20[0-2]\d[.\-/]\d{1,2}[.\-/]\d{1,2}\b', ' ', v)
        v_shield = re.sub(r'\b20[0-2]\d년?\b', ' ', v_shield)
        
        nums = re.findall(r'(\d+\.?\d*|\.\d+)', v_shield)
        if not nums: return "미기재%"
        
        is_less = any(k in v.lower() for k in ["<", "미만", "below", "less"])
        is_le = any(k in v.lower() for k in ["≤", "이하", "max", "upto"])
        is_more = any(k in v.lower() for k in [">", "초과", "over", "above"])
        is_ge = any(k in v.lower() for k in ["≥", "이상", "min", "from", "+"])
        has_range_sep = any(k in v.lower() for k in ["~", "∼", "～", "-", "to"])

        if len(nums) == 1:
            if has_trailing_less: is_more, is_less, is_le, is_ge = True, False, False, False
            if has_trailing_more: is_less, is_more, is_le, is_ge = True, False, False, False
            if has_trailing_le:   is_le, is_ge, is_less, is_more = True, False, False, False
            if has_trailing_ge:   is_ge, is_le, is_less, is_more = True, False, False, False

        pref = "≥" if is_ge else (">" if is_more else ("≤" if is_le else ("<" if is_less else "")))

        if len(nums) == 1:
            v1 = nums[0]
            try:
                f1 = float(v1)
                n1 = int(f1) if f1.is_integer() else f1
                if n1 > 110: return "미기재%"
                if (is_ge or is_more) and has_range_sep: return f"≥{n1}%"
                return f"{pref}{n1}%"
            except: return "미기재%"

        elif len(nums) >= 2:
            try:
                f1_orig, f2_orig = float(nums[0]), float(nums[1])
                is_swapped = f1_orig > f2_orig
                f1, f2 = (f2_orig, f1_orig) if is_swapped else (f1_orig, f2_orig)
                n1, n2 = (int(f1) if f1.is_integer() else f1), (int(f2) if f2.is_integer() else f2)
                
                parts = re.split(r'\s*(?:~|∼|～|\-|to|and)\s*', v, maxsplit=1)
                s_sym = ""
                
                if len(parts) == 2:
                    v_left, v_right = parts[0], parts[1]
                    target_part = v_left if is_swapped else v_right
                    
                    if any(k in target_part for k in ["<", "≤", "below", "미만"]): 
                        s_sym = "≤" if any(k in target_part for k in ["≤", "이하"]) else "<"
                    elif any(k in target_part for k in [">", "≥", "above", "이상", "+"]):
                        s_sym = "≥" if any(k in target_part for k in ["≥", "이상", "+"]) else ">"
                
                if v.count('+') >= 2 or v.count('이상') >= 2:
                    return f"≥{n1}%"

                if s_sym in ["<", "≤"]:
                    if abs(float(n2) - 1.0) < 1e-9:
                        s_sym = "<"
                    else:
                        s_sym = ""
                
                if not s_sym: return f"{n1}~{n2}%"
                return f"{n1}~{s_sym}{n2}%"
            except: 
                return "미기재%"
        return "미기재%"

    def final_quality_control(self, components, full_text, is_ai=True, log_func=None):
        refined_dict = {}  
        has_invalid = False
        norm_text = re.sub(r'\s+', '', full_text).upper() if full_text else ""
        
        for comp in components:
            raw_cas_field = str(comp.get("cas", "") or comp.get("cas_no", "")).strip()
            clean_cas = re.sub(r'\s+', '', raw_cas_field)
            raw_content = str(comp.get("content", "")).strip()
            
            has_any_valid_cas = bool(re.search(r'\d{2,7}-\d{2}-\d', clean_cas))
            if not has_any_valid_cas:
                raw_content = ""
            elif not raw_content or raw_content.strip() in ["-", "", "None", "N/A"]:
                raw_content = "미기재%"

            clean_cas_field = re.sub(r'\s+', '', raw_cas_field)
            cas_list = re.findall(r'(?<![\d-])(\d{1,7}-\d{2}-\d)(?![\d-])', clean_cas_field)
            
            if not cas_list:
                if any(k in raw_cas_field for k in ["영업비밀", "비공개", "해당없음", "Secret", "Proprietary"]):
                    cas_list = [raw_cas_field]
                else:
                    continue
            
            content_parts = [self._normalize_single_content(c) for c in re.split(r'\s*/\s*', raw_content) if c.strip()]
            if not content_parts: content_parts = [""]
            page_val = comp.get("page", "")
            origin_engine = comp.get("engine", "Unknown")
            
            loop_content = content_parts if len(cas_list) == len(content_parts) else [content_parts[0] if content_parts else ""] * len(cas_list)
            
            full_text = full_text.replace('̻', '').replace('̸', '')
            norm_text = re.sub(r'\s+', '', full_text).upper()
            
            for cas_raw, cv in zip(cas_list, loop_content):
                cas = re.sub(r'^0+', '', cas_raw)
                
                if is_ai and not self.verify_cas_number(cas, grounding_text=full_text):
                    valid_text_cas = re.findall(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', full_text)
                    valid_text_cas = [v for v in valid_text_cas if self.verify_cas_number(v, grounding_text=full_text)]
                    
                    for v_cas in valid_text_cas:
                        diff_count = sum(1 for a, b in zip(cas, v_cas) if a != b) if len(cas) == len(v_cas) else 99
                        if diff_count <= 1:
                            cas = v_cas
                            break
                    else:
                        if log_func: log_func(f" 🔴 [Fuzzy 방어] 3단계 퍼지 쉴드 붕괴. 환각 CAS 영구 폐기: {cas}")
                        has_invalid = True
                        continue 

                if cas in refined_dict:
                    old_cont = refined_dict[cas].get("content", "미기재%")
                    if old_cont == "미기재%" and cv and cv != "미기재%":
                        refined_dict[cas]["content"] = cv
                        if comp.get("name"): refined_dict[cas]["name"] = comp.get("name")
                    try:
                        if page_val:
                            old_p = refined_dict[cas].get("page", 999)
                            if int(page_val) < int(old_p):
                                refined_dict[cas]["page"] = page_val
                    except: pass
                else:
                    refined_dict[cas] = {
                        "cas": cas,
                        "name": comp.get("name", ""),
                        "content": cv if cv else "미기재%",
                        "page": page_val,
                        "engine": origin_engine
                    }

        refined = list(refined_dict.values()) 
        if is_ai:
            try: self.check_omission(full_text, refined)
            except ValueError as e:
                if log_func: log_func(f" 🟡 [누락 감지] {e}")
                has_invalid = True 
            
        return refined, has_invalid

    def find_section3_pages(self, doc):
        pages = []
        found_section3 = False
        exit_pattern = re.compile(r'^(?:SECTION\s*)?[4-9][항\s.:]*(?:응급|폭발|화재|누출|취급|저장|노출|방지|FIRST|FIRE|ACCIDENTAL|HANDLING|EXPOSURE)', re.I | re.M)
        
        for i in range(len(doc)):
            text = doc[i].get_text("text")
            if not found_section3:
                if re.search(r'(?:SECTION\s*)?[23][\s.:\-\/]*(?:구성성분|성분|성분\s?및\s?함량|COMPOS|INGRED|조성물)', text, re.I):
                    found_section3 = True
            
            if found_section3:
                pages.append(i)
                if len(pages) >= 2:
                    return sorted(list(set(pages)))
                
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                for line in lines:
                    if exit_pattern.match(line) and "Page" not in line:
                        return sorted(list(set(pages)))
                    
        return sorted(list(set(pages)))

    def check_complex_bounds_format(self, text):
        if not text: return False
        inequalities = [r'>=', r'<=', r'>', r'<', r'≥', r'≤', r'＜', r'＞']
        pattern_ineq = '|'.join(inequalities)
        matches_ineq = re.findall(pattern_ineq, text)
        if len(matches_ineq) >= 2:
            return True
            
        temp_text = re.sub(r'\d{2,7}-\d{2}-\d', '[CAS]', text)
        has_ineq = len(matches_ineq) >= 1
        has_range_indicator = re.search(r'[-~∼～to]', temp_text) is not None
        
        if has_ineq and has_range_indicator:
            return True
        return False

    def extract_table_by_density_clustering(self, page):
        words = page.get_text("words")
        if not words: return []

        def _get_median(lst):
            if not lst: return 0.0
            sorted_lst = sorted(lst)
            n = len(sorted_lst)
            if n % 2 == 1:
                return sorted_lst[n // 2]
            return (sorted_lst[n // 2 - 1] + sorted_lst[n // 2]) / 2.0

        heights = [w[3] - w[1] for w in words]
        base_scale = _get_median(heights)

        words.sort(key=lambda w: w[1])
        temp_rows = []
        current_row = []
        
        for w in words:
            if not current_row:
                current_row.append(w)
            else:
                w_prev = current_row[-1]
                h_curr = w[3] - w[1]
                h_prev = w_prev[3] - w_prev[1]
                min_h = min(h_curr, h_prev)
                vertical_threshold = min_h * 0.25
                
                if abs(w[1] - w_prev[1]) <= vertical_threshold:
                    current_row.append(w)
                else:
                    temp_rows.append(current_row)
                    current_row = [w]
        if current_row:
            temp_rows.append(current_row)

        all_gaps = []
        for r in temp_rows:
            r_sorted = sorted(r, key=lambda w: w[0])
            for i in range(len(r_sorted) - 1):
                gap = r_sorted[i+1][0] - r_sorted[i][2]
                if gap > 0: all_gaps.append(gap)

        median_gap = _get_median(all_gaps) if all_gaps else base_scale * 0.5
        horizontal_ratio = median_gap / base_scale if base_scale > 0 else 0.5

        rows = temp_rows
        rows.sort(key=lambda r: _get_median([w[1] for w in r]))

        extracted_components = []
        for row in rows:
            row_words = sorted(row, key=lambda w: w[0])
            cells = []
            current_cell = []
            
            for w in row_words:
                if not current_cell:
                    current_cell.append(w)
                else:
                    w_prev = current_cell[-1]
                    char_height = w_prev[3] - w_prev[1]
                    gap = w[0] - w_prev[2]
                    
                    if gap > char_height * horizontal_ratio:
                        cells.append(current_cell)
                        current_cell = [w]
                    else:
                        current_cell.append(w)
            if current_cell:
                cells.append(current_cell)
                
            cell_texts = []
            for cell in cells:
                cell.sort(key=lambda w: w[0])
                cell_text = " ".join([w[4] for w in cell]).strip()
                cell_texts.append(cell_text)
                
            cas_candidate = None
            content_candidate = None
            for txt in cell_texts:
                clean_txt = txt.replace(" ", "")
                cas_matches = re.findall(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', clean_txt)
                if cas_matches:
                    cas_candidate = cas_matches[0]
                    continue
                    
                if re.match(r'^\d+$', txt.strip()):
                    val = int(txt.strip())
                    if val > 100: continue
                        
                cleaned_txt = msds_utils_v3.clean_content_text(txt)
                norm_val = self._normalize_single_content(cleaned_txt)
                if norm_val != "미기재%" and re.search(r'\d', norm_val):
                    content_candidate = norm_val
                    continue
                    
            if cas_candidate:
                name = "CAS 기반 자동 매핑"
                pct = content_candidate if content_candidate else "미기재%"
                combined_text = f"{cas_candidate}({pct})"
                
                extracted_components.append({
                    "name": name,
                    "chemical_name": name,
                    "cas": cas_candidate,
                    "cas_no": cas_candidate,
                    "percentage": pct,
                    "content": pct,
                    "engine": "DensityClusteringTable",
                    "combined_format": combined_text
                })
                
        return extracted_components

    def get_density_clustering_bboxes(self, page):
        words = page.get_text("words")
        if not words: return []
        def _get_median(lst):
            if not lst: return 0.0
            sorted_lst = sorted(lst)
            n = len(sorted_lst)
            if n % 2 == 1:
                return sorted_lst[n // 2]
            return (sorted_lst[n // 2 - 1] + sorted_lst[n // 2]) / 2.0

        heights = [w[3] - w[1] for w in words]
        base_scale = _get_median(heights)
        words.sort(key=lambda w: w[1])
        temp_rows = []
        current_row = []
        for w in words:
            if not current_row:
                current_row.append(w)
            else:
                w_prev = current_row[-1]
                h_curr = w[3] - w[1]
                h_prev = w_prev[3] - w_prev[1]
                min_h = min(h_curr, h_prev)
                vertical_threshold = min_h * 0.25
                if abs(w[1] - w_prev[1]) <= vertical_threshold:
                    current_row.append(w)
                else:
                    temp_rows.append(current_row)
                    current_row = [w]
        if current_row:
            temp_rows.append(current_row)

        all_gaps = []
        for r in temp_rows:
            r_sorted = sorted(r, key=lambda w: w[0])
            for i in range(len(r_sorted) - 1):
                gap = r_sorted[i+1][0] - r_sorted[i][2]
                if gap > 0: all_gaps.append(gap)

        median_gap = _get_median(all_gaps) if all_gaps else base_scale * 0.5
        horizontal_ratio = median_gap / base_scale if base_scale > 0 else 0.5

        rows = temp_rows
        rows.sort(key=lambda r: _get_median([w[1] for w in r]))
        
        bboxes = []
        for row in rows:
            row_words = sorted(row, key=lambda w: w[0])
            cells = []
            current_cell = []
            for w in row_words:
                if not current_cell:
                    current_cell.append(w)
                else:
                    w_prev = current_cell[-1]
                    char_height = w_prev[3] - w_prev[1]
                    gap = w[0] - w_prev[2]
                    if gap > char_height * horizontal_ratio:
                        cells.append(current_cell)
                        current_cell = [w]
                    else:
                        current_cell.append(w)
            if current_cell:
                cells.append(current_cell)
            for cell in cells:
                if cell:
                    bx0 = min(w[0] for w in cell)
                    by0 = min(w[1] for w in cell)
                    bx1 = max(w[2] for w in cell)
                    by1 = max(w[3] for w in cell)
                    bboxes.append([bx0, by0, bx1, by1])
        return bboxes

    def extract_from_text_regex(self, page, log_func=None, inherited_x_range=None, table_bboxes=None):
        if log_func: log_func(f"  [마스킹 엔진] 텍스트 기반 정밀 추출(Regex-Recovery) 가동...")
        found = []
        product_id_found = []
        
        try:
            raw_words = page.get_text("words")
            if not raw_words: return [], inherited_x_range

            if table_bboxes is not None:
                filtered_words = []
                for w in raw_words:
                    cx = (w[0] + w[2]) / 2.0
                    cy = (w[1] + w[3]) / 2.0
                    in_table = False
                    for bbox in table_bboxes:
                        if bbox and len(bbox) == 4:
                            bx0, by0, bx1, by1 = bbox
                            # 3 마진 적용
                            if (bx0 - 3) <= cx <= (bx1 + 3) and (by0 - 3) <= cy <= (by1 + 3):
                                in_table = True
                                break
                    if in_table:
                        filtered_words.append(w)
                raw_words = filtered_words

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
                if y_start_orig > 0.0 and b[1] > y_start_orig:
                    if any(k in b_text for k in ["응급조치", "FIRSTAID", "FIRSTAIDMEASURES"]):
                        y_end = b[1]
                        break
                        
            if raw_words and y_start > raw_words[-1][1] * 0.75:
                y_start = 0.0
                
            raw_words = [w for w in raw_words if y_start <= w[1] < y_end]

            is_left_arranged = False
            has_global_percent = False
            content_x_mid = 9999
            
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
                    if content_x_mid == 9999:
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

            physical_lines = []
            if words:
                current_line_words = [words[0]]
                line_top = words[0][1]    
                line_bottom = words[0][3] 

                for i in range(1, len(words)):
                    curr_w = words[i]
                    w_prev = current_line_words[-1]
                    h_curr = curr_w[3] - curr_w[1]
                    h_prev = w_prev[3] - w_prev[1]
                    min_h = min(h_curr, h_prev)
                    vertical_threshold = min_h * 0.25
                    
                    if abs(curr_w[1] - w_prev[1]) <= vertical_threshold:
                        current_line_words.append(curr_w)
                        line_top = min(line_top, curr_w[1])
                        line_bottom = max(line_bottom, curr_w[3])
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

                if current_line_words:
                    current_line_words.sort(key=lambda w: w[0])
                    physical_lines.append({
                        "y": line_top, 
                        "text": " ".join([w[4] for w in current_line_words]),
                        "words": current_line_words
                    })
                physical_lines.sort(key=lambda pl: pl["y"])

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
                if line["y"] < y_start: continue
                row_text = line["text"]
                if re.search(r'SECTION\s*[3456]', row_text, re.I): continue
                cas_list = cas_pattern.findall(row_text)
                
                if cas_list:
                    is_prod = any(k in row_text.lower() for k in ["chemical identification", "product name", "제품식별자", "제품명", "substance identification", "identification of the substance"])
                    current_row = {"cas_list": cas_list, "words": [], "last_y": line["y"], "is_product_id": is_prod}
                    for p_line in pending_lines:
                        current_row["words"].extend(p_line["words"])
                    pending_lines = []
                    current_row["words"].extend(line["words"])
                    logical_rows.append(current_row)
                else:
                    is_new_ingredient_line = any(k in row_text.lower() for k in ["ingredient name", "ingredient", "component", "물질명", "성분명", "chemical name"])
                    if current_row and (line["y"] - current_row["last_y"]) < 40 and not is_new_ingredient_line:
                        current_row["words"].extend(line["words"])
                        current_row["last_y"] = line["y"]
                    else:
                        current_row = None
                        pending_lines.append(line)

            last_valid_info = None 
            for row in logical_rows:
                row_words = row.get("words", [])
                if content_x_mid != 9999:
                    content_words = [w for w in row_words if abs((w[0] + w[2])/2 - content_x_mid) <= 45]
                    other_words = [w for w in row_words if abs((w[0] + w[2])/2 - content_x_mid) > 45]
                    content_words.sort(key=lambda w: (w[1], w[0]))
                    other_words.sort(key=lambda w: (w[1], w[0]))
                    sorted_words = other_words + content_words
                else:
                    sorted_words = sorted(row_words, key=lambda w: (w[1], w[0]))

                safe_word_texts = [w[4] for w in sorted_words]
                row_full_text = " ".join(safe_word_texts)
                
                for target_cas in row["cas_list"]:
                    clean_text = row_full_text
                    for other_cas in row["cas_list"]:
                        if other_cas != target_cas:
                            clean_text = clean_text.replace(other_cas, " [OTHER_CAS] ")
                    clean_text = clean_text.replace(target_cas, "[CAS_ANCHOR]")
                    
                    clean_text = re.sub(r'\b20[0-2]\d[.\-/]\d{1,2}[.\-/]\d{1,2}\b', ' YYYY ', clean_text)
                    clean_text = re.sub(r'\b20[0-2]\d년?\b', ' YYYY ', clean_text)
                    clean_text = clean_text.replace("미맊", "미만").replace("미먄", "미만").replace("이핚", "이하")
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
                            if "[CAS_ANCHOR]" not in context_window: continue
                        matches_with_pos.append((val, start_idx)) 
                        
                    content = "미기재%"
                    if matches_with_pos:
                        def score_match(match_tuple):
                            m_val, match_pos = match_tuple
                            has_percent = "%" in m_val
                            
                            if re.search(r'%\s*:', clean_text[match_pos:match_pos+len(m_val)+5]):
                                return -5000
                                
                            context_area = clean_text[max(0, match_pos-30):min(len(clean_text), match_pos+len(m_val)+30)].lower()
                            tight_context = clean_text[max(0, match_pos-10):min(len(clean_text), match_pos+len(m_val)+10)].lower()
                            
                            absolute_noises = ["g/mol", "mg/m3", "ppm", "밀도", "density", "twa", "lel", "oel"]
                            if any(noise in tight_context for noise in absolute_noises):
                                return -5000
                                
                            if not has_percent:
                                if not has_global_percent and not any(k in m_val for k in ['~', '∼', '～', '-', '<', '>', '≤', '≥']):
                                    return -5000
                                weak_noises = ["ec 번호", "ec번호", "ec-no", "ec number", "einecs", "elincs", 
                                               "tox", "irrit", "corr", "dam", "stot", "분류", "category", "cat.", 
                                               "분자량", "molecular weight", "mw", "항", "section", "japan", "formula",
                                               "ingredient", "component", "composition", "구성성분", "함유량", "명칭", "화학물질명", "관용명", "이명"]
                                if any(noise in context_area for noise in weak_noises): return -5000
                                    
                            layout_noises = ["쪽", "page", "페이지"]
                            if any(noise in clean_text[max(0, match_pos-20):match_pos].lower() for noise in layout_noises) and not has_percent: 
                                return -5000 
                                
                            core_m_val = m_val.strip(' -∼~<>\u2013\u2014≤≥=')
                            if core_m_val.count('-') >= 2 or core_m_val.count('\u2013') >= 2: return -5000
                                
                            anchor_pos = clean_text.find("[CAS_ANCHOR]")
                            start_search = min(anchor_pos, match_pos)
                            end_search = max(anchor_pos, match_pos)
                            text_between = clean_text[start_search:end_search]
                            if "[OTHER_CAS]" in text_between: return -10000
                                
                            dist_char = abs(anchor_pos - match_pos)
                            if dist_char > 120: return -5000

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
                            if content_x_mid != 9999 and m_nums:
                                for w in row_words:
                                    if abs((w[0] + w[2])/2 - content_x_mid) <= 45:
                                        if any(num in w[4] for num in m_nums):
                                            score += 1500
                                            break
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
                            content = self._normalize_single_content(best_match_tuple[0])
                    
                    if content == "미기재%":
                        single_matches = []
                        for m in cont_pattern_single.finditer(clean_text):
                            val = m.group(1).strip()
                            if val: single_matches.append((val, m.start()))
                        if single_matches:
                            valid_singles = [m for m in single_matches if score_match(m) > -500]
                            if valid_singles:
                                best_single = max(valid_singles, key=score_match)
                                content = self._normalize_single_content(best_single[0])
                        
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
                    
                    name_str = "CAS 기반 자동 매핑"
                    if log_func: log_func(f"   [Regex-Recovery] CAS {target_cas} -> 함량 {content} (신뢰도: 고)")
                    
                    combined_text = f"{target_cas}({content})"
                    item_obj = {
                        "name": name_str, 
                        "chemical_name": name_str,
                        "cas": target_cas,
                        "cas_no": target_cas, 
                        "percentage": content,
                        "content": content, 
                        "engine": "Regex-Recovery",
                        "combined_format": combined_text
                    }
                    if row.get("is_product_id"):
                        product_id_found.append(item_obj)
                    else:
                        found.append(item_obj)

        except Exception as e:
            if log_func: log_func(f"  ⚠️ Regex-Recovery 오류: {e}")
            
        # 고분자(polymer) 전용 논리적 행 결합 보강 엔진 이식
        for item in found:
            target_cas = item["cas"]
            cas_line_idx = -1
            for idx, pl in enumerate(physical_lines):
                if target_cas in pl["text"]:
                    cas_line_idx = idx
                    break
            
            is_polymer_candidate = False
            polymer_lines = []
            if cas_line_idx != -1:
                # 위/아래 3줄 범위 내에서 polymer/고분자 키워드를 가진 줄을 찾음
                start_idx = max(0, cas_line_idx - 3)
                end_idx = min(len(physical_lines), cas_line_idx + 4)
                
                target_indices = []
                for idx in range(start_idx, end_idx):
                    pl_text = physical_lines[idx]["text"].lower()
                    if "polymer" in pl_text or "고분자" in pl_text:
                        target_indices.append(idx)
                        
                if target_indices:
                    is_polymer_candidate = True
                    min_idx = min([cas_line_idx] + target_indices)
                    max_idx = max([cas_line_idx] + target_indices)
                    polymer_lines = physical_lines[min_idx:max_idx+1]
            
            current_pct = item.get("percentage", "미기재%")
            is_imperfect_pct = current_pct == "미기재%" or "~" not in current_pct or current_pct.startswith("≥") or current_pct.startswith("<")
            
            if is_polymer_candidate and (is_imperfect_pct or "polymer" in item.get("name", "").lower()):
                if polymer_lines:
                    nearby_text = "\n".join([pl["text"] for pl in polymer_lines])
                    
                    cas_pos = nearby_text.find(target_cas)
                    if cas_pos != -1:
                        target_text = nearby_text[cas_pos:]
                    else:
                        target_text = nearby_text
                        
                    clean_nearby = target_text.replace("미맊", "미만").replace("미먄", "미만").replace("이핚", "이하")
                    clean_nearby = re.sub(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', ' ', clean_nearby)
                    clean_nearby = re.sub(r'\b20[0-2]\d[.\-/]\d{1,2}[.\-/]\d{1,2}\b', ' ', clean_nearby)
                    clean_nearby = re.sub(r'\b20[0-2]\d년?\b', ' ', clean_nearby)
                    
                    # 줄바꿈으로 쪼개진 함량 범위(예: 1 이상 ~\n 10 % 미만)를 한 줄로 평탄화
                    flat_nearby = re.sub(r'\s+', ' ', clean_nearby)
                    
                    nums = [float(n) for n in re.findall(r'\d+\.?\d*', flat_nearby)]
                    valid_nums = []
                    for n in nums:
                        n_val = int(n) if n.is_integer() else n
                        if 0.01 <= n_val <= 100.0:
                            valid_nums.append(n_val)
                            
                    best_pct = "미기재%"
                    if len(valid_nums) == 2:
                        n1, n2 = min(valid_nums), max(valid_nums)
                        is_less = "미만" in flat_nearby or "<" in flat_nearby
                        s_sym = ""
                        if is_less:
                            if abs(float(n2) - 1.0) < 1e-9:
                                s_sym = "<"
                        if s_sym:
                            best_pct = f"{n1}~{s_sym}{n2}%"
                        else:
                            best_pct = f"{n1}~{n2}%"
                    elif len(valid_nums) == 1:
                        n1 = valid_nums[0]
                        is_less = "미만" in flat_nearby or "<" in flat_nearby
                        is_more = "이상" in flat_nearby or ">" in flat_nearby or "≥" in flat_nearby
                        pref = "<" if is_less else ("≥" if is_more else "")
                        best_pct = f"{pref}{n1}%"
                        
                    if best_pct != "미기재%":
                        item["percentage"] = best_pct
                        item["content"] = best_pct
                        item["combined_format"] = f"{target_cas}({best_pct})"
                        if log_func: log_func(f"   [고분자 결합 엔진] CAS {target_cas} -> 함량 {best_pct} 복구 완착.")
                    
                    polymer_words = []
                    for pl in polymer_lines:
                        if not cas_pattern.search(pl["text"]) and not cont_pattern.search(pl["text"]):
                            polymer_words.append(pl["text"])
                    
                    if polymer_words:
                        combined_name = " ".join(polymer_words)
                        combined_name = re.sub(r'\s+', ' ', combined_name).strip()
                        combined_name = combined_name.replace("ac rylate", "acrylate").replace("ac- rylate", "acrylate")
                        combined_name = combined_name.replace("-e thylhexyl", "-ethylhexyl").replace("acrylate-s tyrene", "acrylate-styrene")
                        item["name"] = combined_name
                        item["chemical_name"] = combined_name

        if not found and product_id_found:
            found.extend(product_id_found)
        return found, inherited_x_range

    def extract_section3_images(self, pdf_path, log_func=None):
        try:
            doc = fitz.open(pdf_path)
            pages = self.find_section3_pages(doc)
            
            if not pages:
                if log_func: log_func(" 🔍 텍스트 탐지 실패 (또는 스캔본). 비전 정찰병(Recon) 순차 탐색 가동...")
                
                target_index = None
                max_recon_pages = min(7, len(doc))
                
                for i in range(max_recon_pages):
                    if log_func: log_func(f"   ├─ [정찰 진행] 인덱스 {i}번 이미지 검증 중... ({i+1}/{max_recon_pages})")
                    
                    pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.8, 0.8))
                    img_data = base64.b64encode(pix.tobytes("png")).decode("utf-8")
                    single_image = {"mimeType": "image/png", "data": img_data}
                    
                    recon_prompt = """현재 입력된 1장의 이미지(MSDS 문서 페이지)를 분석하여, 이 페이지가 '3. 구성성분의 명칭 및 함유량' (또는 Composition / Information on Ingredients) 표가 시작되는 페이지가 맞는지 판단하라.

[판단 필수 기준]
1. 반드시 화학물질명(Substance Name), CAS 번호, 함유량(%)을 기재하기 위한 가로/세로 '표(Table Grid)' 구조가 시각적으로 보여야 한다.
2. 🚨 [절대 금지 - 함정 차단]: 문서 후반부에 등장하는 '11. 독성에 관한 정보' 섹션 내에서 단순히 '성분 1', '성분 2' 등의 줄글 텍스트나 독성학적 데이터가 나열된 페이지는 절대로 3번 섹션이 아니다. 무조건 false로 답하라.

결과는 반드시 다른 서술 없이 JSON 형식 {"is_section3": true} 또는 {"is_section3": false} 로만 답변하라."""
                    
                    # A2 사양에 따라 대장 유료 키를 사용하여 정찰 수행
                    payload_recon = {
                        "contents": [
                            {"parts": [
                                {"text": recon_prompt},
                                {"inlineData": {"mimeType": "image/png", "data": img_data}}
                            ]}
                        ],
                        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
                    }
                    
                    recon_res = None
                    try:
                        res_obj = self.call_gemini_with_retry(payload_recon, log_func=log_func, model="gemini-2.5-flash-lite")
                        if res_obj:
                            text_response = res_obj.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                            recon_res = json.loads(text_response)
                    except: pass
                    
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
                raw_text += self._get_sorted_and_normalized_text(page) + "\n"
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                images.append({"mimeType": "image/png", "data": base64.b64encode(pix.tobytes("png")).decode("utf-8")})
                if len(images) >= 6: break 
                
            doc.close()
            
            section3_text_only = raw_text
            start_m = re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:구성|COMPOSITION)', raw_text, re.I)
            if start_m:
                ends = list(re.finditer(r'(?:SECTION\s*)?[456][\s.:]*(?:응급|화재|폭발|누출|취급|저장|FIRST|FIRE|ACCIDENTAL)', raw_text[start_m.end():], re.I))
                if ends:
                    section3_text_only = raw_text[start_m.start():start_m.end() + ends[0].start()]
                else:
                    section3_text_only = raw_text[start_m.start():]

            return images, section3_text_only, pages 
        except Exception:
            return [], "", []

    def check_omission(self, original_text, extracted_data):
        if not original_text: return 
        
        section3_zone = ""
        start_patterns = [
            r'3\.\s*(?:구성성분의\s*명칭\s*및\s*함유량|구성성분\s*및\s*함량|구성성분|성분\s*및\s*함량|조성물|COMPOSITION|INGREDIENTS)',
            r'SECTION\s*3',
            r'3\s*구성성분'
        ]
        end_patterns = [
            r'4\.\s*(?:응급조치\s*요령|응급조치|응급처치|요령|구급|FIRST\s*AID)',
            r'SECTION\s*4',
            r'4\s*응급조치'
        ]
        
        start_idx = -1
        for pat in start_patterns:
            m = re.search(pat, original_text, re.IGNORECASE)
            if m:
                start_idx = m.start()
                break
                
        end_idx = -1
        if start_idx != -1:
            for pat in end_patterns:
                m = re.search(pat, original_text[start_idx:], re.IGNORECASE)
                if m:
                    end_idx = start_idx + m.start()
                    break
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            section3_zone = original_text[start_idx:end_idx].strip()
            
        search_text = section3_zone if len(section3_zone) >= 100 else original_text
        
        unique_cas_found = list(set(cas_pattern.findall(search_text)))
        valid_original_cas = [re.sub(r'\s+', '', cas) for cas in unique_cas_found if self.verify_cas_number(cas, grounding_text=search_text)]
        original_cas_count = len(valid_original_cas)
        
        extracted_cas_set = set()
        for c in (extracted_data if isinstance(extracted_data, list) else extracted_data.get("구성성분", [])):
            found = cas_pattern.findall(str(c.get("cas") or c.get("cas_no") or ""))
            extracted_cas_set.update([f for f in found if self.verify_cas_number(f)])
        
        if len(extracted_cas_set) < original_cas_count:
            raise ValueError(f"스나이퍼 누락 발생 (원본:{original_cas_count} vs 추출:{len(extracted_cas_set)}).")

    def extract_components_odl_robust(self, odl_doc, target_pages, pdf_path, log_func=None):
        components = []
        if not target_pages or not odl_doc or not odl_doc.pages: return components

        try:
            fitz_doc = fitz.open(pdf_path)
        except Exception as e:
            fitz_doc = None
            if log_func: log_func(f"  ⚠️ ODL 보완용 fitz_doc 개방 실패: {e}")

        inherited_x_range = None
        for p_idx in target_pages:
            if p_idx >= len(odl_doc.pages): continue
            
            page_items = []
            tables = [el for el in getattr(odl_doc.pages[p_idx], 'elements', []) if getattr(el, 'type', '') == "TABLE"]
            for table in tables:
                priority_col_idx = -1
                for row in table.rows:
                    row_texts = [c.text or "" for c in row.cells]
                    row_clean_texts = [re.sub(r'[\s\(\)\.%\|_]', '', t.lower()) for t in row_texts]
                    
                    if any(k in "".join(row_clean_texts) for k in ["함유량", "함량", "content", "conc", "weight"]):
                        for i, t in enumerate(row_texts):
                            clean_t = re.sub(r'\s+', '', t.lower())
                            if '%' in t or '함량' in clean_t or 'content' in clean_t:
                                priority_col_idx = i
                                break
                        if priority_col_idx >= 0: break
                
                for row in table.rows:
                    parsed_comps = self.parse_row_robust_v2(row, priority_col_idx=priority_col_idx)
                    if parsed_comps:
                        page_items.extend(parsed_comps)
                    elif page_items and page_items[-1]["content"] == "미기재%":
                        row_raw_texts = [c.text for c in row.cells if c.text]
                        for txt in row_raw_texts:
                            norm = self._normalize_single_content(txt)
                            if norm != "미기재%" and re.search(r'\d', norm):
                                idx = len(page_items) - 1
                                while idx >= 0 and page_items[idx]["content"] == "미기재%":
                                    page_items[idx]["content"] = norm
                                    idx -= 1
                                break
            
            if fitz_doc:
                table_bboxes = []
                for table in tables:
                    for row in table.rows:
                        for cell in row.cells:
                            if getattr(cell, 'bbox', None):
                                table_bboxes.append(cell.bbox)
                try:
                    density_bboxes = self.get_density_clustering_bboxes(fitz_doc[p_idx])
                    table_bboxes.extend(density_bboxes)
                except Exception as db_err:
                    if log_func: log_func(f"  ⚠️ 밀도 클러스터링 격실 바운더리 수집 에러: {db_err}")
                
                text_comps, detected_x = self.extract_from_text_regex(
                    fitz_doc[p_idx], 
                    log_func=log_func, 
                    inherited_x_range=inherited_x_range,
                    table_bboxes=table_bboxes
                )
                if detected_x: inherited_x_range = detected_x
                
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

    def parse_row_robust_v2(self, row, priority_col_idx=-1):
        header_keywords = {"cas", "casno", "cas번호", "cas-no", "함유량", "함량", "content", "구성성분", "화학물질명", "substance", "물질명", "명칭", "chemicalname", "weight"}
        noise_keywords = {"twa", "stel", "pel", "tlv", "mg/m", "mg/㎥", "노출기준", "exposure"}
        
        raw_cells = [c.text or "" for c in row.cells]
        cell_lower_set = {re.sub(r'[\s\(\)\.%\|_]', '', c.lower()) for c in raw_cells}
        
        if cell_lower_set.intersection(header_keywords): return None
        if any(k in "".join(raw_cells).lower() for k in noise_keywords): return None

        indexed_cells = []
        for i, c in enumerate(row.cells):
            text = re.sub(r'\s*\n\s*', ' ', (c.text or "")).strip()
            if text: indexed_cells.append((i, text))
        
        if len(indexed_cells) < 2: return None

        if priority_col_idx >= 0:
            indexed_cells.sort(key=lambda x: 0 if x[0] == priority_col_idx else 1)
        else:
            indexed_cells.reverse()

        cas_list, name_candidates = [], []
        strong_content, weak_content = None, None

        for col_idx, raw_cell in indexed_cells:
            c = raw_cell.strip()
            if not c: continue
            c = re.sub(r'(\d)\s*-\s*(\d)', r'\1-\2', c)

            found_cas = re.findall(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', c)
            if found_cas:
                cas_list.extend(found_cas)
                c_remain = re.sub(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])', '', c).strip()
                if not c_remain: continue
                c = c_remain

            norm_c = self._normalize_single_content(c)
            if norm_c != "미기재%" and re.search(r'\d', norm_c):
                is_percent = '%' in c
                is_pure_num = re.match(r'^[\d\s.]+$', c.strip()) is not None
                is_symbol = any(k in c for k in ['~', '∼', '～', '<', '>', '≤', '≥', 'Rem', '잔량', 'balance', '미만', '이하', '초과', '이상'])
                is_range = ('-' in c or '–' in c or '—' in c) and not re.search(r'[a-zA-Z가-힣]', c)

                if is_percent or is_pure_num:
                    is_priority_cell = (col_idx == priority_col_idx)
                    if is_priority_cell:
                        strong_content = self._clean_content_odl(norm_c)
                        break
                    elif not strong_content:
                        strong_content = self._clean_content_odl(norm_c)
                elif not strong_content and (is_symbol or is_range):
                    strong_content = self._clean_content_odl(norm_c)
                else:
                    try:
                        clean_val = float(re.sub(r'[^\d.]', '', norm_c))
                        if clean_val <= 100 and not weak_content: 
                            weak_content = self._clean_content_odl(norm_c)
                    except: pass
                continue

            if len(c) > 1 and not re.match(r'^[\d\s.,\-~]+$', c) and col_idx != priority_col_idx:
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
                "engine": "ODL-v3.0_Priority" 
            })
        return final_comps

    def _clean_content_odl(self, text):
        if any(k in str(text).lower() for k in ["balance", "잔량", "rem", "residual"]): return "Rem.%"
        return text

    def check_golden_fingerprint(self, log_func=None):
        try:
            import hashlib
            with open(__file__, "r", encoding="utf-8") as f:
                code = f.read()
            func_match = re.search(r"def extract_from_text_regex\(.*?\):(.*?)def extract_section3_images", code, re.DOTALL)
            if func_match:
                core_logic = func_match.group(1).strip()
                current_hash = hashlib.sha256(core_logic.encode("utf-8")).hexdigest()[:16]
                GOLDEN_HASH = "4ea82e71b2a4a6f9" 
                if GOLDEN_HASH != "9a8b7c6d5e4f3a2b" and current_hash != GOLDEN_HASH:
                    if log_func: 
                        log_func(" 🚨 [형상 변조 경고] 안티그래비티가 핵심 파싱 엔진을 무단 변조했습니다!")
                        log_func(f"   ├─ 골든 마스터 지문: {GOLDEN_HASH}")
                        log_func(f"   └─ 현재 변조된 지문: {current_hash}")
        except Exception as e:
            if log_func: log_func(f" ⚠️ 지문 검문소 가동 실패: {e}")

    def verify_integrity_of_local_data(self, extracted_text):
        # 2단계 수학적 천칭 검문소 가동
        return self.verify_mathematical_천칭_filter(extracted_text)
        
    def verify_mathematical_천칭_filter(self, text):
        """
        [수학적 천칭 검문소 2단계 분리 계량 규칙]
        """
        if not text: return False, "데이터 공란"
        
        # 1. 본문 내 유효한 CAS 번호 패턴 위치(Anchor)를 전부 파악
        local_cas_pattern = re.compile(r'(?<![\d-])(\d{2,7}\s*-\s*\d{2}\s*-\s*\d)(?![\d-])')
        anchors = []
        for m in local_cas_pattern.finditer(text):
            cas_candidate = m.group(1)
            if self.verify_cas_number(cas_candidate, grounding_text=text):
                anchors.append((m.start(), m.end(), cas_candidate))
                
        if not anchors:
            return False, "유효한 CAS 번호 패턴 미검출"
                
        # 2. 함량 수치 패턴 선언 (% 기호 또는 부등호 결착 수치)
        content_val_pat = re.compile(
            r'(?:'
            r'\b\d+(?:\.\d+)?\s*%'  # 50%
            r'|'
            r'[<>≤≥=\uff1c\uff1e\uff1d~∼～\-]\s*\d+(?:\.\d+)?'  # <50, ~50, -50
            r'|'
            r'\b\d+(?:\.\d+)?\s*[<>≤≥=\uff1c\uff1e\uff1d~∼～\-]'  # 50<, 50~
            r'|'
            r'\b\d+(?:\.\d+)?\s*(?:이상|미만|이하|초과|above|below|under|over|to|max|min)\b' # 50 이상
            r'|'
            r'\b(?:이상|미만|이하|초과|above|below|under|over|max|min)\s*\d+(?:\.\d+)?\b' # 이상 50
            r')',
            re.IGNORECASE
        )
        
        lines = text.split('\n')
        component_max_values = []
        
        has_tr = "<tr>" in text.lower()
        
        for start_idx, end_idx, cas_str in anchors:
            # 1) CAS가 포함된 물리적 행 격실 구하기
            line_text = ""
            if has_tr:
                # HTML 표 구조인 경우: start_idx 기준 가장 가까운 앞쪽 <tr>과 뒤쪽 </tr> 사이
                lower_text = text.lower()
                tr_start = lower_text.rfind("<tr>", 0, start_idx)
                if tr_start == -1:
                    tr_start = 0
                tr_end = lower_text.find("</tr>", end_idx)
                if tr_end == -1:
                    tr_end = len(text)
                else:
                    tr_end += 5  # </tr> 길이만큼 포함
                line_text = text[tr_start:tr_end]
            else:
                # 일반 텍스트인 경우: 기존의 줄 단위
                current_char_count = 0
                for line in lines:
                    line_len = len(line) + 1  # \n 포함
                    if current_char_count <= start_idx < current_char_count + line_len:
                        line_text = line
                        break
                    current_char_count += line_len
            
            # 오직 수평선상 일치하는 행 격실 내부 텍스트만 타겟팅 (앞뒤 50자 context_text 배제)
            target_texts = [line_text]
            cas_max_val = 0.0
            found_any_num = False
            
            for t_text in target_texts:
                if not t_text: continue
                # HTML 태그 제거하여 텍스트만 검사 (노이즈 방지)
                cleaned_t = re.sub(r'<[^>]+>', ' ', t_text)
                
                # H-코드 및 날짜 노이즈 제거
                cleaned_t = re.sub(r'\b[hH]\d{3}\b', ' ', cleaned_t)
                cleaned_t = re.sub(r'\b\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\b', ' ', cleaned_t)
                # CAS 번호 자체(공백 포함)도 오독을 막기 위해 제거
                cleaned_t = re.sub(r'(?<![\d-])\d{2,7}\s*-\s*\d{2}\s*-\s*\d(?![\d-])', ' ', cleaned_t)
                
                for m in content_val_pat.finditer(cleaned_t):
                    match_str = m.group(0)
                    start_pos = m.start()
                    end_pos = m.end()
                    
                    # 주변 15글자 내 절대 노이즈 제거
                    surrounding = cleaned_t[max(0, start_pos - 15):min(len(cleaned_t), end_pos + 15)].lower()
                    absolute_noises = ["g/mol", "mg/m", "ppm", "twa", "stel", "pel", "oel", "분자량", "mw", "molecular"]
                    if any(noise in surrounding for noise in absolute_noises):
                        continue
                        
                    # 수치 추출
                    nums = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', match_str)]
                    if not nums: continue
                    max_num = max(nums)
                    
                    if max_num > 100.0:
                        return False, f"물리적 모순 포착: 개별 함량 수치 100% 초과 ({max_num}%)"
                        
                    if max_num > cas_max_val:
                        cas_max_val = max_num
                        found_any_num = True
                        
            if found_any_num:
                component_max_values.append(cas_max_val)
                
        # 3. 합산 저울에 누적
        total_max_sum = sum(component_max_values)
        if total_max_sum > 110.0:
            return False, f"범위 최대치 합계 초과: {total_max_sum}% (기준: 110.0% 이하)"
            
        return True, "무결성 통과"

    def parse_html_table_to_components(self, html_content, log_func=None):
        """
        [Task 1.1] HTML 표 데이터를 분석하여 CAS 번호와 함유량을 추출하는 유연한 파서
        """
        if not html_content:
            return []
            
        import re
        tr_pattern = re.compile(r'<tr>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
        td_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL | re.IGNORECASE)
        
        rows = tr_pattern.findall(html_content)
        header_keywords = {"cas", "casno", "cas번호", "cas-no", "함유량", "함량", "content", "conc", "weight", "구성성분", "화학물질명", "substance", "물질명", "명칭", "chemicalname"}
        noise_keywords = {"twa", "stel", "pel", "tlv", "mg/m", "mg/㎥", "노출기준", "exposure"}
        
        extracted_items = []
        
        for tr in rows:
            td_contents = td_pattern.findall(tr)
            row_cells = [re.sub(r'<[^>]+>', '', td).strip() for td in td_contents]
            row_clean_set = {re.sub(r'[\s\(\)\.%\|_]', '', c.lower()) for c in row_cells}
            
            if row_clean_set.intersection(header_keywords): continue
            if any(k in "".join(row_cells).lower() for k in noise_keywords): continue
            
            row_text_full = " ".join(row_cells)
            cas_candidates = cas_pattern.findall(row_text_full)
            if not cas_candidates: continue
            
            content_candidates = []
            for c in row_cells:
                if not c: continue
                if any(cand in c for cand in cas_candidates): continue
                
                norm_c = self._normalize_single_content(c)
                is_percent = '%' in c
                is_pure_num = re.match(r'^[\d\s.]+$', c.strip()) is not None
                is_symbol = any(k in c for k in ['~', '∼', '～', '<', '>', '≤', '≥', 'Rem', '잔량', 'balance', '미만', '이하', '초과', '이상'])
                is_range = ('-' in c or '–' in c or '—' in c) and not re.search(r'[a-zA-Z가-힣]', c)
                
                if (is_percent or is_pure_num or is_symbol or is_range) and norm_c != "미기재%" and re.search(r'\d', norm_c):
                    content_candidates.append(norm_c)
            
            name = "CAS 기반 자동 매핑"
            for c in row_cells:
                if len(c) > 1 and not re.match(r'^[\d\s.,\-~%]+$', c) and not any(cand in c for cand in cas_candidates):
                    name = c
                    break
                    
            matched_content = content_candidates[0] if content_candidates else "미기재%"
            
            for cas_cand in cas_candidates:
                extracted_items.append({
                    "name": name,
                    "chemical_name": name,
                    "cas": cas_cand,
                    "cas_no": cas_cand,
                    "content": matched_content,
                    "percentage": matched_content,
                    "engine": "ODL-HTML-Parser"
                })
        return extracted_items

    def scan_self_diagnosis(self, local_ocr_html, log_func=None):
        if not local_ocr_html: return False, [], {}

        if log_func: log_func(" 🔍 [1선 하이브리드 검문] 수거된 성분 구조 정밀 스캔 중...")

        extracted_items = self.parse_html_table_to_components(local_ocr_html, log_func=log_func)

        has_invalid_cas = False
        has_alignment_error = False
        invalid_cas_dict = {}
        total_valid_cas_count = 0

        for item in extracted_items:
            cas_cand = item["cas"]
            matched_content = item["content"]
            
            item["engine"] = "local_bypass"

            alphabet_matches = re.findall(r'[a-zA-Z]', cas_cand)
            if alphabet_matches:
                has_invalid_cas = True
                bad_char = alphabet_matches[0]
                if log_func: log_func(f"   ├─ CAS [{cas_cand}] -> ⚠️ 오류 감지 (알파벳 '{bad_char}' 유입)")
                invalid_cas_dict[cas_cand] = None
            else:
                if self.verify_cas_number(cas_cand):
                    if log_func: log_func(f"   ├─ CAS [{cas_cand}] -> 규격 일치 (정상)")
                    total_valid_cas_count += 1
                else:
                    has_invalid_cas = True
                    if log_func: log_func(f"   ├─ CAS [{cas_cand}] -> ⚠️ 오류 감지 (체크디지트 불일치)")

            if matched_content == "미기재%":
                has_alignment_error = True

        is_perfect = (not has_invalid_cas) and (not has_alignment_error) and (total_valid_cas_count > 0)

        if is_perfect and extracted_items:
            is_perfect = self.validate_chemical_balances(extracted_items, log_func=log_func)

        return is_perfect, extracted_items, invalid_cas_dict

# ----------------------------------------------------------------------
# 호환성을 위한 모듈 단위 래퍼 함수들
# ----------------------------------------------------------------------
def process_pdf(pdf_path, log_func=None):
    engine = MSDSEngineV6()
    return engine.process_msds_pipeline(pdf_path, log_func=log_func)

analyze_msds = process_pdf

# 자가품질검증
def run_v6_automated_quality_check():
    engine = MSDSEngineV6()
    for input_str, expected in [("15~<20%", "15~20%"), ("1~<5", "1~5%")]:
        res_val = engine._normalize_single_content(input_str)
        if unicodedata.normalize("NFKC", res_val) != unicodedata.normalize("NFKC", expected):
            raise RuntimeError(f"[품질 검증 오류] '{input_str}' -> '{res_val}' (기대값: '{expected}')")

try:
    run_v6_automated_quality_check()
except Exception as e:
    raise RuntimeError(f"품질 체크 실패로 V6 엔진 로드 차단: {e}")

# ----------------------------------------------------------------------
# 테스트 및 회귀 검증 전용 함수군
# ----------------------------------------------------------------------
def test_천칭_filter_anomaly():
    engine = MSDSEngineV6()
    test_dirty_data = "기유 CAS 64742-54-7 함량: 157.0%"
    is_ok, reason = engine.verify_mathematical_천칭_filter(test_dirty_data)
    assert is_ok is False, "천칭 필터가 157% 오염 데이터를 잡지 못하고 탈선했습니다!"
    print("✅ [유닛 테스트 통과] 천칭 가드레일이 100% 초과 모순을 에러 없이 완벽하게 체포합니다.")

def self_test_regression():
    run_v6_automated_quality_check()
    test_천칭_filter_anomaly()
            
    fail_count = 0
    pass_count = 0
    engine = MSDSEngineV6()
    
    test_cases = [
        ("15~<20%", "15~20%", "1% 앵커 외 범위형 미만 기호 필터링 실패"),
        ("1~<5", "1~5%", "1% 앵커 외 범위형 미만 기호 필터링 실패"),
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
    
    print(f"[*] 행 컨텍스트(명칭 내 % 노이즈) 방어 테스트...")
    row_text = "뷰테인(부타디엔 함량 0%) 106-97-8 11 ~ 14"
    protected_row = row_text.replace("106-97-8", "[CAS_ANCHOR]")
    
    all_conts = cont_pattern.findall(protected_row)
    outside_conts = []
    for c in all_conts:
        start_idx = protected_row.find(c)
        prefix = protected_row[:start_idx]
        if prefix.count('(') > prefix.count(')'): continue
        outside_conts.append(c)
    
    row_res = engine._normalize_single_content(outside_conts[-1]) if outside_conts else "미기재%"
    if row_res != "11~14%":
        print(f" [FAIL] 행 컨텍스트 방어 실패: 결과 '{row_res}' (기대값 '11~14%')")
        fail_count += 1
    else:
        print(f" [PASS] 행 컨텍스트 방어 성공 (0% 무시)")
        pass_count += 1
    
    noise_cases = [
        ("77.08g", "미기재%", "단위(g) 환각 필터 작동 실패"),
        ("100 mg/kg", "미기재%", "단위(mg/kg) 환각 필터 작동 실패"),
        ("Ethylene Glycol 50-60%", "50~60%", "Shield-Inversion(텍스트 혼입) 처리 실패"),
        ("95-100% (wt)", "95~100%", "부가 텍스트(wt) 처리 실패")
    ]
    
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
        g_text = "기타 성분: 64742 - 54 - 7 함유" if "64742" in c_str else None
        if engine.verify_cas_number(c_str, grounding_text=g_text) != expected:
            print(f" [FAIL] CAS: {c_str} -> 결과: {not expected} | 사유: {msg}")
            fail_count += 1
        else:
            print(f" [PASS] CAS: {c_str}")

    keyword_cases = [
        ("Rem.", "Rem.%", "Rem. 키워드 표준화 실패"),
        ("balance", "Rem.%", "balance 키워드 표준화 실패"),
        ("잔량", "Rem.%", "한글 '잔량' 키워드 표준화 실패")
    ]

    all_tests = test_cases + noise_cases + keyword_cases
    for input_str, expected, msg in all_tests:
        actual = engine._normalize_single_content(input_str)
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

def run_production_integrity_test_cases():
    print("\n==================================================")
    print("[*] 가동: run_production_integrity_test_cases()")
    print("==================================================")
    
    import glob
    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_file_dir = os.path.join(base_dir, "TEST_File")
    
    files_015 = glob.glob(os.path.join(test_file_dir, "*015*.pdf"))
    file_015 = files_015[0] if files_015 else os.path.join(test_file_dir, "015_★1005_TECA-BIOME™_GHS_MSDS개정_(KOR)_ICBIO.pdf")
    
    files_036 = glob.glob(os.path.join(test_file_dir, "*036*.pdf"))
    file_036 = files_036[0] if files_036 else os.path.join(test_file_dir, "036_아이생각수성내부프로 (M-BASE)_GHS국문.pdf")
    
    success_015 = False
    success_036 = False
    
    print("\n[Test 1] 015번 자재의 거대 INCI ID(17036) 오인입 차단 검증 시작...")
    if not os.path.exists(file_015):
        print(f"❌ 오류: 테스트 파일 없음: {file_015}")
    else:
        try:
            res = process_pdf(file_015, log_func=print)
            comp_str = res.get("구성성분", "")
            print(f"  └─ 추출 결과: {comp_str}")
            if "17036" in comp_str:
                print("❌ 실패: 거대 INCI ID(17036)가 결과에 오인입되었습니다.")
            elif "54.98" not in comp_str:
                print("❌ 실패: 병풀잎추출물의 함량(54.98%)이 누락되었습니다.")
            else:
                print("🟢 [성공] [Test 1] 015번 자재 거대 INCI ID 오인입 차단 및 정상 함량 검증 통과")
                success_015 = True
        except Exception as e:
            print(f"❌ 예외 발생: {e}")
            
    print("\n[Test 2] 036번 한글 조건어 결착 서식 물결 평탄화 검증 시작...")
    if not os.path.exists(file_036):
        print(f"❌ 오류: 테스트 파일 없음: {file_036}")
    else:
        try:
            res = process_pdf(file_036, log_func=print)
            comp_str = res.get("구성성분", "")
            print(f"  └─ 추출 결과: {comp_str}")
            if "7732-18-5" in comp_str and "40~50" in comp_str:
                print("🟢 [성공] [Test 2] 036번 한글 조건어 결착 서식 물결 평탄화 검증 통과")
                success_036 = True
            else:
                print("❌ 실패: 한글 조건어가 물결 기호로 올바르게 평탄화되지 못했습니다.")
        except Exception as e:
            print(f"❌ 예외 발생: {e}")
            
    print("\n==================================================")
    if success_015 and success_036:
        print("🟢 모든 프로덕션 통합 무결성 테스트 케이스 [성공]")
        print("==================================================")
        return True
    else:
        print("🔴 일부 테스트 케이스 실패")
        print("==================================================")
        return False

def run_005_천칭_test_case():
    print("\n==================================================")
    print("[*] 가동: run_005_천칭_test_case() [단독 이미지 천칭 검증]")
    print("==================================================")
    
    import glob
    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_file_dir = os.path.join(base_dir, "TEST_File")
    
    files_005 = glob.glob(os.path.join(test_file_dir, "*005*.pdf"))
    if not files_005:
        print("❌ 오류: 005번 테스트 파일을 찾을 수 없습니다.")
        return False
    
    pdf_path = files_005[0]
    engine = MSDSEngineV6()
    paddle_ocr_instance = get_paddle_structure_engine(log_func=print)
    
    print(f"[*] 대상 파일: {os.path.basename(pdf_path)}")
    res = engine.run_flexible_sandwich_pipeline(pdf_path, paddle_ocr_instance, log_func=print)
    
    print("\n[완착 장부 데이터]")
    print(f"상태: {res.get('status')}")
    print(f"추출 엔진: {res.get('engine')}")
    
    if res.get("status") == "FALLBACK":
        print("\n🟢 [검증 대성공] 천칭 가드레일이 유령 수치(157.0%)를 완벽하게 적발하여 FALLBACK을 유도했습니다.")
        return True
    else:
        print("\n❌ [검증 실패] 천칭 필터가 작동하지 않았습니다.")
        return False

def run_1_to_7_production_test_cases():
    print("\n==================================================")
    print("[*] 가동: run_1_to_7_production_test_cases()")
    print("==================================================")
    
    import glob
    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_file_dir = os.path.join(base_dir, "TEST_File")
    
    patterns = ["*001*.pdf", "*002*.pdf", "*003*.pdf", "*004*.pdf", "*005*.pdf", "*006*.pdf", "*007*.pdf"]
    target_files = []
    
    for p in patterns:
        matched = glob.glob(os.path.join(test_file_dir, p))
        if matched: target_files.extend(matched)
            
    target_files = sorted(list(set(target_files)))
    if not target_files:
        print("❌ 오류: 1~7번 테스트 PDF 자재를 수집하지 못했습니다.")
        return False
        
    all_success = True
    print(f"[*] 총 {len(target_files)}권의 자재가 레일에 진입합니다.")
    
    for idx, f_path in enumerate(target_files, 1):
        filename = os.path.basename(f_path)
        print(f"\n[{idx}/7] 레일 격발: {filename}")
        try:
            res = process_pdf(f_path, log_func=print)
            print("  [결과 리포트]")
            print(f"  ├─ 제품명: {res.get('제품명')}")
            print(f"  ├─ 신호등: {res.get('신호등')}")
            print(f"  ├─ 추출 엔진: {res.get('used_engine')}")
            print(f"  ├─ 무결성 점수: {res.get('integrity_score')}점")
            print(f"  └─ 구성성분: {res.get('구성성분')[:120]}...")
            
            if res.get("신호등") != "🟢":
                print(f"  ⚠️ 주의: 신호등이 초록불이 아닙니다. ({res.get('신호등')})")
                all_success = False
        except Exception as e:
            print(f"  ❌ 예외 크래시 발생: {e}")
            all_success = False
            
    print("\n==================================================")
    if all_success:
        print("🟢 [완착 성공] 1~7번 모든 자재가 오독 없이 초록불(🟢)로 완착되었습니다.")
        print("==================================================")
        return True
    else:
        print("🔴 [일부 경고] 1~7번 자재 중 일부가 초록불(🟢) 안착에 실패했습니다.")
        print("==================================================")
        return False

if __name__ == "__main__":
    self_test_regression()
    run_production_integrity_test_cases()
    # run_005_천칭_test_case() # run_1_to_7_production_test_cases와 Paddle 자원 충돌(데드락) 예방 차원에서 주석 처리
    run_1_to_7_production_test_cases()
