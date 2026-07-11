# MSDS Extraction Cleanroom — 다음 구현 계획

작성일: 2026-07-11  
기준 커밋: 229f9e2 (Initial cleanroom baseline)  
기준 브랜치: main  
현재 골든 회귀: 9/13

## 1. 목표

승인된 골든 데이터 13건을 기준으로 015, 032, 040, 047 회귀를 수정하고,
기존 통과 사례를 깨뜨리지 않은 상태에서 13/13을 달성한다.

이번 단계에서는 미결 정책을 임의로 확정하거나 GUI·업무 기능을 리팩터링하지
않는다. 변경 범위는 구성성분 추출, 후보 병합, 함량 열 판별, 다중 행 매핑과
그에 대한 회귀 테스트로 제한한다.

## 2. 변경 전 고정 조건

- 작업은 main에서 직접 하지 않고 codex/fix-golden-regressions 브랜치에서 한다.
- .env, vertex_key.json, .venv, 실행 로그는 Git에 포함하지 않는다.
- golden/msds_golden_v1.json의 정답은 엔진 결과에 맞춰 수정하지 않는다.
- 각 수정 전에 실패를 재현하는 오프라인 테스트를 먼저 추가한다.
- 한 사례를 통과시켜도 기존 골든 사례가 깨지면 해당 수정을 완료로 보지 않는다.
- 외부 AI가 필요한 실제 PDF 검증은 오프라인 검증 통과 후에만 실행한다.

## 3. 작업 순서

### 단계 A — 테스트 기반 확장

목적: 네 오류를 PDF/API 없이 빠르게 재현할 수 있는 최소 테스트를 만든다.

추가할 테스트:

1. 040 헤더 판별
   - Component | Classification | Concentration 구조
   - Classification 셀에 concentration limits가 있어도 실제 Concentration 열을 선택
   - 기대값: Methanol 45~50%

2. 047 다중 CAS·다중 함량 매핑
   - 한 행에 CAS 5개와 범위 5개가 있는 구조
   - 입력 순서대로 1:1 매핑
   - 2-Propanol의 2를 함량으로 채택하지 않음

3. 015 중첩 CAS 노이즈
   - ODL의 84696-21-9와 밀도 추출의 9884696-21-9가 동시에 존재
   - 내용이 없는 긴 접두 결합 후보를 제거

4. 032 후보 우선순위
   - ODL 70~75%와 밀도 추출 75%가 충돌
   - 원문에 근거한 범위형 ODL 결과를 선택

예상 변경 파일:

- tests/test_golden_regression.py
- 필요하면 tests/test_engine_component_parsing.py 신규 생성

완료 조건:

- 새 테스트가 수정 전 실패하여 실제 회귀를 재현
- 기존 하네스 테스트 5건은 계속 통과

### 단계 B — 040 함량 열 판별 수정

변경 범위:

- msds_engine_v6.py의 extract_components_odl_robust
- 함량 헤더 키워드에 concentration/conc를 일관되게 적용
- 실제 헤더 행에서 우선 열을 확정한 뒤 데이터 행의 % 문자열로 재선정하지 않음

안전장치:

- Content, 함유량(%), 함량, Weight 계열 기존 헤더 동작 보존
- Classification의 농도 한계 문구는 보조 정보로만 취급

검증:

- 040 집중 테스트
- 010, 032 복합 부등호 사례 재검증

### 단계 C — 047 다중 CAS·다중 범위 매핑 수정

변경 범위:

- msds_engine_v6.py의 parse_row_robust_v2
- 우선 함량 셀에서 모든 범위 토큰을 추출
- CAS 개수와 함량 개수가 같으면 순서대로 zip
- 기호 또는 범위를 포함한 우선 셀을 strong content로 인정
- 영문/한글 물질명 셀의 하이픈 숫자를 함량 후보에서 제외

안전장치:

- CAS 1개·함량 1개인 기존 행 동작 유지
- CAS와 함량 개수가 다르면 무리하게 zip하지 않고 기존 단일값/미기재 경로 사용
- 날짜, EC 번호, 분류 번호 필터 유지

검증:

- 047 집중 테스트
- 022의 9성분 수직 표
- 035의 7성분 표

### 단계 D — 015 중첩 CAS 후보 제거

변경 범위:

- 1선 ODL/밀도 후보 병합부
- 밀도 전용 후보가 미기재이고 기존 ODL CAS를 접미부로 포함하는 경우 제거
- 더 짧고 실제 함량이 있는 ODL 후보를 우선

안전장치:

- 단순히 CAS 자릿수가 길다는 이유만으로 제거하지 않음
- 동일 페이지/동일 접미 구조/미기재 후보라는 조건을 함께 사용
- 체크디지트만으로는 결합 노이즈를 구별할 수 없으므로 출처와 함량을 함께 평가

검증:

- 015 집중 테스트
- 유효한 장자리 CAS가 있는 다른 골든 사례 확인

### 단계 E — 032 후보 병합 우선순위 정리

변경 범위:

- ODL과 DensityClusteringTable 결과의 중앙 병합 규칙
- 같은 CAS에서 다음 우선순위를 적용

우선순위:

1. 원문에 존재하고 미기재가 아닌 값
2. 명시적 함량 열에서 얻은 값
3. 범위 전체를 보존한 값
4. 단일 상한/하한 값
5. 미기재

주의:

- 엔진 이름만으로 무조건 우선하지 않고 근거 품질로 평가
- 서로 다른 비미기재 값이 충돌하면 조용히 초록불을 내지 말고 진단 로그를 남김

검증:

- 032 집중 테스트
- 010, 036, 040의 범위 보존 확인

## 4. 단계별 검증 게이트

각 엔진 수정 뒤 다음 순서를 지킨다.

1. 문법 검사
   - python -m py_compile

2. 오프라인 단위 테스트
   - python -m unittest discover -s tests -v

3. 기존 엔진 오프라인 회귀 14건
   - run_v6_automated_quality_check

4. 해당 PDF 집중 회귀
   - tools/golden_regression.py --run-engine --case ID

5. 네 수정 완료 후 골든 13건 전수 회귀
   - tools/golden_regression.py --run-engine

최종 합격 조건:

- 골든 데이터 무결성 13/13
- 실제 엔진 회귀 13/13
- 오프라인 엔진 회귀 14/14
- 단위 테스트 전부 통과
- pip check 통과
- 비밀 파일이 Git에 포함되지 않음

## 5. Git 전략

작업 브랜치:

- codex/fix-golden-regressions

권장 커밋:

1. Add focused regression tests for four golden failures
2. Fix concentration column detection for Giemsa tables
3. Map multiple CAS values to ordered concentration ranges
4. Reject concatenated density CAS candidates
5. Rank grounded range values during extractor merge
6. Document 13-of-13 golden verification

각 커밋은 해당 집중 테스트가 통과한 상태에서 만든다. 전체 13/13 전에는 main에
병합하지 않는다.

## 6. 미결 정책 처리

다음 정책은 회귀 13/13 이후 별도 결정한다.

- 함량 합계 허용 상한 110% 또는 130%
- 100% 초과 원문의 일반 처리와 Glycine 예외
- False Green 발생 시 신호등 강등 여부
- 제품명 파일명 보정 허용 여부
- 완전한 1선 결과에서 제품명 AI 호출 생략 여부

정책 결정은 파서 결함 수정과 섞지 않는다. 각 정책은 예시 입력, 기대 출력,
기존 골든 영향도를 표로 정리한 뒤 승인받는다.

## 7. 후속 단계

13/13 달성 후:

1. AI 호출 공통 계측 추가
   - 공급자, 모델, 토큰, 시간, 재시도, 성공 여부, 추정 비용
   - 비밀키와 원문 민감정보 기록 금지
2. Vertex `gemini-2.5-flash-lite` 비교 실험
   - 제품명과 간단한 디지털 텍스트 정제를 우선 대상으로 사용
   - 동일 입력으로 2.5 Flash와 정확도·지연·429·비용 비교
   - 예상 운영 동시성에서 반복 호출하여 재시도율 확인
3. 조건부 라우팅 검증
   - 로컬 → Flash-Lite → 로컬 완전성 재검증 → 필요 시 2.5 Flash
   - 1섹션과 3섹션 호출은 분리 유지
   - 모델 충돌은 자동 확정하지 않고 노란불 사용자 검토
4. Flash-Lite 채택 판단
   - 초기 후보 기준: 대상 작업 통과율 95% 이상
   - 초기 후보 기준: 2.5 Flash 승격률 5~10% 이하
   - 기준 미달 시 해당 작업은 2.5 Flash 유지
5. GUI 최소 실행 점검
6. 새 설치 환경에서 smoke test
7. README의 현재 상태 갱신
8. SUCCESS_DNA_HISTORY가 아닌 현행 사양 문서에 확정 규칙 반영
9. 검증 결과 커밋 및 GitHub push
10. main 병합 여부 사용자 승인

## 8. 중단 및 롤백 조건

다음 중 하나가 발생하면 즉시 해당 변경을 중단한다.

- 기존 통과 사례가 새로 실패
- CAS가 없는 성분에 CAS를 생성
- 3섹션 밖 CAS가 최종 결과에 포함
- 원문 범위를 단일값으로 축소
- 스캔본 005 또는 046이 다시 실패
- 외부 AI 결과 변동 때문에 재현이 불가능

롤백은 문제 커밋만 되돌리고 초기 기준 커밋 229f9e2는 보존한다.

## 9. 첫 실행 항목

다음 작업을 시작할 때 가장 먼저 할 일:

1. 새 작업 공간을 MSDS_Extraction_Cleanroom으로 연다.
2. main 최신 상태와 clean worktree를 확인한다.
3. codex/fix-golden-regressions 브랜치를 만든다.
4. 단계 A의 네 오프라인 실패 재현 테스트부터 작성한다.

엔진 수정은 단계 A의 테스트가 준비된 뒤 시작한다.
