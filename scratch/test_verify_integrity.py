# -*- coding: utf-8 -*-
import sys
import os

# 모듈이 위치한 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v5 import verify_integrity_of_local_data, scan_self_diagnosis

def run_tests():
    print("=== [테스트 시작] 함량 무결성 검증 저울 센서 테스트 ===")
    
    # 케이스 1: 정상 청정 함량
    text_clean = "10~20% 40~50% 1.5% 미만"
    is_valid, reason = verify_integrity_of_local_data(text_clean)
    print(f"Case 1 (정상): {is_valid} | 사유: {reason}")
    assert is_valid == True, "정상 케이스 검증 실패"

    # 케이스 2: 100% 초과 오독 수치 감지
    text_invalid_100 = "10~150% 1~10%"
    is_valid, reason = verify_integrity_of_local_data(text_invalid_100)
    print(f"Case 2 (100% 초과): {is_valid} | 사유: {reason}")
    assert is_valid == False, "100% 초과 오독 감지 실패"
    assert "물리적 모순 포착" in reason, "에러 메시지 일치하지 않음"

    # 케이스 3: 누적 함량 비정상 비대화 감지 (평균 90% 초과 및 3개 성분 이상)
    text_heavy = "95% 91% 92%"
    is_valid, reason = verify_integrity_of_local_data(text_heavy)
    print(f"Case 3 (누적 함량 비대화): {is_valid} | 사유: {reason}")
    assert is_valid == False, "누적 함량 비대화 감지 실패"
    assert "누적 함량 비정상 비대화" in reason, "에러 메시지 일치하지 않음"

    # 케이스 4: 누적 함량은 높지만 성분이 2개인 경우 (통과되어야 함)
    text_heavy_two = "95% 92%"
    is_valid, reason = verify_integrity_of_local_data(text_heavy_two)
    print(f"Case 4 (성분 2개 누적): {is_valid} | 사유: {reason}")
    assert is_valid == True, "성분 2개 케이스 오탐 실패"

    # 케이스 5: html 문자열을 모킹하여 scan_self_diagnosis에 대한 통합 테스트
    # 정상 케이스
    clean_html = """
    <table>
      <tr><td>물질명</td><td>CAS 번호</td><td>함량</td></tr>
      <tr><td>물</td><td>7732-18-5</td><td>40~50%</td></tr>
      <tr><td>에탄올</td><td>64-17-5</td><td>10~20%</td></tr>
    </table>
    """
    is_perfect, items, invalid_dict = scan_self_diagnosis(clean_html)
    print(f"scan_self_diagnosis (정상): {is_perfect} | 아이템 개수: {len(items)}")
    assert is_perfect == True, "scan_self_diagnosis 정상 케이스 통과 실패"

    # 100% 초과 오독 케이스
    bad_html = """
    <table>
      <tr><td>물질명</td><td>CAS 번호</td><td>함량</td></tr>
      <tr><td>물</td><td>7732-18-5</td><td>40~150%</td></tr>
      <tr><td>에탄올</td><td>64-17-5</td><td>10~20%</td></tr>
    </table>
    """
    is_perfect, items, invalid_dict = scan_self_diagnosis(bad_html)
    print(f"scan_self_diagnosis (100% 초과 오독): {is_perfect} | 아이템 개수: {len(items)}")
    assert is_perfect == False, "scan_self_diagnosis 오독 케이스 기각 실패"

    print("=== [테스트 성공] 모든 함량 저울 센서 검증 검사 통과! ===")

if __name__ == "__main__":
    run_tests()
