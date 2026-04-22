# MSDS Extraction Engine - Version History

이 문서는 MSDS 추출 엔진의 버전별 업데이트 내역과 주요 개선 사항을 추적합니다.

---

## [v4.0_Zero-Touch] - 2026-03-23
### 🎯 무결점 자동화 (Final Architect v4.0)
- **[Visual Context Builder]** 앵커 주변 300px 내의 텍스트를 좌표 기반으로 구조화하여 LLM이 실제 문서의 시각적 형태(표 구조 등)를 그대로 이해하도록 전달.
- **[Confidence Engine]** 추출된 성분의 CAS 유효성, 함유량 상한(100%), 중복 여부를 Python 레이어에서 2차 검증하여 `[PASS]` 또는 `[REVIEW]` 태그 자동 부여.
- **[Structured LLM Inference]** Llama 3.2 3B 모델에 JSON Schema를 강제 적용하여 제품명, 성분, **추론 근거(Reasoning)**를 일괄 획득.
- **[Regression Shield]** 100% 초과 수치 및 단위 미기재 대형 숫자 차단 로직(Value Guard)을 `msds_utils_v3`로 격리 강화.

## [v3.3_하이브리드] - 2026-03-23

## [v3.2_하이브리드] - 2026-03-23
### 🚀 초정밀 고도화 (Senior Architect V3.2)
- **[Value Guard]** 함유량 수치 폭주 방지 및 단위 정밀 판독 시스템 도입.
- **[SAS v3.2 Tuning]** 수평 오차(dx) 페널티 강화(x40)로 표 외부 데이터 오추출 차단.
- **[Ollama Resilience]** LLM 검증 타임아웃 20초 확장으로 응답 안정성 확보.

---

## [v3.1_하이브리드] - 2026-03-23

---

## [v3.0_하이브리드] - 2026-03-22
### ✨ 기능 추가
- **하이브리드 엔진 통합**: Fast Text 추출과 PaddleOCR 기반 정밀 추출을 결합한 하이브리드 로직 도입.
- **PBSS (Pattern Based Space Slicing)**: 패턴 기반 공간 분할을 통한 제품명 앵커 탐색 기능 구현.
- **Ollama 연동**: 로컬 LLM(llama3.2)을 활용한 최종 제품명 시맨틱 검증 레이어 추가.

---

## [v2.x] - 이전 버전
- **공간 자물쇠(Spatial Lock)** 도입: CAS 번호와 함유량의 물리적 위치 기반 매칭.
- **체크디지트 검증**: CAS 번호 유효성 검증 로직 구현.
- **Gear 1/2 시스템**: 라인 기반 매칭(Gear 1)과 윈도우 기반 매칭(Gear 2)의 단계적 탐색.
