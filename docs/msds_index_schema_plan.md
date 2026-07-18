# MSDS 측정인자 데이터셋 스키마 및 구현 계획

## 1. 설계 원칙

- CAS는 후보 그룹 검색키이며 profile 고유키가 아니다.
- 모든 최종 선택, 저장, 정렬 및 출력은 `profile_id`를 기준으로 한다.
- 동일 CAS 다중 행은 자동 병합하거나 부모·자식으로 자동 확정하지 않는다.
- 직접 검출 후보와 공정 추천은 별도 컬렉션 및 `selection_source`로 유지한다.
- Excel 원본의 모든 행·열·시트/행 번호를 추적 가능하게 보존한다.
- 데이터에 없는 법적·분석 값을 생성하지 않는다.
- 관계 및 규칙은 검토상태와 근거를 가져야 하며 미승인 데이터는 자동 추천에 사용하지 않는다.

## 2. 데이터 층

1. `substance_profiles`: 선택 가능한 측정인자와 분석·법적 속성
2. `substance_relations`: profile 간 정적 관계
3. `recommendation_rules`: 공정·작업 조건에 따른 동적 추천
4. `substance_aliases`: 명칭/CAS 외 검색과 매핑
5. 변경·검토 상태: 각 테이블의 상태·버전·근거 및 별도 change log

## 3. `substance_profiles`

| 필드 | 형식/제약 | 설명 |
|---|---|---|
| profile_id | string PK, immutable | `SP_` + UUID. 정렬·명칭 변경과 무관 |
| parent_profile_id | nullable FK | 승인된 부모만 연결 |
| cas_no | nullable string | 표준 CAS 한 개. 원문은 별도 보존 |
| cas_raw | nullable string | `14808-60-7 등` 같은 원문 |
| canonical_name | required string | GUI/출력 표준명 |
| base_name | required string | 검토된 기본명. 괄호 자동 확정 금지 |
| form_code | nullable enum/code | 금속분진, 흄, 가용성 등 코드 |
| form_name | nullable string | 사용자 표시 성상 |
| category_code | required string | 분진/금속/유기 등 분류 코드 |
| category_name | required string | 현재 V24 대분류 표시명 |
| category_order | integer | 정렬 1차 키 |
| sort_group | string | 정렬 2차 키, 예: `3M-20` |
| sort_order | integer | 정렬 3차 키, 예: `140` |
| legacy_sort_code | string | V24 정렬코드 원문. PK 아님 |
| selectable | boolean | 부모/안내 전용 profile 비선택 처리 가능 |
| active | boolean | 논리 삭제 |
| analysis_method | nullable string | 분석방법 |
| sample_count | nullable number/string | V24 시료수 보존을 위해 추가 |
| sampling_media | nullable string | 실무용 매체 |
| sampling_media_reference | nullable string | 원본 매체 |
| preferred_flow_rate | nullable structured/raw | 적정유속 |
| flow_rate | nullable structured/raw | 허용 유속 |
| minimum_air_volume_l | nullable number/raw | 최소 공기량 |
| maximum_air_volume_l | nullable number/raw | 최대 공기량 |
| sampling_volume_or_time | nullable string | 기존 요청 필드; 통합 표시값 |
| desorption_solvent | nullable string | V24 손실 방지를 위해 추가 |
| transport_method | nullable string | 운반방법 |
| storage_method | nullable string | 보관방법 |
| method_summary | nullable string | Method |
| method_kosha/niosh/osha/other | nullable string | 분석 근거별 방법 |
| twa | nullable structured | raw/value/unit/basis |
| stel | nullable structured | raw/value/unit/basis |
| unit | nullable string | 단순 호환 필드. 실제 단위는 기준별 보존 |
| management_target | nullable boolean | 측정 대상 |
| special_management | nullable boolean | 특별관리 |
| permit_required | nullable boolean | 허가대상 |
| health_exam_target | nullable boolean | 특검 대상 |
| carcinogenicity | nullable string | V24 코드 원문/정규화값 |
| germ_cell_mutagenicity | nullable string | V24 생식세포 열 |
| reproductive_toxicity | nullable string | V24 생식독성 열 |
| analysis_available | nullable status | 분석가능여부 |
| analysis_notes | nullable string | 분석 특이사항 |
| limit_of_detection | nullable structured/raw | LOD |
| review_status | enum | `AUTO_MIGRATED`, `REVIEW_REQUIRED`, `APPROVED`, `REJECTED` |
| source_version | string | `V24` 등 |
| source_row_id | required immutable string | 원본 lineage 식별자 |
| source_sheet | string | `Sheet1` |
| source_row_number | integer | 최초 원본 행 번호 |
| source_row_hash | string | raw 행 변경 탐지 |
| notes | nullable string | 일반 참고 |
| source_extra | nullable object | 미매핑 원본 열 보존 |

`twa`, `stel`, 유속과 LOD는 초기에 raw 문자열을 반드시 함께 저장한다. 파싱 실패를 빈값으로 바꾸지 않는다.

## 4. `substance_relations`

| 필드 | 형식/제약 | 설명 |
|---|---|---|
| relation_id | string PK | `REL_` + UUID |
| source_profile_id | FK required | 관계 출발 profile |
| target_profile_id | FK required | 관계 대상 profile |
| relation_type | enum | 아래 유형 |
| bidirectional | boolean | 역방향 적용 여부 |
| allow_source_only | boolean | 소스만 선택 가능 |
| allow_target_only | boolean | 대상만 선택 가능 |
| allow_multiple | boolean | 복수 선택 허용 |
| default_selected | boolean | 추천 기본 체크. 초기 기본값 false |
| recommendation_level | enum | `weak`, `medium`, `strong`, `required_review` |
| require_user_confirmation | boolean | 공정 생성 추천은 기본 true |
| active | boolean | 활성 여부 |
| guide_message | string | GUI 안내 |
| evidence_note | string | 업무/법령/분석 근거 |
| review_status | enum | 승인 전 실행 제외 |
| version | string | 관계 버전 |
| source_reference | string | V24/VBA/코드/외부 근거 위치 |

지원 유형:

- `SAME_CAS_VARIANT`
- `PARENT_CHILD`
- `PROCESS_GENERATED`
- `CO_EXPOSURE`
- `ALTERNATIVE`
- `MULTI_SELECT`
- `ANALYTICAL_RELATION`
- `MANUAL_REVIEW`

동일 profile 쌍에 여러 관계 유형이 있을 수 있으므로 유일성은 `(source_profile_id, target_profile_id, relation_type, version)`으로 관리한다.

## 5. `recommendation_rules`

| 필드 | 형식/제약 | 설명 |
|---|---|---|
| rule_id | string PK | `RULE_` + UUID |
| source_profile_id | nullable FK | 특정 출발 profile |
| source_cas | nullable string | profile 미확정 입력용 후보 조건 |
| condition_type | enum | PROCESS_NAME, WORK_METHOD, GENERATION_MECHANISM, RAW_MATERIAL_FORM, HIGH_HEAT, WELDING, THERMAL_CUTTING, GRINDING, CRUSHING, PLATING, MIXING, PRODUCT_FORM, USER_SELECTION, ALREADY_SELECTED |
| condition_value | string/object | 조건 값 |
| match_operator | enum | equals, contains, regex, in, true, false |
| condition_group | string | AND/OR 복합 조건 그룹 |
| condition_operator | enum | AND/OR |
| target_profile_id | FK required | 추천 profile |
| relation_type | enum | 주로 PROCESS_GENERATED/CO_EXPOSURE/ANALYTICAL_RELATION |
| recommendation_level | enum | weak/medium/strong |
| default_selected | boolean | 초기에는 false 권장 |
| allow_multiple | boolean | 크롬 등 true |
| require_user_confirmation | boolean | 기본 true |
| exclusion_condition | nullable object/string | 제외 조건 |
| guide_message | string | 사용자 표시 이유 |
| evidence_note | string | 근거 |
| active | boolean | 활성 여부 |
| review_status | enum | 승인 전 실행 제외 |
| version | string | 규칙 버전 |

단순 1행 1조건만으로 복합 공정을 표현하기 어려우므로 `condition_group`, `condition_operator`, `match_operator`를 필수 확장으로 권고한다.

## 6. `substance_aliases`

| 필드 | 형식/제약 | 설명 |
|---|---|---|
| alias_id | string PK | `ALS_` + UUID |
| alias_text | required string | 원문 별칭 |
| normalized_alias | indexed string | 공백/대소문자 정규화 검색키 |
| target_profile_id | nullable FK | 특정 profile 대상 |
| target_parent_id | nullable FK | 후보 그룹 대상 |
| alias_type | enum | official, common, english, abbreviation, legacy, process_term |
| language | string | ko/en 등 |
| priority | integer | 충돌 시 후보 순위. 자동확정 근거는 아님 |
| active | boolean | 활성 여부 |
| review_status | enum | 승인 상태 |
| source_reference | string | 출처 |

`target_profile_id`와 `target_parent_id` 중 정확히 하나만 값이 있도록 제약한다.

## 7. 변경·검토 상태

별도 `dataset_changes` 또는 manifest에 다음을 둔다.

- dataset_version, source_version, built_at, builder_version
- source_workbook_sha256, row_count, profile_count, relation_count, rule_count, alias_count
- review_required_count, approved_count, validation_error_count
- change_id, entity_type, entity_id, changed_fields, before_hash, after_hash, reviewer, reviewed_at, review_note

운영 GUI는 `APPROVED`이고 `active=true`인 관계/규칙만 자동 추천에 사용한다.

## 8. profile ID와 부모·자식 규칙

### profile ID

1. bootstrap 변환에서 각 V24 행에 opaque UUID 기반 `profile_id`를 한 번 발급한다.
2. 발급 ID를 관리 원본 Excel의 새 `profile_id` 열 또는 별도 ID registry에 영구 저장한다.
3. 이후 빌드는 기존 ID가 없으면 자동 재생성하지 않고 검증 오류로 중단한다.
4. 정렬코드, CAS, 명칭, 행 번호는 ID 생성 후 변경되어도 profile ID를 바꾸지 않는다.
5. 사람이 읽는 코드는 별도 `profile_code`로 둘 수 있으나 PK로 사용하지 않는다.

초기 bootstrap의 재현성만 위해 namespace UUID와 `V24|Sheet1|최초 정렬코드|최초 명칭|CAS raw`를 사용할 수 있다. 이 문자열은 ID 발급용 최초 migration identity일 뿐, 이후 ID 재계산 입력으로 사용하면 안 된다.

### 부모·자식

- 동일 CAS 또는 최단 명칭만으로 부모를 정하지 않는다.
- 자동 분석은 `parent_candidate_group`만 제시한다.
- 승인된 경우에만 `parent_profile_id`와 `PARENT_CHILD` 관계를 함께 저장한다.
- 부모 profile은 선택 가능 여부를 `selectable`로 명시한다. 대표명도 실제 측정인자이면 선택 가능할 수 있다.

## 9. 정렬 구조

V24 `3M-20-146` 예시:

- `category_order = 3`
- `sort_group = "3M-20"`
- `sort_order = 146`
- `legacy_sort_code = "3M-20-146"`

최종 정렬키:

```text
(category_order, sort_group, sort_order, canonical_name, profile_id)
```

`profile_id`는 완전 동률일 때만 안정적 tie-breaker로 사용한다. 정렬키는 ID 생성에 영향을 주지 않는다.

## 10. resolver 반환 계약

```json
{
  "detected": {
    "name": "Chromium compound",
    "cas_no": "7440-47-3",
    "content": "1~5%"
  },
  "candidates": [
    {
      "profile_id": "SP_...",
      "selection_source": "msds_detected",
      "selected": true,
      "reason": "CAS 후보 그룹"
    }
  ],
  "related_recommendations": [
    {
      "profile_id": "SP_...",
      "selection_source": "process_recommended",
      "rule_id": "RULE_...",
      "recommendation_level": "strong",
      "default_selected": false,
      "require_user_confirmation": true,
      "reason": "용접·고열 산화 조건에서 6가크롬 생성 가능성"
    }
  ],
  "selection_mode": "multiple"
}
```

허용 `selection_source`:

- `msds_detected`
- `same_cas_variant`
- `process_recommended`
- `manually_added`
- `restored_from_saved_selection`

저장 선택은 `profile_id`, `selection_source`, `rule_id`, 사용자 확인 시각을 함께 보존한다.

## 11. JSON과 SQLite 비교

| 항목 | JSON | SQLite |
|---|---|---|
| 1차 구현/검토 | 단순하고 diff가 쉬움 | schema/migration 작업 필요 |
| 297행 규모 조회 | 충분히 빠름 | 충분히 빠름 |
| 관계 무결성 | validator가 별도 보장 | FK/UNIQUE/CHECK로 강제 가능 |
| 복합 조건/색인 | 코드에서 순회 | 인덱스와 질의에 유리 |
| 사람이 검토 | 텍스트 diff 용이 | 전용 조회 도구 필요 |
| 동시 갱신/트랜잭션 | 취약 | 강함 |
| 배포 | 파일 하나로 간단 | 파일 하나지만 migration 필요 |

### 권고

초기 GUI adapter와 데이터 검토 단계는 **정규화된 JSON**을 우선한다. 현재 297행 규모에서는 성능보다 추적성과 리뷰 용이성이 중요하다. 다만 원본 Excel의 4개 논리 테이블이 확정되고 규칙/관계 편집과 변경 이력이 증가하면 SQLite가 더 적합하다.

권장 경로는 Excel → 검증된 canonical JSON → 필요 시 같은 builder 모델에서 SQLite 동시 생성이다. JSON과 SQLite를 각각 수작업 관리하지 않는다.

SQLite 전환 기준 예시:

- 관계/규칙이 수천 건 이상
- 다중 버전 동시 조회 또는 migration 필요
- FK 무결성과 트랜잭션이 운영 요구가 됨
- GUI가 복합 조건을 빈번하게 질의함

## 12. 손실 없는 1차 변환기 설계

### 단계

1. workbook hash와 모든 시트/행/열을 읽는다.
2. 각 원본 행에 `source_row_id`, source sheet/row, raw object를 만든다.
3. 36열을 `source_column_mapping.csv`에 따라 복사/파싱한다.
4. 정렬코드는 분해하되 원문을 유지한다.
5. CAS는 표준 형식만 검색키로 만들고 공란/비표준은 raw로 유지한다.
6. bootstrap profile ID를 발급하고 registry에 고정한다.
7. 동일 CAS/명칭/노출기준/분석조건 충돌을 validator가 보고한다.
8. 관계와 부모는 자동 생성하지 않고 review candidate 파일만 생성한다.
9. `dataset_manifest.json`에 입력 hash, 행 수, 오류 수를 기록한다.
10. source 297행과 generated profile 297행을 일대일 대조한다.

### validator 필수 규칙

- source 행 수 = staging 행 수 = 최초 profile 행 수
- 모든 profile에 고유 `profile_id`와 `source_row_id`
- CAS 형식 오류는 원문 보존 + review 상태
- FK 대상 존재, relation 자기참조 금지
- 정렬 필드 타입 및 안정적 정렬 결과
- 동일 CAS를 자동 병합하지 않음
- 법적/분석 충돌을 경고로 유지
- 미승인 관계/규칙은 runtime artifact에서 비활성
- raw source hash와 manifest 일치

## 13. GUI 최소 변경안

전면 재작성하지 않고 다음 경계를 추가한다.

1. `load_mes_master()` 내부 파일 읽기를 `index_loader` 호출로 교체한다.
2. `find_mes_candidates()`와 `find_auto_twa_matched_candidate()`의 역할을 `substance_resolver.resolve()`로 이동한다.
3. 기존 `SubstanceSelectDialog` 레이아웃과 복수 체크 UI는 유지하되, 직접 검출/동일 CAS/공정 추천 섹션과 badge를 추가한다.
4. 캐시의 `selected_code_{cas}`를 새 `selected_profiles` 구조로 병행 저장한다. 구버전 캐시는 정렬코드로 profile ID를 찾아 migration하되 모호하면 사용자 확인한다.
5. `clean_measure_duplicates()`와 `render_file_rows()`의 중복키를 CAS가 아니라 `(profile_id, selection_source)`로 바꾼다.
6. 최종 분석방법·매체·유속·노출기준·정렬키는 resolver가 반환한 profile에서 읽는다.

호환 기간에는 기존 `msds_index.json` adapter를 fallback으로 유지하고 feature flag로 신/구 resolver 결과를 비교한다.

## 14. 권장 프로젝트 구조

```text
data/
  master/
    msds_index_V24.xlsx
  generated/
    substance_profiles.json
    substance_relations.json
    recommendation_rules.json
    dataset_manifest.json
    profile_id_registry.json
  review/
    2026-07-18_msds_index_review/
      MSDS_측정인자_1차검토표_최종수정.xlsx
      same_cas_candidates.csv
      cross_cas_relation_candidates.csv
      gui_hardcoding_inventory.csv
      source_column_mapping.csv
      README.md
dataset/
  review_decision_loader.py
  index_builder.py
  index_validator.py
  index_loader.py
  substance_resolver.py
  models.py
tests/
  test_index_builder.py
  test_index_validator.py
  test_review_decision_loader.py
  test_substance_resolver.py
```

위 구조가 2026-07-18 1차 승인 세트의 실제 구현 경로다. 다음 검토는 날짜·버전이 다른 새 폴더로 만들고, 로더에는 경로를 명시적으로 전달한다.

## 15. 구현 순서와 승인 게이트

### 0단계: 데이터 검토

- 45개 동일 CAS 그룹과 16개 교차 CAS 후보 검토
- `Unnamed: 25` 의미 확정
- 297개 profile ID 발급 정책 승인
- 부모·자식 및 form code 사전 승인

### 1단계: 모델·schema·builder

- models/schema
- lossless builder
- manifest 및 row reconciliation
- validator와 fixture

### 2단계: loader·resolver

- CAS 후보 검색
- same-CAS variant 반환
- process context 규칙 평가
- selection source 분리
- 저장 선택 복원

### 3단계: GUI adapter

- 기존 dialog 유지
- 후보 섹션/출처 badge
- profile ID 저장
- 구 캐시 migration

### 4단계: 회귀 검증

- 기존 단일 CAS 결과 동일성
- 알루미늄 단일/복수 선택
- 크롬 직접검출과 6가크롬 공정추천 분리
- 니켈 수용성/불용성 조건 보존
- 실리카/탄산칼슘 자동확정 방지
- 기존 측정계획 정렬·방법 그룹화 snapshot 비교

### 5단계: 향후 출력 통합

- profile ID 기반 Excel 출력
- VBA 결과와 Python 결과 비교
- 승인 후에만 VBA 기능을 단계적으로 대체

## 16. 기존 기능 회귀 위험

- CAS 최초행 표준명이 바뀌어 기존 표시명이 달라질 수 있음
- 정렬코드 저장 캐시를 profile ID로 이관할 때 모호한 동일 CAS 선택 발생
- `(단)`/`(다)` 분석방법 그룹화와 첫 물질 매체 대표 규칙이 달라질 수 있음
- 공정 내 문자열 중복 제거를 profile 기준으로 바꾸며 출력 행 수가 늘 수 있음
- 직접 치환하던 Limestone/탄산칼슘/금홍석이 사용자 확인 추천으로 바뀌어 기존 자동 결과가 달라질 수 있음
- 용접 시 원성분 치환을 추천 추가로 바꾸면 결과 문자열과 건수가 달라질 수 있음
- 법적 플래그의 빈값/false 의미를 잘못 정규화할 위험

위 위험 때문에 첫 구현은 shadow mode로 신 resolver 결과를 기록만 하고 기존 출력은 유지해야 한다.
