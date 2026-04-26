# [GSD Spec] smu_gui.py ExtractionWorker AI 재시도 조건에 수동 입력(manual_data) 방어막 추가

## 1. 개요
`ExtractionWorker.run` 로직에서 AI 추출 실패 건에 대한 자동 재시도 기능을 수행할 때, 사용자가 이미 수동으로 수정한 데이터(`manual_data`)가 존재한다면 AI 재시도를 수행하지 않고 수동 수정본을 최우선으로 로드하도록 보강한다.

## 2. 변경 사항
### smu_gui.py
#### 1) `ExtractionWorker.run` (약 387-413행 부근)
- 캐시 체크 로직 수정: `manual_data` 존재 여부를 먼저 확인.
- `if not manual and (실패 조건)` 인 경우에만 AI 재시도 수행.
- 수동 데이터가 있거나 성공적인 캐시인 경우, 기존 V11.6 로직에 따라 최우선 로드 수행.

## 3. 상세 구현 계획
1. `smu_gui.py`의 `ExtractionWorker.run` 내 캐시 체크 블록(`if f_hash and ... in self.cache:`)을 찾는다.
2. 사용자 지시서에서 제공한 `V11.7` 통합 로직으로 해당 블록을 전면 교체한다.
3. 들여쓰기와 기존 로직 흐름(continue 등)이 깨지지 않도록 정밀하게 교체한다.

## 4. 검증 계획
- `python -m py_compile smu_gui.py` 실행을 통한 문법 검증.
- '제품명 확인 필요' 상태이더라도 수동 수정 데이터가 있다면 AI 재추출 없이 수동 데이터가 로드되는지 확인.
