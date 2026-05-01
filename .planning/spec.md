# [GSD2] V15.8.7: 사령부 변수 동기화 강제 (Heart Surgery)

## 1. 개요
`process_pdf` 심장부에서 각 AI 호출 단계마다 스나이퍼 탄창을 최신화하여, 네트워크 오류나 키 교체 상황에서도 즉각적으로 가장 '신선한' 스나이퍼를 투입하도록 로직을 강화합니다.

## 2. 작업 상세 (FTF 프로토콜 적용)

### [Forest] 사전 분석
- **현상**: 현재 `current_sniper`가 `process_pdf` 시작 시점에 한 번 배정되거나 일부 단계에서만 동기화되고 있음.
- **영향**: 이전 단계에서 API 오류가 발생하여 탄창이 교체되었더라도, 다음 단계 호출 시 이전 스나이퍼 변수를 그대로 들고 있을 위험이 있음.

### [Tree] 정밀 수정 단계

#### 🛠️ [심장 수술] `process_pdf` 내 스나이퍼 동기화 강화 (`msds_engine_v5.py`)
- **단계 1**: `extract_section3_images` 호출 직전 `get_next_sniper()` 실행.
- **단계 2**: `extract_product_name_hybrid` 호출 직전 `get_next_sniper()` 실행.
- **단계 3**: `call_gemini_2_5_flash` 호출 직전 `get_next_sniper()` 실행. (기존 로직 유지 및 강화)

### [Forest] 사후 검증
- [ ] 각 단계 진입 시 로그에 표시되는 스나이퍼가 최신 탄창 상태를 반영하는지 확인.
- [ ] `py_compile` 구문 검사 통과.

## 3. 성공 기준 (UAT)
1. 제품명 추출과 성분 추출 사이에 스나이퍼 탄창이 변하더라도, 실시간으로 배정받은 최신 스나이퍼가 투입됨.
2. 모든 AI 호출 함수에 `current_sniper` 변수가 누락 없이 전달됨.
