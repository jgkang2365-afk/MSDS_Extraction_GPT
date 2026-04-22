# msds_engine_v3 구현 및 검증 태스크 리스트

## [Phase 1] 데이터 추출 레이어 구축
- [x] PyMuPDF (`fitz`) `dict` 모드 통합 (`get_text("dict")`)
- [x] 페이지별/라인별 텍스트 블록 및 bbox(좌표) 데이터 구조화
- [x] 텍스트 높이(Font Size) 기반 유의미한 블록 필터링

## [Phase 2] 공간 분석 레이어 (SAS 엔진) 구현
- [x] `patterns.json` 기반 제품명 앵커(키워드) 탐색 로직
- [x] SAS 스코어링 알고리즘 ($S = (W_{align} \times A) - (W_{dist} \times D)$) 구현
- [x] 앵커 우측/하단 후보군 선별 및 스코어링 자동화
- [x] 제품명 후보군 시각적 정렬 가중치 미세 조정

## [Phase 3] 시맨틱 검증 레이어 (Ollama) [Optional]
- [x] 로컬 Ollama API (`llama3.2`) 연동 인터페이스 구현
- [x] SAS 상위 후보군 대상 최종 제품명 판별 프롬프트 설계
- [x] Ollama 응답 실패 시 SAS 1순위 자동 폴백 시스템 구축

## [Phase 4] 레거시 통합 및 예외 처리
- [x] CAS 번호 체크디지트 검증 로직 이식 (`is_valid_cas`)
- [x] NFKC 텍스트 정규화 로직 통합 (`normalize_text`)
- [x] 함유량 범위 및 기호 정규화 로직 통합 (`format_content`)
- [x] 앵커 미발견 시 v2 윈도우 탐색 모드 폴백 구현

## [Phase 5] 최종 검증 및 테스트
- [/] 하드코어 테스트 파일 11종 대상 정확도 검증 (진행 중)
- [ ] 기존 성공 케이스 88종 대상 회귀 테스트 (Regression Test)
- [ ] 제품명 추출 정확도(Precision) 98% 달성 확인
