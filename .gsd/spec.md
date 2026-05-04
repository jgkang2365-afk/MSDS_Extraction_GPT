# [Plan] Kosha API 조회 오류 (AttributeError) 긴급 해결

## 1. 개요
`msds_engine_v5.py`에 `MES_MASTER_MAP` 속성이 누락되어 Step 2 검증 시 발생하는 `AttributeError`를 해결하고, 환경 변수 파일(`.env`)의 형식을 정문화합니다.

## 2. 작업 상세 (Tree)

### 2.1 msds_engine_v5.py 수정
- `MES_MASTER_MAP` 변수 선언 및 `MES_MASTER_LOOKUP.json` 기반 초기화 로직 추가.
- 엔진의 독립성을 위해 파일 부재 시에도 프로세스가 중단되지 않도록 예외 처리 적용.

### 2.2 .env 파일 수정
- `SERVICE_KEY` 및 `BASE_URL` 할당문의 불필요한 공백 제거.

## 3. 검증 계획 (Forest)
- `msds_engine_v5.py`를 직접 실행하여 `MES_MASTER_MAP`이 정상적으로 구축되는지 확인.
- `smu_gui.py` 재실행 후 Step 2(API 검증) 단계에서 동일한 `AttributeError`가 발생하지 않는지 확인.

## 4. 추가 제언 (승인 범위 외)
- `유해인자_MES.txt` 파일이 누락되어 있습니다. 해당 파일 확보 시 마스터 데이터셋 기능을 온전히 사용할 수 있습니다.
