# [V5 엔진 통합 및 정규화]

두 개의 폴더(v24 코어 + GUI 통합본)를 합치는 과정에서 발생한 엔진 버전 혼선을 정리하고, 주님의 지시대로 **V5 버전을 메인**으로 확정합니다.

## User Review Required

> [!IMPORTANT]
> - `msds_engine_v6.py`, `msds_engine_v7.py` 및 관련 v7 수정 스크립트들을 삭제합니다.
> - `smu_gui.py`와 `msds_core.py`가 모두 `msds_engine_v5.py`를 바라보도록 강제합니다.

## Proposed Changes

### [MODIFY] [msds_core.py](file:///c:/Users/USER/Desktop/%EC%95%88%ED%8B%B0%EA%B7%B8%EB%9E%98%ED%8B%B0%EB%B9%84/MSDS_EXtaction_V3%28v24+GUI%ED%86%B5%ED%95%A9%29/msds_core.py)
- `import msds_engine_v6` -> `import msds_engine_v5` 수정
- `extract_from_pdf` 함수 내 호출부를 `msds_engine_v5.process_pdf`로 변경

### [MODIFY] [smu_gui.py](file:///c:/Users/USER/Desktop/%EC%95%88%ED%8B%B0%EA%B7%B8%EB%9E%98%ED%8B%B0%EB%B9%84/MSDS_EXtaction_V3%28v24+GUI%ED%86%B5%ED%95%A9%29/smu_gui.py)
- `import msds_engine_v7 as engine` -> `import msds_engine_v5 as engine` 수정
- `engine.analyze_msds` 호출부를 `engine.process_pdf`로 변경

### [MODIFY] [msds_engine_v5.py](file:///c:/Users/USER/Desktop/%EC%95%88%ED%8B%B0%EA%B7%B8%EB%9E%98%ED%8B%B0%EB%B9%84/MSDS_EXtaction_V3%28v24+GUI%ED%86%B5%ED%95%A9%29/msds_engine_v5.py)
- GUI와의 호환성을 위해 파일 끝에 `analyze_msds = process_pdf` 별칭 추가

### [DELETE] 불필요한 쓰레기 파일
- `msds_engine_v6.py`, `msds_engine_v7.py` 등 v6/v7 관련 파일 삭제

## Verification Plan

### Automated Tests
- `python test_v5.py` 실행하여 엔진 기본 동작 확인

### Manual Verification
- `python smu_gui.py` 실행하여 GUI에서 PDF 드랍 후 추출 기능이 V5 엔진으로 정상 작동하는지 확인
