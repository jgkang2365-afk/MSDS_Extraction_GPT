import re
import sys
import os

# msds_engine_v5 로직을 직접 테스트하기 위해 경로 추가 (부모 디렉토리)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import msds_engine_v5 as engine

class MockPage:
    def __init__(self, words):
        self.words = words
    def get_text(self, mode):
        if mode == "words":
            return self.words
        return ""

def run_logic_test():
    print(f"*** [{engine.VERSION}] Logic Integrity Verification Start ***\n")
    
    test_cases = [
        {
            "name": "Scenario A: Standard Forward (CAS -> Content)",
            "words": [
                (10, 100, 50, 115, "1330-20-7"), # CAS
                (100, 100, 150, 115, "10"),     # Content
                (155, 100, 180, 115, "%")
            ],
            "expected_cas": "1330-20-7",
            "expected_cont": "10%"
        },
        {
            "name": "Scenario B: Standard Backward (Content -> CAS)",
            "words": [
                (10, 200, 80, 215, "40~50%"),   # Content
                (100, 200, 180, 215, "7732-18-5") # CAS
            ],
            "expected_cas": "7732-18-5",
            "expected_cont": "40~50%"
        },
        {
            "name": "Scenario C: 2-Line Cell Merge (Multiline Content)",
            "words": [
                (10, 300, 50, 315, "0.1"),      # Content L1
                (55, 300, 80, 315, "above"),
                (10, 320, 50, 335, "1%"),       # Content L2
                (55, 320, 80, 335, "below"),
                (100, 320, 180, 335, "108-01-0") # CAS (on L2)
            ],
            "expected_cas": "108-01-0",
            "expected_cont": "0.1~1%"
        },
        {
            "name": "Scenario D: Header Noise Blocking (NFPA Noise)",
            "words": [
                (10, 10, 100, 25, "NFPA (0~4)"), # Noise (should be blocked)
                (10, 50, 100, 65, "Component Name"), # Header
                (110, 50, 200, 65, "CAS NO"),   # Header
                (10, 100, 50, 115, "10%"),      # Data
                (110, 100, 200, 115, "1317-65-3") # CAS
            ],
            "expected_cas": "1317-65-3",
            "expected_cont": "10%"
        },
        {
            "name": "Scenario E: Date Misdetection Guard (Date Guard)",
            "words": [
                (10, 400, 100, 415, "2024-05-07"), # Date (Should NOT be CAS)
                (10, 430, 100, 445, "1333-86-4"),  # Real CAS
                (110, 430, 150, 445, "5%")         # Content
            ],
            "expected_cas": "1333-86-4",
            "expected_cont": "5%"
        }
    ]

    success_count = 0
    for tc in test_cases:
        print(f"[TEST] {tc['name']}")
        mock_page = MockPage(tc["words"])
        results = engine.extract_from_text_regex(mock_page)
        
        # 결과 검증
        found_cas = results[0]["cas_no"] if results else None
        found_cont = results[0]["content"] if results else None
        
        if found_cas == tc["expected_cas"] and found_cont == tc["expected_cont"]:
            print(f"  [OK] PASS (CAS: {found_cas}, Cont: {found_cont})")
            success_count += 1
        else:
            print(f"  [FAIL] FAIL (Expected: {tc['expected_cas']} / {tc['expected_cont']}, Found: {found_cas} / {found_cont})")
            if not results: print("     -> No results found!")

    print(f"\nSummary: {success_count}/{len(test_cases)} Passed")
    if success_count == len(test_cases):
        print("Final Result: SUCCESS")
    else:
        print("Final Result: FAILURE")

if __name__ == "__main__":
    run_logic_test()
