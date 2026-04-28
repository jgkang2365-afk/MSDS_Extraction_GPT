# [GSD2] API 토큰 다이어트 및 프롬프트 예시 오염 제거 계획

## 1. 개요
시스템 응답 속도 최적화를 위해 `msds_engine_v5.py`의 텍스트 추출 제한을 복구하고, AI의 정확도를 높이기 위해 `prompt_system_v5.txt`를 전면 교체합니다.

## 2. 작업 상세 (FTF 프로토콜 적용)

### [Forest] 사전 분석
- **속도 이슈**: 현재 `extract_context_for_ai`에서 텍스트를 무제한으로 반환하여 API 토큰 사용량이 급증하고 응답 속도가 저하됨. 5000자 제한을 통해 이를 해결.
- **프롬프트 오염**: 기존 프롬프트의 예시 숫자를 AI가 그대로 베끼는 현상이 발생. 변수 처리 및 시각 판독 강제 룰이 포함된 V13.4 프롬프트로 교체 필요.

### [Tree] 정밀 수정 단계

#### 🛠️ 제1작업: `msds_engine_v5.py` 5000자 제한 복구
- 파일 위치: `msds_engine_v5.py`
- 함수명: `extract_context_for_ai` (L412-436 근처)
- 수정 내용:
  ```python
  # [수정 전]
  # return target_text

  # [수정 후]
  return target_text[:5000]
  ```

#### 🛠️ 제2작업: `prompt_system_v5.txt` 전면 교체
- 파일 위치: `prompt_system_v5.txt`
- 작업 내용: 파일 내용을 제공된 V13.4(시각 강제 및 예시 멸균) 프롬프트로 100% 덮어쓰기.

### [Forest] 사후 검증
- `msds_engine_v5.py` 문법 오류(Syntax Error) 여부 확인.
- `prompt_system_v5.txt`가 정상적으로 로드되는지 확인 (`load_system_prompt` 함수 로직상 문제없음).
- 5000자 제한이 실제 반환값에 적용되는지 로직 확인.

## 3. 성공 기준 (UAT)
1. `extract_context_for_ai` 함수의 반환값이 최대 5000자로 제한됨.
2. `prompt_system_v5.txt` 내용이 요청받은 최신 버전으로 업데이트됨.
3. 시스템 가동 시 "✅ 파이썬 속도 복구(5000자 제한) 및 프롬프트 V13.4(시각 강제 및 예시 멸균) 통합 적용 완료" 메시지 출력 준비.
