# MSDS 3종 Scanned 자재 Lite 모델 정합성 종합 검증 보고서

- **검증 대상 모델**: `gemini-2.5-flash-lite` (대조군: `gemini-2.5-flash`)
- **검증 대상 자재**: 3종 scanned 자재 (005, 037, 046)

## 1. 모델별 정합성 비교 대조표

| 자재 ID | 평가 항목 | 골든 정답 원장 | Gemini 2.5 Flash | Gemini 2.5 Flash Lite | Lite 판정 (PASS/FAIL) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **005** | 제품명 | `Super Way Lube 32` | `Super Way Lube 32` | `Super Way Lube 32` | 🟢 PASS |
| **005** | 구성성분 | `64742-54-7(>97%); 68649-42-3(<2%)` | `64742-54-7(>97%); 68649-42-3(<2%)` | `64742-54-7(미기재%); 68649-42-3(미기재%)` | 🔴 FAIL |
| **037** | 제품명 | `SODIUM CACODYLATE BUFFER 0.2M, pH 7.4` | `SODIUM CACODYLATE BUFFER 0.2M, pH 7.4` | `SODIUM CACODYLATE BUFFER 0.2M, pH 7.4` | 🟢 PASS |
| **037** | 구성성분 | `124-65-2(2.5~10%)` | `124-65-2(2.5~10%)` | `124-65-2(2~5%)` | 🔴 FAIL |
| **046** | 제품명 | `테트라하이드로퓨란 250ppm BHT[Tetrahydrofuran Stabilized with 250ppm BHT]` | `테트라하이드로퓨란 250ppm BHT[Tetrahydrofuran Stabilized with 250ppm BHT]` | `테트라하이드로퓨란 250ppm BHT[Tetrahydrofuran Stabilized with 250ppm BHT]` | 🟢 PASS |
| **046** | 구성성분 | `109-99-9(99~100%); 7732-18-5(0~1%); 128-37-0(0.025%)` | `109-99-9(99~100%); 7732-18-5(0~1%); 128-37-0(0.025%)` | `109-99-9(미기재%)` | 🔴 FAIL |

## 3. 종합 검증 요약
- **제품명 부문 합격률**: 3/3 (100.0%)
- **구성성분 부문 합격률**: 0/3 (0.0%)
- **전체 종합 합격률**: 3/6 (50.0%)

## 2. 자재별 세부 대조 내역 및 오독 분석

### [자재 005] 005_★SUPER WAY LUBE 32.pdf
- **제품명 비교**:
  - 골든 원장 정답: `Super Way Lube 32`
  - Gemini 2.5 Flash: `Super Way Lube 32`
  - Gemini 2.5 Flash Lite: `Super Way Lube 32`
  - **제품명 판정 결과**: 🟢 PASS (일치)
- **구성성분 비교 (CAS 및 함량)**:
  - 골든 원장 정답: `64742-54-7(>97%); 68649-42-3(<2%)`
  - Gemini 2.5 Flash: `64742-54-7(>97%); 68649-42-3(<2%)`
  - Gemini 2.5 Flash Lite: `64742-54-7(미기재%); 68649-42-3(미기재%)`
  - **성분 판정 결과**: 🔴 FAIL (불일치 - 사유: Lite 모델의 함량 수치/부등호 오독 또는 CAS 번호 환각 및 누락)

### [자재 037] 037_Sodium Cacodylate Buffer, 0.2M, pH 7.4.pdf
- **제품명 비교**:
  - 골든 원장 정답: `SODIUM CACODYLATE BUFFER 0.2M, pH 7.4`
  - Gemini 2.5 Flash: `SODIUM CACODYLATE BUFFER 0.2M, pH 7.4`
  - Gemini 2.5 Flash Lite: `SODIUM CACODYLATE BUFFER 0.2M, pH 7.4`
  - **제품명 판정 결과**: 🟢 PASS (일치)
- **구성성분 비교 (CAS 및 함량)**:
  - 골든 원장 정답: `124-65-2(2.5~10%)`
  - Gemini 2.5 Flash: `124-65-2(2.5~10%)`
  - Gemini 2.5 Flash Lite: `124-65-2(2~5%)`
  - **성분 판정 결과**: 🔴 FAIL (불일치 - 사유: Lite 모델의 함량 수치/부등호 오독 또는 CAS 번호 환각 및 누락)

### [자재 046] 046_★THF_MSDS.pdf
- **제품명 비교**:
  - 골든 원장 정답: `테트라하이드로퓨란 250ppm BHT[Tetrahydrofuran Stabilized with 250ppm BHT]`
  - Gemini 2.5 Flash: `테트라하이드로퓨란 250ppm BHT[Tetrahydrofuran Stabilized with 250ppm BHT]`
  - Gemini 2.5 Flash Lite: `테트라하이드로퓨란 250ppm BHT[Tetrahydrofuran Stabilized with 250ppm BHT]`
  - **제품명 판정 결과**: 🟢 PASS (일치)
- **구성성분 비교 (CAS 및 함량)**:
  - 골든 원장 정답: `109-99-9(99~100%); 7732-18-5(0~1%); 128-37-0(0.025%)`
  - Gemini 2.5 Flash: `109-99-9(99~100%); 7732-18-5(0~1%); 128-37-0(0.025%)`
  - Gemini 2.5 Flash Lite: `109-99-9(미기재%)`
  - **성분 판정 결과**: 🔴 FAIL (불일치 - 사유: Lite 모델의 함량 수치/부등호 오독 또는 CAS 번호 환각 및 누락)