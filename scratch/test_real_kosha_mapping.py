import sys
import os
import re
import json

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kosha_client import KoshaAPIClient

def parse_twa_and_cat(detail_text):
    """KOSHA 상세 텍스트에서 TWA와 카테고리 추출"""
    if not detail_text: return None, None, None
    
    # TWA 수치 및 단위 추출
    twa_match = re.search(r"TWA\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(mg/m3|㎎/㎥|ppm)", detail_text, re.I)
    val = float(twa_match.group(1)) if twa_match else None
    unit = twa_match.group(2) if twa_match else None
    
    # 카테고리 추출 (TWA 뒤에 오는 명칭)
    cat_match = re.search(r"TWA\s*[:：]?\s*[\d.]+\s*(?:mg/m3|㎎/㎥|ppm)?\s*([가-힣0-9\(\), ]+)", detail_text, re.I)
    cat = cat_match.group(1).strip() if cat_match else ""
    
    return val, unit, cat

def convert_twa(value, unit, mw):
    """단위 환산: ppm -> mg/m3"""
    if not value or not mw: return value
    if unit and unit.lower() == 'ppm':
        try:
            mw_val = float(mw)
            return round((value * mw_val) / 24.45, 3)
        except: return value
    return value

def evaluate_score(target_cas, target_twa_val, target_cat, mes_entry):
    """실제 매핑 점수 계산"""
    score = 0
    # 1. CAS 일치
    mes_cas = str(mes_entry.get("CAS번호", "")).strip()
    if target_cas == mes_cas:
        score += 100
        
    # 2. TWA 일치 (오차범위 5%)
    try:
        mes_twa_raw = str(mes_entry.get("노출기준(TWA)", "")).strip()
        mes_twa_match = re.search(r"[\d.]+", mes_twa_raw)
        if mes_twa_match and target_twa_val:
            mes_twa_val = float(mes_twa_match.group())
            if abs(target_twa_val - mes_twa_val) / (mes_twa_val + 1e-9) < 0.05:
                score += 50
    except: pass
            
    # 3. 키워드 일치
    mes_name = mes_entry.get("물질명", "") or mes_entry.get("상용명", "")
    keywords = ["크롬", "6가", "수용성", "티타늄", "이산화", "규산", "석영"]
    for k in keywords:
        if k in mes_name and k in target_cat:
            score += 15
            
    return score

def main():
    client = KoshaAPIClient()
    master_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'MES_MASTER_LOOKUP.json')
    
    with open(master_path, 'r', encoding='utf-8') as f:
        master_data = json.load(f)["master_list"]

    test_cas_list = ["7778-50-9", "1317-80-2", "13463-67-7", "14808-60-7"]
    
    print(f"{'CAS':<15} | {'KOSHA TWA':<15} | {'매핑 결과':<20} | {'점수':<5}")
    print("-" * 75)

    for cas in test_cas_list:
        # 1. 실전 KOSHA API 호출
        chem_id, chem_name = client.get_chem_id(cas)
        if not chem_id:
            print(f"{cas:<15} | {'API 실패':<15} | {'-':<20} | -")
            continue
            
        detail = client.get_item_detail(chem_id, "chemdetail08", "국내규정")
        twa_val, twa_unit, cat = parse_twa_and_cat(detail)
        
        # 2. MES 마스터 전체 루프 (실전 비교)
        best_match = None
        max_score = -1
        
        for entry in master_data:
            # 유닛 환산을 위한 분자량 (있으면 사용)
            mw = entry.get("분자량", 0)
            unified_twa = convert_twa(twa_val, twa_unit, mw)
            
            score = evaluate_score(cas, unified_twa, cat, entry)
            if score > max_score:
                max_score = score
                best_match = entry
        
        status = "확정" if max_score >= 80 else "확인필요" if max_score >= 40 else "실패"
        res_name = (best_match.get("물질명") or best_match.get("상용명")) if best_match else "없음"
        
        print(f"{cas:<15} | {str(twa_val)+(' '+twa_unit if twa_unit else ''):<15} | {res_name[:18]:<20} | {max_score}")

if __name__ == "__main__":
    main()
