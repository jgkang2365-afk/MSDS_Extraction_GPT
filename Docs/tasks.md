# tasks.md: v3_하이브리드 구현 로드맵

- [x] **Task 1: msds_utils_v3.py 안정화 패치**
    - [x] `format_content` 내부에 val > 100.0 즉시 기각 로직 및 % 단위 필수 체크 구현
    - [x] `is_garbage`에 목차 패턴(`r'^[가-하나-힣\d]\s*[.)]'`) 및 구분선 감지 추가

- [x] **Task 2: V3 엔진 '공간 맵핑' 리팩토링**
    - [x] `extract_product_name_sas`를 좌표 기반의 Context String 생성기로 개조
    - [x] 수집된 블록을 시각적 순서(Y축 -> X축 순)로 정렬하여 LLM에 전달

- [x] **Task 3: Ollama 지능형 파싱 및 JSON 리턴**
    - [x] Ollama 응답을 `{product_name, composition, reasoning}` 구조의 JSON으로 강제
    - [x] 타임아웃 25초 설정 및 통신 에러 발생 시 [REVIEW] 자동 할당

- [x] **Task 4: GUI 로그 및 새로고침 구현**
    - [x] 로그창에 'Ollama Reasoning(판단 근거)' 노출 로직 추가
    - [x] '엔진 새로고침' 버튼 클릭 시 모듈 재로드 기능 구현

- [x] **Task 5: v4.1 고도화 및 전처리 최적화**
    - [x] `VisualContextBuilder` 동적 버킷팅 및 마진 필터링 구현
    - [x] `patterns.json` 기반의 전역 패턴 외주 통합
    - [x] GUI [REVIEW] 전용 필터 기능 및 엑셀 추론 근거 컬럼 추가
