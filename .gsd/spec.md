# [Spec] Graphify 백그라운드 워커 및 CAS 명칭 표준화 정밀 이식

## 1. 개요
지능형 MSDS 추출 시스템의 완성도를 높이기 위해, 지식 그래프(Graphify)의 비동기 업데이트와 마스터 데이터 기반의 성분명 표준화 및 미등록 플래그 기능을 이식합니다.

## 2. 변경 사항

### [Task 1] smu_gui.py: 우뇌 각성 및 GUI 안전장치
- **GraphifyIndexerThread 추가**: 비동기 지식 학습을 위한 QThread 클래스 구현. `graphify.update_graph_incremental` 호출.
- **스레드 관리**: `__init__`에서 `self.active_graph_threads` 리스트 초기화 및 스레드 생명주기 관리.
- **백그라운드 트리거**: `add_result_to_table`에서 UI 업데이트 직후 학습 스레드 발사. 상태바(StatusBar)에 진행 상태 연동.
- **Graceful Shutdown**: `closeEvent` 오버라이드를 통해 활성 학습 스레드 존재 시 종료 경고 메시지 출력 (DB 손상 방지).

### [Task 2] msds_engine_v5.py: 좌뇌 정제 및 미등록 플래그
- **마스터 DB 로드**: `MES_MASTER_LOOKUP.json` 기반 `MES_MASTER_MAP` 구축.
- **AI 결과 처리 고도화**:
    - CAS 번호 형식 검증 및 `영업비밀` 예외 처리.
    - 함유량 자동 정제 (단위 `%` 보정 및 미기재 처리).
    - **명칭 표준화**: 마스터 DB 존재 시 표준명 사용, 부재 시 `[미등록]` 태그 부착.
- **포맷 통일**: `성분명[CAS(함유량)]` 형식으로 AI 추출 및 Baseline(1차) 결과 포맷 일원화.

## 3. 상세 수정 계획

### msds_engine_v5.py
- **위치 1**: 상단 마스터 데이터 로드부 (라인 34 부근).
- **위치 2**: `process_pdf` 내 AI 결과 파싱 루프 (라인 545 부근).
- **위치 3**: `run_v24_baseline` 내 결과 조합부 (라인 296 부근).

### smu_gui.py
- **위치 1**: 상단 임포트 영역 아래 `GraphifyIndexerThread` 정의.
- **위치 2**: `SMUGUI.__init__` 내 스레드 리스트 초기화.
- **위치 3**: `add_result_to_table` 하단 (라인 2832 부근) 스레드 발사 로직.
- **위치 4**: `SMUGUI` 클래스 내 `closeEvent` 추가.

## 4. 검증 계획 (FTF Protocol)
1. **Forest (사전 분석)**: `statusBar` 및 `closeEvent` 등 PyQt5 API 활용 가능성 확인.
2. **Tree (정밀 수정)**: 지시서의 코드를 기반으로 정밀 이식.
3. **Forest (사후 검증)**:
    - `py_compile`을 통한 문법 오류 체크.
    - `msds_engine_v5.py` 단독 실행 테스트 (가상) - 포맷 확인.
