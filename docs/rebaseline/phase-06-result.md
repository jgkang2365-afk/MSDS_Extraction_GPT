# Phase 06 — Golden v2 approval contract foundation

## Scope actually implemented

- Added only `golden/v2` contract assets and Golden v2 tests: the independent
  lifecycle `CANDIDATE → HUMAN_REVIEWED → APPROVED`, three case kinds, ordered
  lossless value rows, approval history, portable source references, local
  source/hash validation, and an approved-only selector.
- Added dependency-free `validate_dataset(..., source_roots=...)`. It returns
  errors and findings without mutating supplied case data. Missing/mismatched
  local assets are errors for APPROVED and review blockers for lower lifecycle
  states.
- Kept the Phase 5 product/component status and evidence contract lossless:
  duplicate CAS/order and shared content relations remain rows; no CAS-keyed
  representation or synthetic joined ambiguous content is accepted.
- Fresh Verifier #1 FAIL에 따라 lifecycle final-stage/selector, SAFE_REVIEW,
  actual-PDF asset/provenance, timestamp, unit-context, and source transcription
  contracts을 보완했다. Fresh Verifier #2 FAIL의 최소 보완으로 APPROVED human
  provenance, ordered transcription/component relation, asset read failure, and
  no-space direct-unit contracts의 회귀를 추가했다. No Golden v1 import or copy
  path exists. Fresh Verifier #3 FAIL의 최소 보완으로 APPROVED PDF-kind/source
  asset selector gate, ordered evidence occurrence 1:1 relation, and null
  unit-context evidence invariant의 회귀를 추가했다. Fresh Verifier #5 FAIL의
  reopen 4 최소 보완으로 schema 자체의 approval/expected/unit·ambiguity 계약,
  schema-invalid selector 입력 차단, full locator identity 비교와 jsonschema
  회귀를 추가했다. Fresh Verifier #6 FAIL의 단일 schema transcription-shape
  finding에 따라 reopen 5에서는 APPROVED 전사의 local shape, human evidence와
  `raw_reading` 금지를 schema-level로 보강하고, cross-row exact relation은 helper
  책임임을 명시했다. Fresh Verifier #7 FAIL의 F1~F3에 따라 reopen 6에서는
  APPROVED human evidence의 OCR `raw_reading` semantic fence, selector의
  dataset-level duplicate `case_id` gate, 그리고 `NOT_STATED` content/pair
  contradiction rejection을 최소 보완했다. Fresh Verifier #8 FAIL의 F1~F4에
  따라 reopen 7에서는 nested human-evidence `raw_reading` fence, exact
  content/pair status mapping, whole-dataset Draft 2020-12 selector gate,
  그리고 uppercase `PPM` direct-unit schema 회귀를 보완했다. Fresh Verifier #9
  FAIL의 F1~F2에 따라 reopen 8에서는 shared-content row consistency와 ordered
  review timestamp monotonicity semantic gate를 보완했다. Fresh Verifier #10
  FAIL의 F1~F5에 따라 reopen 9에서는 malformed container fail-closed guard,
  APPROVED product transcription correspondence, CANDIDATE timestamp 금지,
  strict timezone offset, 그리고 transcription-wide schema `raw_reading`
  fence를 보완했다. Fresh Verifier #11 FAIL의 F1~F2에 따라 reopen 10에서는
  malformed public API/source-root fail-closed guard와 JSON type-exact locator
  comparison 및 boolean bbox coordinate schema rejection을 보완했다. Fresh
  Verifier #12 FAIL의 단일 finding에 따라 reopen 11에서는 mapping 내부 malformed
  source-root value의 `Path(...)` TypeError를 source-asset unavailable 결과로
  fail-closed 처리했다. Fresh Verifier #13 FAIL의 단일 finding에 따라 reopen
  12에서는 empty/whitespace source-root string이 working directory로 해석되지
  않도록 unavailable 처리했다. External P1 compatibility 지시에 따라 reopen
  13에서는 Phase 5 resolver의 non-`VALID` CAS(`INVALID`)가 모든 content 상태를
  `pair_status: REVIEW`로 override하는 계약을 Golden v2 helper/schema/selector에
  반영했다. Phase 5가 내지 않는 Golden 확장 CAS `NOT_READABLE`/`REVIEW`는
  review-only 상태로 명시하고 역시 `REVIEW` pair만 허용한다.

## Corpus and pilot decision

No candidate, HUMAN_REVIEWED, or APPROVED Golden v2 data was added. No
repository-local, approval-ready source PDF was identified within the permitted
scope, so pilot CANDIDATE generation is **deferred**. This phase therefore does
not claim a human-reviewed corpus, source-PDF review, corpus accuracy, or Gate
3 completion.

PRD decision: **NO change** — product policy did not change. TRD decision:
**YES, minimal v1.1 technical synchronization** — portable source references,
lifecycle/history requirements, and Phase 6 scope/deferral are recorded without
changing the v1.1 version convention.

## Execution boundary

Vercel calls: **0**. External calls (OCR/AI/API/ODL/KOSHA/MES/DB): **0**.
No UI, localhost server, production, PDF extraction, or source-PDF review ran.

| Role | Model | Effort | Execution | Evidence |
| --- | --- | --- | --- | --- |
| Single WRITE Lead | gpt-5.6-terra | high | direct / serial | terminal TUI runtime 관측 |
| Fresh Verifier #1 | gpt-5.6-sol | high | READ_ONLY / 종료 | **FAIL**; verifier는 수정하지 않았고 Lead가 reopen 1건을 보완 |
| Fresh Verifier #2 | gpt-5.6-sol | high | READ_ONLY / 종료 | **FAIL**; 4개 최소 finding으로 reopen 2건을 보완 중 |
| Fresh Verifier #3 | gpt-5.6-sol | high | READ_ONLY / 종료 | **FAIL**; 3개 finding으로 reopen 3건을 보완 |
| Fresh Verifier #4 | 미확인 | 미확인 | READ_ONLY / interrupted | **no final result**; PASS 또는 FAIL로 판정하지 않음 |
| Fresh Verifier #5 | gpt-5.6-sol | high | READ_ONLY / 종료 | **FAIL**; F15 schema contract, F16 schema-invalid selector bypass, F17 exact evidence locator의 3개 finding으로 reopen 4건을 보완 |
| Fresh Verifier #6 | gpt-5.6-sol | high | READ_ONLY / 종료 | **FAIL**; schema가 malformed APPROVED `source_transcription` shape를 허용한 단일 finding으로 reopen 5를 시작 |
| Fresh Verifier #7 | 미확인 | 미확인 | READ_ONLY / 종료 | **FAIL**; F1 schema-invalid APPROVED selector, F2 duplicate `case_id` selector bypass, F3 `NOT_STATED` semantic contradiction의 3개 finding으로 reopen 6을 시작 |
| Fresh Verifier #8 | 미확인 | 미확인 | READ_ONLY / 종료 | **FAIL**; F1 nested human-evidence `raw_reading`, F2 content/pair mapping, F3 whole-dataset schema selector gate, F4 uppercase `PPM` schema regression의 4개 finding으로 reopen 7을 시작 |
| Fresh Verifier #9 | 미확인 | 미확인 | READ_ONLY / 종료 | **FAIL**; F1 shared-content row consistency, F2 review-history timestamp monotonicity의 2개 finding으로 reopen 8을 시작 |
| Fresh Verifier #10 | 미확인 | 미확인 | READ_ONLY / 종료 | **FAIL**; F1 malformed container fail-closed, F2 approved transcription product correspondence, F3 CANDIDATE timestamp, F4 timezone offset minute, F5 recursive transcription `raw_reading` schema의 5개 finding으로 reopen 9를 시작 |
| Fresh Verifier #11 | 미확인 | 미확인 | READ_ONLY / 종료 | **FAIL**; F1 malformed public API/container/source-root robustness, F2 JSON type-exact locator comparison과 boolean bbox schema의 2개 finding으로 reopen 10을 시작 |
| Fresh Verifier #12 | 미확인 | 미확인 | READ_ONLY / 종료 | **FAIL**; mapping 내부 invalid source-root value가 `Path` TypeError를 내는 단일 finding으로 reopen 11을 시작 |
| Fresh Verifier #13 | 미확인 | 미확인 | READ_ONLY / 종료 | **FAIL**; empty/whitespace mapped source-root string이 working directory로 해석될 수 있는 단일 finding으로 reopen 12를 시작 |
| Final Fresh Verifier R8 | UNVERIFIABLE | UNVERIFIABLE | fresh context / READ_ONLY / superseded | 이전 PASS 보고는 external P1 compatibility 변경으로 superseded되었으며, 현재 변경에 대한 final verifier verdict는 **없음** |

Fresh Verifier #1 finding은 7건이다: lifecycle/selector final-stage 검증, ambiguous
final raw 차단, SAFE_REVIEW의 REVIEW_REQUIRED 강제, 실제 PDF asset/provenance,
실제 timestamp 파싱, header unit-context evidence, 그리고 별도 human
`source_transcription` 계약. Fresh Verifier #2 finding은 4건이다: APPROVED evidence의
의미 있는 human source provenance, ordered transcription/component source relation,
source asset resolve/read OSError·PermissionError 처리, 그리고 공백 없는 direct-unit
lexical 검증. Fresh Verifier #3 finding은 3건이다: `validate_case`/selector의
APPROVED PDF-kind 및 source asset gate, transcription/component evidence의 ordered
occurrence 1:1 연계, 그리고 null `unit_context_raw`의 evidence 금지다. Fresh Verifier
#5 finding은 3개다: F15는 schema가 Python approval/expected/unit·ambiguity 구조
계약을 스스로 거부하지 않는 문제, F16은 absolute source field·boolean evidence
page·numeric shared-content ID가 selector까지 통과할 수 있는 문제, F17은 같은 page의
서로 다른 bbox/region locator 순서가 뒤집혀도 transcription correspondence가 통과하는
문제다. #6 finding은 1개다: APPROVED `source_transcription`의 direct human
confirmation/method, component-row minimum shape, non-empty rows, 그리고 OCR
`raw_reading` 금지가 schema 자체에 충분히 표현되지 않은 문제다. #7 finding은 F1
schema-invalid APPROVED(특히 human evidence의 OCR `raw_reading`)가 selector를 통과할
수 있는 문제, F2 dataset duplicate `case_id` 오류가 selector를 우회할 수 있는 문제,
F3 `NOT_STATED`가 nonempty content raw/normalized 또는 `PAIRED`와 공존할 수 있는
문제다. #8 finding은 F1 human evidence 내부 annotation 등의 모든 중첩 위치에 있는
`raw_reading`, F2 content/pair status의 불일치, F3 다른 어느 case의 schema 오류도
selector가 전체 dataset에서 차단해야 하는 문제, F4 uppercase `PPM` 직접 단위에
header context를 schema가 허용하는 문제다. #9 finding은 F1 같은 non-null
`shared_content_id`의 component rows가 하나의 source content fact를 가리키는데도
content/unit-context가 불일치할 수 있는 문제와 F2 lifecycle action 순서는 맞아도
timezone-aware review timestamp가 역행할 수 있는 문제다. #10 finding은 F1 `components`
container가 schema-invalid일 때 helper/selector가 예외를 내는 문제, F2 APPROVED
transcription product raw/provenance locator 대응 부재, F3 CANDIDATE optional timestamp,
F4 timezone offset minute 검증, F5 nested additional transcription annotation의
`raw_reading` schema fence 부재다. #11 finding은 F1 case/lifecycle/status/pair/action/
history/expected/source-root 등 malformed JSON-compatible 값이 public API 예외로
이어질 수 있는 문제와 F2 locator comparison에서 boolean과 integer가 같게 취급되고
bbox boolean coordinate를 schema가 허용하는 문제다. #12 finding은 mapping 자체는
유효하지만 mapped root 값이 `false`/`0`/list/dict 등일 때 `Path`가 TypeError를 내는
문제다. #13 finding은 mapped root value가 empty 또는 whitespace-only string일 때
`Path('')`가 current working directory를 가리킬 수 있는 문제다. External P1은
Phase 5 resolver가 실제로 생성하는 CAS `FOUND`/`INVALID` 중 `INVALID`가 모든
`FOUND`/`NOT_STATED`/`NOT_READABLE`/`PAIR_AMBIGUOUS` content 상태를 `REVIEW`로
override하는 compatibility matrix를 요구했다. Golden 확장 CAS
`NOT_READABLE`/`REVIEW`는 runtime 출력 주장 없이 review-only로 같은 `REVIEW`
pair rule을 적용한다. Reopen count는 **13**이며, #3의 실제 관측 model/effort는 `gpt-5.6-sol`/`high`, #4는 interrupted로
final result가 없고, #5와 #6의 실제 관측 model/effort는 각각
`gpt-5.6-sol`/`high`이며 모두 final FAIL이다. `schema.json`은 local structure와
locally expressible promotion gate만 검사한다. Draft 2020-12가 source transcription과
component 배열 간 arbitrary row coverage/value/locator exact equality를 표현할 수
없으므로, 그 semantic cross-row relation은 `validate_case`/`validate_dataset` helper가
authoritative하게 검사한다. 이는 schema-expressible 범위를 넘는 schema/Python 완전
동치 주장이 아니다. R8의 이전 fresh-context PASS 보고는 기록으로 보존하되 external
P1 compatibility 변경 뒤에는 superseded되었다. 따라서 현재 working tree에는 final
Fresh Verifier verdict가 없으며, P1은 malformed source-root mapping, recursive OCR
`raw_reading`, approved-only dataset integrity, product/component transcription locator
identity, duplicate/shared CAS, status/unit context, lifecycle timestamp, immutable
validation, Golden v1/forbidden fallback의 기존 보장에 CAS/content/pair matrix
regression을 추가한 상태다.

## Local verification

| Command | Result |
| --- | --- |
| `python -m pytest tests/rebaseline/test_golden_v2_contract.py tests/rebaseline/test_golden_v2_dataset.py -q` | 143 passed (P1 Golden helper/Draft schema/approved-selector matrix 포함) |
| `python -m pytest tests/rebaseline/test_resolver.py tests/rebaseline/test_validation.py -q` | 41 passed (P1 Phase 5 resolver/validation compatibility focus) |
| `python -m pytest tests/rebaseline -q` | 407 passed |
| `python -m pytest tests/test_common_normalization.py -q` | 6 passed |
| `python -m compileall -q src/msds golden/v2` | PASS |
| import / JSON parse / Draft 2020-12 schema check | PASS |
| `git diff --check` / forbidden-scope diff | PASS / 0 changed forbidden paths |

## Known deferrals

- Human source-PDF review, real approved corpus, pilot fixture, and holdout
  evaluation require a separately supplied/authorized local source set and a
  human reviewer.
- Real OCR/AI/ODL/KOSHA/MES, database persistence, GUI/Excel, deployment, and
  production validation remain out of scope.

## Resumption checkpoint

This existing worktree was read-only verified and formally resumed on
2026-09-09 without recreating its branch, worktree, or contract assets. Its
seven pre-existing Phase 6 changes were preserved unchanged. The current Orca
runtime reported zero Phase 6 terminals and no path-owned worker process before
resumption. A new WRITE-worker terminal was attempted three times via the
required direct terminal lifecycle and each attempt returned `Timed out waiting
for terminal handle after creation`; every follow-up terminal/dispatch query
reported no created worker. No further terminal retry was made.

Reopen 13의 semantic test evidence는 Golden focused 143 passed, Phase 5
resolver/validation focused 41 passed, full rebaseline 407 passed, common
normalization 6 passed, compile/import/JSON parse/Draft schema check, 그리고
`git diff --check` PASS다. R8은 external P1로 superseded되었고, 새 independent
Fresh Verifier가 final PairStatus compatibility semantic state를 fresh context /
READ_ONLY로 검수하여 PASS, findings 0을 반환했다. runtime model/effort는 독립
관측 근거가 없어 UNVERIFIABLE이다. PR #9는 Draft로 유지하며 merge는 실행하지
않고 `main`은 변경하지 않는다.
