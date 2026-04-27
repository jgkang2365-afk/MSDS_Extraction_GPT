# [GSD2] msds_engine_v5.py 제품명 2중 방어망 (워터폴) 구축 계획

## 1. 개요
`msds_engine_v5.py`에 메인 AI 가동 전, 파이썬 정규식과 Gemini Flash-Lite를 이용해 제품명을 사전에 확정 짓는 '2중 방어망(워터폴)' 로직을 추가합니다.

## 2. 작업 상세 (FTF 프로토콜 적용)

### [Forest] 사전 분석 및 충돌 방지
- 현재 `msds_engine_v5.py`에 동일한 이름의 `extract_product_name_hybrid` 함수가 존재함 (V24용).
- 사용자 요청 함수와 이름이 겹치므로, 기존 함수를 `extract_product_name_v24`로 리네이밍하여 보존함.
- `run_v24_baseline`에서 호출하는 부분도 함께 수정하여 기존 로직의 무결성을 유지함.

### [Tree] 정밀 수정 단계

#### 🛠️ 제1작업: 하이브리드 추출 헬퍼 함수 신설
- 파일 상단(API 키 세팅 아래)에 `extract_product_name_hybrid(text_chunk, api_key)` 함수를 추가.
- 1차: 파이썬 샌드위치 컷 (Regex)
- 2차: Gemini Flash-Lite 텍스트 스나이핑

#### 🛠️ 제2작업: 메인 프로세스에 사전 추출 로직 끼워넣기
- `process_pdf` 함수 내 `text_chunk` 추출 직후에 사전 추출 로직 실행.
- `log_func`를 통해 획득 여부를 기록.

#### 🛠️ 제3작업: 메인 AI 결과물에 제품명 강제 덮어쓰기
- `process_pdf` 내 AI 호출 성공 직후(`ai_res` 또는 `final_ai_result` 획득 시), 사전 추출된 제품명이 있다면 강제로 덮어씌움.

### [Forest] 사후 검증
- Python 구문 오류 여부 확인.
- `api_key` 누락 시의 방어 로직 확인.
- 기존 `v24_baseline` 로직에 영향이 없는지 확인.

## 3. 수정 위치 및 코드 매핑
- **함수 신설**: `msds_engine_v5.py` L21 근처
- **기존 함수 리네이밍**: `extract_product_name_hybrid` -> `extract_product_name_v24` (L127, L305)
- **사전 추출 삽입**: `process_pdf` L574 아래
- **강제 덮어쓰기 삽입**: `process_pdf` L591 아래 (Gemini), L620 아래 (GPT)

## 4. 제약 사항
- 성분 추출 및 신호등 로직은 절대 수정 금지.
- 1,000줄 이상의 파일 전체 재작성 금지.
