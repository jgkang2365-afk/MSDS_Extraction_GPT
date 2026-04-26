# Spec: MSDS GUI System Reconstruction (Track 2 Unification)

## 1. 개요 (Overview)
복잡하게 얽힌 지식 DB 및 지능형 매칭 로직을 완전히 제거하고, 사용자가 GUI 테이블에서 수동 편집한 데이터를 기반으로 KOSHA API와 결합하여 엑셀에 직저장하는 **'트랙 2' 단일화 파이프라인**을 구축합니다.

## 2. 요구 사항 (Requirements)
- **Bloatware 완전 제거**:
    - `KnowledgeDBTab`, `MatchingTab`, `MatchingWorker` 클래스 삭제.
    - `sqlite3`, `thefuzz` 관련 임포트 및 로직 삭제.
- **데이터 소스 단일화**:
    - 엑셀 저장 시 `self.results` 캐시 대신 **`self.table` (GUI 테이블)**의 현재 값을 직접 참조.
- **KOSHA API 연동**:
    - 저장 시점에 테이블의 CAS 번호를 바탕으로 규제 정보를 실시간 조회하여 엑셀에 기록.
- **지혈 작업 (Hemostasis)**:
    - 삭제된 기능의 잔재(need_review 큐, 동기화 함수 등)를 완전히 제거하여 AttributeError 방지.
- **엑셀 저장 순서 동기화 (Visual Sync)**:
    - 저장 시 `self.results` 순서가 아닌 **GUI 테이블의 시각적 행 순서**를 기준으로 엑셀에 기록.
- **마이크로 버그 클린업 (Micro Cleanup)**:
    - 상태 인식 오타, 중복 예외 처리, 메모리 동기화 오타, 중복 함수 호출 등 4종 버그 수정.
- **절대 방어**:
    - `msds_engine_v5.py`의 추출 로직(Vision 안내견 등)은 절대 수정 금지.

## 3. 상세 설계 (Detailed Design)

### 3.1 UI 구조 변경
- 상단 탭에서 "추출 결과" 탭만 남기고 "지식 DB", "매칭 결과" 탭 삭제.

### 3.2 엑셀 저장 프로세스 (Visual Order Sync)
1. GUI 테이블의 모든 행을 시각적 순서대로 순회 (`range(rowCount)`).
2. 각 행에서 `파일명`을 추출하여 추출 결과 데이터(`table_dict`)와 매칭.
3. 사용자 입력 시작 행(`st_row`)부터 순차적으로(`st_row + saved_count`) 엑셀에 기록.

## 4. 작업 계획 (Action Plan)
1. **[Cleanup]** `smu_gui.py`에서 DB 및 매칭 관련 클래스, UI, 임포트 제거. (완료)
2. **[Refactor]** `perform_standard_save` 메서드 재구축. (완료)
3. **[Hemostasis]** 삭제된 기능의 잔재(Dead Code) 박멸. (완료)
4. **[Visual Sync]** 테이블 시각적 순서와 엑셀 저장 순서 동기화 구현. (완료)
5. **[Micro Cleanup]** smu_gui.py 내 마이크로 버그 4종 수정. (진행 예정)
6. **[Verify]** 최종 시스템 동작 검증.

## 5. 지혈 및 클린업 상세 (Hemostasis & Cleanup Details)
- **Hemostasis**: `need_review` 큐 및 동기화 함수 제거 완료.
- **Micro Cleanup**:
    - `update_validation_row`: 상태 체크 로직 보정 (`"검증 완료" in status`).
    - `update_validation_row`: 중복 `except` 블록 통합.
    - `on_table_item_changed`: `hash` -> `f_hash` 오타 수정.
    - `add_result_to_table`: `_safe_resize_rows()` 중복 호출 제거.

## 6. 절대 준수 사항
- 모든 작업은 한국어로 보고한다.
- `msds_engine_v5.py`는 단 한 줄도 건드리지 않는다.
