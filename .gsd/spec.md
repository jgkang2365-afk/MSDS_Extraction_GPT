# [GSD Spec] smu_gui.py 논리적 매칭 탭 '초록불 일괄 자동 학습' 기능 추가 (V11.9)

## 1. 개요
매칭 탭(`LogicMatchTab`)에서 신뢰도가 높은(초록불, 🟢) 항목들을 하나씩 수동으로 확정하지 않고, 버튼 하나로 일괄적으로 지식 DB(`msds_knowledge.db`)에 학습시키고 매칭을 확정하는 기능을 추가한다.

## 2. 변경 사항
### smu_gui.py
#### 1) 매칭 탭 UI 레이아웃 (약 1430행 부근)
- `self.btn_batch_confirm = QPushButton("🟢 초록불 일괄 자동 학습")` 버튼 추가.
- 스타일: `background-color: #007bff; color: white; font-weight: bold; padding: 8px; margin-left: 10px;`
- 기존 `btn_confirm`과 수평으로 배치하기 위해 `QHBoxLayout` 도입 또는 레이아웃에 추가.

#### 2) `batch_auto_confirm` 메서드 추가
- `match_table`의 모든 행을 순회.
- 0번 컬럼(신뢰도)이 "🟢"인 경우:
    - PDF 제품명, 매칭 엑셀 항목, 바인딩 데이터를 수집.
    - 메인 테이블(`self.table`)에서 해당 제품명의 최신 추출 데이터(CAS, 규제 정보 등)를 조회.
    - `self.km.update_experience` 및 `self.save_db_knowledge`를 호출하여 DB 기록.
    - `match_table`의 UI 상태(아이콘, 유사도, 배경색 등) 업데이트.
- 작업 완료 후 "총 N건의 초록불 데이터가 지식 DB에 일괄 학습되었습니다!" 메시지 출력.

## 3. 상세 구현 계획
1. 매칭 탭의 버튼 생성부에서 새 버튼을 정의하고 `batch_auto_confirm`에 연결한다.
2. `batch_auto_confirm` 로직은 기존 `confirm_manual_match`의 핵심 저장 로직을 루프 내에서 수행하도록 구현하되, 팝업은 최소화한다.

## 4. 검증 계획
- `python -m py_compile smu_gui.py` 실행을 통한 문법 검증.
- 매칭 결과에 초록불이 있는 상태에서 버튼 클릭 시, 로그가 출력되고 DB에 정상 저장되는지 확인.
- 최종 완료 팝업이 한 번만 뜨는지 확인.
