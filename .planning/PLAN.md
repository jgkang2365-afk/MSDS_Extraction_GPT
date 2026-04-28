# Implementation Plan: V15.0 Vision-Only Architecture

## Phase 1: Engine Core Cleanup & Section 3 Detection
- [ ] `msds_engine_v5.py`: `find_section3_pages` 함수 구현 (텍스트 기반 정밀 탐지)
- [ ] `msds_engine_v5.py`: `extract_table_images` 해상도 상향 (2.5x) 및 폴백 로직 제거
- [ ] `msds_engine_v5.py`: `run_v24_baseline` 호출부 제거 및 관련 코드 정리

## Phase 2: Pipeline Simplification
- [ ] `msds_engine_v5.py`: `process_pdf`에서 텍스트 페이로드(`text_chunk`) 제거
- [ ] `msds_engine_v5.py`: AI 호출 함수(`call_gemini_2_5_lite`, `call_gpt_4o_mini`)에서 텍스트 파라미터 제거
- [ ] `msds_engine_v5.py`: `extract_product_name_hybrid`를 통한 제품명 확정 로직 강화

## Phase 3: Post-processing & Validation Reform
- [ ] `msds_engine_v5.py`: `minimal_clean` 함수 구현 및 기존 `format_content_v3` 대체
- [ ] `msds_engine_v5.py`: `validate_components` 수정 (부분 폐기 원칙 적용)
- [ ] `msds_engine_v5.py`: 최종 결과 JSON 구성 및 "시각_분석_로그" 포함

## Phase 4: Final Verification
- [ ] 테스트 스크립트 실행 및 Section 3 미탐지 시 예외 처리 확인
- [ ] GUI 연동 테스트 (이미지 기반 추출 결과가 정상적으로 테이블에 기입되는지 확인)
