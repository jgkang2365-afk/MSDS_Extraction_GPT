# Phase 03 — Digital Collectors

## 목적과 경계

- Phase 2가 만든 confirmed, `TEXT` `SectionInput`만 받아 Section 1 제품명 및 Section 3 CAS/함유량의 **후보와 원문 evidence**를 수집한다.
- Collector는 filename, 다른 section, OCR/Vision AI, KOSHA/MES, 외부 DB/API를 읽지 않는다. Resolver, Validator, 최종 Result 및 `ComponentPair`도 생성하지 않는다.
- `PARTIAL` 및 `NOT_FOUND` fence는 기존 `build_section_input`에서 차단되므로 collector에 전달되는 경로가 없다. public collector는 추가로 `SectionInput` 타입, 해당 section 번호 및 `TEXT` capability만 수용한다.

## 후보 계약

- `ProductCollection`은 순서가 있는 `ProductCandidate`를 담는다. 후보는 raw 원문(여러 줄·공백·괄호·모델·Grade·농도 포함), 별도 comparison normalized 값, source order, line evidence를 보존한다. 명시 product label이 없으면 빈 후보 집합이다.
- `Section3Collection`은 순서가 있는 `Section3BlockCandidate`를 담는다. 각 block/row는 evidence, `CasCandidate` occurrence(중복 포함), `ContentCandidate`를 보존한다. CAS가 없는 content-only row는 block 후보가 아니다. Header에서 관측한 단위는 raw에 추정 결합하지 않고 `unit_context_raw` 및 그 evidence로 별도 보존한다. 직접 기재된 `50 ppm`·`10%`는 raw 자체가 단위 증거이므로 header-derived context는 `None`·빈 evidence다.
- CAS raw substring은 Unicode dash/공백만 기존 pure normalization으로 비교값을 만들며 check digit 실패도 raw·evidence와 함께 보존한다. date와 EC number는 후보로 승격하지 않는다. 명시 `EC No.`/`EC Number`와 `CAS`가 함께 있는 표에서는 후속 정렬 행의 EC 열만 제외하며, 실제 CAS 열은 그대로 수집한다.
- 함유량 raw는 부등호, range, `Rem.`, `Balance`, `wt%`, `vol%`, `ppm` 의미를 보존한다. bare number/range는 명시 CAS header와 단위 header가 같은 표의 선행 행에 있고, 해당 CAS/단위 열이 구조적으로 정렬된 경우에만 content 후보가 되며, 설명문·다른 표의 unit text는 재사용하지 않는다. header 단위는 raw에 붙이지 않는다. 하나의 block에 CAS 여러 개와 content 하나가 있어도 source relation만 남기며 pairing은 하지 않는다.
- Section 1은 Product/Product name/Product identifier 및 제품명/제품 식별자의 명시 라벨만 수집하고, inline·동일 행 우측 cell·아래 multiline value를 원문 그대로 보존한다. 모든 시작 형식은 다음 structural field(Company/Supplier/회사명 등)에서 multiline 수집을 멈추며, inline 값은 같은 행의 별도 우측 cell을 중복 수집하지 않는다.
- CAS와 content candidate의 `source_order`는 page → y → x → substring position의 실제 관측 순서를 따른다. block 순서는 pairing이 아니다.

## 외부 호출과 검증

- Collector 모듈은 로컬 dataclass/정규식/기존 pure normalization만 사용하며 네트워크·DB·외부 API 호출 경로가 없다. synthetic `SectionInput`과 PDF fence fixtures가 이를 범위 내에서 검증한다.
- `python -m pytest tests/rebaseline/test_collectors.py -q`: **33 passed in 1.79s**. synthetic 및 실제 PyMuPDF PDF의 Section 3 EC/CAS/Content 별도 셀 표, Section 1 inline 및 동일 행 label/value 뒤 multiline·company 종료 회귀를 포함한다.
- `python -m pytest tests/rebaseline -q`: **132 passed in 7.77s**.
- `python -m pytest tests/test_common_normalization.py -q`: **6 passed in 1.04s**.
- `python -m compileall -q src/msds golden/v2`: **passed**.
- 지정 import smoke test (`models`, `normalization`, `pdf_io`, `sections`, `collectors`): **`imports OK`**.
- `git diff --check`: **passed**. 지정한 네 파일만 변경되었고 Phase 2 보호 파일은 변경하지 않았다.
- field-sample PDF corpus 검증은 이번 단계 범위에 포함하지 않았으며, synthetic fixture로 후보 계약과 fence를 회귀 검증한다.
