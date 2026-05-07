import sys
import os

# 스크립트의 상위 디렉토리를 sys.path에 추가 (kosha_client.py 임포트를 위함)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kosha_client import KoshaAPIClient

def main():
    cas_no = "7778-50-9"
    client = KoshaAPIClient()
    
    print(f"[*] CAS No. {cas_no}에 대한 KOSHA API 조회 시작...")
    
    # 1. Chem ID 조회
    chem_id, chem_name = client.get_chem_id(cas_no)
    if not chem_id:
        print(f"[!] CAS No. {cas_no}에 대한 정보를 찾을 수 없습니다.")
        return

    print(f"[*] 화학물질명: {chem_name}")
    print(f"[*] Chem ID: {chem_id}")
    
    # 2. 8번 항목 (노출방지 및 개인보호구)의 상세 정보 조회
    # chemdetail08: 8. 노출방지 및 개인보호구
    # msdsItemNameKor 가 '국내규정'인 항목 찾기
    detail_text = client.get_item_detail(chem_id, "chemdetail08", "국내규정")
    
    if detail_text:
        print("\n[8. 노출방지 및 개인보호구 - 국내규정 상세 내용]")
        print("-" * 50)
        print(detail_text)
        print("-" * 50)
        
        # TWA 값 추출 시도 (다양한 형식 대응)
        import re
        # ppm 형식
        twa_ppm = re.search(r"TWA\s*[:：]?\s*(\d+(?:\.\d+)?)\s*ppm", detail_text, re.I)
        # mg/m3 또는 ㎎/㎥ 형식 (m3, m^3, ㎥ 등 대응)
        twa_mg = re.search(r"TWA\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:mg/m\^?3|㎎/㎥|mg/m3)", detail_text, re.I)
        
        print("\n[추출된 TWA 값]")
        twa_val = []
        if twa_ppm:
            twa_val.append(f"{twa_ppm.group(1)} ppm")
        if twa_mg:
            twa_val.append(f"{twa_mg.group(1)} mg/m³")
            
        if twa_val:
            print(f"국내규정 TWA: {', '.join(twa_val)}")
        else:
            print("국내규정 TWA 값을 텍스트에서 자동으로 찾을 수 없습니다. 위 상세 내용을 확인하세요.")
    else:
        print("[!] '국내규정' 항목의 상세 정보를 가져오지 못했습니다.")

if __name__ == "__main__":
    main()
