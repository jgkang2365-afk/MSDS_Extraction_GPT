# -*- coding: utf-8 -*-
import sys
import os
import re

# 모듈 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smu_gui import validate_composition_limits

def run_tests():
    print("=== [테스트 시작] GUI 크롭 및 저울 센서 검증 ===")
    
    # 1. 100% 초과 감지 테스트
    bad_text = "기유 64742-54-7 157~265%"
    is_valid, reason = validate_composition_limits(bad_text)
    print(f"오독 수치 검증 결과: {is_valid} | 사유: {reason}")
    assert is_valid == False, "100% 초과 오독 검지 실패"
    assert "초과 포착" in reason, "예외 사유 매칭 실패"
    
    # 2. 정상 수치 테스트
    good_text = "기유 64742-54-7 15~26%"
    is_valid, reason = validate_composition_limits(good_text)
    print(f"정상 수치 검증 결과: {is_valid} | 사유: {reason}")
    assert is_valid == True, "정상 수치 오탐 실패"
    
    # 3. 빈 텍스트 테스트
    is_valid, reason = validate_composition_limits("")
    print(f"공란 검증 결과: {is_valid} | 사유: {reason}")
    assert is_valid == False, "공란 검증 실패"
    
    print("=== [테스트 성공] GUI 저울 센서 검증 통과! ===")

if __name__ == "__main__":
    run_tests()
