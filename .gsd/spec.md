# [GSD2] V15.8.7 Final Evolution: Intelligent Cell Division & Omission Control

## 1. 개요
MSDS 엔진 V15.8.7의 최종 완성 단계로, 한 셀에 다수의 CAS 번호가 포함된 경우 이를 지능적으로 분리(Cell Division)하여 데이터 유실을 방지하고, 누락 탐지기(Omission Detector)를 통해 데이터의 완전성을 검증합니다.

## 2. 핵심 변경 사항 (FTF 프로토콜)

### [Forest] 사전 분석
- **대상**: `msds_engine_v5.py` 내 `final_quality_control` 함수.
- **현상**: `re.search` 기반의 단일 CAS 추출 로직으로 인해 다중 CAS 데이터가 유실됨.
- **목표**: `re.findall`을 통한 다중 행 복제 및 누락 방지 로직 완성.

### [Tree] 정밀 수정 단계

#### 🛠️ 미션 1: 지능형 다중 CAS 분리 엔진 구현
- `final_quality_control` 루프 내에서 `re.findall(r'(\d{1,7}-\d{2}-\d)', cas_raw)` 사용.
- 발견된 모든 CAS에 대해 `refined.append({"cas": cas, "content": content})` 실행.
- 함유량 정제 로직을 CAS 추출 이전 또는 공통 영역으로 이동하여 효율화.

#### 🛠️ 미션 2: 누락 탐지기(Omission Detector) 연결
- `check_omission` 함수가 분리된 행 개수를 정확히 인식하도록 파라미터 조정.
- 누락 발생 시 `has_invalid = True`를 통해 GUI에 황색불 신호 전달.

#### 🛠️ 미션 3: 불필요한 레거시 주석 제거 및 버전 유지
- 기존 `V15.8.7`의 정체성을 유지하며 코드 안정성 확보.

### [Forest] 사후 검증
- 다중 CAS가 포함된 테스트 데이터로 행 분리 여부 확인.
- `check_omission`이 의도대로 작동하여 누락 시 경고를 띄우는지 확인.

## 3. 성공 기준 (UAT)
1. 한 셀에 `CAS1 / CAS2`가 있을 때, 결과 리스트에 2개의 성분이 각각 나타남.
2. 원본 PDF의 CAS 개수보다 추출된 CAS 개수가 적을 경우 GUI에 로그와 함께 🟡 표시됨.
3. 부등호(`≤`, `<`, `~`) 및 `Rem.%` 등 특수 포맷이 깨지지 않고 보존됨.
