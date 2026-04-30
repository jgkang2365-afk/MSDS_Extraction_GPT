# Implementation Plan: V15.6 Architecture Consolidation

## Phase 1: Core Refactoring (Mission 1)
- [ ] `msds_engine_v5.py`: `minimal_clean` 함수 제거 (L216-228)
- [ ] `msds_engine_v5.py`: `final_quality_control` 함수 삽입 (동일 위치)
- [ ] `msds_engine_v5.py`: `VERSION` 변수 `15.6`으로 업데이트

## Phase 2: Pipeline Simplification (Mission 2)
- [ ] `msds_engine_v5.py`: `process_pdf` 내 Phase 6 루프(L485-521) 제거
- [ ] `msds_engine_v5.py`: `final_quality_control` 호출 및 결과 바인딩 코드 삽입

## Phase 3: Verification
- [ ] `py_compile msds_engine_v5.py` 실행하여 구문 오류 체크
- [ ] `smu_gui.py` 실행 테스트 (선택 사항)
