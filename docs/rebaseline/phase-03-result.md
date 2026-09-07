# Phase 03 — Digital Collectors

## 목적과 경계

- Phase 2가 만든 confirmed, `TEXT` `SectionInput`만 받아 Section 1 제품명 및 Section 3 CAS/함유량의 **후보와 원문 evidence**를 수집한다.
- Collector는 filename, 다른 section, OCR/Vision AI, KOSHA/MES, 외부 DB/API를 읽지 않는다. Resolver, Validator, 최종 Result 및 `ComponentPair`도 생성하지 않는다.
- `PARTIAL` 및 `NOT_FOUND` fence는 기존 `build_section_input`에서 차단되므로 collector에 전달되는 경로가 없다. public collector는 추가로 `SectionInput` 타입, 해당 section 번호 및 `TEXT` capability만 수용한다.

## 후보 계약

- `ProductCollection`은 순서가 있는 `ProductCandidate`를 담는다. 후보는 raw 원문(여러 줄·공백·괄호·모델·Grade·농도 포함), 별도 comparison normalized 값, source order, line evidence를 보존한다. 명시 product label이 없으면 빈 후보 집합이다.
- `Section3Collection`은 순서가 있는 `Section3BlockCandidate`를 담는다. 각 block/row는 evidence, `CasCandidate` occurrence(중복 포함), `ContentCandidate`를 보존한다. CAS가 없는 content-only row는 block 후보가 아니다.
- CAS raw substring은 Unicode dash/공백만 기존 pure normalization으로 비교값을 만들며 check digit 실패도 raw·evidence와 함께 보존한다. date와 EC number는 후보로 승격하지 않는다.
- 함유량 raw는 부등호, range, `Rem.`, `Balance`, `wt%`, `vol%` 의미를 보존한다. 하나의 block에 CAS 여러 개와 content 하나가 있어도 source relation만 남기며 pairing은 하지 않는다.

## 외부 호출과 검증

- Collector 모듈은 로컬 dataclass/정규식/기존 pure normalization만 사용하며 네트워크·DB·외부 API 호출 경로가 없다. synthetic `SectionInput`과 PDF fence fixtures가 이를 범위 내에서 검증한다.
- `python -m pytest tests/rebaseline -q`: **111 passed** (pytest cache 쓰기 권한 경고 1건).
- `python -m pytest tests/test_common_normalization.py -q`: **6 passed in 0.84s**.
- `python -m compileall -q src/msds golden/v2`: **passed**.
- 지정 import smoke test: **`PyMuPDF 1.27.2; imports OK`**.
- `git diff --check`: **passed**. `pdf_io.py`의 source diff는 없고 (`git diff --exit-code -- src/msds/pdf_io.py`), Phase 2 보호 파일을 변경하지 않았다.
- field-sample PDF corpus 검증은 이번 단계 범위에 포함하지 않았으며, synthetic fixture로 후보 계약과 fence를 회귀 검증한다.
