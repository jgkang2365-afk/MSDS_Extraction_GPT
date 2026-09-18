# Phase 07 — Golden v2 regression pilot v1.3

## v1.3.1 product raw boundary + extension pilot

`024_★Sodium Hydroxide(NaOH).pdf`의 Section 1 제품명 뒤에 있던
whitespace-only visual continuation 한 건이 collector에 의해 product raw/evidence에
포함되는 결함을 확인했다. 이는 source value correction이 아니라
**COLLECTOR_BOUNDARY_FIX**다. collector는 이제 whitespace-only cell을 raw join과
provenance에서 함께 제외하며, non-empty multiline product line의 raw whitespace와
source order는 보존한다. Sodium machine proposal의 product raw는
`수산화나트륨[수산화나트륨[Sodium Hydroxide]]`이며 trailing continuation은 없다.

동일 audit에서 `CAS 번호 또는 식별번호` + `함유량(%)` 표 header가 기존 English-only
CAS header contract에 걸려, aligned bare concentration 대신 ingredient-name 내부 `%`를
관측할 수 있는 일반 table-context gap도 발견했다. collector는 explicit Korean CAS
identifier header를 같은 CAS/unit table header로 인식하고, 그런 table row에서는
unit-aligned concentration cell만 채택하도록 보완했다. 따라서 `011`의 `40 ~ 50`,
`10 ~ 25`, `16 ~ 21`, `11 ~ 14`와 `020`의 `100.0`은 source row/column evidence로
각 CAS에 paired된다. 이 역시 document/CAS/product exception이 아니다.

adversarial collector contract는 inline/separate-cell product, meaningful multiline,
whitespace-only trailing/empty visual row, 다음 company field, 괄호·농도·Unicode를
포함한다. 이 변경은 product 전체에 `.strip()`을 적용하지 않는다.

추가 authorized local source 10건(`005`, `007`, `011`, `020`, `027`, `030`, `032`,
`036`, `040`, `043`)은 OCR/AI/외부 호출 없이 layout, capability, Section 1/3 fence,
local TEXT core를 감사했다. 전체 SHA·page 수·machine proposal/evidence는 ignored
local review packet에만 기록했다. 이 결과는 Golden truth나 human review가 아닌
`MACHINE_DIAGNOSTIC_ONLY`다.

| ID | Capability / route | Section 1 | Section 3 | 결과 |
| --- | --- | --- | --- | --- |
| 005 | `IMAGE_ONLY`, OCR deferred | NOT_FOUND | NOT_FOUND | `DEFERRED_OCR_REQUIRED` |
| 007 | digital text, multi-SDS | CONFIRMED | CONFIRMED | 3 isolated SDS results; CAS/content pairs PASS |
| 011 | TEXT core | CONFIRMED | CONFIRMED | 4 components, `PASS` |
| 020 | TEXT core | CONFIRMED | CONFIRMED | 1 component, `PASS` |
| 027 | digital text | NOT_FOUND | NOT_FOUND | `GENERALIZATION_GAP`: `항 N:` heading / `a.` label grammar |
| 030 | digital text | NOT_FOUND | NOT_FOUND | `GENERALIZATION_GAP`: `항 N:` heading, split CAS header, concentration-limit context |
| 032 | digital text | NOT_FOUND | NOT_FOUND | `GENERALIZATION_GAP`: `항 N:` heading, split CAS header, concentration-limit context |
| 036 | digital text | CONFIRMED | CONFIRMED | product and 9 components, `PASS` |
| 040 | digital text | CONFIRMED | PARTIAL | fail-closed deferred |
| 043 | digital text | PARTIAL | PARTIAL | fail-closed deferred |

`007`은 page 0/18/39에서 독립 Section 1이, page 1/19/40에서 독립 Section 3이
반복되어 하나의 PDF에 최소 세 SDS sequence가 존재한다. 대표 product 선택, first/last
selection, sequence merge는 현 canonical policy에 없으므로 수행하지 않았다.

추가 10개 중 confirmed Section 1/3 TEXT core complete route는 2건뿐이다. `027`/`030`/`032`는
digital text지만 `항 N:` heading을 인식하지 못한다. `030`/`032`에는 split CAS header와
본 함유량과 농도 한계 문구를 분리해야 하는 추가 context contract도 있다. 부분 heading
인식만으로 product continuation 또는 concentration을 추측하지 않았고, 이는 후속
`GENERALIZATION_GAP`으로 남겼다. OCR로 표본을 보충하지 않았으므로 5개 TEXT corpus gate는
충족하지 못했다. 따라서 이 extension은 다형식 일반화 완료 증거나 merge/freeze-ready 판정이
아니며, `MULTI_SDS_POLICY_REQUIRED`, `GENERALIZATION_GAP`, `INSUFFICIENT_TEXT_CORPUS`를 남긴다.

Human direct-source review 사실은 보존하되 Golden promotion은 의도적으로 연기했다.
세 Golden v2 case는 계속 `VALUE_TRUTH` / `CANDIDATE`이며
`source_transcription`, `HUMAN_REVIEWED`, `APPROVED`는 모두 0이다.

## 결과

사용자가 제공한 세 authorized local PDF를 외부 전송 없이 현재 Phase 1--5 TEXT
core로 처리했다. local 처리에서 SHA-256을 계산해 candidate/manifest 값으로
기록했으며, 테스트는 source bytes와 hash를 비교한다. portable corpus에는 source
root 이름과 파일명만 기록했다. 세 canonical file은 모두 `VALUE_TRUTH`/
`CANDIDATE`이며 human provenance, `source_transcription`, `HUMAN_REVIEWED`,
`APPROVED`는 없다.

| Candidate | Portable source / locally computed SHA-256 | v1.2 이전 | v1.3 actual local core |
| --- | --- | --- | --- |
| `008-sarapong.candidate.json` | `phase7-test-file/008_★msds_사라퐁.pdf` / `2e684040b696104a85d5368adb528e4f0a2468472daaac51a4c62e18fe1eee2d` | 2 CAS가 `INVALID/REVIEW`, CAS uncertainty 2건 | `7732-18-5` `60 ~ 70`, `1310-73-2` `< 1` 모두 `FOUND/PAIRED`; CAS-less content는 component 미생성; `PASS`, uncertainty 0 |
| `015-teca-biome.candidate.json` | `phase7-test-file/015_★1005_TECA-BIOME™_GHS_MSDS개정_(KOR)_ICBIO.pdf` / `88fe15b8c8f6741905543af9523ab902bb4b4f1727e8479a191835a0a9e4ed0b` | 12 component 중 `6920-22-5`만 `INVALID/REVIEW`, uncertainty 1건 | source order 12개 전부 `FOUND/PAIRED` (6920 포함); `92128-87-5`·`308068-11-3`은 각각 shared source-row `1.00`; `PASS`, uncertainty 0 |
| `024-sodium-hydroxide.candidate.json` | `phase7-test-file/024_★Sodium Hydroxide(NaOH).pdf` / `25811ad3e84472d9f8b244a8e391ca66af2714d24a8021efb1e3908b290780c6` | 2 CAS가 `INVALID/REVIEW`, uncertainty 2건 | `1310-73-2` `92-100％`, `7732-18-5` `8-0％` 모두 `FOUND/PAIRED`; raw는 변경하지 않고 fence 밖 값 누출 없음; `PASS`, uncertainty 0 |

### v1.3 actual component output

| Candidate | CAS / source-order component | content raw | final |
| --- | --- | --- | --- |
| Sarapong | `7732-18-5` | `60 ~ 70` | `FOUND/PAIRED` |
| Sarapong | `1310-73-2` | `< 1` | `FOUND/PAIRED` |
| TECA-BIOME™ | `84696-21-9`, `96507-89-0`, `98-92-0`, `25265-71-8` | `54.98`, `10.0`, `5.00`, `5.00` | all `FOUND/PAIRED` |
| TECA-BIOME™ | `6920-22-5`, `81-13-0` | `2.00`, `1.00` | all `FOUND/PAIRED` |
| TECA-BIOME™ | `92128-87-5`, `308068-11-3` | `1.00`, `1.00` | all `FOUND/PAIRED`; same `section3-row-9`, shared source-row content |
| TECA-BIOME™ | `16830-15-2`, `18449-41-7`, `464-92-6`, `53238-80-5` | `0.40`, `0.30`, `0.30`, `0.01` | all `FOUND/PAIRED` |
| Sodium Hydroxide | `1310-73-2` | `92-100％` | `FOUND/PAIRED` |
| Sodium Hydroxide | `7732-18-5` | `8-0％` | `FOUND/PAIRED` |

## v1.3 변경과 제거된 false blocker

- `normalize_cas`는 raw/dash whitespace/shape/checksum만 책임진다. ISO 형식처럼
  보인다는 전역 거부를 제거했으며 특정 CAS whitelist, fuzzy correction, external
  lookup을 추가하지 않았다.
- Collector는 `Revision`, `Issue`, `Prepared Date`, 작성일·개정일·제조일 등의
  날짜 metadata 문맥을 명시적으로 제외한다. label/value가 분리된 경우에도 바로
  다음의 aligned value cell만 제외하며, 이후 genuine CAS 행까지 상태를 전파하지
  않는다. 같은 행의 각 date label은 자체 value cell로 완료 여부를 독립 판정하므로,
  한 sibling field의 완료가 label-only sibling의 다음 행 차단을 해제하지 않는다.
  기존 explicit EC column/prefix 차단은 유지한다.
- explicit Section 3 `CAS No: 2000-01-3`은 checksum-valid이면 수집한다. 동일
  문자열이 날짜 metadata 문맥이면 수집하지 않는다. 이 CAS label 우선권은 후보의
  local field에만 적용되므로, 같은 행에서 뒤따르는 날짜 field의 값까지 허용하지
  않는다.
- 제거된 false blocker는 세 pilot의 `CAS_READ_UNCERTAIN` 다섯 건이다. Sarapong의
  CAS-less content 제외는 정상적인 구조 규칙이며 error/blocking finding으로 남기지
  않고 component로도 승격하지 않는다.
- candidate JSON은 실제 machine proposal과 blocker 상태만 갱신했다. human/approved/
  transcription 값은 추가하거나 변경하지 않았다.

## v1.3 verifier reopen history

R1--R6 Fresh Verifier 재오픈은 date-like CAS의 문맥 책임을 넓히되 genuine CAS를
차단하지 않는지 단계적으로 검증한 결과다. 각 reopen의 finding과 최종 반영 범위는
다음과 같다.

| Reopen | finding | final semantic worktree 반영 |
| --- | --- | --- |
| R1 | Korean `작성일자`/`개정일자`/`제조일자`, 날짜 표기 및 split label/value 문맥이 부족 | 같은 행과 바로 다음 aligned value cell을 분리해 date metadata를 차단 |
| R2 | peer-cell 및 inline-pipe label이 행 결합 문자열에서 누락 | 개별 label cell과 후보 직전 prefix를 검사하고 `CAS No` local field를 우선 |
| R3 | split value의 whitespace와 행 내 stale CAS label 우선권 | whitespace-tolerant lexical match와 nearest local field context로 제한 |
| R4 | 이미 같은 행에서 소비된 date value가 다음 genuine CAS를 차단 | completed date field는 다음 row로 문맥을 전파하지 않음 |
| R5 | ISO가 아닌 일반 날짜/`not stated`가 completion으로 인식되지 않음 | inline 또는 바로 오른쪽 value cell의 일반 field completion을 처리 |
| R6 | row-wide completion이 label-only sibling의 차단을 해제 | 각 date label의 own value cell로 completion을 독립 판정 |

최종 R7 Fresh Verifier는 final semantic worktree를 fresh context에서 독립 검수해
**PASS (findings 0)** 를 반환했다. 이 verdict는 machine candidate의 현재 semantic
contract와 검증 결과에 대한 것이며, M1 human direct PDF review·transcription·approval을
대체하지 않는다.

## lifecycle / review gate

- 모든 `review_history`는 timestamp 없는 `CANDIDATE` action/status 한 건이다.
- `select_approved_cases(...) == ()`; human lifecycle status 수는 0이다.
- Human gate는 **REVIEW_READY**, M1(qualified human direct PDF review,
  transcription, lifecycle transition)은 **pending**이다. Machine `PASS`는 이 gate를
  대체하지 않는다.
- local-only 검토 패킷은 `.local-review/phase-07/`에 있고 `.git/info/exclude`에만
  등록했다. repository `.gitignore`는 바꾸지 않았다.
- merge, human approval, OCR, AI, ODL, KOSHA, MES, DB, filename fallback, Golden v1
  value copy, network/API, Vercel은 실행하지 않았다.

## 문서 결정

PRD는 변경하지 않았다. PRD 정책의 변경이 아니라 정규화/collector 책임 분리의 구현
정정이므로 TRD v1.1에 최소 동기화를 추가했다. 다형식 확장 원칙은
`multiformat-msds-generalization-guideline-v1.md`로 분리했으며, 이 가이드라인은
PRD/TRD보다 낮은 권위이고 3개 Korean digital PDF를 전 세계·다국어 완료 증거로
해석하지 않는다. repository root README는 이 Phase의 canonical 안내문이 아니며
수정하지 않았다.

## 검증

| Command | Result |
| --- | --- |
| `PHASE7_TEST_FILE_ROOT=<authorized TEST_File> python -m pytest tests/rebaseline/test_normalization_contract.py tests/rebaseline/test_collectors.py tests/rebaseline/test_phase07_golden_v2_pilot.py -q` | `112 passed` |
| `PHASE7_TEST_FILE_ROOT=<authorized TEST_File> python -m pytest tests/rebaseline/test_normalization_contract.py tests/rebaseline/test_collectors.py tests/rebaseline/test_sections.py tests/rebaseline/test_scan_ocr.py tests/rebaseline/test_phase07_golden_v2_pilot.py -q` | `244 passed` |
| `python -m pytest tests/rebaseline/test_resolver.py tests/rebaseline/test_validation.py tests/rebaseline/test_golden_v2_contract.py tests/rebaseline/test_golden_v2_dataset.py -q` | `184 passed` |
| `PHASE7_TEST_FILE_ROOT=<authorized TEST_File> python -m pytest tests/rebaseline -q` | `450 passed` |
| `python -m pytest tests/test_common_normalization.py -q` | `6 passed` |
| `python -m compileall -q src/msds golden/v2 tests/rebaseline` / import + Draft 2020-12 schema + candidate JSON smoke / production literal scan / `git diff --check` | PASS |

`golden/v2/schema.json`, `golden/v2/validation.py`, `golden/v1`, PRD는 변경하지 않았다.

## v1.3.2a-R2 — multi-page Section 3 column-signature continuation

### v1.3.2 R2 final implementation record

The former implementation-start statement (`COLUMN_SIGNATURE_CONTINUATION_READY`,
rebaseline **462**, Fresh Verifier **PASS**, blocking findings **0**, commit `2a5f45b`)
was not final-run evidence and is removed. This final record is limited to local
machine structural verification: no Golden promotion, human approval, merge, OCR, AI,
or external call occurred.

| Concern | Final generic change | Boundary retained |
| --- | --- | --- |
| Multi-SDS `007` | `locate_sds_segments` returns three independently bounded sequences while canonical `locate_sections` remains a single-result API | no cross-segment join or Golden schema change |
| Heading grammar | semantic locator accepts `항 N:` and `SECTION N:` | semantic fences remain mandatory; ambiguous starts fail closed |
| Table / named-field values | Korean CAS headers, header-aligned multiline comparator values, local flexible named fields, and Korean/English note boundaries are recognized | EC/index/classification/foreign values and note-separated values do not promote |
| R2 continuation | transient CAS/content geometry carries only across the current Section 3 table | `040` has four paired rows and EC/exposure promotion is zero |

### v1.3.2 final actual local PDF results

These final results supersede the earlier extension-pilot diagnostic table for the same
IDs. All sources were read from authorized local `TEST_File`; OCR, AI, network, and
external calls were not used.

| ID | Final local result |
| --- | --- |
| `005` | `IMAGE_ONLY`; Section 1/3 are both `FENCE_NOT_FOUND` (`SECTION_START_NOT_FOUND`); OCR remains deferred. |
| `007` | `TEXT`; canonical Section 1/3 are confirmed. Three independent segment results are PC100(크리어), PC420(페퍼), and PC220(오크), each with exact source-local CAS/content pairs and `PASS` quality. A checksum-valid CAS substring inside the proven CAS/identifier cell is retained; adjacent `/ KE-*` text is neither interpreted nor output. |
| `011` | `PASS`: `64742-47-8=40 ~ 50`, `64742-54-7=10 ~ 25`, `74-98-6=16 ~ 21`, `106-97-8=11 ~ 14`. |
| `020` | `PASS`: `122-99-6=100.0`. |
| `027` | confirmed fences; the CAS-only component is retained as `90-80-2` `FOUND` with empty `NOT_STATED` content. Its intrinsic `pair_status` is `NOT_STATED` and local quality is `PASS`; neither means the CAS was rejected or that content was invented. |
| `030` | `PASS`: `7647-01-0` raw `>= 35 - < 40 %`, normalized `>=35~<40%`. |
| `032` | `PASS`: `7697-37-2` raw `>= 70 - < 75 %`, normalized `>=70~<75%`; Section 3 has a decorative-logo reason. |
| `036` | Section 1/3 are confirmed. Product is `아이생각수성내부프로 (M-BASE)`; all nine Section 3 rows pair: `7732-18-5=40 이상 ~\\n50 % 미만`; `14807-96-6=20 이상 ~\\n30 % 미만`; `1317-65-3=10 이상 ~\\n20 % 미만`; `26636-08-8`, `92704-41-1`, `13463-67-7`, `471-34-1`, `57-55-6` each `=1 이상 ~\\n10 % 미만`; `108-01-0=0.1 이상 ~\\n1 % 미만`. |
| `040` | `PASS`: `67-56-1`, `56-81-5` raw `>= 45 - < 50 %`; `660-68-4`, `17372-87-1` raw `< 1 %`; all paired. |
| `043` | `PASS`: product `Glycine`; `56-40-6` raw `98.5～101.5`, normalized `98.5~101.5`. |

Section 3의 다음 페이지가 표 header를 반복하지 않는 경우에도, 시작 페이지의 명시적
CAS/content header와 column geometry로만 만든 locator-internal transient signature를
carry-forward한다. `PageRegion.allowed_rects`의 기존 multi-rect 표현을 사용하여
CAS/content source line 전체의 token-union rect만 포함한다. 따라서 page break는 section
end가 아니지만, Section 4 heading은 계속 hard stop이고 exposure/independent columns는
fence에 포함되지 않는다.

- 040 Giemsa: 4개 source pair (`67-56-1`, `56-81-5`, `660-68-4`, `17372-87-1`)가
  continuation page에서 유지되며 validation PASS다.
- 036 secondary probe: continuation page의 `108-01-0` 및 `0.1 이상 ~ 1 % 미만`
  source tokens가 multi-rect SectionInput에 유지되며, raw line break를 보존한 comparator
  normalization과 confirmed Section 1 product resolve가 PASS다.
- synthetic regression은 (A) repeated English header/continued heading, (B) Korean
  headerless continuation, signature 밖 foreign independent table, signature 안의
  EC/exposure numeric source text를 분리한다. EC/exposure text가 `SectionInput`에
  남더라도 CAS/component promotion은 0이며, geometry가 다른 duplicate Section 3
  heading은 `SECTION_START_AMBIGUOUS`로 fail-closed한다.
- 모델, PageRegion, SectionInput, Golden schema/validator 및 human lifecycle은 변경하지
  않았다. 이 결과는 machine structural verification이며 human Golden promotion이 아니다.

## v1.3.3 — CAS-column proof closure

검증 기준 HEAD는 `2ecbb61aea3e7d4baa5af233754a7fe79913b5ef`이며, 이 closure는
header-proven CAS/content table에서 **CAS candidate admission 자체**가 proven CAS
column을 따르도록 보완한다. 즉 ingredient, reference, exposure, note 열의
checksum-valid CAS-shaped text는 CAS candidate가 아니다. CAS/identifier 열 안에서는
유효 CAS만 후보가 되며 `KE-*`나 임의 identifier는 해석하거나 출력하지 않는다.

- CAS column 외 valid CAS promotion: `0`
- mixed identifier cell: valid CAS만 유지, KE/generic identifier output `0`
- checksum-invalid CAS: valid CAS로 자동 승격하지 않음
- CAS/identifier 또는 content cell이 blank/unreadable/identifier-only인 row도 이미
  증명된 표 geometry를 잃지 않아 다른 열의 CAS를 승격하지 않음
- CAS/content band의 설명문은 header continuation 근거가 아니므로 bare numeric value를
  함유량으로 승격하지 않음

split CAS header는 adjacent same-band fragment와 content header가 있어야 하며, distant,
wrong-column, unrelated-intervening fragment는 proof를 만들지 않는다. Multi-SDS
adversarial regression은 TOC/body reference false positive, empty page, page-number reset,
same-page 다음 SDS를 product와 source-local CAS/content pair까지 검증한다.

실제 local TEXT 결과는 유지됐다: `007`은 3 independent segment와 exact PAIRED CAS/content,
`036`은 `아이생각수성내부프로 (M-BASE)` 및 9 components, `043`은 `Glycine` /
`56-40-6` / raw `98.5～101.5` / normalized `98.5~101.5`이다. `008`, `015`, `024`,
`011`, `020`, `027`, `030`, `032`, `040`의 canonical 보호 회귀도 통과했다.

| Validation | Final local result |
| --- | --- |
| focused + actual Phase 7 Golden | `198 passed` (최종 full suite에 포함) |
| `python -m pytest tests/rebaseline -q` | `497 passed`, required skips `0` |
| `python -m pytest tests/test_common_normalization.py -q` | `6 passed` |
| compileall / import / Golden schema + candidate smoke / `git diff --check` | PASS |
| Fresh Verifier | READ_ONLY, PASS, blocking findings `0` |

Golden promotion, `source_transcription`, `HUMAN_REVIEWED`, `APPROVED`, approved selector,
Golden schema/validator, PRD, TRD public contract는 모두 변경하지 않았다. OCR, AI/API,
ODL, KOSHA, MES, DB, Vercel, internet PDF download는 모두 `0`이다. CI는 실행하거나
조회하지 않았으므로 `CI 없음`으로 기록한다. PR은 Draft/Open 및 human Golden approval
전 상태를 유지하며 `merge-ready`로 표현하지 않는다.
