import requests
import re
import xml.etree.ElementTree as ET
from threading import Lock
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

SERVICE_KEY = os.getenv("SERVICE_KEY")
BASE_URL = os.getenv("BASE_URL")

class KoshaAPIClient:
    def __init__(self):
        self.session = requests.Session()
        self.lock = Lock()
        self.cache = {}

    def get_chem_id(self, cas_no: str):
        """CAS 번호로 chemId 및 국문 화학물질명 조회 (3회 재시도 적용)"""
        if not cas_no: return None, None
        if cas_no in self.cache: return self.cache[cas_no]

        url = f"{BASE_URL}/chemlist"
        params = {"serviceKey": SERVICE_KEY, "searchWrd": cas_no, "searchCnd": 1}
        
        for attempt in range(3):
            try:
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                root = ET.fromstring(response.content)
                
                if root.findtext("./header/resultCode") != "00":
                    return None, None
                    
                item = root.find("./body/items/item")
                if item is None: return None, None

                result = (item.findtext("chemId"), item.findtext("chemNameKor"))
                self.cache[cas_no] = result
                return result
            except Exception:
                if attempt < 2: time.sleep(2)
                continue
        return None, None

    def get_item_detail(self, chem_id: str, operation: str, target_item_name: str):
        """상세 정보 API 호출하여 특정 항목의 상세 내용 추출 (3회 재시도 적용)"""
        url = f"{BASE_URL}/{operation}"
        params = {"serviceKey": SERVICE_KEY, "chemId": chem_id}
        
        for attempt in range(3):
            try:
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                root = ET.fromstring(response.content)
                
                if root.findtext("./header/resultCode") != "00":
                    return None

                items = root.findall("./body/items/item")
                for item in items:
                    name = item.findtext("msdsItemNameKor")
                    if name and target_item_name in name:
                        return item.findtext("itemDetail")
                return None
            except Exception:
                if attempt < 2: time.sleep(2)
                continue
        return None

    def get_full_substance_info(self, cas_no: str, full=True):
        """1SMU 고도화: 제품명, CAS, 노출기준, 산안법(6종), 화관법(6종) 등 정보 반환
        full=False일 경우 노출기준 및 화관법 조회를 생략하여 성능 최적화 (가로형용)"""
        chem_id, chem_name_kor = self.get_chem_id(cas_no)
        if not chem_id:
            return None

        # 1. 제품명
        product_name = self.get_item_detail(chem_id, "chemdetail01", "제품명")
        if not product_name:
            product_name = chem_name_kor if chem_name_kor else "제품명 확인 불가"

        # 🚨 [V27.7] 한글 제품명인 경우 공백을 완전 제거하여 표준명 일치율 향상 (예: 탄산 칼슘 -> 탄산칼슘)
        if product_name and re.search(r'[가-힣]', product_name):
            product_name = product_name.replace(" ", "")

        # 2. 노출기준 (full=True일 때만 조회)
        exposure = {"twa_ppm": "-", "twa_mg": "-", "stel_ppm": "-", "stel_mg": "-"}
        if full:
            exp_text = self.get_item_detail(chem_id, "chemdetail08", "국내규정")
            exp_text_safe = (exp_text or "")
            twa_ppm = re.search(r"TWA\s*[:：]?\s*(\d+(?:\.\d+)?)\s*ppm", exp_text_safe, re.I)
            twa_mg = re.search(r"TWA\s*[:：]?\s*(\d+(?:\.\d+)?)\s*㎎/㎥", exp_text_safe, re.I)
            stel_ppm = re.search(r"STEL\s*[:：]?\s*(\d+(?:\.\d+)?)\s*ppm", exp_text_safe, re.I)
            stel_mg = re.search(r"STEL\s*[:：]?\s*(\d+(?:\.\d+)?)\s*㎎/㎥", exp_text_safe, re.I)
            exposure = {
                "twa_ppm": twa_ppm.group(1) if twa_ppm else "-",
                "twa_mg": twa_mg.group(1) if twa_mg else "-",
                "stel_ppm": stel_ppm.group(1) if stel_ppm else "-",
                "stel_mg": stel_mg.group(1) if stel_mg else "-"
            }

        # 3. 법적 규제 (chemdetail15에서 산안법/화관법 통합 조회 시도)
        osh_info = {k: False for k in ["is_measured", "is_special", "is_managed", "is_special_mgmt", "is_permit", "is_prohibited"]}
        osh_info["raw_text"] = ""
        cca_info = {k: False for k in ["acute", "chronic", "ecology", "accident", "prohibited", "restricted"]}
        
        # 산안법은 가로형/세로형 공통으로 필요하므로 항상 조회
        osh_text = self.get_item_detail(chem_id, "chemdetail15", "산업안전보건법에 의한 규제")
        if osh_text:
            osh_info = {
                "is_measured": "작업환경측정대상물질" in osh_text,
                "is_special": "특수건강진단대상물질" in osh_text,
                "is_managed": "관리대상유해물질" in osh_text,
                "is_special_mgmt": "특별관리물질" in osh_text,
                "is_permit": "허가대상물질" in osh_text,
                "is_prohibited": "금지물질" in osh_text,
                "raw_text": osh_text
            }

        # 화관법은 full=True일 때만 조회
        if full:
            cca_text = self.get_item_detail(chem_id, "chemdetail15", "화학물질관리법에 의한 규제")
            if cca_text:
                cca_info = {
                    "acute": "유독물질" in cca_text,
                    "chronic": "관찰물질" in cca_text,
                    "ecology": "" in cca_text, 
                    "accident": "사고대비물질" in cca_text,
                    "prohibited": "금지물질" in cca_text,
                    "restricted": "제한물질" in cca_text
                }

        return {
            "chem_id": chem_id,
            "product_name": product_name,
            "cas_no": cas_no,
            "exposure": exposure,
            "osh": osh_info,
            "cca": cca_info
        }

    def get_regulation_info(self, cas_no: str, full=False):
        """기존 호환성 유지용: 가로형(full=False) 또는 세로형(full=True) 정보 반환"""
        info = self.get_full_substance_info(cas_no, full=full)
        if not info:
            return None, cas_no, False, False, False, False
        
        return (
            info["product_name"], 
            info["cas_no"], 
            info["osh"]["is_measured"], 
            info["osh"]["is_special"], 
            info["osh"]["is_special_mgmt"], 
            info["osh"]["is_permit"]
        )

    def fetch_msds_info(self, cas_no: str):
        """사용자 요청에 따른 핵심 로직: 제품명 및 규제 정보 추출"""
        chem_id, chem_name_kor = self.get_chem_id(cas_no)
        if not chem_id:
            return None

        # 15. 법적 규제현황 확인
        # 가. 산업안전보건법에 의한 규제 텍스트 확인을 위해 chemdetail15 호출
        reg_text = self.get_item_detail(chem_id, "chemdetail15", "산업안전보건법에 의한 규제")
        
        if not reg_text:
            return None

        is_work_env = "작업환경측정대상물질" in reg_text
        is_special_health = "특수건강진단대상물질" in reg_text

        # 1. 화학제품과 회사에 관한 정보 (chemdetail01) 에서 제품명 가져오기
        product_name = self.get_item_detail(chem_id, "chemdetail01", "제품명")
        
        if not product_name:
            # 제품명이 없으면 기본 검색된 화학물질명 사용
            product_name = chem_name_kor if chem_name_kor else "제품명 확인 불가"

        # 🚨 [V27.7] 한글 제품명인 경우 공백을 완전 제거하여 표준명 일치율 향상 (예: 탄산 칼슘 -> 탄산칼슘)
        if product_name and re.search(r'[가-힣]', product_name):
            product_name = product_name.replace(" ", "")

        # 결과 판단 로직 및 포맷팅: 제품명(cas번호)
        if is_special_health and not is_work_env:
            return f"[특검]{product_name}({cas_no})"
        elif is_work_env or is_special_health:
            # 둘 다 있거나 작업환경측정만 있는 경우
            return f"{product_name}({cas_no})"
        else:
            # 해당하지 않는 경우 전달하지 않음
            return None

if __name__ == "__main__":
    # 간단한 테스트 코드
    client = KoshaAPIClient()
    test_cas = "64-17-5" # 에탄올
    print(f"CAS {test_cas} 결과: {client.fetch_msds_info(test_cas)}")

