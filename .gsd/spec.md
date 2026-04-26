# Specification: MSDS API & Logic Refinement (Final Patch)

## 1. 개요 (Overview)
`msds_engine_v5.py` 내의 하급 오류(환경변수 모순, 가변 객체 기본값, API 규격 불일치)를 일괄 정리하여 시스템 안정성을 확보합니다.

## 2. 변경 사항 (Changes)

### 2.1 환경변수 모순 해결
- `GOOGLE_API_KEY` 로드 시 키값을 `MSDS_GOOGLE_API_KEY`로 변경하여 `.env` 파일과 동기화.

### 2.2 가변 객체 기본값(Mutable Default) 수정
- `call_gemini_2_5_lite` 및 `call_gpt_4o_mini` 함수의 `image_list=[]` 파라미터를 `image_list=None`으로 수정.
- 함수 내부 상단에 `if image_list is None: image_list = []` 안전 로직 추가.

### 2.3 Gemini REST API 규격 준수 (CamelCase)
- `call_gemini_2_5_lite` 내 페이로드의 `inline_data` -> `inlineData`, `mime_type` -> `mimeType`으로 수정.

## 3. 상세 구현 계획 (Implementation Plan)

### Phase 1: Tree 수정 (Surgical Edits)
- [x] `msds_engine_v5.py` Line 20 수정.
- [x] `msds_engine_v5.py` Line 450-468 수정 (`call_gemini_2_5_lite`).
- [x] `msds_engine_v5.py` Line 492-495 수정 (`call_gpt_4o_mini`).

### Phase 2: Forest 사후 검증
- [x] 문법 오류 확인 (Python compile check).
- [x] 기존 V24 로직 및 Vision Fallback 로직 훼손 여부 최종 확인.

## 4. 사용자 승인 요청
위의 3가지 핵심 수정 사항을 즉시 반영해도 될까요?
