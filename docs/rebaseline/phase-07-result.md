# Phase 07 — Golden v2 regression pilot v1.1

## 결과

세 authorized local PDF를 외부 전송 없이 현재 Phase 1--5 TEXT core로만 처리했다.
SHA-256은 작업지시서가 직접 제공한 값이며, portable corpus에는 source root 이름과
파일명만 기록했다. 세 canonical file은 모두 `VALUE_TRUTH`/`CANDIDATE`이고 human
provenance, `source_transcription`, `HUMAN_REVIEWED`, `APPROVED`는 없다.

| Candidate | Portable source / user-supplied SHA-256 | v1.0 fence 결과 | v1.1 core 결과 |
| --- | --- | --- | --- |
| `008-sarapong.candidate.json` | `phase7-test-file/008_★msds_사라퐁.pdf` / `2e684040b696104a85d5368adb528e4f0a2468472daaac51a4c62e18fe1eee2d` | S1/S3 start 미검출 | S1/S3 confirmed; 제품 `사라퐁`; CAS-bearing 2행은 `INVALID/REVIEW`, CAS-less 행은 미승격 |
| `015-teca-biome.candidate.json` | `phase7-test-file/015_★1005_TECA-BIOME™_GHS_MSDS개정_(KOR)_ICBIO.pdf` / `88fe15b8c8f6741905543af9523ab902bb4b4f1727e8479a191835a0a9e4ed0b` | S3 mixed fence partial | S1/S3 confirmed; 제품 `TECA-BIOME™`; 12 component source relations (11 `PAIRED`, 1 `INVALID/REVIEW`) |
| `024-sodium-hydroxide.candidate.json` | `phase7-test-file/024_★Sodium Hydroxide(NaOH).pdf` / `25811ad3e84472d9f8b244a8e391ca66af2714d24a8021efb1e3908b290780c6` | S1 end 미검출 | S1/S3 confirmed; explicit named fields의 `92-100％`, `8-0％`와 CAS 2행을 `INVALID/REVIEW`로 보존 |

v1.1의 최소 core 변경은 다음으로 한정했다.

- split Korean section number/title, 역순 `위험 유해성`, 반복 top-right decorative logo를 안전하게 fence 처리했다.
- Section 1 `물질명` label과 full-width percent를 보존했다.
- CAS header table의 date-shaped CAS는 임의 보정하지 않고 source observation `INVALID/REVIEW`로만 유지했다. prose date는 계속 제외한다.
- explicit `성분` → `C A S` → `함유량` named-field group은 table route와 상호배타로 수집한다. 따라서 NaOH의 raw `8-0％`가 보존되며 fence 밖 CAS나 CAS-less content는 component로 만들지 않는다.

## lifecycle / review gate

- 모든 `review_history`는 timestamp 없는 `CANDIDATE` action/status 한 건이다.
- `select_approved_cases(...) == ()`; human lifecycle status 수는 0이다.
- Human gate는 **REVIEW_READY**, M1(qualified human direct PDF review, transcription, lifecycle transition)은 **pending**이다.
- local-only 검토 패킷은 `.local-review/phase-07/`에 있고 `.git/info/exclude`에만 등록했다. repository `.gitignore`는 바꾸지 않았다.
- merge는 실행하지 않았고 human approval도 수행하지 않았다.

## 검증

| Command | Result |
| --- | --- |
| `PHASE7_TEST_FILE_ROOT=<authorized TEST_File> python -m pytest tests/rebaseline/test_collectors.py tests/rebaseline/test_sections.py tests/rebaseline/test_phase07_golden_v2_pilot.py -q` | `92 passed` |
| `PHASE7_TEST_FILE_ROOT=<authorized TEST_File> python -m pytest tests/rebaseline/test_collectors.py tests/rebaseline/test_sections.py tests/rebaseline/test_phase07_golden_v2_pilot.py tests/rebaseline/test_scan_ocr.py -q` | `180 passed` (v1.2 F1/F2 adversarial 포함) |
| `PHASE7_TEST_FILE_ROOT=<authorized TEST_File> python -m pytest tests/rebaseline/test_golden_v2_contract.py tests/rebaseline/test_golden_v2_dataset.py tests/rebaseline/test_phase07_golden_v2_pilot.py -q` | `144 passed` |
| `python -m pytest tests/rebaseline/test_resolver.py tests/rebaseline/test_validation.py -q` | `41 passed` |
| `PHASE7_TEST_FILE_ROOT=<authorized TEST_File> python -m pytest tests/rebaseline -q` | `413 passed` |
| `python -m pytest tests/test_common_normalization.py -q` | `6 passed` |
| `python -m compileall -q src/msds golden/v2 tests/rebaseline` / import+Draft 2020-12 schema+candidate JSON smoke | PASS |
| `git diff --check` | PASS |

OCR, AI, ODL, KOSHA, MES, DB, filename fallback, Golden v1 value copy, network/API, Vercel은 사용하지 않았다.

## verifier reopen history

초기 Fresh Verifier는 README가 candidate 부재라고 서술한 점과 pilot이 fence-blocked
failure behavior만 검증한 점(F1/F2)을 FAIL로 반환했다. 그 reopen은 당시
`FAILURE_BEHAVIOR` 후보에 대한 수정이었다. v1.1은 실제 local core fence/collector/
resolver/validation 경로를 다시 실행해 VALUE_TRUTH CANDIDATE로 교체했으므로, 이전
fence-blocked PASS 주장은 더 이상 현재 결과가 아니다. 이 v1.1 변경에 대한 신규
독립 verifier verdict는 아직 기록하지 않는다.

후속 Fresh Verifier는 (F1) repeated CAS/content band에서 전체 `lines`를 허용해
foreign column CAS가 들어갈 수 있는 범위 확장과, (F2) section 내부 반복만으로
top-right raster를 decorative logo로 간주한 조건을 FAIL로 반환했다. v1.2는 F1의
전체 폭 확장을 제거하고 explicit content-before-CAS header column으로만 역방향
표 relation을 허용했다. 별도 foreign CAS column은 SectionInput과 collector에서
제외하는 회귀를 추가했다. F2는 동일 geometry와 동일 embedded-image xref가 문서의
모든 page에 있고 각 page의 관측 text보다 위인 경우(1pt PDF bbox rounding 허용)만
반복 header logo로 허용한다. 동일 geometry라도 서로 다른 raster, 또는 본문 위치인
큰 raster는 `SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED`로 남는 회귀를 추가했다.

R3 최종 Fresh Verifier는 최신 semantic worktree를 fresh READ_ONLY context에서 독립
검수하여 **PASS (findings 0)** 를 반환했다. F1의 foreign CAS column 배제와 F2의
document-wide 동일 geometry·동일 embedded-image xref 조건 및 서로 다른 raster의
mixed fence 회귀를 확인했다. 세 authorized local source의 SHA-256/portable reference,
TEXT-only core route와 external/Vercel 호출 0, Golden v2 schema/validator 무변경,
`git diff --check` 및 protected-scope diff 안전성도 확인했다. 이 verdict는
**REVIEW_READY** 상태를 확정할 뿐 M1 human review/approval을 대체하지 않으며,
merge는 실행하지 않았다.

`golden/v2/schema.json`, `golden/v2/validation.py`, `golden/v1`, PRD, TRD는 변경하지 않았다.
