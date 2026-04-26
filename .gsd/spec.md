# [GSD Spec] smu_gui.py 엑셀 COM 객체 DispatchEx 강제 격리 할당 (V11.8)

## 1. 개요
엑셀 작업을 수행할 때 기존의 `Dispatch` 방식 대신 `DispatchEx` 방식을 사용하여 독립된 엑셀 프로세스를 강제로 생성함으로써, 기존에 실행 중인 다른 엑셀 프로세스와의 충돌을 방지하고 작업 안정성을 높인다.

## 2. 변경 사항
### smu_gui.py
#### 1) `assign_excel_numbers` 함수 (약 2483행 부근)
- `excel = win32com.client.Dispatch("Excel.Application")` -> `excel = win32com.client.DispatchEx("Excel.Application")`

#### 2) `perform_standard_save` 함수 (약 3102행 부근)
- `excel = win32com.client.Dispatch("Excel.Application")` -> `excel = win32com.client.DispatchEx("Excel.Application")`

## 3. 상세 구현 계획
1. `smu_gui.py`에서 `win32com.client.Dispatch("Excel.Application")` 코드를 사용하는 두 위치를 찾는다.
2. 해당 코드를 `win32com.client.DispatchEx("Excel.Application")`로 변경한다.

## 4. 검증 계획
- `python -m py_compile smu_gui.py` 실행을 통한 문법 검증.
- 엑셀 저장 기능을 실행하여 독립된 프로세스로 엑셀이 기동되는지 확인.
