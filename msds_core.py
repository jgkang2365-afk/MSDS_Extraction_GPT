import os
import sys
import json
import argparse
from datetime import datetime
import msds_engine_v5
from kosha_client import KoshaAPIClient
from exposure_lookup import ExposureLookup
import re

import hashlib

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

    def extract_from_pdf(self, pdf_path, log_func=None):
        """1단계: PDF에서 제품명 및 성분 추출"""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {pdf_path}")
        return msds_engine_v5.process_pdf(pdf_path, log_func=log_func)

    # [수정] 인자에 f_hash=None 추가
    def validate_with_kosha(self, cas_content, log_func=None, full=False, f_hash=None):
        # [V7.0 캐시 선제 타격] 주님의 교정 데이터가 있다면 API 통신 전면 차단
        manual_data = self._get_cached_manual_data(f_hash)
        if manual_data:
            if log_func: log_func(f"[*] 🛡️ 캐시 방어막 가동: 교정 데이터 발견 (API 통신 스킵)")
            return {"status": "Cache-Hit", "manual_data": manual_data}

        """2단계: CSV 및 KOSHA API를 통한 성분 검증 및 상세 규제 정보 조회"""
        if not cas_content or "미기재" in cas_content or "오류" in cas_content:
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
                "cca": info["cca"]
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
