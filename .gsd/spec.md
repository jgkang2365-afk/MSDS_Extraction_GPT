# [GSD Spec] smu_gui.py ExtractionWorker 수동 수정(manual_data) 최우선 로드 적용

## 1. 개요
`ExtractionWorker.run` 로직에서 캐시를 로드할 때, 사용자가 수동으로 수정한 데이터(`manual_data`)가 존재하면 이를 원본 AI 추출 결과보다 우선적으로 UI에 반영하도록 개선한다.

## 2. 변경 사항
### smu_gui.py
#### 1) `ExtractionWorker.run` (약 394-407행 부근)
- `else` 블록 내 `res_data` 생성 로직 수정.
- `manual_data`를 체크하여 `product_name` 및 `raw_content`를 우선적으로 덮어씀.
- `manual_data`가 존재하는 경우 `status`를 "수동 수정됨"으로 표시.

## 3. 상세 구현 계획
1. `smu_gui.py`의 `ExtractionWorker.run` 내 캐시 발견 시의 `else` 블록을 찾는다.
2. 사용자 지시서에서 제공한 `manual_data` 최우선 로드 로직으로 해당 코드를 교체한다.

## 4. 검증 계획
- `python -m py_compile smu_gui.py` 실행을 통한 문법 검증.
- 캐시에 수동 수정된 데이터가 있는 파일을 로드할 때 UI에 수정된 값이 정상적으로 표시되는지 확인.
