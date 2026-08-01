# MSDS Diagnostic Trace

## 문서 요약

- run_id: `20260801_200232_51c6c1a1`
- file_trace_id: `76c6e3f866b15da3caf204c5`
- source: <repo>/TEST_File/051_★금속광택제(피칼)_MSDS.pdf
- mode: `SUMMARY`

## 최종 결과

```json
{"status": "completed", "제품명": "금속광택제튜브타입", "구성성분": "", "함유량": "", "신호등": "🔴", "used_engine": "error_isolation", "document_type": "mixed", "product_name_source": "", "local_text_candidate": "", "verification_status": "", "cas_candidates": [], "content_matching_complete": true, "error_code": "", "last_completed_stage": ""}
```

## 실행 단계 (시간순)

- stage_start `msds_pipeline` (15.0 ms) — {"module": "msds_engine_v6", "function": "process_msds_pipeline", "engine": "MSDSEngineV6", "input_summary": {"file_path": "<repo>/TEST_File/051_★금속광택제(피칼)_MSDS.pdf"}}
- stage_result `msds_pipeline` (78078.0 ms) — {"status": "empty", "output_summary": {"used_engine": "error_isolation"}, "candidate_count": 0, "elapsed_ms": 78072.386}

## 엔진별 결과

- engine_isolation_started: {"document_type": "mixed", "timeout_seconds": 240.0}
- engine_child_started: {"file_path": "<repo>/TEST_File/051_★금속광택제(피칼)_MSDS.pdf"}
- stage_start: {"module": "msds_engine_v6", "function": "process_msds_pipeline", "engine": "MSDSEngineV6", "input_summary": {"file_path": "<repo>/TEST_File/051_★금속광택제(피칼)_MSDS.pdf"}}
- pymupdf.text_source: {"page_number": 1, "block_count": 35, "word_count": 59}
- pymupdf.text_source: {"page_number": 2, "block_count": 39, "word_count": 52}
- pymupdf.text_source: {"page_number": 3, "block_count": 24, "word_count": 42}
- pymupdf.text_source: {"page_number": 4, "block_count": 24, "word_count": 44}
- pymupdf.text_source: {"page_number": 5, "block_count": 31, "word_count": 44}
- pymupdf.text_source: {"page_number": 6, "block_count": 38, "word_count": 52}
- pymupdf.text_source: {"page_number": 7, "block_count": 32, "word_count": 54}
- pymupdf.text_source: {"page_number": 8, "block_count": 30, "word_count": 60}
- pymupdf.text_source: {"page_number": 9, "block_count": 28, "word_count": 41}
- pymupdf.text_source: {"page_number": 10, "block_count": 29, "word_count": 45}
- pymupdf.text_source: {"page_number": 11, "block_count": 28, "word_count": 38}
- pymupdf.text_source: {"page_number": 12, "block_count": 24, "word_count": 41}
- pymupdf.text_source: {"page_number": 13, "block_count": 26, "word_count": 45}
- pymupdf.text_source: {"page_number": 14, "block_count": 30, "word_count": 54}
- pymupdf.text_source: {"page_number": 15, "block_count": 30, "word_count": 48}
- pymupdf.text_source: {"page_number": 16, "block_count": 29, "word_count": 38}
- pymupdf.text_source: {"page_number": 17, "block_count": 24, "word_count": 33}
- pymupdf.text_source: {"page_number": 18, "block_count": 26, "word_count": 35}
- pymupdf.text_source: {"page_number": 19, "block_count": 30, "word_count": 42}
- pymupdf.text_source: {"page_number": 20, "block_count": 30, "word_count": 44}
- pymupdf.text_source: {"page_number": 21, "block_count": 26, "word_count": 46}
- pymupdf.text_source: {"page_number": 22, "block_count": 34, "word_count": 78}
- pymupdf.text_source: {"page_number": 23, "block_count": 24, "word_count": 46}
- section3.page_search: {"page_indexes": [], "document_pages": 23}
- ocr.paddle.start: {"method": "ocr", "purpose": "1~3페이지 3항 정찰 OCR", "page_index": 0, "image_width": 893, "image_height": 1263}
- ocr.paddle.complete: {"page_index": 0, "page_number": 1, "image_width": 893, "image_height": 1263, "purpose": "1~3페이지 3항 정찰 OCR", "method": "ocr", "elapsed_seconds": 21.053819299995666}
- section3.recon_attempt: {"page_index": 0, "render_scale": 1.5, "line_count": 53, "score": 100.0, "accepted": true}
- section3.recon_direct_decision: {"page_index": 0, "bounds": {"y_start": 210.47999572753906, "y_end": 505.1519897460937, "found_heading": false}, "candidate_count": 0, "accepted": false}
- section3.selection: {"page_indexes": [0], "image_count": 1, "text_length": 194, "recon_used": true}
- pymupdf.text_source: {"page_number": 1, "block_count": 35, "word_count": 59}
- pymupdf.text_source: {"page_number": 2, "block_count": 39, "word_count": 52}
- pymupdf.text_source: {"page_number": 3, "block_count": 24, "word_count": 42}
- pymupdf.text_source: {"page_number": 4, "block_count": 24, "word_count": 44}
- pymupdf.text_source: {"page_number": 5, "block_count": 31, "word_count": 44}
- pymupdf.text_source: {"page_number": 6, "block_count": 38, "word_count": 52}
- pymupdf.text_source: {"page_number": 7, "block_count": 32, "word_count": 54}
- pymupdf.text_source: {"page_number": 8, "block_count": 30, "word_count": 60}
- pymupdf.text_source: {"page_number": 9, "block_count": 28, "word_count": 41}
- pymupdf.text_source: {"page_number": 10, "block_count": 29, "word_count": 45}
- pymupdf.text_source: {"page_number": 11, "block_count": 28, "word_count": 38}
- pymupdf.text_source: {"page_number": 12, "block_count": 24, "word_count": 41}
- pymupdf.text_source: {"page_number": 13, "block_count": 26, "word_count": 45}
- pymupdf.text_source: {"page_number": 14, "block_count": 30, "word_count": 54}
- pymupdf.text_source: {"page_number": 15, "block_count": 30, "word_count": 48}
- pymupdf.text_source: {"page_number": 16, "block_count": 29, "word_count": 38}
- pymupdf.text_source: {"page_number": 17, "block_count": 24, "word_count": 33}
- pymupdf.text_source: {"page_number": 18, "block_count": 26, "word_count": 35}
- pymupdf.text_source: {"page_number": 19, "block_count": 30, "word_count": 42}
- pymupdf.text_source: {"page_number": 20, "block_count": 30, "word_count": 44}
- pymupdf.text_source: {"page_number": 21, "block_count": 26, "word_count": 46}
- pymupdf.text_source: {"page_number": 22, "block_count": 34, "word_count": 78}
- pymupdf.text_source: {"page_number": 23, "block_count": 24, "word_count": 46}
- ai.input: {"purpose": "product_name", "requested_model": "gemini-2.5-flash", "input_mode": "text", "text_length": 1461, "image_count": 0, "max_retries": 2}
- ai.call.start: {"provider": "deepseek", "model": "deepseek/deepseek-v4-flash", "purpose": "product_name", "input_mode": "text", "attempt_number": 1}
- ai.call.failure: {"provider": "deepseek", "model": "deepseek/deepseek-v4-flash", "purpose": "product_name", "error_type": "Exception"}
- ai.failover: {"from_provider": "deepseek", "to_provider": "vertex", "purpose": "product_name", "error_type": "Exception"}
- ai.call.start: {"provider": "vertex", "model": "gemini-2.5-flash", "purpose": "product_name", "input_mode": "text", "attempt_number": 2}
- ai.call.response: {"provider": "vertex", "model": "gemini-2.5-flash", "purpose": "product_name", "response_text_length": 9, "provider_response_returned": true, "json_parse_succeeded": false, "raw_response": null, "product_name_harvested": true, "cas_harvest…
- candidate_registered: {"derived_from": null, "value": "금속광택제튜브타입", "source": "ai_product_name_response", "field": "product_name", "engine": "gemini"}
- ai.result_application: {"purpose": "product_name", "applied_fields": ["product_name"], "applied": true, "discard_reason": ""}
- section1.product_result: {"source": "ai", "verification_status": "unverified", "accepted": true, "engine": "제미나이"}
- engine_checkpoint: {"checkpoint_stage": "ai_response_complete", "next_stage": "product_name_verification"}
- engine_checkpoint: {"checkpoint_stage": "product_name_complete", "next_stage": "section3_recon"}
- ai.component_input_selection: {"target_page_index": 2, "source_page_indexes": [0], "image_count": 1, "section3_text_length": 194}
- ai.component_image_metadata: {"image_count": 1, "encoded_byte_lengths": [63236]}
- ai.input: {"purpose": "component_extraction", "requested_model": "gemini-2.5-flash", "input_mode": "image", "text_length": 2185, "image_count": 1, "max_retries": 2}
- ai.call.start: {"provider": "vertex", "model": "gemini-2.5-flash", "purpose": "component_extraction", "input_mode": "image", "attempt_number": 3}
- ai.call.response: {"provider": "vertex", "model": "gemini-2.5-flash", "purpose": "component_extraction", "response_text_length": 16, "provider_response_returned": true, "json_parse_succeeded": true, "raw_response": null, "product_name_harvested": false, "ca…
- ai.input: {"purpose": "component_extraction", "requested_model": "gemini-2.5-flash", "input_mode": "image", "text_length": 1956, "image_count": 1, "max_retries": 2}
- ai.call.start: {"provider": "vertex", "model": "gemini-2.5-flash", "purpose": "component_extraction", "input_mode": "image", "attempt_number": 4}
- ai.call.response: {"provider": "vertex", "model": "gemini-2.5-flash", "purpose": "component_extraction", "response_text_length": 16, "provider_response_returned": true, "json_parse_succeeded": true, "raw_response": null, "product_name_harvested": false, "ca…
- engine_child_completed: {}
- engine_isolation_completed: {}

## 후보 변화

- `candidate-001` ← `source`
- `candidate-002` ← `engine_result`
- 변환: 1 / 탈락: 0 / 병합: 0 / 수동 재정의: 0

## 이미지 분석

- 저장된 이미지 없음

## 최종 원인

최초 실패 지점: 없음
직접 실패 원인: 없음
후속 우회 경로: 해당 없음
우회 경로 실패 원인: 해당 없음
최종 결과에 미친 영향: 없음
권장 확인 지점: 해당 없음
