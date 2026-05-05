
import sys
import os
import re

# Mocking classes to simulate ODL structure
class MockCell:
    def __init__(self, text):
        self.text = text

class MockRow:
    def __init__(self, texts):
        self.cells = [MockCell(t) for t in texts]

class MockElement:
    def __init__(self, rows):
        self.type = "TABLE"
        self.rows = rows

class MockPage:
    def __init__(self, elements):
        self.elements = elements

class MockDoc:
    def __init__(self, pages):
        self.pages = pages

# Import the logic from msds_engine_v5
sys.path.append(os.getcwd())
from msds_engine_v5 import extract_components_odl_robust

def test_regression():
    print("=== MSDS Engine V17.3.1.6 Regression Test ===")
    
    # 시나리오 1: 139번 파일 (가짜 헤더 + ENCS 노이즈)
    # 1행: Substance (가짜 헤더 - % 없음)
    # 2행: Chemical Name | Weight-% | ENCS | CAS No. (진짜 헤더 - % 있음)
    # 3행: Sodium Borate | 99.5-101.0 | (1)-69 | 1303-96-4 (데이터)
    rows_139 = [
        MockRow(["Single Substance or Mixture", "Substance"]),
        MockRow(["Chemical Name", "Weight-%", "ENCS", "CAS No."]),
        MockRow(["Sodium Tetraborate", "99.5-101.0", "(1)-69", "1303-96-4"])
    ]
    doc_139 = MockDoc([MockPage([MockElement(rows_139)])])
    
    print("\n[Test 1] 139번 시나리오 (가짜 헤더 & 우선순위 열):")
    res_139 = extract_components_odl_robust(doc_139, [0])
    for c in res_139:
        print(f"  Result: CAS {c['cas_no']}, Content {c['content']}")
        assert c['cas_no'] == "1303-96-4"
        assert c['content'] == "99.5~101%" # 100% 초과 허용 확인
        assert "1~69" not in c['content'] # ENCS 노이즈 배제 확인

    # 시나리오 2: 1327-41-9 (행 분리 현상)
    # 1행: 알루미늄... | 1327-41-9 | (함량 비어있음)
    # 2행: (함량만 덩그라니) | | 28.3
    rows_split = [
        MockRow(["물질명", "CAS 번호", "함유량(%)"]),
        MockRow(["알루미늄 클로로수화물", "1327-41-9", ""]),
        MockRow(["", "", "28.3"])
    ]
    doc_split = MockDoc([MockPage([MockElement(rows_split)])])
    
    print("\n[Test 2] 1327-41-9 시나리오 (행 분리 보정):")
    res_split = extract_components_odl_robust(doc_split, [0])
    for c in res_split:
        print(f"  Result: CAS {c['cas_no']}, Content {c['content']}")
        assert c['cas_no'] == "1327-41-9"
        assert c['content'] == "28.3%" # 분리된 행에서 가져오기 확인

    print("\n✅ 모든 데몬스트레이션 테스트 통과!")

if __name__ == "__main__":
    try:
        test_regression()
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
