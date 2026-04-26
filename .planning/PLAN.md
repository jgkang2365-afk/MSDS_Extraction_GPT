# Implementation Plan: System Reconstruction (V24.2)

## Phase 1: Bloatware Removal (Cleanup) [COMPLETED]
- [x] `smu_gui.py` 상단 임포트 제거 (`sqlite3`, `thefuzz`, `process` 등)
- [x] `KnowledgeManager` 클래스 및 DB 관리 로직 전체 삭제
- [x] `MatchingWorker` 클래스 및 매칭 페이지(`_create_matching_page`) 전체 삭제
- [x] `SMUGUI.__init__`에서 DB 연결 및 지식 베이스 초기화 코드 삭제
- [x] `GraphifyIndexerThread` 삭제 및 관련 UI 인덱싱 트리거 제거
- [x] GUI 레이아웃에서 불필요한 위젯(사후 검수 대기열 등) 제거

## Phase 2: Excel Pipeline Refactoring [COMPLETED]
- [x] `perform_standard_save` 메서드 전면 수정:
    - `self.results` 순서 기반 저장 로직 구현
    - 테이블 셀 값(`item.text()`) 직접 읽기 파이프라인 구축
    - `usage_map`, `index_map` 등 구형 매칭 변수 완전 제거
- [x] 데이터 검증 로직 단일화:
    - KOSHA API와 로컬 마스터 DB(`유해인자_MES.txt`) 연동 체계만 유지
- [x] 엑셀 기록 필드 매핑 최적화 (제품명, CAS, 측정대상, 규제결과 등)

## Phase 3: Final Polish & Verification [COMPLETED]
- [x] UI 텍스트 정제: 도움말 다이얼로그(`show_help_dialog`)에서 삭제된 기능(지식 그래프 등) 언급 제거
- [x] 페이지 전환(`switch_page`) 로직 복구 및 사이드바 버튼 연결 수정
- [x] `msds_engine_v5.py` 무결성 최종 점검 (절대 방어 준수)

## Phase 4: Dead Code & Synchronization Cleanup (Hemostasis) [IN PROGRESS]
- [ ] `on_validation_result`: `Review Required` 큐잉 블록 삭제
- [ ] `on_validation_finished`: `need_review` 분기 제거 및 메시지 통합
- [ ] 동기화 좀비 함수(5종) 완전 박멸
- [ ] `_update_combo_sheets`: 타 콤보박스 동기화 로직 제거

## Phase 5: Final System Verification [PLANNED]
- [ ] 전체 시스템 가동 테스트: PDF 추출 -> 테이블 수동 수정 -> 엑셀 저장 (API 연동 확인)
- [ ] 최종 코드 무결성 검사 및 지혈 확인

---
**주님, 지혈 작업(Dead Code 제거) 계획을 수립했습니다. 이대로 착수할까요?**
