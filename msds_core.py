import os
import sys
import json
import argparse
from datetime import datetime
import msds_engine_v6
from kosha_client import KoshaAPIClient
from exposure_lookup import ExposureLookup
import re
import multiprocessing
import queue
import time

import hashlib
import threading

from batch_pipeline import build_partial_timeout_result, timeout_for_document


_OCR_FILE_SEMAPHORE = threading.Semaphore(1)


def _isolated_engine_entry(pdf_path, result_queue, cancel_event):
    """PDF 한 건의 엔진 처리를 별도 프로세스에 격리한다."""
    try:
        result = msds_engine_v6.process_pdf(
            pdf_path,
            log_func=lambda message: result_queue.put(("log", str(message))),
            cancel_check=cancel_event.is_set,
            checkpoint_func=lambda payload: result_queue.put(("checkpoint", payload)),
        )
        result_queue.put(("result", result))
    except InterruptedError:
        result_queue.put(("cancelled", None))
    except BaseException as exc:
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


class MSDSCore:
    """
    MSDS Extraction & Validation Core (1-Source)
    함유량(Min/Max) 분리 파싱 및 규제 데이터 통합 담당.
    """
    def __init__(self):
        self.api_client = KoshaAPIClient()
        self.exposure_lookup = ExposureLookup()
        self.cache_path = "smu_cache.json" # [V7.0 추가]

    # [V7.0 추가] 캐시에서 주님의 교정 데이터(manual_data) 추출
    def _get_cached_manual_data(self, f_hash):
        if not f_hash or not os.path.exists(self.cache_path): return None
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
                return cache.get(f_hash, {}).get("manual_data")
        except: return None

    def calculate_file_hash(self, file_path):
        """파일의 SHA-256 해시 계산"""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"Hash calculation error: {e}")
            return None

    def extract_min_max(self, range_str):
        """함유량 텍스트(10~20, >10, <10)에서 최소값과 최대값 추출"""
        if not range_str or "미기재" in range_str:
            return "100", "100"
        
        # 숫자 및 범위 기호 추출
        range_str = str(range_str).replace(" ", "").replace("%", "")
        
        # 1. '10~20' 또는 '10-20' 형태
        match = re.search(r"(\d+(?:\.\d+)?)\s*[~-]\s*(\d+(?:\.\d+)?)", range_str)
        if match:
            return match.group(1), match.group(2)
        
        # 2. '>10' 또는 '>=10' 형태
        match = re.search(r"[>≥]\s*(\d+(?:\.\d+)?)", range_str)
        if match:
            return match.group(1), "100"
            
        # 3. '<10' 또는 '<=10' 형태
        match = re.search(r"[<≤]\s*(\d+(?:\.\d+)?)", range_str)
        if match:
            return "0", match.group(1)
            
        # 4. 단일 숫자 '10'
        match = re.search(r"(\d+(?:\.\d+)?)", range_str)
        if match:
            return match.group(1), match.group(1)
            
        return "-", "-"

    def _run_engine_isolated(
        self,
        pdf_path,
        log_func=None,
        cancel_check=None,
        timeout_seconds=None,
        document_type=None,
    ):
        """멈춘 PDF 한 건이 GUI와 후속 파일을 붙잡지 못하게 격리 실행한다."""
        if timeout_seconds is None:
            timeout_seconds = timeout_for_document(document_type)

        context = multiprocessing.get_context("spawn")
        result_queue = context.Queue()
        cancel_event = context.Event()
        process = context.Process(
            target=_isolated_engine_entry,
            args=(pdf_path, result_queue, cancel_event),
            daemon=False,
        )
        process.start()
        deadline = time.monotonic() + timeout_seconds
        final_result = None
        final_error = None
        was_cancelled = False
        last_checkpoint = {}

        try:
            while True:
                if cancel_check and cancel_check():
                    was_cancelled = True
                    cancel_event.set()
                elif time.monotonic() >= deadline:
                    final_error = (
                        f"파일별 제한시간 {timeout_seconds:g}초 초과"
                    )
                    cancel_event.set()

                try:
                    message_type, payload = result_queue.get(timeout=0.1)
                    if message_type == "log":
                        if log_func:
                            log_func(payload)
                    elif message_type == "result":
                        final_result = payload
                        break
                    elif message_type == "checkpoint" and isinstance(payload, dict):
                        last_checkpoint = {**last_checkpoint, **payload}
                    elif message_type == "cancelled":
                        if final_error is None:
                            was_cancelled = True
                        break
                    elif message_type == "error":
                        final_error = payload
                        break
                except queue.Empty:
                    pass

                if was_cancelled or final_error:
                    process.join(timeout=3)
                    if process.is_alive():
                        process.terminate()
                    break

                if not process.is_alive():
                    process.join()
                    if final_result is None:
                        final_error = (
                            final_error
                            or f"격리 엔진 비정상 종료(code={process.exitcode})"
                        )
                    break
        finally:
            if process.is_alive():
                process.terminate()
            process.join(timeout=3)
            result_queue.close()
            result_queue.join_thread()

        if was_cancelled:
            raise InterruptedError("사용자 중지 요청")
        if final_error:
            if last_checkpoint.get("product_name") or last_checkpoint.get("구성성분"):
                return build_partial_timeout_result(last_checkpoint, timeout_seconds, final_error)
            raise TimeoutError(final_error)
        return final_result

    def extract_from_pdf(
        self,
        pdf_path,
        log_func=None,
        cancel_check=None,
        timeout_seconds=None,
        document_type=None,
    ):
        """1단계: PDF에서 제품명 및 성분 추출"""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {pdf_path}")
        lock = _OCR_FILE_SEMAPHORE if document_type == "image" else None
        if lock:
            lock.acquire()
        try:
            ext_res = self._run_engine_isolated(
                pdf_path,
                log_func=log_func,
                cancel_check=cancel_check,
                timeout_seconds=timeout_seconds,
                document_type=document_type,
            )
        finally:
            if lock:
                lock.release()
        
        # LLM 엔진으로부터 반환된 데이터를 정류 가공하여 세미콜론 체인으로 가동
        if ext_res and isinstance(ext_res, dict):
            raw_comps = []
            
            # 경로 1: ext_res["함유량"]에 개별 성분 리스트 덩어리가 들어있는 경우
            if "함유량" in ext_res and isinstance(ext_res["함유량"], list):
                for item in ext_res["함유량"]:
                    if isinstance(item, dict):
                        cas = item.get("cas") or item.get("cas_no") or ""
                        content = item.get("content") or item.get("percentage") or ""
                        raw_comps.append({"cas": cas, "content": content})
            # 경로 2: ext_res["구성성분"]에 세미콜론 텍스트 체인이 들어있는 경우 역분석
            elif "구성성분" in ext_res and isinstance(ext_res["구성성분"], str):
                comp_str = ext_res["구성성분"]
                parts = [p.strip() for p in comp_str.split(";") if p.strip()]
                for part in parts:
                    cas_match = re.search(r"(\d{2,7}-\d{2}-\d)", part)
                    if cas_match:
                        cas = cas_match.group(1).strip()
                        content = ""
                        content_match = re.findall(r"\(([^)]+)\)", part)
                        if content_match:
                            content = content_match[-1].strip()
                        raw_comps.append({"cas": cas, "content": content})
                        
            # 가공 및 정제 단계 집행
            from msds_utils_v3 import is_valid_cas
            comp_parts = []
            for item in raw_comps:
                cas_val = item.get("cas")
                content_val = item.get("content")
                
                # CAS 번호가 없고 함유량만 있는 것 또는 CAS 번호가 아예 없는 것 기각 (버림)
                if not cas_val:
                    continue
                    
                # [공정 1] 전역 트림 및 소문자 세탁
                cas_val = str(cas_val).strip().replace("\n", "").replace("\r", "").lower()
                content_val = str(content_val).strip().replace("\n", "").replace("\r", "").lower() if content_val else ""
                
                # [차세대 방법론] 유효 CAS 체크디지트 필터 선행 가동
                if not is_valid_cas(cas_val):
                    continue
                    
                # CAS 번호는 유효한데 함유량이 비어 있는 경우 -> 미기재% 처리
                if not content_val or content_val == "none" or content_val == "null" or content_val == "미기재%":
                    final_content = "미기재%"
                else:
                    # [공정 2] 잔량 토큰의 'Rem.' 단일 규격 치환
                    keywords = ["balance", "remainder", "rest", "residual", "잔량", "나머지"]
                    if any(kw in content_val for kw in keywords):
                        final_content = "Rem."
                    elif content_val == "rem.":
                        final_content = "Rem."
                    else:
                        # [공정 3] 'CAS번호(함유량%);' 수평 체인 결합
                        if not content_val.endswith("%") and not content_val.endswith("rem.") and not content_val.endswith("rem"):
                            content_val = content_val + "%"
                        final_content = content_val.replace("rem.%", "Rem.%")
                        
                comp_parts.append(f"{cas_val}({final_content})")
                
            # [공정 4] 최종 안착 및 토스 계약 집행
            # 세미콜론 뒤 한 칸의 공백(; )을 완벽하게 보존하여 조인
            chain_str = "; ".join(comp_parts) if comp_parts else ""
            ext_res["함유량"] = chain_str
            ext_res["구성성분"] = chain_str
            
        return ext_res

    # [수정] 인자에 f_hash=None 추가
    def validate_with_kosha(self, cas_content, log_func=None, full=False, f_hash=None):
        # [V7.0 캐시 선제 타격] 주님의 교정 데이터가 있다면 API 통신 전면 차단
        manual_data = self._get_cached_manual_data(f_hash)
        if manual_data:
            if log_func: log_func(f"[*] 🛡️ 캐시 방어막 가동: 교정 데이터 발견 (API 통신 스킵)")
            return {"status": "Cache-Hit", "manual_data": manual_data}

        """2단계: CSV 및 KOSHA API를 통한 성분 검증 및 상세 규제 정보 조회"""
        if not cas_content or cas_content.strip() in ["", "미기재%"] or "오류" in cas_content:
            return {"status": "검증 불가", "components": []}

        detailed_components = []
        has_special_overall = False

        # 성분별 파싱 (예: 64-17-5(10~20); 1333-86-4(5))
        items = cas_content.split(";")
        for item in items:
            item = item.strip()
            match = re.search(r"(\d{2,7}-\d{2}-\d)\s*(?:\(([^)]+)\))?", item)
            if not match: continue

            cas = match.group(1)
            range_val = match.group(2) if match.group(2) else ""
            
            # 1. KOSHA API 기본 조회 (full 여부에 따라 상세 정보 포함 여부 결정)
            info = self.api_client.get_full_substance_info(cas, full=full)
            if not info:
                # API에 없는 경우 기본 정보만 생성
                info = {
                    "product_name": "Unknown", "cas_no": cas,
                    "exposure": {"twa_ppm": "-", "twa_mg": "-", "stel_ppm": "-", "stel_mg": "-"},
                    "osh": {k: False for k in ["is_measured", "is_special", "is_managed", "is_special_mgmt", "is_permit", "is_prohibited"]},
                    "cca": {k: False for k in ["acute", "chronic", "ecology", "accident", "prohibited", "restricted"]}
                }

            # 2. 노출기준 CSV 우선 조회 (User Requirement)
            csv_exp = self.exposure_lookup.lookup(cas)
            if csv_exp:
                # CSV에 값이 명시된 필드만 덮어쓰기 (빈 값 '-' 제외)
                for k in ["twa_ppm", "twa_mg", "stel_ppm", "stel_mg"]:
                    if csv_exp.get(k) and csv_exp.get(k) != "-":
                        info["exposure"][k] = csv_exp[k]

            # 3. 데이터 정제 및 플래그 설정
            if info["osh"]["is_special"]: has_special_overall = True
            
            # 4. 함유량 Min/Max 추출
            c_min, c_max = self.extract_min_max(range_val)
            
            # 결과 저장
            comp_detail = {
                "cas": cas,
                "name": info["product_name"],
                "content": range_val,
                "content_min": c_min,
                "content_max": c_max,
                "exposure": info["exposure"],
                "osh": info["osh"],
                "cca": info["cca"],
                # [주님 지시 고정] N열 안전 안착을 위한 고유 금고 열쇠 포워딩 경로 동기화
                "combined_format": info.get("combined_format") or f"{info['product_name']}({range_val})[{cas}]"
            }
            detailed_components.append(comp_detail)

        return {
            "status": "검증 완료 (특검 포함)" if has_special_overall else "검증 완료",
            "components": detailed_components
        }

def main():
    parser = argparse.ArgumentParser(description="MSDS Core CLI (1SMU High-Fidelity)")
    parser.add_argument("--file", help="분야할 PDF 파일 경로")
    parser.add_argument("--json", action="store_true", help="결과를 JSON 형식으로 출력")
    args = parser.parse_args()

    if not args.file:
        parser.print_help(); return

    core = MSDSCore()
    try:
        ext_res = core.extract_from_pdf(args.file)
        val_res = core.validate_with_kosha(ext_res.get("함유량", ""))
        
        output = {
            "filename": os.path.basename(args.file),
            "product_name": ext_res.get("제품명"),
            "reliability": ext_res.get("신뢰도"),
            "validation": val_res
        }

        if args.json:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(f"\n[분석 결과: {output['filename']}]")
            print(f"제품명: {output['product_name']} ({output['reliability']})")
            for c in val_res["components"]:
                print(f"- {c['name']} [{c['cas']}] ({c['content']}%)")
                print(f"  └ 노출기준: TWA({c['exposure']['twa_ppm']}ppm / {c['exposure']['twa_mg']}mg), STEL({c['exposure']['stel_ppm']}ppm)")
                osh_active = [k for k, v in c['osh'].items() if v]
                print(f"  └ 산안법: {', '.join(osh_active) if osh_active else '해당없음'}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
