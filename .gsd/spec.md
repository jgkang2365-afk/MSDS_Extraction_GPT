# [GSD Spec] smu_gui.py Excel COM 객체 속성 에러(AttributeError) 방어 로직 전면 적용

## 1. 개요
엑셀 COM 객체(`excel`)의 속성(`Visible`, `DisplayAlerts`, `Interactive`, `UserControl`)을 설정할 때 발생하는 `AttributeError`를 방지하기 위해 모든 해당 코드 라인에 `try-except AttributeError: pass` 방어 로직을 적용한다.

## 2. 변경 대상 및 내용
### smu_gui.py
#### 1) `assign_excel_numbers` 함수 (약 2472행, 2509-2510행 부근)
- `excel.Visible = False` -> `try-except` 적용
- `excel.Visible = True`, `excel.UserControl = True` -> `try-except` 적용

#### 2) `perform_standard_save` 함수 (약 3090-3091행, 3316-3317행, 3322행 부근)
- `excel.Visible = False`, `excel.DisplayAlerts = False` -> `try-except` 적용
- `excel.Visible = True`, `excel.Interactive = True` -> `try-except` 적용
- `if excel: excel.Visible = True` -> `try-except` 적용

## 3. 상세 구현 계획
1. `smu_gui.py`에서 `excel.Visible`, `excel.DisplayAlerts`, `excel.Interactive`, `excel.UserControl` 속성에 값을 할당하는 모든 코드를 찾아 `try: ... except AttributeError: pass` 블록으로 감싼다.
2. 기존의 핵심 로직(데이터 기록, 워크북 오픈 등)은 변경하지 않는다.

## 4. 검증 계획
- `python -m py_compile smu_gui.py` 실행을 통한 문법 검증.
- 엑셀 관련 기능을 실행하여 오류 없이 동작하는지 확인.
