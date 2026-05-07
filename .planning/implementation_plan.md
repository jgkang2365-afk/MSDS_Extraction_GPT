# [MES 측정대상 자동 매핑 및 1% 필터링] Implementation Plan (Final v3)

> **Target Version:** Engine v18.0.0.0 / GUI v3.0.0.0
> **For Antigravity:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 1% 농도 필터링, Section 15 법적 명칭 기반 다중 매핑, 분자량 기반 TWA 정밀 비교를 통해 MES 측정대상을 자동 확정함.

---

### Task 0: 버전 업그레이드 및 환경 준비
- [ ] `msds_engine_v5.py`: `VERSION = "18.0.0.0"` 업데이트.
- [ ] `smu_gui.py`: `v3.0 - Enterprise Intelligence` 표기 업데이트.
- [ ] 기존 파일 백업 생성 (`.bak`).

### Task 1: 농도 판정 및 다중 CAS 분리 엔진 고도화
**Files:** `msds_engine_v5.py`
- [ ] `is_measurement_target(content_str)` 구현 (1.0% 미만 제외 로직).
- [ ] 성분 파편화 (CAS Splitting): 한 행의 다중 CAS를 개별 매핑 큐로 분리.

### Task 2: KOSHA Section 15 다중 물질명 파싱
**Files:** `kosha_client.py`
- [ ] `get_substance_legal_info(cas_no)`:
    - Section 15: `작업환경측정대상물질` 괄호 내 **모든 명칭 리스트** 추출 기능 추가.

### Task 3: 정밀 매핑 엔진 (분자량 환산 + 점수제)
**Files:** `msds_engine_v5.py`
- [ ] **TWA 단위 환산**: 분자량(MW) 정보를 활용하여 ppm -> mg/m³ 정밀 변환.
- [ ] **1:N 매핑 엔진**: Section 15 리스트를 순회하며 마스터 DB와 대조하여 복수 매핑 허용.
- [ ] `이산화티타늄; 기타광물성분진` 형태의 최종 결과 조합.

### Task 4: [GUI] 지연 리뷰 및 일괄 확정 UI 구현
**Files:** `smu_gui.py`
- [ ] 전체 분석 종료 후, 모호한 매핑 건들을 한눈에 보여주고 사용자가 선택하는 다이얼로그 구현.

---

### Task 5: 통합 검증 및 사후 분석 (FTF Protocol)
- [ ] **Forest (사전 분석)**: 전체 아키텍처 영향도 평가.
- [ ] **Tree (정밀 수정)**: 위 Task별 코드 수정 집행.
- [ ] **Forest (사후 검증)**: 금홍석(1317-80-2) 등 복합 사례 최종 테스트.
