# TRD: Spatial Anchor Scoring (SAS) 아키텍처

## 1. 시스템 아키텍처
시스템은 데이터 추출 레이어, 공간 분석 레이어, 시맨틱 검증 레이어의 3단계로 구성됨.

### A. 데이터 추출 레이어 (Extraction Layer)
- **Library**: PyMuPDF (`fitz`)
- **Method**: `page.get_text("dict")` 호출을 통해 텍스트 블록(Block), 라인(Line), 스판(Span)의 bbox 정보 획득.

### B. 공간 분석 레이어 (Analysis Layer - SAS 엔진)
- **앵커 정의**: `patterns.json`의 `PRODUCT_NAME_KEYS`를 정규식으로 매칭하여 기준 좌표($X_a, Y_a$) 설정.
- **스코어링 알고리즘 ($S$)**:
  $$S = (W_{align} \times A) - (W_{dist} \times D)$$
  - $A$ (Alignment): 앵커의 $x0$와 후보의 $x0$ 차이가 적을수록(수직 정렬) 가산점 부여.
  - $D$ (Distance): 앵커 하단 끝($y1$)과 후보 상단($y0$)의 물리적 거리 감점.
- **필터링**: 텍스트 높이(Font Size)가 너무 작거나, 숫자/특수기호로만 구성된 블록은 1차 제외.

### C. 시맨틱 검증 레이어 (Verification Layer - Ollama) [Optional]
> Phase 1·2(SAS)만으로 정확도가 충분할 경우 생략 가능한 선택적 확장 모듈.

- **Model**: Llama 3.2 3B (또는 사양에 따라 Phi-3 mini)
- **Workflow**: SAS 점수 상위 3개 후보군을 프롬프트에 삽입.
- **Prompt**: "다음 3개 후보 중 MSDS의 '제품 이름'에 해당하는 것을 하나만 골라라. 설명 없이 결과만 출력하라."

## 2. 레거시 로직 통합 계획 (Self-Review Checklist)
새로운 SAS 규칙 적용 시, 이전 단계에서 성공한 아래 세부 규칙들을 반드시 보존함:
- **is_valid_cas**: 체크디지트 기반의 엄격한 CAS 유효성 검사.
- **normalize_text**: NFKC 정규화 및 전각/반각 문자 통일.
- **format_content**: 함유량 범위(~) 및 기호(<, >) 정규화.
- **2단 폴백 탐색**: Section 1(Identification) 우선 탐색 후 실패 시 상단 3500자 광역 탐색.

## 3. 예외 처리 (Edge Cases)
- **앵커 미발견 시**: 기존 윈도우 탐색 모드로 자동 전환(Fallback).
- **멀티 앵커 발생**: 가장 좌상단에 위치한 앵커를 우선 순위로 설정.
