# Phase 07 — Golden v2 regression pilot

## 결과

Golden v2의 독립 lifecycle과 portable source 계약을 유지한 채, 작업 범위로 제공된
로컬 `TEST_File` PDF 세 건으로 작은 회귀 파일럿을 만들었다. 각 PDF의 SHA-256은
작업지시서의 값과 일치했다. PDF는 복사·업로드·외부 전송하지 않았으며,
`pdf_io`와 `sections`의 현재 디지털 텍스트 route만 사용했다.

| Canonical candidate | Portable source | SHA-256 | Core fence observation | Candidate result |
| --- | --- | --- | --- | --- |
| `008-sarapong.candidate.json` | `phase7-test-file/008_★msds_사라퐁.pdf` | `2e684040…fe1eee2d` | S1 `FENCE_NOT_FOUND`, S3 `FENCE_NOT_FOUND` (`SECTION_START_NOT_FOUND`) | `FAILURE_BEHAVIOR`, `CANDIDATE`, `FENCE_BLOCKED` |
| `015-teca-biome.candidate.json` | `phase7-test-file/015_★1005_TECA-BIOME™_GHS_MSDS개정_(KOR)_ICBIO.pdf` | `88fe15b8…a9e4ed0b` | S1 confirmed; S3 `FENCE_PARTIAL` (`SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED`) | `FAILURE_BEHAVIOR`, `CANDIDATE`, `FENCE_BLOCKED` |
| `024-sodium-hydroxide.candidate.json` | `phase7-test-file/024_★Sodium Hydroxide(NaOH).pdf` | `25811ad3…290780c6` | S1 `FENCE_PARTIAL` (`SECTION_END_NOT_FOUND`); S3 confirmed | `FAILURE_BEHAVIOR`, `CANDIDATE`, `FENCE_BLOCKED` |

두 대상 section의 confirmed fence가 모두 있는 사례가 없어서
`collectors`/`resolver`/`validation`에 임의의 `SectionInput`을 주입하지 않았다.
제품명·CAS·함유량 value proposal, source transcription, human provenance는 만들지
않았다. 특히 OCR, AI, ODL, KOSHA, MES, DB, filename fallback, Golden v1 value copy는
모두 사용하지 않았다.

## Corpus 및 검토 상태

- Canonical data: `golden/v2/cases/regression-pilot/`의 candidate JSON 세 건과
  portable manifest 한 건이다. source reference는 root 이름과 파일명만 포함한다.
- 각 `review_history`는 timestamp 없는 `CANDIDATE` action/status 한 건뿐이며,
  `HUMAN_REVIEWED` 및 `APPROVED` status 수는 0이다.
- `select_approved_cases(...)` 결과는 빈 tuple이다. 이 파일럿은 approved truth를
  선택하거나 승격하지 않는다.
- 로컬 검토 패킷은 `.local-review/phase-07/`에만 두고 Git local exclude에만
  등록했다. 이 패킷만 authorized source의 absolute local path와 core fence
  observation을 보관하며, repository `.gitignore`는 변경하지 않았다.
- Human gate는 **REVIEW_READY**다. M1(qualified human의 direct source-PDF review,
  source transcription, lifecycle transition)은 **pending**이다.

## 검증

| Command | Result |
| --- | --- |
| `PHASE7_TEST_FILE_ROOT=<authorized TEST_File> python -m pytest tests/rebaseline/test_phase07_golden_v2_pilot.py -q` | 1 passed |
| `PHASE7_TEST_FILE_ROOT=<authorized TEST_File> python -m pytest tests/rebaseline/test_golden_v2_contract.py tests/rebaseline/test_golden_v2_dataset.py tests/rebaseline/test_phase07_golden_v2_pilot.py -q` | 144 passed |
| `python -m pytest tests/rebaseline/test_resolver.py tests/rebaseline/test_validation.py -q` | 41 passed |
| `PHASE7_TEST_FILE_ROOT=<authorized TEST_File> python -m pytest tests/rebaseline -q` | 408 passed |
| `python -m pytest tests/test_common_normalization.py -q` | 6 passed |
| `python -m compileall -q src/msds golden/v2 tests/rebaseline` | PASS |
| import smoke (`models`, `normalization`, `pdf_io`, `sections`, `collectors`, `resolver`, `validation`, `golden.v2.validation`) | PASS |
| JSON parse / local Draft 2020-12 candidate schema check | PASS |
| `git diff --check` and new-file whitespace check | PASS |
| protected-scope/schema diff (`src/msds`, `golden/v1`, `golden/v2/schema.json`, `golden/v2/validation.py`, PRD, TRD) | 0 changed protected paths |

External network/API/AI/ODL/KOSHA/MES/DB calls: **0**. Vercel calls: **0**.

## Fresh Verifier reopen

Initial independent Fresh Verifier verdict was **FAIL** with two minimal
findings: (F1) the Golden v2 README still described the pre-Phase-07 empty
corpus, and (F2) the pilot test did not independently compare candidate
blockers with the actual local `pdf_io`/`sections` fence result. This reopen
updates only those two surfaces: the README now records the three
`CANDIDATE`/`FAILURE_BEHAVIOR` files and explicitly states that no
`HUMAN_REVIEWED`/`APPROVED` data exists; the pilot test now runs only the local
TEXT fence path, verifies zero external calls/no OCR route, verifies that both
fences are not confirmed, and compares every candidate blocker to observed
S1/S3 status/reason. It does not call collectors, resolver, or validation to
produce a value proposal. The post-reopen independent Fresh Verifier ran in a
fresh READ_ONLY context and returned **PASS** with findings 0: it independently
rechecked local file existence/SHA, candidate lifecycle and approval exclusion,
portable canonical paths, packet exclusion, the three exact fence
status/reason blocker pairs, source-transcription/human-provenance absence, and
protected scope. Runtime model/effort was not independently observable and is
recorded as UNVERIFIABLE.

## 범위 확인

`src/msds`, `golden/v1`, Golden v2 schema/validator, PRD, TRD는 변경하지 않았다.
Phase 07이 추가한 tracked scope는 candidate corpus/manifest, local-only pilot test,
Golden v2 corpus-status README correction, 그리고 이 결과 문서다. This branch is
review-ready, not human-approved: no merge is run and `main` is unchanged.
