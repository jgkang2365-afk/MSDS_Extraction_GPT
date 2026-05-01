# Implementation Plan: V15.8.8 Page Tracking & Reliability Boost

## Phase 1: Engine Reliability - Omission Detector Polish
- [ ] `msds_engine_v5.py`: `check_omission` 함수 개선
    - [ ] `set()` 제거 및 원본 CAS 리스트 전체 카운트와 비교 (중복 허용)
    - [ ] 누락된 구체적인 CAS 번호를 식별하여 로그(ValueError)에 포함
    - [ ] `final_quality_control`에서 `check_omission` 호출 시 에러 핸들링 보강

## Phase 2: GUI Intelligence - PDF Page Tracking
- [ ] `smu_gui.py`: `on_row_clicked` 수정
    - [ ] `COL_IDX_PAGE` (10번 열)에서 데이터 추출
    - [ ] `self.preview_pane.navigate_to_page(int_page)` 호출
    - [ ] 페이지가 1보다 작거나 없으면 1페이지로 세이프가드 처리

## Phase 3: GUI Robustness - Session Recovery Check
- [ ] `smu_gui.py`: `restore_table_from_session` 로직 재점검
    - [ ] 캐시 복구 시 `page` 정보가 정확히 테이블에 기입되는지 확인

## Phase 4: Verification
- [ ] `py_compile smu_gui.py` & `msds_engine_v5.py`
- [ ] 가상 테스트 (Dry run) 및 시각적 사후 검증 계획 수립
