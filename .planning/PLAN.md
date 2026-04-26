# Implementation Plan: System Reconstruction (V24.2)

## Phase 1: Bloatware Removal (Cleanup) [COMPLETED]
- [x] `smu_gui.py` 상단 임포트 제거 (`sqlite3`, `thefuzz`, `process` 등)
- [x] `KnowledgeManager` 클래스 및 DB 관리 로직 전체 삭제
- [x] `MatchingWorker` 클래스 및 매칭 페이지 전체 삭제
- [x] `SMUGUI.__init__`에서 DB 연결 및 지식 베이스 초기화 코드 삭제

## Phase 2: Excel Pipeline Refactoring [COMPLETED]
- [x] `perform_standard_save` 메서드 전면 수정:
    - 테이블 셀 값(`item.text()`) 직접 읽기 파이프라인 구축
    - `usage_map`, `index_map` 등 구형 매칭 변수 완전 제거
- [x] 데이터 검증 로직 단일화 (KOSHA API 연동)

## Phase 3: Final Polish [COMPLETED]
- [x] UI 텍스트 정제 및 페이지 전환 로직 복구
- [x] `msds_engine_v5.py` 무결성 최종 점검 (절대 방어 준수)

## Phase 4: Dead Code & Synchronization Cleanup (Hemostasis) [COMPLETED]
- [x] `on_validation_result`: `Review Required` 큐잉 블록 삭제
- [x] `on_validation_finished`: `need_review` 분기 제거 및 메시지 통합
- [x] 동기화 좀비 함수(5종) 완전 박멸
- [x] `_update_combo_sheets`: 타 콤보박스 동기화 로직 제거

## Phase 5: Visual Order Sync (Save Logic Enhancement) [COMPLETED]
- [x] `perform_standard_save`: `self.results` 루프를 `self.table.rowCount()` 루프로 교체
- [x] 파일명(Column 7) 기반 매칭 및 순차적 행 기입 로직 적용

## Phase 6: Micro Bug Cleanup [IN PROGRESS]
- [ ] `update_validation_row`: 상태 체크 조건문 수정 (`"검증 완료" in status`)
- [ ] `update_validation_row`: 중복된 `except` 구문 하나로 통합
- [ ] `on_table_item_changed`: 메모리 동기화 키워드 오타 수정 (`hash` -> `f_hash`)
- [ ] `add_result_to_table`: `_safe_resize_rows()` 중복 호출 제거

## Phase 7: Final System Verification [PLANNED]
- [ ] 전체 시스템 가동 테스트: PDF 추출 -> 테이블 수동 수정 -> 엑셀 저장
- [ ] 최종 코드 무결성 검사 및 지혈 확인

---
**주님, 마이크로 버그 4종 클린업 계획을 수립했습니다. 이대로 착수할까요?**
