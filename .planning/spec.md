# Spec: MSDS GUI System Reconstruction (Track 2 Unification)

## 1. 개요 (Overview)
복잡하게 얽힌 지식 DB 및 지능형 매칭 로직을 완전히 제거하고, 사용자가 GUI 테이블에서 수동 편집한 데이터를 기반으로 KOSHA API와 결합하여 엑셀에 직저장하는 **'트랙 2' 단일화 파이프라인**을 구축합니다.

## 2. 요구 사항 (Requirements)
- **Bloatware 완전 제거**:
    - `KnowledgeDBTab`, `MatchingTab`, `MatchingWorker` 클래스 삭제.
    - `sqlite3`, `thefuzz` 관련 임포트 및 로직 삭제.
    - 2단계 검증용 캐시/DB 참조 로직 폐기.
- **데이터 소스 단일화**:
    - 엑셀 저장 시 `self.results` 캐시 대신 **`self.table_step1` (GUI 테이블)**의 현재 값을 직접 참조.
- **KOSHA API 연동**:
    - 저장 시점에 테이블의 CAS 번호를 바탕으로 규제 정보를 실시간 조회하여 엑셀에 기록.
- **절대 방어**:
    - `msds_engine_v5.py`의 추출 로직(Vision 안내견 등)은 절대 수정 금지.

## 3. 상세 설계 (Detailed Design)

### 3.1 UI 구조 변경
- 상단 탭에서 "추출 결과" 탭만 남기고 "지식 DB", "매칭 결과" 탭 삭제.
- 환경설정에서 매칭 경로 등 불필요한 설정 항목 제거.

### 3.2 엑셀 저장 프로세스 (Refactored `perform_standard_save`)
1. GUI 테이블(`table_step1`)의 모든 행을 순회.
2. 각 행에서 `제품명`, `CAS 원본` 등을 추출.
3. **[핵심]** CAS 번호를 KOSHA 규제 조회 함수에 전달하여 최신 결과 획득.
4. 사용자 입력 시작 행(`st_row`)부터 순차적으로 엑셀에 기록 및 저장.

## 4. 작업 계획 (Action Plan)
1. **[Cleanup]** `smu_gui.py`에서 DB 및 매칭 관련 클래스, UI, 임포트 제거.
2. **[Refactor]** `perform_standard_save` 메서드를 GUI 테이블 직접 참조 방식으로 재구축.
3. **[Integrate]** 저장 시점 KOSHA API 호출 로직 삽입 및 필드 매핑.
4. **[Verify]** 테이블 편집 내용이 엑셀에 그대로 반영되는지 최종 검증.

## 5. 절대 준수 사항
- 모든 작업은 한국어로 보고한다.
- `msds_engine_v5.py`는 단 한 줄도 건드리지 않는다.
