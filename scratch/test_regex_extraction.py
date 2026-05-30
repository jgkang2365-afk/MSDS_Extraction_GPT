import sys
import os
import re

# msds_engine_v5 임포트를 위해 경로 설정
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))
import msds_engine_v5

class MockPage:
    def __init__(self, words):
        self._words = words
        
    def get_text(self, option, **kwargs):
        if option == "words":
            return self._words
        if option == "blocks":
            return []
        return ""

def run_test():
    # 이미지의 3. 구성성분의 명칭 및 함유량 표를 시각적 좌표(words) 구조로 모방함
    words = [
        # 3. 구성성분의 명칭 및 함유량
        (10, 10, 30, 25, "3.", 0, 0, 0),
        (35, 10, 100, 25, "구성성분의", 0, 0, 1),
        (105, 10, 150, 25, "명칭", 0, 0, 2),
        (155, 10, 175, 25, "및", 0, 0, 3),
        (180, 10, 230, 25, "함유량", 0, 0, 4),
        
        # 표 헤더
        (10, 40, 100, 55, "INCI명", 1, 0, 0),
        (300, 40, 400, 55, "CAS번호", 1, 0, 1),
        (500, 40, 600, 55, "함유량(%)", 1, 0, 2),
        
        # 첫 번째 성분 행: Iron Oxides (CI 77491) | 1309-37-1 | 97.0
        (10, 70, 50, 85, "Iron", 2, 0, 0),
        (60, 70, 110, 85, "Oxides", 2, 0, 1),
        (120, 70, 150, 85, "(CI", 2, 0, 2),
        (160, 70, 220, 85, "77491)", 2, 0, 3),
        (300, 70, 400, 85, "1309-37-1", 2, 0, 4),
        (500, 70, 550, 85, "97.0", 2, 0, 5),
        
        # 두 번째 성분 행: Triethoxycaprylylsilane | 2943-75-1 | 3.0
        (10, 100, 180, 115, "Triethoxycaprylylsilane", 3, 0, 0),
        (300, 100, 400, 115, "2943-75-1", 3, 0, 1),
        (500, 100, 550, 115, "3.0", 3, 0, 2)
    ]
    
    mock_page = MockPage(words)
    print("=== [테스트 시작] msds_engine_v5.extract_from_text_regex 모의 가동 ===")
    
    # 텍스트 기반 추출 가동
    extracted, inherited_x = msds_engine_v5.extract_from_text_regex(mock_page, log_func=print)
    
    print("\n=== [추출 가공 전 원본 데이터] ===")
    for item in extracted:
        print(item)
        
    print("\n=== [최종 퀄리티 컨트롤 (final_quality_control) 적용 시뮬레이션] ===")
    # full_text 모방 구성
    full_text = "3. 구성성분의 명칭 및 함유량\nINCI명 CAS번호 함유량(%)\nIron Oxides (CI 77491) 1309-37-1 97.0\nTriethoxycaprylylsilane 2943-75-1 3.0\n4. 응급조치 요령"
    
    refined, has_invalid = msds_engine_v5.final_quality_control(extracted, full_text, is_ai=False, log_func=print)
    
    print("\n=== [최종 추출 성분 결과] ===")
    for item in refined:
        print(f"CAS: {item['cas']} | 이름: {item['name']} | 함유량: {item['content']}")

if __name__ == "__main__":
    run_test()
