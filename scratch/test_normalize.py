# -*- coding: utf-8 -*-
import sys
import os
import re

# 부모 디렉토리를 sys.path에 추가하여 msds_engine_v6, msds_utils_v3를 임포트할 수 있도록 함
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import normalize_concentration, MSDSEngineV6, update_regex_pattern
from msds_utils_v3 import clean_text_for_msds

def run_tests():
    print("[*] 단위 테스트 시작...")
    
    # 1. normalize_concentration 테스트
    test_cases_normalize = [
        ("≧ 5.0 % 미만", "≧5.0%미만"),
        ("10%이상", "10%이상"),
        ("120%", "미기재%"), # 110% 초과 필터링
        ("5~10%", "5~10%"),   # 변형 없음 (원본 반환)
        ("5%", "5%"),
        ("≦ 0.5 %", "≦0.5%"),
    ]
    
    success = True
    print("\n--- normalize_concentration 테스트 ---")
    for inp, expected in test_cases_normalize:
        out = normalize_concentration(inp)
        if out == expected:
            print(f"🟢 [성공] '{inp}' ➔ '{out}'")
        else:
            print(f"❌ [실패] '{inp}' ➔ expected: '{expected}', got: '{out}'")
            success = False

    # 2. _normalize_single_content 테스트 (MSDSEngineV6의 내부 메서드 검증)
    print("\n--- MSDSEngineV6._normalize_single_content 테스트 ---")
    engine = MSDSEngineV6()
    test_cases_single_content = [
        ("≧ 5.0 % 미만", "≧5.0%미만"),
        ("10%이상", "10%이상"),
        ("120%", "미기재%"),
        ("5~10%", "5~10%"),
        ("5", "5%"),
        ("≦ 0.5 %", "≦0.5%"),
    ]
    for inp, expected in test_cases_single_content:
        out = engine._normalize_single_content(inp)
        if out == expected:
            print(f"🟢 [성공] '{inp}' ➔ '{out}'")
        else:
            print(f"❌ [실패] '{inp}' ➔ expected: '{expected}', got: '{out}'")
            success = False

    # 3. clean_text_for_msds 테스트
    test_cases_clean_text = [
        ("≧ 5.0 % 미만", "concentration", "≧ 5.0 % "),
        ("≧ 5.0 % 미만", "standard", " 50  미만"), # 유니코드 한글 보존 규칙 반영
        ("10%이상", "concentration", "10%"),
        ("10%이상", "standard", "10이상"),
    ]
    
    print("\n--- clean_text_for_msds 테스트 ---")
    for inp, mode, expected in test_cases_clean_text:
        out = clean_text_for_msds(inp, mode=mode)
        if out == expected:
            print(f"🟢 [성공] '{inp}' (mode={mode}) ➔ '{out}'")
        else:
            print(f"❌ [실패] '{inp}' (mode={mode}) ➔ expected: '{expected}', got: '{out}'")
            success = False

    # 4. update_regex_pattern 테스트
    print("\n--- update_regex_pattern 테스트 ---")
    pat_str = update_regex_pattern()
    expected_pat = r"Concentration\s*[:]\s*([><=≧≦]?\s*\d+\s*%)"
    if pat_str == expected_pat:
        print("🟢 [성공] 정규식 패턴 문자열이 일치합니다.")
    else:
        print(f"❌ [실패] 패턴 불일치. expected: {expected_pat}, got: {pat_str}")
        success = False
        
    # 5. MSDSEngineV6.comp_pattern 강제 결선 테스트
    print("\n--- MSDSEngineV6.comp_pattern 강제 결선 테스트 ---")
    if hasattr(engine, "comp_pattern") and engine.comp_pattern is not None:
        print("🟢 [성공] engine 인스턴스에 'comp_pattern' 속성이 존재합니다.")
        
        test_match_cases = [
            ("Concentration : ≧ 5 %", "≧ 5 %"),
            ("Concentration : 10%", "10%"),
            ("Concentration:≦5%", "≦5%"),
        ]
        for text, expected_match in test_match_cases:
            m = engine.comp_pattern.search(text)
            if m and m.group(1) == expected_match:
                print(f"🟢 [성공] '{text}' ➔ 매칭 성공: '{m.group(1)}'")
            else:
                actual_match = m.group(1) if m else "None"
                print(f"❌ [실패] '{text}' ➔ expected: '{expected_match}', got: '{actual_match}'")
                success = False
    else:
        print("❌ [실패] engine 인스턴스에 'comp_pattern' 속성이 존재하지 않습니다.")
        success = False

    print("\n==================================")
    if success:
        print("🟢 모든 단위 테스트 통과!")
    else:
        print("🔴 일부 단위 테스트 실패!")
    print("==================================")

if __name__ == "__main__":
    run_tests()
