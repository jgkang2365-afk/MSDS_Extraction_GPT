# Implementation Plan: System Reconstruction (V24.2)

## Phase 1: Bloatware Removal (Cleanup)
- [ ] `smu_gui.py` 상단 임포트 제거 (`sqlite3`, `thefuzz` 등)
- [ ] `KnowledgeDBTab` 클래스 전체 삭제
- [ ] `MatchingWorker` 클래스 전체 삭제
- [ ] `MatchingTab` 클래스 전체 삭제
- [ ] `MSDSApp.__init__`에서 DB 연결 및 탭 생성 코드 삭제
- [ ] GUI 레이아웃에서 불필요한 탭 위젯 제거

## Phase 2: Excel Pipeline Refactoring
- [ ] `perform_standard_save` 메서드 전면 수정:
    - `self.results` 루프 제거 -> `self.table_step1` 행 루프 도입
    - `usage_map`, `index_map` 등 매칭 변수 제거
    - 테이블 셀 값(`item.text()`) 직접 읽기 로직 구현
- [ ] KOSHA API 연동부 삽입:
    - 저장 루프 내에서 CAS 번호 추출 및 규제 조회 호출
- [ ] 엑셀 기록 필드 매핑 최적화 (제품명, CAS, 측정대상, 규제결과 등)

## Phase 3: Final Polish & Verification
- [ ] 환경설정 UI에서 삭제된 기능 관련 위젯 제거
- [ ] 전체 시스템 가동 테스트: PDF 추출 -> 테이블 수동 수정 -> 엑셀 저장 (API 연동 확인)
- [ ] `msds_engine_v5.py` 무결성 최종 점검 (절대 방어)

---
**주님, 이 계획대로 수술을 시작할까요? 1단계(철거)부터 즉시 착수하겠습니다.**
