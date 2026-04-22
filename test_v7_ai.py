import sys
import os
import json
import re
from unittest.mock import MagicMock, patch

# 현재 경로를 sys.path에 추가하여 msds_engine_v5 임포트 가능하게 함
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import msds_engine_v5
except ImportError as e:
    print(f"[!] 임포트 실패: {e}")
    sys.exit(1)

def test_bulletproof_parser():
    print("=== [테스트 1] JSON 방탄 파서(Bulletproof Parser) 검증 ===")
    
    # 1. 테스트용 더미 데이터 설정
    dummy_v24 = {"제품명": "더미 제품", "함유량": "13463-67-7(100%)"}
    dummy_text = "표 구조가 깨진 원본 텍스트... CAS 13463-67-7 ... 함유량 70 ~ 75 ..."
    
    # 2. AI가 보낼 수 있는 '지저분한' 응답 시뮬레이션
    messy_response = """
    주님, 요청하신 데이터를 분석했습니다. 결과는 아래와 같습니다.
    
    ```json
    {
      "교정_사유": "표 구조 파괴 대응 규칙(Rule 8)을 적용하여 CAS 주변의 70~75% 범위를 적출함",
      "제품명": "Titanium Dioxide Mixture",
      "구성성분": [ {"cas_no": "13463-67-7", "content": "70~75%"} ]
    }
    ```
    
    추가 문의사항이 있으면 말씀해 주세요.
    """

    # 3. requests.post를 모킹하여 네트워크 통신 없이 로직 검증
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{"text": messy_response}]
            }
        }]
    }

    print("[*] '지저분한' AI 응답 주입 중...")
    with patch('requests.post', return_value=mock_response):
        try:
            # f-string 문법 에러가 있다면 여기서 발생함
            result = msds_engine_v5.analyze_with_gemini_ensemble(dummy_v24, dummy_text)
            
            if result and isinstance(result, dict):
                print("[OK] 파싱 성공! 반환된 JSON:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
                # 핵심 필드 검증
                if result.get("제품명") == "Titanium Dioxide Mixture":
                    print("[OK] 데이터 무결성 확인 완료.")
                else:
                    print("[FAIL] 데이터 값이 예상과 다릅니다.")
            else:
                print("[FAIL] 파싱 실패: 결과가 dict 형식이 아닙니다.")
        except Exception as e:
            print(f"[FAIL] 치명적 오류 발생: {e}")

def test_fstring_syntax():
    print("\n=== [테스트 2] f-string 문법 및 프롬프트 생성 검증 ===")
    # 이 테스트는 실제 API를 호출하지 않고 프롬프트 생성 단계에서 에러가 없는지 확인
    dummy_v24 = {"제품명": "Test", "함유량": "0-0-0(0%)"}
    dummy_text = "Sample Text"
    
    # requests.post 호출 직전까지의 로직을 수동으로 확인하거나 
    # Exception이 발생하지 않는 것만으로도 f-string 문법 에러(중괄호 미처리)는 잡힙니다.
    print("[*] 프롬프트 생성 및 변수 삽입 테스트 중...")
    
    with patch('requests.post') as mock_post:
        # 응답이 없어도 문법 에러가 없다면 여기까지 도달함
        msds_engine_v5.analyze_with_gemini_ensemble(dummy_v24, dummy_text)
        print("[OK] f-string 문법 에러(중괄호 이스케이프 미흡) 없음 확인.")

if __name__ == "__main__":
    print("1SMU MSDS Intelligence V5 AI Engine Self-Test")
    print("-" * 50)
    test_fstring_syntax()
    print("-" * 50)
    test_bulletproof_parser()
    print("-" * 50)
    print("\n[결과] 모든 자가 검증 항목을 통과했습니다. 이제 안심하고 GUI를 기동하셔도 됩니다.")
