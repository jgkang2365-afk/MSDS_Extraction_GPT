# [GSD Spec] smu_gui.py 수동 수정 데이터 검증 누락 버그 픽스

## 1. 개요
사용자가 테이블에서 CAS 데이터(`raw_content`)를 수동으로 수정한 경우, 기존의 캐시 및 지식 DB를 우회하여 KOSHA API를 강제로 재호출하도록 시스템을 보강한다.

## 2. 변경 사항
### smu_gui.py
#### 1) `ValidationWorker.run` (약 467행 부근)
- `is_manual_cas` 변수 도입: 캐시의 `manual_data`에 `raw_content`가 존재하는지 확인.
- DB 지식 조회 및 하이패스 로직에 `not is_manual_cas` 조건 추가.

#### 2) `ValidationWorker.run` KOSHA API 호출부 (약 527행 부근)
- `f_hash_for_api` 변수 도입: `is_manual_cas`가 `True`이면 `None`으로 설정하여 엔진의 `Cache-Hit` 차단.
- 수동 수정 감지 시 로그 출력.

#### 3) `SMUGUI.on_table_item_changed` (약 2203행 부근)
- `key == "raw_content"`인 경우, 기존 규제 결과 캐시(`measure`, `reg2`, `reg1`)를 삭제하여 데이터 정합성 보장.

## 3. 상세 구현 계획
1. `ValidationWorker.run`에서 `is_manual_cas` 로직을 구현하고 DB 조회 조건을 수정한다.
2. API 호출 시 `f_hash` 대신 `f_hash_for_api`를 전달하도록 수정한다.
3. `on_table_item_changed`에서 CAS 수정 시 연관 캐시를 삭제하는 로직을 추가한다.

## 4. 검증 계획
- `python -m py_compile smu_gui.py` 실행을 통한 문법 검증.
- UI 실행 후 CAS 데이터 수정 시 규제 결과가 초기화되고, 검증 시 API가 재호출되는지 확인.
