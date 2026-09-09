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
  책임임을 명시했다.

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
| Final Fresh Verifier | pending | pending | READ_ONLY / not started | reopen 5 수정 뒤 독립 최종 검수 대기; PASS를 주장하지 않음 |

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
`raw_reading` 금지가 schema 자체에 충분히 표현되지 않은 문제다. Reopen count는
**5**이며, #3의 실제 관측 model/effort는 `gpt-5.6-sol`/`high`, #4는 interrupted로
final result가 없고, #5와 #6의 실제 관측 model/effort는 각각
`gpt-5.6-sol`/`high`이며 모두 final FAIL이다. `schema.json`은 local structure와
locally expressible promotion gate만 검사한다. Draft 2020-12가 source transcription과
component 배열 간 arbitrary row coverage/value/locator exact equality를 표현할 수
없으므로, 그 semantic cross-row relation은 `validate_case`/`validate_dataset` helper가
authoritative하게 검사한다. 이는 schema-expressible 범위를 넘는 schema/Python 완전
동치 주장이 아니다. 이번 수정의 focused/whole/common/compile/schema-dataset/diff
검증 후에도 final independent re-verification은 **pending**이다. 따라서 최종 Fresh
Verifier PASS를 주장하지 않는다.

## Local verification

| Command | Result |
| --- | --- |
| `python -m pytest tests/rebaseline/test_golden_v2_contract.py tests/rebaseline/test_golden_v2_dataset.py -q` | 81 passed; pytest cache permission warning 1건 |
| `python -m pytest tests/rebaseline -q` | 345 passed; pytest cache permission warning 1건 |
| `python -m pytest tests/test_common_normalization.py -q` | 6 passed (managed sandbox system-temp permission failure 후 동일 명령 승인 재실행) |
| `python -m compileall -q src/msds golden/v2` | PASS |
| import / jsonschema structural probe | PASS (Draft 2020-12 schema check, valid candidate/APPROVED and invalid structural probes) |
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

The existing final semantic test evidence remains current because no Phase 6
contract file changed after it: focused Golden 81 passed, full rebaseline 345
passed, common normalization 6 passed, compile/import passed, and `git diff
--check` passed. Final independent Fresh Verifier remains pending because a
fresh Orca terminal could not be started. This checkpoint may be committed,
pushed, and opened as a Draft PR for remote preservation, but it is not
merge-ready and must not be reported as final PASS or COMPLETE.
