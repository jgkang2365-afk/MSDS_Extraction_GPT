# [GSD Spec] msds_engine_v5.py 하이브리드 AI 듀얼 엔진 (V12.0)

## 1. 개요
추출 정확도 향상 및 비용 최적화를 위해 Gemini 2.5 Flash-Lite를 기본 엔진(1차)으로 사용하고, 실패 시 GPT-4o-mini(2차)로 자동 전환되는 2단계 앙상블 파이프라인을 구축한다.

## 2. 변경 사항
### msds_engine_v5.py
#### 1) 환경 변수 및 모델 설정
- `GOOGLE_API_KEY` 로드.
- `GEMINI_API_URL` 상수 정의 (v1beta 규격).

#### 2) `call_gemini_2_5_lite` 함수 신설
- Google AI API (Contents/Parts) 규격을 준수하여 구현.
- `temperature: 0.0`, `response_mime_type: "application/json"` 적용.
- 비전 데이터(이미지) 포함 가능하도록 설계.

#### 3) `process_pdf` 메인 로직 개조
- **1단계**: `call_gemini_2_5_lite` 호출 (최대 2회 자가 치유 시도).
- **검증**: 결과가 성공적이고 CAS 체크섬 오류가 없으면 즉시 반환.
- **2단계 (Fallback)**: Gemini 실패 시 `call_gpt_4o_mini` (기존 `analyze_with_gemini_ensemble`)로 긴급 전환.

#### 4) 로그 및 태그 고도화
- `추론근거`: "Gemini 2.5 Flash-Lite (1차 성공)" 또는 "GPT-4o-mini (2차 Fallback)" 명시.
- `tag`: `[G2.5-PASS]`, `[GPT-FIXED]` 등 엔진 정보 포함.

## 3. 상세 구현 계획
1. 상단 환경 변수 섹션에 `GOOGLE_API_KEY` 및 URL 추가.
2. `call_gemini_2_5_lite` 함수를 `analyze_with_gemini_ensemble` 이전에 추가.
3. `process_pdf` 내부의 `while` 루프 및 엔진 전환 로직 구현.
4. `analyze_with_gemini_ensemble`의 이름을 `call_gpt_4o_mini`로 변경하거나, 내부 호출만 GPT로 유지.

## 4. 검증 계획
- `python -m py_compile msds_engine_v5.py` 실행을 통한 문법 검증.
- 더미 PDF 데이터를 활용하여 1차 엔진 호출 로그 및 2차 전환 로그가 정상적으로 출력되는지 확인.
