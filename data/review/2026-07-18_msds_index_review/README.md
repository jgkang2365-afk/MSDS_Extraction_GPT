# MSDS 측정인자 1차 검토 세트

- 검토 세트명: `2026-07-18_msds_index_review`
- 검토일: 2026-07-18
- 원본 데이터 버전: `msds_index_V24`
- 사용자 승인 파일: `MSDS_측정인자_1차검토표_최종수정.xlsx`

## 파일별 역할

- `MSDS_측정인자_1차검토표_최종수정.xlsx`: 사용자가 직접 승인·수정·제외·보류한 최종 결정 원본
- `same_cas_candidates.csv`: 동일 CAS 다중 측정인자 후보와 분석조건 비교
- `cross_cas_relation_candidates.csv`: 서로 다른 CAS 및 CAS 없는 측정인자 간 관계 후보
- `gui_hardcoding_inventory.csv`: Python GUI에 남아 있는 물질별 하드코딩 목록
- `source_column_mapping.csv`: V24 36개 원본 열과 신규 데이터 필드의 매핑

사용자 승인 Excel의 결정값이 모든 후보 CSV와 기존 분석 문서보다 우선한다. 후보 CSV는 결정 근거와 lineage를 확인하기 위한 참고자료이며 승인 Excel을 덮어쓰지 않는다.

## 승인 파일 시트

### `동일CAS_우선검토`

동일 CAS 후보별 `항목판정`, `기본추천`, `사용자 의견`을 기록한다.

- `선택가능`: GUI에서 직접 선택할 수 있는 profile
- `부모·대표`: 동일 CAS 그룹을 묶거나 대표하는 profile. `selectable`과 `is_parent`는 데이터에서 별도 필드로 유지한다.
- `별칭·중복`: 검색과 명칭 매핑에는 사용하지만 중복 선택지로 표시하지 않는다.
- `제외`: 실행 데이터셋의 활성 선택지에서 제외하되 원본 lineage는 보존한다.
- `보류`: 운영에 자동 반영하지 않고 `REVIEW_REQUIRED` 상태로 유지한다.

### `교차CAS_16건`

관계 후보별 `최종결정`, `수정 조건/추천강도`, `기본체크`, `복수선택`, `사용자 의견`을 기록한다.

- `승인`: 승인된 내용으로 운영 추천 규칙을 생성한다.
- `수정`: 시트에 수정된 원인자·추천인자·조건과 사용자 의견을 우선 적용한다.
- `제외`: 실행 추천 규칙은 만들지 않고 검토 이력만 보존한다.
- `보류`: 비활성 `REVIEW_REQUIRED` 상태로 보존한다.

공란은 임의로 추정하지 않는다. 필요한 정책 값이 공란이면 validator 경고와 `REVIEW_REQUIRED` 상태로 유지한다.

## 후속 생성 데이터

승인 결과에서 생성된 실행 데이터는 `data/generated/`에 저장한다.

- `substance_profiles.json`
- `substance_relations.json`
- `recommendation_rules.json`
- `dataset_manifest.json`

## 버전 관리 원칙

이 검토 세트는 완료된 기록이므로 이후 수정하지 않는다. 2차 검토는 예를 들어 `data/review/2026-07-25_msds_index_review_v2/`처럼 새 폴더에 만들고 기존 세트를 덮어쓰지 않는다.
