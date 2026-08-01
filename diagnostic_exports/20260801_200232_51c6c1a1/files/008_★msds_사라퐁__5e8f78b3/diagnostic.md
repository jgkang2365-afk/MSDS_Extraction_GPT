# MSDS Diagnostic Trace

## 문서 요약

- run_id: `20260801_200232_51c6c1a1`
- file_trace_id: `5e8f78b3fd6689ce1618ef34`
- source: <repo>/TEST_File/008_★msds_사라퐁.pdf
- mode: `SUMMARY`

## 최종 결과

```json
{"status": "completed", "제품명": "사라퐁", "구성성분": "7732-18-5(60~70%); 1310-73-2(>3%)", "함유량": "7732-18-5(60~70%); 1310-73-2(>3%)", "신호등": "🟢", "used_engine": "analytic", "document_type": "text", "product_name_source": "ai", "local_text_candidate": "", "verification_status": "unverified", "cas_candidates": [], "content_matching_complete": true, "error_code": "", "last_completed_stage": ""}
```

## 실행 단계 (시간순)

- stage_start `msds_pipeline` (0.0 ms) — {"module": "msds_engine_v6", "function": "process_msds_pipeline", "engine": "MSDSEngineV6", "input_summary": {"file_path": "<repo>/TEST_File/008_★msds_사라퐁.pdf"}}
- stage_result `msds_pipeline` (7360.0 ms) — {"status": "success", "output_summary": {"used_engine": "analytic"}, "candidate_count": 2, "elapsed_ms": 7356.458}

## 엔진별 결과

- engine_isolation_started: {"document_type": "text", "timeout_seconds": 180.0}
- engine_child_started: {"file_path": "<repo>/TEST_File/008_★msds_사라퐁.pdf"}
- stage_start: {"module": "msds_engine_v6", "function": "process_msds_pipeline", "engine": "MSDSEngineV6", "input_summary": {"file_path": "<repo>/TEST_File/008_★msds_사라퐁.pdf"}}
- pymupdf.text_source: {"page_number": 1, "block_count": 33, "word_count": 116}
- section3.page_search: {"page_indexes": [1, 2, 3], "document_pages": 7}
- pymupdf.text_source: {"page_number": 2, "block_count": 32, "word_count": 149}
- pymupdf.text_source: {"page_number": 3, "block_count": 32, "word_count": 72}
- pymupdf.text_source: {"page_number": 4, "block_count": 35, "word_count": 110}
- section3.text_source_result: {"engine": "PyMuPDF blocks", "page_indexes": [1, 2, 3], "page_numbers": [2, 3, 4], "character_count": 2232, "raw_text": null, "status": "success"}
- section3.selection: {"page_indexes": [1, 2, 3], "image_count": 3, "text_length": 2232, "recon_used": false}
- pymupdf.text_source: {"page_number": 1, "block_count": 33, "word_count": 116}
- pymupdf.text_source: {"page_number": 2, "block_count": 32, "word_count": 149}
- pymupdf.text_source: {"page_number": 3, "block_count": 32, "word_count": 72}
- pymupdf.text_source: {"page_number": 4, "block_count": 35, "word_count": 110}
- pymupdf.text_source: {"page_number": 5, "block_count": 34, "word_count": 106}
- pymupdf.text_source: {"page_number": 6, "block_count": 32, "word_count": 104}
- pymupdf.text_source: {"page_number": 7, "block_count": 24, "word_count": 88}
- ai.input: {"purpose": "product_name", "requested_model": "gemini-2.5-flash", "input_mode": "text", "text_length": 1596, "image_count": 0, "max_retries": 2}
- ai.call.start: {"provider": "deepseek", "model": "deepseek/deepseek-v4-flash", "purpose": "product_name", "input_mode": "text", "attempt_number": 1}
- ai.call.response: {"provider": "deepseek", "model": "deepseek/deepseek-v4-flash", "purpose": "product_name", "response_text_length": 3, "provider_response_returned": true, "json_parse_succeeded": false, "raw_response": null, "product_name_harvested": true, …
- candidate_registered: {"derived_from": null, "value": "사라퐁", "source": "ai_product_name_response", "field": "product_name", "engine": "deepseek"}
- ai.result_application: {"purpose": "product_name", "applied_fields": ["product_name"], "applied": true, "discard_reason": ""}
- engine_checkpoint: {"checkpoint_stage": "ai_response_complete", "next_stage": "product_name_verification"}
- engine_checkpoint: {"checkpoint_stage": "product_name_complete", "next_stage": "section3_recon"}
- pymupdf.text_source: {"page_number": 2, "block_count": 32, "word_count": 149}
- pymupdf.text_source: {"page_number": 3, "block_count": 32, "word_count": 72}
- pymupdf.text_source: {"page_number": 4, "block_count": 35, "word_count": 110}
- candidate_registered: {"derived_from": null, "value": {"cas": "7732-18-5", "content": "60~70%"}, "source": "refine_msds_components_strict", "engine": "Regex-Recovery", "page": ""}
- candidate_registered: {"derived_from": null, "value": {"cas": "1310-73-2", "content": ">3%"}, "source": "refine_msds_components_strict", "engine": "Regex-Recovery", "page": ""}
- section3.local_branch: {"candidate_count": 2, "perfect": false, "invalid_cas": false, "integrity_valid": true}
- pymupdf.text_source: {"page_number": 2, "block_count": 32, "word_count": 149}
- pymupdf.text_source: {"page_number": 3, "block_count": 32, "word_count": 72}
- pymupdf.text_source: {"page_number": 4, "block_count": 35, "word_count": 110}
- engine_checkpoint: {"checkpoint_stage": "cas_candidates_complete", "next_stage": "cas_content_pairing"}
- engine_checkpoint: {"checkpoint_stage": "cas_content_matching_complete", "next_stage": "finalize"}
- engine_child_completed: {}
- engine_isolation_completed: {}

## 후보 변화

- `candidate-001` ← `source`
- `candidate-002` ← `source`
- `candidate-003` ← `source`
- `candidate-004` ← `candidate-001`
- `candidate-005` ← `source`
- `candidate-006` ← `source`
- `candidate-007` ← `candidate-004`
- 변환: 11 / 탈락: 0 / 병합: 1 / 수동 재정의: 0

## 이미지 분석

- 저장된 이미지 없음

## 최종 원인

최초 실패 지점: 없음
직접 실패 원인: 없음
후속 우회 경로: 해당 없음
우회 경로 실패 원인: 해당 없음
최종 결과에 미친 영향: 없음
권장 확인 지점: 해당 없음
