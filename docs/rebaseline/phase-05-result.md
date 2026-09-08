# Phase 05 — Resolver / Validator Foundation

## 구현 범위

- `resolver.py`가 Phase 3의 `ProductCollection`과 `Section3Collection`만 받아
  최종 `ProductResult`와 `ComponentPair`를 결정한다. 파일명, 다른 section,
  legacy, Golden, 외부 DB/API, AI 및 자동 보정 경로는 추가하지 않았다.
- 명확한 S1 후보 하나(동일 제품의 반복 관측 포함)는 `FOUND`로, 서로 다른
  제품 후보는 첫 후보를 선택하지 않고 `REVIEW`로 남긴다. 같은 source fact의
  evidence만 중복 제거하며 모든 관측 evidence를 보존한다.
- S3는 source row/block 관계만 사용한다. CAS 하나와 content 하나는
  `PAIRED`, CAS 여러 개와 공유 content 하나는 source 순서대로 각각 pair가
  된다. 중복 CAS 행도 그대로 보존한다. content 후보가 없다는 사실만으로
  `NOT_STATED`가 되지 않는다.
- `ContentFieldState`로 `ABSENT`, `EXPLICIT_BLANK`, `UNREADABLE`, `UNKNOWN`을
  구분했다. explicit header가 확인된 빈 content cell만 `NOT_STATED`이고,
  unreadable 원문은 `NOT_READABLE`, 나머지 부재/미확정 관계는
  `PAIR_AMBIGUOUS`이다. raw concentration, range/operator, `Balance`, `Rem.`,
  ppm/wt/vol 및 100 초과 값은 수정하지 않았다. header unit context는 raw와
  별도 evidence로 유지한다.
- `models.py`에 단일 typed finding 계약(`FindingCode`, `FindingSeverity`,
  `FindingContext`, `QualityFinding`, `QualityReport`)을 추가했다. Validator는
  immutable final result를 바꾸지 않고 `PASS` 또는 `REVIEW_REQUIRED`와
  finding만 반환한다.
- Fresh Verifier finding 1건으로 CAS 정규식이 `64-17-5X`, `X64-17-5`,
  `64-17-5-99`에서 유효 접두사를 절단하는 문제가 reopen 1건으로 수정됐다.
  collector는 인접 영숫자/하이픈을 포함한 전체 source token을
  `FORMAT_INVALID` 후보와 evidence로 보존한다. resolver는 invalid CAS pair를
  `REVIEW`로, validator는 `CAS_READ_UNCERTAIN`으로 남기며 단독
  `64-17-5`는 계속 `VALID`/`PASS`다.

## 검증 결과

| Command | Result |
| --- | --- |
| `python -m pytest tests/rebaseline/test_collectors.py tests/rebaseline/test_resolver.py tests/rebaseline/test_validation.py -q` | 71 passed (CAS malformed-token collector → resolver → validator regression 포함) |
| `python -m pytest tests/rebaseline -q` | 255 passed |
| `python -m pytest tests/test_common_normalization.py -q` | 6 passed (최종 managed worker 실행) |
| `python -m compileall -q src/msds golden/v2` | PASS |
| import smoke (`models normalization pdf_io sections collectors ocr resolver validation`) | PASS |
| `git diff --check` | PASS |

모든 pytest 실행에는 기존 `.pytest_cache` 쓰기 권한 warning 1건이 있었으며
테스트 assertion 실패와는 별개다.

## 실행 메타데이터

| Role | Model / effort | Runtime / orchestration |
| --- | --- | --- |
| Phase 5 implementation | gpt-5.6-terra / high | serial: 초기 구현 terminal `term_781f2734-6bfc-4b91-ba86-afbe961fd2e6`, P1 재개 terminal `term_4877099e-55df-497b-9d2d-25dd3d18611b`에서 실제 TUI runtime 관측. |
| Fresh Verifier | gpt-5.6-sol / high | READ_ONLY: initial terminal `term_ff0bdc73-8ed7-4960-9d0c-0d07f9e90bdb`가 finding 1 / reopen 1을 반환했고, final terminal `term_08cb5f34-6f8f-426e-8e8e-3228a03f97f8`가 focused 71, rebaseline 255, common normalization 6 및 adversarial checks 후 PASS를 반환했다. |

외부 네트워크, API, 실제 OCR/AI, DB, Golden/legacy 또는 production route는 이
Phase에서 실행하지 않았다.

## Phase 5 v1.1 — P1/P2 boundary hardening (Implementation Lead handoff)

### Implemented scope

- **P1-1 OCR missing content:** a confirmed OCR `SectionInput` with a
  unit-bearing header and CAS but no content candidate is `UNKNOWN`, never
  `EXPLICIT_BLANK`; resolution is `PAIR_AMBIGUOUS` and validation emits
  `FindingCode.PAIR_AMBIGUOUS`. TEXT header-derived explicit blanks still
  resolve as `NOT_STATED`, while explicit unreadable OCR observations remain
  `NOT_READABLE` / `CONTENT_NOT_READABLE`. No blank detector, Vision, ODL, or
  OCR routing change was added.
- **P1-2 typed unit context:** `ContentResult` now carries backward-compatible
  `unit_context_raw` and `unit_context_evidence`. Header-derived bare values
  preserve raw/normalized values without unit injection; direct `%`, `ppm`,
  `wt%`, and `vol%` values have no header context.
- **P1-3 ambiguous mappings:** multiple content candidates produce empty final
  raw/normalized values with `PAIR_AMBIGUOUS`; candidate raws remain lossless
  on `Section3Collection` and are retained in finding raw candidates/evidence.
  No source-order one-to-one pairing was introduced for multiple CAS/content.
- **P2 confirmed fence propagation:** `SectionInput.fence_status` defaults to
  `None`, so hand-built inputs are rejected unless explicitly
  `FENCE_CONFIRMED`. The Phase 2 TEXT and Phase 4 OCR builders propagate the
  confirmed status; collectors and resolver convenience routing reject
  partial, not-found, and unconfirmed inputs.

### Implementation verification

| Command | Result |
| --- | --- |
| `python -m pytest tests/rebaseline/test_collectors.py tests/rebaseline/test_resolver.py tests/rebaseline/test_validation.py -q` | 86 passed (existing pytest cache permission warning only) |
| `python -m pytest tests/rebaseline/test_scan_ocr.py -q` | 88 passed (same warning) |
| `python -m pytest tests/rebaseline -q` | 273 passed (same warning) |
| `python -m pytest tests/test_common_normalization.py -q` | 6 passed |
| `python -m compileall -q src/msds golden/v2` | PASS |
| import smoke (`models normalization pdf_io sections collectors ocr resolver validation`) | PASS |

External extraction/API/AI/DB calls: **0**. Real OCR was not run; all OCR
tests use the injected local fake engine. Protected locator/routing algorithm,
legacy, Golden, ODL, AI/KOSHA/MES, GUI, and main remain unchanged.

이 Implementation Lead handoff 시점에는 v1.1 final independent Fresh
Verifier가 Coordinator 대기 상태였다. 아래는 그 후 코드 대상 HEAD에 대해
수행된 최종 독립 검수 기록이다.

## Phase 5 v1.1 — Final independent Fresh Verifier record

### Review target and verdict

- Code-review target HEAD: `b7fed70abb481985766cc30d3ab24c71c3e9cb50`.
- Fresh verdict: **PASS**; findings: **0**.
- 이 후의 documentation-only commit은 PASS 코드 검토 이후의 기록 마감이며,
  코드 대상은 계속 위 `b7fed70…`이다.

### Independent execution evidence

| Role | Model / effort | Execution / evidence |
| --- | --- | --- |
| Implementation Lead | gpt-5.6-terra / high | 이 Lead terminal의 실제 runtime을 Coordinator가 관측했다. |
| Fresh Verifier | gpt-5.6-sol / high | fresh context, implementation과 분리된 READ_ONLY terminal `term_607b69bc-c976-492c-8b57-9a4e9869e78c`; direct serial terminal lifecycle. |
| Coordinator / Orchestrator | UNVERIFIABLE | model/effort 관측 근거 없음. |

Supervised Orca DAG/dispatch는 사용하지 않았다. Fresh Verifier는 구현에
참여하지 않은 독립 context에서 READ_ONLY 검수를 수행했다.

### Final verification evidence

| Check | Result |
| --- | --- |
| independent focused 5 files | 191 passed |
| `python -m pytest tests/rebaseline -q` | 273 passed |
| `python -m pytest tests/test_common_normalization.py -q` | 6 passed |
| adversarial contract probe | PASS |
| `git diff --check` | PASS |
| protected-scope diff | 0 changed protected paths |
| worktree | clean |

`common_normalization` 첫 실행은 managed-sandbox temporary-directory trace
permission issue가 있었고 assertion failure는 아니었다. 이후 normal temp
context에서 재확인하여 **6 passed**를 얻었다.

The independent probe verified all of the following: OCR absence follows
`UNKNOWN → PAIR_AMBIGUOUS → REVIEW_REQUIRED`; TEXT explicit blanks remain
`NOT_STATED`; unreadable observations remain `NOT_READABLE`; header-unit raw
preservation has no unit injection; multiple candidates create no synthetic
joined raw; partial/not-found/`None` fences are rejected; invalid and duplicate
CAS facts are retained; validator immutability holds; and no external-truth
fallback exists.

Actual external extraction/API/AI/DB/real-OCR calls: **0**.
