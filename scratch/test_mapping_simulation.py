import re
import json

# 가상의 MES 마스터 데이터 (테스트용)
MES_MASTER_SAMPLES = [
    {"물질명": "6가크롬(수용성)", "CAS번호": "7440-47-3", "노출기준(TWA)": "0.05 ㎎/㎥", "분자량": 51.996},
    {"물질명": "이산화티타늄", "CAS번호": "13463-67-7", "노출기준(TWA)": "10 ㎎/㎥", "분자량": 79.866},
    {"물질명": "결정형 유리규산(석영)", "CAS번호": "14808-60-7", "노출기준(TWA)": "0.05 ㎎/㎥", "분자량": 60.08}
]

def is_measurement_target(content_str):
    """농도 필터링 로직: 1.0% 미만 제외"""
    # 단순화된 파싱 로직
    nums = re.findall(r'(\d+\.?\d*)', content_str)
    if not nums: return True # Rem. 등
    val = float(nums[-1]) # 최댓값 기준
    if "<" in content_str and val <= 1.0: return False
    return val >= 1.0

def convert_twa(value, unit, mw):
    """TWA 단위 환산: ppm -> mg/m3"""
    if unit.lower() == 'ppm':
        return round((value * mw) / 24.45, 3)
    return value

def evaluate_score(target_cas, target_twa_info, mes_entry):
    """매핑 점수 계산기"""
    score = 0
    # 1. CAS 일치 (7440-47-3은 크롬 금속이지만 6가크롬의 대표 CAS로 쓰이는 경우 대응)
    if target_cas == mes_entry["CAS번호"]:
        score += 100
    
    # 2. TWA 일치 (환산 후)
    mes_twa_val = float(re.search(r'[\d.]+', mes_entry["노출기준(TWA)"]).group())
    if abs(target_twa_info['value'] - mes_twa_val) < 0.001:
        score += 50
        
    # 3. 키워드 일치
    keywords = ["크롬", "6가", "수용성", "티타늄", "이산화"]
    for k in keywords:
        if k in mes_entry["물질명"] and k in target_twa_info['category']:
            score += 15
            
    return score

def simulate():
    # 테스트 케이스
    test_cases = [
        {"cas": "7778-50-9", "content": "1.5%", "twa": 0.05, "unit": "mg/m3", "cat": "크롬(6가, 수용성)화합물", "mw": 294.18},
        {"cas": "7778-50-9", "content": "0.5%", "twa": 0.05, "unit": "mg/m3", "cat": "크롬(6가, 수용성)화합물", "mw": 294.18},
        {"cas": "1317-80-2", "content": "10%", "twa": 10, "unit": "mg/m3", "cat": "이산화티타늄", "mw": 79.87},
        {"cas": "Unknown", "content": "5%", "twa": 0.023, "unit": "ppm", "cat": "6가크롬", "mw": 52.0} # ppm 환산 테스트
    ]

    print(f"{'CAS':<15} | {'농도':<6} | {'판정':<6} | {'매핑 결과':<20} | {'점수':<5}")
    print("-" * 70)

    for tc in test_cases:
        # 1. 농도 필터링
        target = is_measurement_target(tc["content"])
        if not target:
            print(f"{tc['cas']:<15} | {tc['content']:<6} | {'제외':<6} | {'-'*20} | -")
            continue

        # 2. 단위 환산
        unified_twa = convert_twa(tc["twa"], tc["unit"], tc["mw"])
        twa_info = {"value": unified_twa, "category": tc["cat"]}

        # 3. 매핑 시도
        best_match = None
        max_score = -1
        
        for entry in MES_MASTER_SAMPLES:
            score = evaluate_score(tc["cas"], twa_info, entry)
            if score > max_score:
                max_score = score
                best_match = entry

        status = "확정" if max_score >= 80 else "확인필요" if max_score >= 40 else "실패"
        result_str = f"{best_match['물질명'] if best_match else '없음'}({status})"
        
        print(f"{tc['cas']:<15} | {tc['content']:<6} | {'대상':<6} | {result_str:<20} | {max_score}")

if __name__ == "__main__":
    simulate()
