# Implementation Plan: V15.8.7 Heart Surgery (Sniper Sync)

## Phase 1: Heart Surgery (msds_engine_v5.py)
- [ ] `process_pdf` 내 스나이퍼 호출 지점 3개소 수정
    - [ ] 1. `extract_section3_images` 전
    - [ ] 2. `extract_product_name_hybrid` 전
    - [ ] 3. `call_gemini_2_5_flash` 전 (재확인)

## Phase 2: Verification
- [ ] `py_compile msds_engine_v5.py`
- [ ] 런타임 변수 충돌 여부 확인
