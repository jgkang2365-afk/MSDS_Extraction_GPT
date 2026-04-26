# [GSD Spec] smu_gui.py 미리보기 스크롤 추적 로직 제거

## 1. 개요
`smu_gui.py`의 `on_row_clicked` 함수에서 복잡한 페이지 이동 및 스크롤 추적 로직을 삭제하고, 테이블 행 클릭 시 항상 PDF의 1페이지(최상단)가 표시되도록 단순화한다.

## 2. 변경 사항
### smu_gui.py
- `on_row_clicked` 함수 (약 1935행 부근) 내부 로직 교체
  - `target_page_item` 및 페이지 이동 관련 로직 제거
  - `self.preview_pane.verticalScrollBar().setValue(0)`을 사용하여 스크롤을 최상단으로 고정

## 3. 상세 구현 계획
1. `smu_gui.py` 파일을 열어 `on_row_clicked` 함수의 위치를 확인한다. (현재 확인 결과 1935행)
2. 사용자로부터 제공받은 코드로 해당 함수를 전면 교체한다.
3. 기존의 다른 코드 구조(시그널 연결 등)는 유지한다.

## 4. 검증 계획
- UI를 실행하여 테이블 행 클릭 시 PDF 미리보기가 로드되고 스크롤이 항상 최상단에 위치하는지 확인한다.
- `COL_IDX_FILEPATH` 등 상수 참조에 문제가 없는지 확인한다.
