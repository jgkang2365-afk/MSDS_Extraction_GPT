# MSDS 진단 추적 흐름

`diagnostic_trace.py`는 추출·OCR·AI 처리와 분리된 파일 단위 관측 계층이다. 진단 기록 실패는 예외를 다시 던지지 않으므로 추출 결과에는 영향을 주지 않는다. 이 문서는 파일명만 보고 추정한 구조가 아니라 현재 GUI 진입점에서 실제 호출되는 경로를 기준으로 한다.

## 현재 활성 처리 흐름

1. `smu_gui.py`의 `run_extraction`이 캐시 상태를 판단하고, 미처리 PDF를 `ExtractionWorker._run_classified_batch`에 전달한다.
2. `batch_pipeline.classify_and_order`가 PyMuPDF의 첫 1~3페이지 텍스트·이미지 면적만으로 `text → mixed → image` 순서를 만든다. 이 단계에서는 OCR을 호출하지 않는다.
3. 각 파일은 `MSDSCore.extract_from_pdf`에서 문서 유형별 제한시간과 이미지용 단일 세마포어를 적용한 뒤 spawn 자식 프로세스의 `process_pdf → process_msds_pipeline → _process_msds_pipeline_impl`로 들어간다.
4. 디지털 경로는 Section 1 로컬 제품명 후보, PyMuPDF text/words/blocks, ODL, 밀도 기반 표 후보, 정규식 스나이퍼를 사용한다. 이미지 경로는 저비용 Paddle 정찰, Section 3/4 범위 결정, 동일 재단 이미지의 원격 OCR 또는 로컬 PPStructure/멀티모달 AI 우회를 사용한다. 혼합형은 텍스트 후보를 우선 수집하되 부족한 영역에서 이미지 경로를 사용한다.
5. `refine_msds_components_strict`와 `final_quality_control`이 CAS 형식·체크디지트·함유량 연결·중복 우선순위를 적용한다. 이어 `MSDSCore._postprocess_extraction_result`가 GUI 계약 문자열로 다시 직렬화하므로 이 지점이 엔진 결과를 최종적으로 덮어쓰는 활성 경계다.
6. 부모 프로세스의 `BatchRunLogger.record_file`이 부분 결과·타임아웃·최종 GUI 후보와 diagnostic 파일을 확정한다. GUI는 캐시와 테이블에 결과를 반영한다.
7. 2단계 검증은 `ValidationWorker → MSDSCore.validate_with_kosha → KoshaAPIClient`로 이어진다. 파일의 직렬화된 trace context를 다시 활성화하므로 메모리/영구/음성 캐시, 네트워크, 재시도와 예산 이벤트가 같은 `file_trace_id`에 추가된다.

## 값이 변경되거나 사라지는 활성 지점

- 제품명: Section 1 로컬 후보 → AI 제품명 → 정규화 비교 → mismatch 경고 → 최종 GUI 후보. 파일명은 식별용으로만 사용된다.
- CAS/함유량: 엔진별 원시 후보 → `refine_msds_components_strict` 형식 정제 → `final_quality_control` 체크디지트·중복 우선순위 → 코어 GUI 문자열 직렬화.
- 이미지: 페이지 렌더링 → 정찰 OCR 입력 → Section 3/4 좌표 → 샌드위치 재단 → 표/AI 공용 입력. 저장된 이미지 이벤트에는 렌더 크기, DPI, crop box, 비율과 후보 박스 ID가 연결된다.
- 부분 타임아웃: 제품명, CAS 후보, CAS-함유량 매칭, AI 응답 체크포인트를 부모 메모리에 누적한다. CAS 후보 단계만 끝난 경우 `content_matching_complete=False`와 `validation_eligible=False`가 유지되어 `미기재%`로 승격하거나 정상 2단계 검증하지 않는다.

## 비활성·구형 경로

- `ExtractionWorker.run`의 즉시 `return self._run_classified_batch()` 아래 구현은 현재 실행되지 않는다.
- `get_table_engine`, `update_regex_pattern`, `parse_local_table_to_json` 등 호환/보조 함수는 현재 GUI 기본 추출 경로의 주 처리기가 아니다.
- 원격 OCR은 설정이 활성화된 경우에만 실행되며 기본 운영 경로가 아니다. scratch/archive 성격 파일과 오프라인 테스터도 GUI 추출 경로에 포함되지 않는다.
- 진단 계측은 위 활성 경계에만 추가했고 이 비활성 코드의 우선순위·호출 수를 바꾸지 않았다.

## 데이터 흐름과 저장 위치

1. 호출자는 `create_trace_context(source, ...)`로 실행 ID와 파일 추적 ID를 만든다. 이 컨텍스트는 `to_dict()`로 직렬화해 자식 프로세스에 전달할 수 있다.
2. `with activate_trace(context) as tracer:` 범위에서 `stage`, `candidate`, `transform`, `reject`, `merge`, `override`, `image`를 호출한다.
3. 이벤트는 `logs/runs/<run_id>/files/<file_trace_id>/events.jsonl`에 append된다. 모든 이벤트에는 `run_id`, `file_trace_id`, `stage_id`, `parent_stage_id`, `candidate_id`, `timestamp`, `elapsed_ms`, `event_type`가 포함된다. 이전 소비자 호환을 위해 `event`도 함께 기록한다.
4. 완료 시 `finalize_trace(context, result)` 또는 `tracer.finalize(result)`가 같은 디렉터리에 `diagnostic.json`, `diagnostic.md`를 쓴다.

`MSDS_DIAGNOSTIC_MODE`가 우선이며, 없으면 선택적 `config.json`의 `diagnostic.mode` 또는 `diagnostics.mode`를 읽고 기본값은 `SUMMARY`다. `OFF`는 파일을 만들지 않고, `SUMMARY`는 중요하거나 실패와 관련된 이미지만, `FULL`은 요청된 모든 이미지를 보관한다.

## 정합성과 실패 처리

- 후보는 `candidate_id`를 명시하면 이후 `transform`에서도 동일 ID를 유지한다. 자동 ID는 사람이 읽기 쉬운 `candidate-001` 형식이며, 새 후보에 `derived_from`을 지정하면 계보가 보고서에 남는다.
- 중첩 `stage`는 부모 stage ID를 자동 기록하며, 정상 종료·오류·skip 이벤트를 구분한다.
- 이벤트와 보고서는 API 키, Authorization 값, service account/private key, 긴 base64 원문을 기록 전 마스킹한다.
- 파일 쓰기, 이미지 인코딩, 보고서 생성 실패는 내부에서 흡수하고 debug 로그만 남긴다. `activate_trace(None)`도 no-op tracer를 반환한다. 재시도는 호출자가 안전하게 같은 `run_id`/새 `file_trace_id`로 수행할 수 있으며 JSONL append는 잠금으로 같은 tracer 내 동시 호출을 보호한다. parent/child가 별도 tracer로 같은 파일 JSONL에 기록할 경우 finalizer는 디스크 이벤트를 다시 구성해 후보·이미지·단계가 빈 상태로 덮어써지지 않게 한다.

`diagnostic.json`은 이벤트 재구성 결과(단계, 후보, 변환, 탈락, 병합, 재정의, 이미지, 엔진 이벤트, 실패)를 포함한다. `diagnostic.md`는 문서 요약, 최종 결과, 시간순 실행 단계, 엔진별 결과, 후보 변화, 이미지 분석, 최초 실패 지점과 직접 원인·우회·영향·권장 확인 지점을 제공한다. `stage(..., status=..., output_summary=..., candidate_count=...)` 또는 `stage_result(...)`로 결과 메타데이터를 남길 수 있다.

## 이미지와 보존 정책

`image()`는 PIL 이미지, 이미지 경로 또는 바이트를 받고 PNG/WebP로 저장한다. `candidate_boxes={candidate_id: (x1,y1,x2,y2)}`와 `table_lines=[(x1,y1,x2,y2)]`를 지정하면 후보 ID·박스와 표선을 오버레이한다.

`cleanup_retention()`은 경로가 정확히 `logs/runs`일 때만 그 바로 아래 실행 디렉터리를 삭제한다. `retention_days` 및 `max_runs` 인자를 우선 사용하고, 없으면 선택적 `diagnostic.retention.retention_days`, `diagnostic.retention.max_runs`를 읽는다. 다른 경로 삭제와 심볼릭 링크를 통한 범위 이탈을 거부한다. 운영 로그 정리는 별도 승인 및 스케줄링 정책 아래에서 호출한다.
