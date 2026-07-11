# MSDS Extraction Cleanroom

기존 프로젝트를 삭제하거나 이동하지 않고, 현행 V6 실행선과 승인된 골든 회귀 자산만 복사한 작업 폴더입니다.

## 현재 실행선

```text
smu_gui.py
  -> msds_core.py
    -> msds_engine_v6.py
      -> msds_utils_v3.py
```

## 포함 범위

- 현행 GUI, 코어, V6 엔진, 공통 유틸리티
- KOSHA 및 노출기준 조회 모듈
- 제품명/구성성분 프롬프트
- MES 및 MSDS 인덱스 데이터
- 로컬 OpenDataLoader 브리지
- 승인 상태의 골든 데이터 13건과 대응 PDF 13개
- 로컬 실행용 `.env`, `vertex_key.json` (Git 제외 대상)

## 의도적으로 제외한 항목

- 기존 `config.json`, `smu_cache.json`
- `msds_engine_v5.py`
- `archive`, `scratch`, `.planning`, `.gsd`, `diary`
- 과거 테스트 스크립트와 실행 보고서
- `__pycache__` 및 생성 로그

캐시와 설정은 새 실행 환경에서 다시 생성해야 합니다. 과거 캐시를 복사하면 잘못된 결과가 재사용될 수 있습니다.

## 골든 기준

- 파일: `golden/msds_golden_v1.json`
- 검토 상태: `approved`
- 문서: 13개
- 유효 CAS 정답: 58개
- 파일명에 `★`가 붙은 난제 PDF: 전부 포함

## 골든 회귀 하네스

데이터셋 구조, 필수 `★` PDF 포함 여부, 원본 SHA-256을 외부 API 호출 없이 검사합니다.

```powershell
python tools/golden_regression.py
python -m unittest discover -s tests -v
```

패키지 설치가 끝난 뒤 실제 엔진 결과를 비교할 때만 `--run-engine`을 사용합니다. 이 모드는 외부 AI API를 호출할 수 있습니다.

```powershell
python tools/golden_regression.py --run-engine --case 008 --save-results reports/golden_008.json
python tools/golden_regression.py --results reports/golden_008.json --case 008
```

## Python 환경

검증된 기준은 Python 3.12이며, `requirements.txt`는 cleanroom에서 실제 설치·검증한 전체 의존성 잠금 파일입니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\golden_regression.py
```

## 아직 필요한 작업

1. 골든 회귀 보고서의 4개 엔진 수정 명세 사용자 승인
2. 승인 후 015, 032, 040, 047 회귀 수정
3. 골든 13건 전수 재검증 및 13/13 통과
4. 현행 사양의 미결 정책 확정

현재 회귀 상태와 수정 제안은 reports/GOLDEN_REGRESSION_2026-07-10.md에 기록되어 있습니다.
다음 구현 순서와 검증 게이트는 docs/NEXT_IMPLEMENTATION_PLAN.md를 따릅니다.

## 프로젝트 문서

- docs/PROJECT_DIRECTION.md: 프로젝트 목표, 성공 기준, 단계별 로드맵
- docs/CURRENT_SPEC_DRAFT.md: 현재 확정 범위와 미결 정책
- docs/NEXT_IMPLEMENTATION_PLAN.md: 다음 엔진 수정의 실행 계획
- docs/DECISION_LOG.md: 정책 결정 기록
- docs/RELEASE_CHECKLIST.md: 배포 전 검증 기준
- reports/GOLDEN_REGRESSION_2026-07-10.md: 현재 회귀 증거

이 폴더가 검증되기 전까지 기존 프로젝트 폴더는 원본 보관소로 유지합니다.
