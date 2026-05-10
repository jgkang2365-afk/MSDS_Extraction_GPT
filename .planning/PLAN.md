# 📝 Implementation Plan: File 13 Fix & CAS Filtering Enforcement

## Phase 1: Success DNA & Rule Synchronization
- [ ] `SUCCESS_DNA.md`에 "CAS 번호 부재 시 성분 제외" 규칙 명시적 추가.
- [ ] `msds_engine_v5.py` 내 `final_quality_control` 로직 검토.

## Phase 2: Core Engine Refinement (Tree)
- [ ] **CAS Filtering**: `final_quality_control`에서 `-`, `None` 등 유효하지 않은 CAS를 가진 행을 `continue` 처리하여 결과에서 원천 배제.
- [ ] **Product Name**: 
    - `extract_product_name_hybrid`에 429 에러 발생 시 `time.sleep` 후 최대 3회 재시도 로직 강화.
    - 영문 MSDS 전용 제품명 추출 프롬프트/힌트 로직 보강.

## Phase 3: Verification (Forest)
- [ ] `test_file_013.py`를 통한 단일 검증 (제품명 및 성분 결과 확인).
- [ ] `test_v17_4_bulk.py`를 통한 전체 회귀 테스트 수행.
- [ ] 주님(사용자) 최종 승인 및 .planning 아카이빙.

---
**성공 DNA 대조**: 
- 과거 '영업비밀' 보존 규칙과 상충하지 않는지 확인. 
- `-` (하이픈)만 있는 경우는 사용자 지침에 따라 제거 대상으로 확정.
