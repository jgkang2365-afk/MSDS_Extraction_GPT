# MSDS 추출 시스템 재기준화 TRD v1.1

**문서 ID:** MSDS-TRD-001
**문서 상태:** 검토·승인 대기 — 구현·운영 전환 승인이 아님
**작성일:** 2026-09-06 (한국시간); 2026-09-09 Phase 5 v1.1 기술 동기화
**상위 기준:** MSDS 추출 시스템 재기준화 PRD v1.1
**개정 대상:** TRD v1.0
**개정 목적:** 정확도·속도·비용과 데이터 보존에 필요한 설계는 구체화하고, 효과가 확인되지 않은 구조 확장은 줄인다.

본 문서는 PRD v1.1의 업무 정책을 변경하지 않는 기술 보완본이다. 승인되면 TRD v1.0의 기술 설계를 대체한다. 이번에는 문서와 제한된 기존 ODL 연결부를 확인했으며, 운영 PC·실제 PDF·추출 성능·API 응답시간을 실측한 것은 아니다. 아래 합격 조건은 향후 검증 기준이지 현재 프로그램의 PASS 보고가 아니다.

## 1. 검토 결론과 변경 범위

### 1.1 설계 판단 기준

구조를 나누는 목적은 파일 수를 늘리는 것이 아니라 결과의 혼입·덮어쓰기와 불필요한 재처리를 줄이는 데 있다. 기능을 추가하려면 정확도, 처리시간, 외부 호출 비용, 교정 데이터 보존 또는 장애 복구 중 어떤 문제를 해결하는지 설명할 수 있어야 한다. 논리적 책임 분리와 물리적 파일·클래스 분리는 동일하지 않다.

| v1.0 검토 지점 | v1.1 결정 | 기대 기여와 제한 |
|---|---|---|
| §5의 세분화된 디렉터리·인터페이스 | 책임은 유지하고 소규모 함수·모듈로 시작 | 구현·회귀 범위 축소; 사용하지 않는 확장 계층 미구현 |
| ODL 적용 조건과 실제 구현체 미명시 | 기존 CLI 브릿지를 선택적 3항 구조 판독기로 명시 | 필요한 자료에서만 정확도·AI 호출 감소 효과 검증 |
| Fence는 정의됐지만 실제 전달 객체가 불명확 | 확정 영역만 담는 SectionInput을 공통 경계로 정의 | 전체 PDF 전달·후처리 필터만으로 격리했다고 오판하는 문제 방지 |
| §9·11의 정찰 후 재OCR로 읽힐 수 있는 흐름 | Fence 내부 정찰 토큰은 재사용, 부족한 영역만 재판독 | 중복 OCR·렌더링 감소 |
| 여러 판독기의 일치와 원본 확인 관계 불명확 | 일치는 보조 근거; 단일 판독도 근거 조건 충족 시 허용 | 상시 이중 판독 방지와 오확정 억제 |
| 완전성 확인 방법·미해결 후보 처리 부족 | 영역 처리 장부와 후보 처분 사유를 최소 기록 | 일부 성공을 전체 PASS로 처리하거나 잡음 하나로 항상 REVIEW 되는 문제 방지 |
| Domain 예시에 단위·끝점 의미가 미구체화 | 최초값·정규화·단위·경계 포함 여부를 구분 | 부등호·단위 손실 및 후단 문자열 재파싱 방지 |
| 실행 단계와 실행 결과 상태가 혼용 | 실행 상태, 현재 단계, 품질 판정 분리 | 실패·취소·부분 처리와 REVIEW 혼동 방지 |
| §18의 문서 격리·OCR 공유 구현이 불명확 | 순차 문서 작업 프로세스와 지연 로딩 OCR 프로세스만 사용 | GUI 장애 격리·OCR 재부팅 감소; 프로세스 풀 미도입 |
| §21의 실행·결과 중복 테이블 및 교정 참조 부족 | 실행별 기계 결과 1개, 최소 5개 테이블·단일 저장 책임 | 이력 보호 유지; ORM·범용 이벤트 소싱 제외 |
| §23의 승인 즉시 자동 API 등록으로 해석 가능 | 기존 사용자 조회 동작 유지, 요청된 보강만 비동기 수행 | 숨은 자동 호출·업무 흐름 변경 방지 |
| §33의 4개 설정 파일과 null 예산 | 기존 설정의 한 구역에 통합; 유한한 실행 예산 필수 | 설정 불일치·무제한 호출 방지 |
| §28·31의 많은 테스트 계층·10단계 이행 | 테스트 3군·이행 5단계로 묶되 AC는 보존 | 검증 효과 유지, 불필요한 승인·운영 절차 감소 |

원문·교정 이력·Fence·안전한 실패는 성능 최적화와 교환하지 않는다. 반대로 모델 여러 개 상시 실행, 모든 문서의 신구 이중 실행, 전체 성공 과정 이미지 보관은 기본 범위에 넣지 않는다.

### 1.2 기준 자료

PRD v1.1과 TRD v1.0의 Markdown 및 Word 내용을 확인했다. 기존 구현 관련 추가 확인은 TRD v1.0에 기록된 GitHub 커밋 `fd47657fd561ccb22cc2d80feeafc0c5fe724e44`의 `opendataloader/pdf/__init__.py`와 해당 폴더에 한정했다. 이 커밋을 현재 로컬 운영 최신 버전이라고 주장하지 않는다. 정확한 파일 해시와 기술 참고자료는 §21에 기록한다. [B1–B3]

## 2. 최소 구현 구조와 범위

### 2.1 유지·조건부·보류

| 구분 | 설계 범위 |
|---|---|
| 필수 유지 | 1항·3항 격리, 구조화 결과, CAS↔함유량 매칭, 원문·교정 보존, PASS/REVIEW, OCR 배치 재사용, 기존 GUI/Excel, KOSHA 비동기·지연 응답 차단 |
| 조건부 채택 | ODL 선택 호출, 추가 OCR 재판독, AI fallback, 제한적인 판독 자료 캐시; 자료군별 실측 효과와 안전 조건을 만족할 때 적용 |
| 이번에 구현하지 않음 | 범용 플러그인 레지스트리, 규칙 DSL, 벡터 DB/RAG, 별도 서버·메시지 브로커, 다중 모델 상시 투표, 상시 OCR/ODL 서버, 별도 사용자 수정 앱 |
| 계속 보류 | KOSHA 전체 로컬 마스터·Bulk 파일 확보·2항/8항 정보 확장, MES 업무 규칙 전면 재설계 |

SQLite는 승인·교정 결과의 원자적 저장과 개정 연결을 위해 유지한다. KOSHA 전체 DB 구축과는 다른 용도다. 추출 알고리즘을 검증하는 초기 단계부터 GUI·DB 이행까지 모두 완성하도록 요구하지 않는다.

### 2.2 모듈 경계

새 코드는 기존 루트 파일 옆의 `src/msds/`에서 시작한다. 아래는 책임 묶음이며 함수 하나마다 파일·클래스·서비스를 만드는 명세가 아니다.

| 책임 묶음 | 초기 배치 예 | 주된 역할 |
|---|---|---|
| 계약·정규화 | `models.py`, `normalization.py` | 값·상태·근거, 순수 변환 |
| PDF·Fence | `pdf_io.py`, `sections.py` | 경량 분석, 좌표 변환, 입력 격리 |
| 후보·판정 | `collectors.py`, `resolver.py`, `validation.py` | 후보 생성, 관계 판정, 품질 판단 |
| 실행·자원 | `pipeline.py`, `workers.py` | 순차 조율, 취소·예산, OCR 수명 |
| 저장·수정 | `store.py`, `review.py` | 기계·교정·승인 이력 |
| 후단·표시 | `enrichment.py`, `presentation.py` | KOSHA/MES 연결, 기존 UI·Excel 연동 |
| 외부·레거시 | `adapters/` | 필요한 ODL·OCR·AI·Legacy 연결만 구현 |

`Resolver`와 `Validator`는 같은 패키지의 함수로도 충분하다. `domain` 성격의 코드에는 GUI·네트워크·OCR SDK 의존을 넣지 않는다. 외부 기술의 호출 형식만 어댑터에 모으고, 아직 사용하지 않는 제공자용 인터페이스를 선행 구축하지 않는다.

## 3. 실행 흐름과 프로세스 책임

### 3.1 전체 흐름

```text
파일 입력 / 원본 식별
  → 경량 분석 / 항별 처리 가능성 확인
  → Locator → 확정 Fence → SectionInput
  → 기본 로컬 후보 수집
  → 필요한 경우만 ODL / OCR / AI 보조
  → Resolver → Validator → Machine Result 저장·표시
  → 자동 PASS 또는 사용자 보완 → Approved Result
  → 사용자가 요청한 KOSHA/MES 보강 → 기존 표시·내보내기
```

1항과 3항은 독립 처리한다. 한 항의 실패 때문에 다른 항의 정상 결과를 삭제하지 않는다. 위 흐름은 논리 순서이며 무조건 모든 판독기를 차례로 호출하는 순서가 아니다.

### 3.2 최소 실행 구성

기존 PyQt GUI와 QThread 기반 연결을 유지한다. GUI 메인 스레드는 위젯을 갱신하고, Coordinator는 메시지·상태·짧은 저장 작업을 조율한다. CPU 작업과 PDF 파싱은 순차 문서 작업 프로세스에 맡긴다. PyMuPDF의 다중 스레드 사용 제한을 고려해 GUI와 추출 스레드가 같은 프로세스에서 동시에 PDF 파싱을 수행하지 않도록 한다. [S3, S5]

문서 작업 프로세스는 배치 내 재사용하되 파일별 문서 핸들·토큰·후보·임시 경로를 초기화한다. 오류는 파일별로 격리하고, native crash 또는 작업 deadline 초과 시 해당 프로세스만 교체한다. 기본 동시 문서 처리는 1개다.

OCR 모델은 별도의 배치 범위 OCR 프로세스가 소유한다. 문서 프로세스가 재시작돼도 OCR 모델을 매 파일 다시 로딩하지 않는다. OCR이 필요 없는 배치에는 이 프로세스가 없다. 두 프로세스의 분리는 PDF 장애 격리와 OCR 재로딩 방지에 한정하며 분산 서비스나 Worker pool을 만들지 않는다.

KOSHA는 기존 비동기 Worker를 우선 재사용하고 없거나 책임이 섞인 부분만 분리한다. GUI와 Worker 사이에는 구조화된 결과와 Qt queued signal을 전달하며 Worker가 위젯을 직접 수정하지 않는다. [S5]

### 3.3 기본 IPC와 종료

요청 키는 `(run_id, stage, request_seq)`로 구성한다. 이미지 전달은 작업 전용 임시 PNG 경로와 영역·해상도 정보로 시작한다. 대형 이미지 배열 복사나 shared memory 프로토콜은 병목 실측 전에는 추가하지 않는다. 작은 결과는 메시지로 반환한다.

취소는 먼저 요청 수신 중단·취소 신호·짧은 정상 종료 대기를 수행한다. 불응 프로세스는 소유 PID/프로세스 트리만 정리한다. 타임아웃 난 채널은 폐기하고 늦은 응답을 버린다. `python` 또는 `java`라는 이름으로 전체 프로세스를 종료하지 않는다. GUI나 KOSHA 스레드에 강제 `terminate()`를 기본 적용하지 않는다.

## 4. 내부 데이터 계약

### 4.1 식별자와 불변성

| 식별자 | 규칙 |
|---|---|
| `document_id` | 원본 SHA-256과 동일하게 사용; 파일명은 별도 운영 메타데이터 |
| `run_id` | 한 번의 기계 추출 시도; 최종 Machine Result의 식별자로도 사용 |
| `mention_id` | 해당 run의 원문 CAS 기재 단위; CAS 값·행 배열 인덱스로 대체 금지 |
| `evidence_id`, `candidate_id` | run 내부 식별자; 별도 전역 ID 서비스 불필요 |
| `correction_id`, `approved_id` | 사용자 교정 개정·업무용 확정 개정 |

실행별 최종 Machine Result는 저장 후 불변이다. 재추출은 새 run이다. 진행 중 checkpoint는 미완료 상태로 갱신할 수 있으나 이미 최종화된 결과를 수정하지 않는다. `result_revision_id`를 run과 별도로 중복 발급하지 않는다.

### 4.2 필수 결과 구조

```text
MachineResult
  document_id, run_id, versions
  execution: state, terminal_reason, last_stage
  section1, section3: fence, coverage, state
  product: raw_reading, display_value, compare_key, status, evidence_ids
  components[]: mention_id, ordinal, source_group_id
    cas: raw_reading, value, evidence_ids
    content: raw_reading, normalized, status, evidence_ids
    pair: kind, shared_content_id, relation_reason
  unresolved[]: field, reading, reason, evidence_ids
  provenance[]: essential readings, selected/rejected reason, transformations
  quality: PASS / REVIEW_REQUIRED / NOT_EVALUATED, reasons[], warnings[]
```

구조화는 주 업무 데이터에 적용한다. `payload_json`으로 저장·IPC 직렬화하는 것은 허용한다. 금지하는 것은 `CAS(함유량); ...` 표시 문자열을 주 계약으로 만들고 여러 계층에서 다시 해석하는 것이다.

`components`에는 원문에서 확인되고 형식·체크디지트 검증을 통과한 CAS 기재를 담는다. 함유량이 불확실해도 CAS는 보존한다. 실패한 CAS 후보는 `unresolved`에 두고 정상 성분 또는 자동 KOSHA 조회 대상으로 승격하지 않는다. 명백한 날짜·EC 번호·레이블 숫자는 배제 사유를 남기고 제외할 수 있다.

### 4.3 근거 계약

근거에는 원본 SHA-256, 항 번호, 0부터 시작하는 실제 페이지 번호, 원문 영역, 판독 방법·버전, 최초 판독 문자열이 연결된다. 내부 좌표는 **회전 보정 전 PyMuPDF 페이지 좌표계, 좌상단 기준, PDF point 단위**로 통일한다. 화면 표시 시 페이지 번호에 1을 더한다.

입력 페이지 회전·Crop·배율을 보존하고 OCR/ODL 좌표는 어댑터에서 한 번 변환한다. 다중페이지 기재는 복수 근거로 표현한다. 결과에 좌표가 없으면 실제 원문 블록·토큰 식별자가 같은 역할을 해야 한다. 새 자동 PASS에서 페이지를 1로 채우거나 이미지 전체를 모든 성분의 동일 근거로 찍어 넣지 않는다.

기계 최초 판독값은 원본 자체가 아니다. 잘못 읽은 첫 후보와 재판독 후 채택값을 구분한다. 채택·충돌·정정에 필요한 최초 판독과 근거는 Machine Result에 남기며, 진단 로그를 지웠다고 함께 사라져서는 안 된다. 상세 중간 후보 전체를 DB 테이블로 만들지는 않는다.

### 4.4 함유량의 최소 구조

정규화값은 `display`, `kind`, `unit`, `unit_evidence_ids`를 가진다. 수치가 명확한 경우 `lower`, `upper`, `lower_inclusive`, `upper_inclusive`를 추가한다. 수치는 float가 아니라 Decimal로 파싱하고 JSON에는 십진 문자열로 저장한다.

| 예 | 내부 의미 |
|---|---|
| `≥0.1~<1%` | lower=0.1 포함, upper=1 미포함, unit=% |
| `100 ppm` | 단일값 100, unit=ppm; % 환산 금지 |
| `잔량` | kind=REMAINDER; 수치 끝점 없음 |
| 대응 칸 실제 공란 | status=NOT_STATED; normalized=null |
| 숫자는 있으나 불명확 | status=NOT_READABLE; normalized=null; 후보 보존 |
| 값은 읽었으나 연결 불명확 | status=PAIR_AMBIGUOUS; 확정 함유량 없음 |

`FOUND`는 수치뿐 아니라 원문에 명시된 잔량 같은 값에도 사용한다. 미기재는 표시할 때만 `미기재%`로 만든다. 아직 탐색하지 못한 상태는 별도 미해결 사유로 남기며 미기재가 아니다. 복잡한 조건식·여러 등급을 해석하는 범용 수식 엔진은 만들지 않는다. 구조를 명확히 표현하지 못하면 원문을 보존하고 REVIEW로 보낸다.

## 5. Fence와 전달 데이터의 실제 격리

### 5.1 Locator와 SectionInput

Locator는 전체 문서에서 경계를 탐색할 수 있지만 값 확정에는 관여하지 않는다. 시작·종료와 근거를 찾은 후 `pdf_io`의 한 경계 함수가 SectionInput을 만든다.

```text
SectionInput
  document_id, section_no, fence_id
  ordered_regions[]: page_index, allowed_rects, excluded_rects
  tokens[]: token_id, text, bbox, source_reading
  images[]: crop_ref, source_transform
  input_digest
```

Collector에는 원본 전체 PDF 경로·문서 핸들·전체 텍스트를 주지 않는다. 디지털 Collector는 Fence 내부 토큰·행/셀 구조만, 이미지 판독기는 격리된 이미지와 필요한 내부 표제만 받는다. 이는 논리적 입력 계약이며 별도 보안 서버나 샌드박스 제품을 신설하라는 뜻은 아니다.

`PARTIAL` 또는 `NOT_FOUND`에서는 값을 추출하지 않고 경계 재탐색 또는 REVIEW로 간다. 한 항만 확정됐으면 그 항의 작업은 진행할 수 있다.

### 5.2 다중페이지와 안전한 재단

1항은 원칙적으로 2항 시작 전, 3항은 4항 시작 전까지다. 동등한 종료 근거는 실제 구조와 함께 기록하고, 문서 끝이라는 이유만으로 생략·잘린 문서를 완전한 항으로 판단하지 않는다. 중간 페이지도 머리말·꼬리말·다른 항을 제외한 실제 허용 영역을 목록으로 관리한다.

단순 페이지 번호 목록이나 전체 폭 Y축 한 구간만으로 모든 다단 문서를 처리하지 않는다. 여러 사각 영역이 필요할 수 있으나 복잡한 문서 분할 엔진은 선행 구축하지 않는다. 구조를 확인하지 못한 자료는 안전하게 REVIEW로 남긴다.

글자·행이 경계를 가로지르면 전체 블록을 자동 포함하지 않는다. 작은 토큰 단위로 재확인하거나 경계를 재탐색한다. 재판독에 필요한 표제·연속 행은 같은 Fence 안에서만 확장한다.

### 5.3 정찰 자료 재사용

정찰 토큰은 Fence 확정 후 내부 토큰만 필터링해 후보 생성 입력으로 재사용한다. 좌표·해상도·원본 해시가 맞고 판독 품질이 충분하면 같은 영역을 다시 OCR하지 않는다. 정찰에서 바로 최종 제품명·CAS·함유량을 반환하는 우회 경로는 없다. OCR 결과 재사용은 공식 PDF 처리 지침에서도 권장되는 최적화이며, 어떤 해상도가 충분한지는 본 프로젝트 자료로 측정한다. [S2]

## 6. 디지털 제품명과 기본 3항 처리

### 6.1 제품명

로컬은 1항 토큰·좌표·레이블 관계로 후보를 생성한다. 다음이 모두 충족돼야 `LOCAL_CONFIRMED`다: 확정 Fence, 내부 출처, 레이블과 값의 직접 관계, 회사·주소·용도와의 구분, 강한 경쟁 후보 부재, 텍스트·배치 비모순. 위치·폰트 크기나 점수 하나로 승인하지 않는다.

로컬이 불확실하면 승인된 AI에 **1항 전체 Fence 또는 관계가 보존된 내부 영역**을 보낸다. 제품명만 짧게 잘라 레이블·연속 줄을 없애지 않는다. AI에는 제품명 후보, 짧은 인용, 입력 토큰/영역 참조, 불확실 여부를 반환하도록 요구한다.

디지털에서는 반환 문자열이 입력 토큰 또는 원문 연속 구간과 대응하는지 검사한다. 스캔에서는 이미지 위치·레이블 관계·문자/화질 불확실성과 해당 판독 경로의 검증된 수용 조건을 함께 확인한다. AI가 스스로 붙인 confidence나 인용문만으로 검증을 통과시키지 않는다. 이 검증은 원문이 틀리지 않았다는 절대 증명이 아니며 자동 PASS 오류율을 별도 평가한다.

제품명 `display_value`는 원문 식별정보·대소문자·기호를 보존한다. 비교용 `compare_key`는 표시값을 덮어쓰지 않는다. 최초 OCR 오독은 provenance에 남기고 새 판독을 별도 후보로 채택한다.

### 6.2 기본 3항 Collector

확정된 3항 토큰에서 CAS 후보와 함유량 후보를 수집하고 원문 행·셀·블록에 연결한다. 우선 적용하는 것은 **같은 원문 관계에 대한 명시적 증거**이며, '같은 줄이면 항상 우선' 같은 전역 순위를 만들지 않는다. 표가 깨진 경우에만 좌표 재구성 또는 선택적 구조 판독기로 보완한다.

화학물질명은 출력하지 않고 CAS/함유량을 생성하는 사전으로 사용하지 않는다. 주변 글자는 행·블록 경계와 숫자 역할을 구분하는 데만 사용할 수 있다. CAS 없는 행도 내부 구조 장부에는 남겨 그 함유량이 다른 행으로 이동하지 않도록 한다.

기본 결과가 충분하면 추가 ODL·OCR·AI를 호출하지 않는다. 일부 CAS가 추출됐다는 이유만으로 전체 성공으로 조기 종료하지 않는다.

## 7. ODL: 유지하되 효과가 있는 범위에만 적용

### 7.1 무엇을 사용하는가

기존 저장소의 `opendataloader/pdf/__init__.py`는 `PDFParser.parse()`에서 임시 PDF를 만들고 `python -m opendataloader_pdf` CLI를 실행해 JSON을 호환 객체로 변환하는 **브릿지**다. 자체 학습 모델이 아니다. 공개 OpenDataLoader PDF는 로컬 파싱 모드와 별도의 hybrid 모드를 제공한다. 로컬 설치 버전·모드가 최신 공개 기능과 같다고 가정하지 않는다. [B3, S1]

확인한 기존 브릿지는 parse 호출마다 임시 디렉터리·PDF 저장·subprocess 실행을 수행한다. `communicate(timeout=0.2)` 반복에는 전체 실행 deadline이 없고, 취소로 발생한 `InterruptedError`가 바깥의 일반 `except Exception`에서 `None`으로 바뀔 수 있다. 또한 일부 페이지 정보가 없을 때 기본 1을 사용한다. 이것들은 호출 지연·취소·근거 보존 관점의 연결부 보완 대상이며, 이번에 실제 지연 크기를 측정한 것은 아니다. [B3]

### 7.2 채택 위치와 조건

ODL은 디지털 3항의 **선택적 Table/Structure Collector**다. 기본 로컬 Collector가 해결하지 못한 표 열 관계·읽기 순서·연속 셀을 복구해 자동 처리 정확도나 AI 호출량을 개선하는지 평가한다.

| 상황 | ODL 처리 |
|---|---|
| 기본 로컬 결과·영역 처리가 명확 | 호출하지 않음 |
| 표 구조를 복원하면 Pair 충돌을 해결할 가능성이 있음 | 검증된 적용 유형에서 선택 호출 |
| 스캔본이며 텍스트 없는 이미지 | 이번 ODL 로컬 경로 대상 아님; 기존 OCR/AI 경로 사용 |
| Fence 미확정 | 값 추출 ODL 호출 금지 |
| ODL이 설치되지 않음·실패·상한 초과 | 가능한 다른 승인 경로 또는 REVIEW; 기본 추출 시작 자체는 막지 않음 |

새 파이프라인에서의 운영 활성화는 비교 검증 후 결정한다. 기존 Legacy의 ODL 사용은 문서 개정만으로 제거하지 않는다. 검증 결과 효과가 없으면 새 경로에서 비활성 상태로 남겨도 재기준화 실패가 아니다.

### 7.3 ODL에도 Fence 적용

전체 PDF를 ODL에 넘긴 뒤 결과에서 3항만 고르는 것은 새 값 추출 경계로 인정하지 않는다. ODL 입력은 허용된 3항 내용만 담아 텍스트·표 구조를 보존한 임시 파생 PDF이거나, 설치 버전이 검증된 영역 제한 입력을 제공하는 경우 그 입력이어야 한다.

PDF의 보이는 CropBox만 변경하거나 흰 사각형을 덧씌우는 것만으로 내용 제거를 보장하지 않는다. 파생 자료는 다른 항의 텍스트·이미지·숨은 내용이 판독되지 않는지, 3항 원문이 변형되지 않았는지 확인한다. 원본 PDF는 수정하지 않는다. 영역 격리를 안전하게 구현하는 비용이 ODL의 효과를 넘으면 ODL 경로를 보류하고 전체 PDF 전달로 타협하지 않는다. [S4]

파생 페이지와 원본 페이지·좌표의 대응표를 유지한다. ODL의 셀/행/병합 구조와 원본 좌표를 전달하고, 좌표가 없는 결과를 임의 페이지·행으로 채우지 않는다. 공개 JSON의 좌표 정의를 설치 버전의 실제 출력과 대조해 변환한다. [S1]

### 7.4 호출·자원·검증 규칙

한 문서의 ODL 대상 3항 영역은 가능한 한 한 호출로 처리하고 동일 입력을 반복 실행하지 않는다. stdout/stderr 크기, deadline, 취소와 소유 자식 프로세스 종료를 명시한다. 취소는 취소로 전파한다. ODL의 OCR/hybrid·자동 모델 다운로드·외부 전송은 기본 비활성이다. 상시 JVM 서버나 원격 서비스를 신규 구축하지 않는다.

공식 안내에도 호출별 JVM 기동 비용을 고려한 묶음 처리가 설명돼 있다. 다만 다른 PDF를 합쳐 하나의 판독 문맥으로 만들거나, 묶음 완성을 기다리느라 단건 결과 표시를 늦추는 것은 기본안이 아니다. [S1]

비교는 같은 자료·같은 Fence에서 '기본 로컬'과 '기본 로컬+선택 ODL'을 대상으로 한다. CAS 누락·오추출, Pair·부등호·단위, 전체 PASS 오류, 자동 처리 비율, 첫 결과·전체시간, **파생 PDF 생성+CLI 초기화+실제 파싱+결과 변환** 시간, 최대 메모리와 AI 호출 감소를 함께 보고한다. 동일 PDF 입력 또는 공통 전처리에 의존한 두 결과의 일치를 독립적인 정확성 증명으로 취급하지 않는다. 공개 일반 PDF 벤치마크를 MSDS 성능으로 대신하지 않는다.

## 8. 스캔·혼합형과 OCR 자원 수명

최초 경량 분석은 OCR을 import·초기화하지 않는다. 문서 표시용 `text/mixed/image` 분류는 유지할 수 있지만 실제 라우팅은 경계 탐색·1항·3항의 `TEXT_USABLE / IMAGE_REQUIRED / HYBRID / UNKNOWN` 근거에 따른다. 로고가 있다는 이유로 OCR을 실행하지 않는다.

OCR 상태는 `STOPPED → STARTING → READY → BUSY → READY → STOPPING`으로 충분하다. 첫 필요한 판독에서 한 번 로딩하고 같은 배치에서 재사용한다. 초기화 실패·중단은 실패 사유로 보존하며 매 파일마다 동일 부팅 실패를 반복하지 않는다.

이미지 정찰은 필요한 페이지부터 순차 진행한다. 경계를 찾은 뒤에는 불필요한 뒷부분을 정찰하지 않는다. 낮은 품질 정찰이 실패했을 때만 관련 페이지·영역의 품질을 높여 재판독한다. 해상도는 모델·문자 크기·스캔 상태별 측정값으로 정하며 낮은 해상도가 항상 충분하다고 가정하지 않는다.

Fence 내부 정찰 OCR이 충분하면 재사용한다. 부족한 제품명·CAS·기호·Pair만 정밀 판독한다. 블록 Crop에 표제나 이어지는 행이 필요하면 같은 Fence 안에서 포함한다. CAS가 읽혔는데 함유량 토큰이 없다는 사실만으로 NOT_STATED를 확정하지 않는다.

배치 입력은 시작 시 묶고 진행 중 추가 파일은 다음 묶음으로 취급한다. 더 이상 OCR 요청이 없다는 것을 확인하거나 배치·취소가 끝나면 OCR 프로세스를 종료한다. 모델만 메모리에서 지웠다고 자원이 반환됐다고 보고하지 않는다. 종료 PID와 자원 상태를 확인하되 OS 캐시까지 완전히 원복돼야 한다는 조건은 두지 않는다. 상시 워밍은 하지 않는다.

## 9. Resolver와 문서 완전성

### 9.1 후보 검증과 기재 식별

체크디지트는 구분기호를 정리한 CAS 후보의 조립 오류 검사다. 실패하면 같은 원문 관련 영역만 재판독한다. 외부 DB·다른 항·비슷한 번호로 치환하지 않는다. 형식 통과만으로 해당 행의 CAS임을 확정하지 않는다.

원문 기재는 페이지·CAS 토큰·행/블록 관계로 식별한다. 같은 원문 토큰을 여러 판독기가 읽은 결과는 하나의 mention에 연결한다. 원문 서로 다른 위치의 동일 CAS는 각각 보존한다. OCR 상자 좌표가 조금 다르다는 이유로 새 행을 만들지 않으며, 반대로 CAS 값이 같다는 이유로 병합하지 않는다. 대응이 불확실하면 충돌로 남긴다.

복수 CAS에 공통 함유량이 있으면 각 mention에 같은 `shared_content_id`를 연결한다. 그 공통 관계는 셀 병합·블록·표제 범위 근거가 있어야 한다. 각 CAS에 함유량 숫자를 나누거나 합산하지 않는다. 원문 순서는 단순한 전 페이지 Y좌표 정렬이 아니라 확인한 표·단·블록 읽기 순서로 부여한다. 이어지는 페이지의 표제·행 관계는 carry-over context로 전달하되 앞 페이지의 아무 함유량을 다음 CAS에 복제하지 않는다.

### 9.2 충돌과 정규화

Resolver는 순수 판정 함수이며 직접 OCR·AI를 호출하지 않는다. 재판독이 필요하면 목적·대상 영역·사유를 반환하고 Coordinator가 남은 예산 안에서 실행한다. 판독기 우선순위가 아니라 같은 원문에 대한 구조·문자·단위 근거로 채택한다.

명백히 틀린 후보는 사유를 남기고 기각할 수 있다. **기각된 잡음 후보와 미해결 유력 후보는 다르다.** 모든 기각 후보를 미해결로 남겨 전체 문서가 항상 REVIEW가 되지 않도록 한다. 후보 다수결, AI 자신감, 같은 값을 두 번 얻었다는 이유만으로 확정하지 않는다. 정상적인 단일 판독 결과에 추가 판독을 의무화하지 않는다.

정규화는 한 함수군에서 수행하고 다른 모듈은 이를 호출한다. 원문 수치·부등호·단위·잔량·등급 조건을 보존한다. 숫자 역순은 구조적으로 동일 구간임이 확인될 때만 표시를 정리한다. 100% 초과와 합계는 필요 시 경고일 뿐 값 삭제 조건이 아니다.

### 9.3 최소 완전성 장부

각 항에는 `planned_regions`, `processed_regions`, `unreadable_regions`, `pending_groups`, `unresolved_candidates`, `end_boundary_checked`를 기록한다. 유효 CAS 개수만 세어 완전성을 판단하지 않는다.

각 읽은 블록의 처분은 결과 기재, CAS 없는 행으로 제외, 표제/잡음으로 제외, 미해결 중 하나다. 모든 작은 문자에 영구 장부를 만들지 않고 결과·예외·처리 범위를 확인할 수 있는 블록 수준으로 관리한다. 빈 OCR 응답이나 캐시 hit만으로 영역을 읽었다고 간주하지 않는다.

문서 전체 PASS에는 확정 제품명, 확정 1항·3항, 대상 범위 완료, 해결된 Pair, 판독 불가·유력 미해결·누락 의심 없음이 필요하다. 3항 정상 0건도 범위가 읽히고 실제 CAS 기재가 없다는 판단이 있어야 한다. CAS처럼 보이는 미판독 후보가 남았다면 정상 0건이 아니다. 이 장부는 자동 합격 조건이지 실제 누락이 절대 없다는 증명이 아니다.

## 10. 실행·품질·사용 가능 상태

| 축 | 값과 의미 |
|---|---|
| 실행 상태 | QUEUED / RUNNING / COMPLETED / PARTIAL / FAILED / CANCELLED |
| 종료 사유 | TIMEOUT / BUDGET / UNSUPPORTED / WORKER_ERROR / USER_CANCEL 또는 없음 |
| 현재 단계 | ANALYZE / LOCATE / COLLECT / RESOLVE / VALIDATE / SAVE |
| 품질 | PASS / REVIEW_REQUIRED / NOT_EVALUATED |
| 업무용 승인 | AUTO_PASS / HUMAN_CONFIRMED; 미승인 결과는 승인 ID 없음 |

TIMEOUT은 종료 사유로 독립 기록한다. 확보한 유효 부분이 있으면 PARTIAL, 처리 자체가 불가능하면 FAILED이며 정상 PASS는 아니다. 취소도 완료·오류로 바꾸지 않는다. 항별·필드별 상태는 유지한다.

Validator는 최종값을 변경하지 않고 `ValidationDecision`만 반환한다. Coordinator가 결과와 판정을 함께 저장한다. 처리 전·입력 실패는 NOT_EVALUATED, 판독·경계·매칭 미해결은 REVIEW_REQUIRED다.

미해결 함유량 상태에는 `CONTENT_NOT_READABLE`, `PAIR_AMBIGUOUS`, `CONTENT_LOCATION_UNRESOLVED`를, 경계·CAS·제품명·부분 처리에도 별도 사유를 사용한다. 숫자가 특이하더라도 원문이 명확한 경고와 판독 불확실로 인한 REVIEW를 구분한다.

## 11. 저장·사용자 교정·재처리

### 11.1 최소 저장 구조

단일 PC의 로컬 `msds_state.db`와 Python `sqlite3`를 사용한다. 네트워크 공유 드라이브·동기화 폴더에 활성 DB를 두지 않는다. ORM·범용 이벤트 소싱·분산 DB·상시 DB 서버를 도입하지 않는다. SQLite의 동시 접근·백업 제약은 연결부에 한정한다. [S6, S7]

| 테이블 | 키·필수 연결 | 보존 내용 |
|---|---|---|
| documents | document_id=SHA-256 | 원본 위치, 페이지 수, 현재 승인 ID, 현재 편집 개정 |
| runs | run_id, document_id FK | 실행 메타데이터, 최종 machine_json, validation_json, 최종화 여부 |
| corrections | correction_id, base_run_id FK, document_id FK | 변경 묶음, 대상 mention_id/필드, 이전값·수정값, 근거, 저장 시점 |
| approvals | approved_id, base_run_id FK, document_id FK | 적용 교정 묶음, 승인 방식, 불변 업무용 snapshot |
| enrichments | approved_id FK, CAS, profile, 조회 개정 | 성공·실패·미조회 상태, 필수 보강 payload·조회시점 |

SQLite journal 모드는 기본 방식으로 시작하고 WAL·별도 튜닝은 필요가 확인될 때만 적용한다. FK 검증을 켜고 한 StateStore 소유 스레드에서 짧은 transaction으로 저장한다. GUI·문서/OCR/KOSHA Worker가 같은 DB를 직접 동시에 쓰지 않는다. 후보 전체·실행 이벤트·OCR 토큰을 개별 테이블로 쪼개지 않는다. 읽기 전용 결과 스냅샷을 UI에 전달한다.

각 참조가 같은 document와 올바른 base run에 속하는지 저장 전에 검증한다. Machine 최종 저장, 교정 묶음 저장, 승인 생성과 현재 승인 포인터 변경은 각각 원자적 작업이다. 디스크 부족·저장 실패 시 저장 완료·승인 완료를 표시하지 않는다. 미저장 편집은 화면에 명시하고 원본·이전 승인본을 유지한다.

### 11.2 교정 계약

교정은 `base_run_id + mention_id + field`를 기준으로 한다. 배열 인덱스나 CAS만으로 대상을 찾지 않는다. 기존 UI에서 가능한 행 추가·삭제도 기계 원문 삭제가 아니라 교정 작업으로 기록한다. 승인본에는 완성된 업무용 snapshot을 저장하므로 매번 전체 이력을 재생하지 않는다.

화면은 Draft 또는 Approved snapshot을 표시한다. 교정 저장은 사람의 전체 승인과 다르다. 일부 필드만 수정해도 다른 미해결 항목이 자동 해제되지 않는다. 사람은 원문을 확인하고 검토 사유를 해결·기각한 근거를 남길 수 있으나, 형식상 잘못된 CAS를 정상 CAS로 강제 승인해 API로 보내지는 않는다.

기계 결과의 경계 실패를 후단 사람이 원문 영역을 확인해 해결할 수 있다. 이때 Machine Result는 그대로 REVIEW 상태로 남고, Human Correction 및 HUMAN_CONFIRMED 승인본에 사람의 근거를 연결한다. 반드시 엔진 재추출을 성공시켜야만 수동 보완할 수 있는 구조로 만들지 않는다.

### 11.3 재추출과 원본 변경

재추출은 새 run이며 기존 교정·승인본은 보존한다. 이미 사람의 수정·승인이 있거나 미저장 편집이 있으면 새 자동 PASS도 현재 업무용 결과를 자동 교체하지 않는다. 차이를 제시하고 적용 여부를 사용자가 정한다. 최초 정상 추출이며 보호할 기존 수정본이 없는 경우에만 AUTO_PASS 승인본을 자동 생성할 수 있다.

원본 해시가 달라지면 새 document다. 이전 교정을 파일명으로 재적용하지 않는다. 원본을 다시 열거나 검토할 때 해시를 확인하고 다른 파일로 조용히 연결하지 않는다. 원본이 이동·유실된 경우 근거 미접근을 표시하며 옛 이력은 삭제하지 않는다. 원본 관리·백업 위치는 착수 시 확인하고 필요한 근거 파일을 승인 없이 정리하지 않는다.

기존 `smu_cache.json`은 백업 후 읽기 전용 import를 우선한다. 같은 import를 반복해 이력이 중복되거나 교정이 덮어써지지 않도록 파일 해시·가져온 항목을 기록한다. 없는 raw·좌표·승인 이력은 UNKNOWN으로 둔다. 새 교정을 예전 cache에 이중 WRITE하지 않는다.

### 11.4 초기화·복구

화면 초기화는 목록·뷰만, 실행 캐시 정리는 재생성 가능한 임시 자료만 대상으로 한다. 기계 결과·교정·승인·Golden 삭제와 구분한다. schema 변경 전 DB 백업은 안전한 backup API 또는 연결 종료 후 일관된 파일 백업을 사용한다. 열려 있는 DB의 본체 파일 하나만 복사해 복구 가능하다고 간주하지 않는다. [S6]

## 12. KOSHA/MES 비동기 후단

### 12.1 기존 조작 유지

현재의 '2단계 검증' 등 사용자가 조회를 요청하는 동작을 기본 트리거로 유지한다. Approved Result 생성만으로 모든 CAS를 자동 선조회하지 않는다. 이미 비동기인 부분은 활용하고, 추출·수정·결과 표시를 붙잡는 대기만 제거한다. 별도 웹 서버·asyncio 통합·영속 작업 브로커는 만들지 않는다.

확정된 문서의 요청된 CAS만 크기가 제한된 큐에서 순차 조회한다. 큐가 차면 UI를 block하지 않고 대기/보류 상태를 표시한다. 프로그램 종료 후 자동 백그라운드 동기화는 이번 범위가 아니다.

### 12.2 중복 요청과 늦은 응답

동일 CAS·동일 조회 profile·호환 최신성 조건이면 기존 API 캐시와 한 배치의 요청 재사용을 허용한다. 원문의 서로 다른 동일 CAS 행은 그대로 둔 채 보강 응답만 공유한다. API 응답에 함유량을 합쳐 캐시하지 않는다.

응답 적용 전 `document_id + approved_id + CAS + query_profile`를 확인한다. 현재 승인본과 다르거나, UI가 더 최신 교정 Draft를 보고 있다면 그 화면에 덮어쓰지 않는다. 이전 결과를 보존하거나 재사용 가능한 캐시에 넣더라도 최신 결과인 것처럼 표시하지 않는다. DB 승인 포인터 확인과 결과 연결은 transaction으로 처리한다.

### 12.3 실패 의미와 캐시

조회 상태, 캐시 출처, 적용 상태는 구분한다. 상태는 QUEUED/RUNNING/COMPLETE/PARTIAL/NOT_FOUND/FAILED/CANCELLED 정도로 두고, 실패 사유에 RATE_LIMIT/AUTH/TIMEOUT 등을 기록한다. `STALE_DROPPED`는 적용하지 않은 사유이며 통신 성공 여부와 별개다.

규제 플래그는 확인된 True/False와 미확인 null을 구분한다. 통신 실패·자료 없음·필수 항목 누락을 False로 채우지 않는다. 기존 client가 실패와 자료 없음을 같은 None으로 반환한다면 어댑터에서 추측하지 않고 원인 상태를 전달하도록 최소 범위의 client 수정이 필요하다.

캐시의 생성시점·만료·profile을 확인한다. 오래된 실패가 정상 '자료 없음'으로 재사용되거나, 일부 실패가 섞인 payload가 전체 정상으로 저장되지 않도록 한다. 기존 유효 캐시는 활용하되 과거 None의 원인을 복원하지 못하면 미확인으로 취급한다. TTL을 임의 연장하거나 속도를 위해 필수 조회항목을 삭제하지 않는다.

### 12.4 성능 측정과 변경 경계

queue 대기, pacing 대기, HTTP, retry, 캐시·DB 저장, 화면 반영을 구분해 기록한다. 호출 간격·예산은 실제 계정 조건을 확인한 값으로 운영하며 코드상의 안전예산을 공식 제한으로 오인하지 않는다. 429/Retry-After와 취소·누적 deadline을 존중하고 서비스 한도를 알아내기 위한 부하 실험은 수행하지 않는다.

KOSHA/MES 보강은 제품명·CAS·함유량을 수정할 수 없다. MES의 기존 명칭·측정대상 매핑은 보존하되 명시적 후단 결과로 분리한다. 규제·업무 계산이 미기재 함유량을 내부적으로 100%로 대체해도 되는지는 기존 확정 업무 의미를 확인해야 하며, 이번 추출 정규화에서 그런 기본값을 만들지 않는다.

전체 로컬 마스터·Bulk 확보·새 2항/8항 정보는 계속 보류한다. 본 SQLite의 작업별 보강 이력 저장을 그 보류 과제의 우회 구현으로 확장하지 않는다.

## 13. GUI·Excel 호환과 표시

기존 GUI·원본 미리보기·수정·열 매핑·파일 입력·중지 흐름을 우선 활용한다. 사람의 로컬 PDF 미리보기는 전체 문서를 보여줄 수 있으나 판독기에 전달하는 Fence 경계와 혼동하지 않는다. 별도 검토 앱이나 대규모 화면 재설계는 하지 않는다.

표시 문자열은 Presenter 한 곳에서 만든다. 화면의 CAS 셀처럼 기존 문자열 편집을 유지해야 하면 **그 편집 입력 경계에서만** 검증된 파싱을 허용하고 구조화 교정으로 저장한다. 다른 계층에서 화면 문자열을 재파싱해 정답을 만들지 않는다.

업무용 내보내기는 Approved snapshot을 사용한다. REVIEW·Draft는 검토용에만 포함한다. 배치 중 정상 문서는 저장할 수 있지만 제외·보류 문서를 명시한다. 기계 재추출로 기존 사람 승인본과 충돌한 경우 어떤 개정을 출력하는지 숨기지 않는다.

필수 보강정보가 미완료인 업무 형식은 그 업무의 미완료로 표시한다. 보강정보 없이 가능한 추출 결과 출력까지 일괄 차단하지 않는다. 승인된 CAS 순서·반복·공통 함유량·부등호·단위와 기존 열 매핑을 유지한다. 문자열을 날짜나 수식으로 변환하지 않고, 단위 표현이 기존 후단에서 지원되지 않으면 변환해 밀어 넣지 않고 해당 필드의 확인 필요를 표시한다.

## 14. 설정·시간·호출 예산

기존 `config.json`의 `rebaseline` 구역과 기존 secret 환경변수를 사용한다. 별도 설정 파일 네 개, 설정 서비스, 동적 규칙 편집기는 만들지 않는다. 값 추출 범위·CAS 없는 행 제외 같은 업무 정책은 설정으로 끌 수 없다.

| 설정군 | 필수 확인 |
|---|---|
| 파이프라인 | legacy/new 명시; shadow 비교는 별도 시험 모드 |
| 판독 수단 | 승인 OCR/AI 버전, ODL 선택 사용 여부·적용 유형 |
| 유한한 예산 | 문서/단계 deadline, 요청 수, 재시도, 이미지 크기·외부 비용 |
| 외부 전송 | 허용 provider, 전송 가능 여부, 저장하지 않을 비밀정보 |
| 보존 | 임시·진단 보존 설정과 업무 이력 보존의 분리 |

비용·시간 상한을 null=무제한으로 해석하지 않는다. 필수 상한이나 가격 정보가 미설정된 외부 호출은 시작하지 않고 설정 미완료를 알린다. 기본 로컬 단위 테스트는 외부 호출 없이 실행할 수 있다. 과거 설정은 실제 확인 후 출발값으로 재사용할 수 있으나 성능 합격 수치로 자동 승격하지 않는다.

재시도는 개선할 근거가 있을 때만 사용한다. 같은 입력·같은 설정으로 같은 실패를 반복하거나 SDK와 앱 양쪽의 재시도를 중첩하지 않는다. 기본 경로→선택 보조→필요 시 제한 AI라는 작은 분기만 두고 모델별 다단 라우터는 만들지 않는다.

## 15. 진단·보안·보존 비용

기존 `diagnostic_trace`를 재사용한다. 기본은 단계 시간, 판독 호출 수, 후보/기재 수, 채택·기각·검토 사유와 OCR 수명·KOSHA 지연만 요약한다. 상세 후보·중간 이미지 기록은 실패/REVIEW 또는 사용자가 선택한 진단에서만 확대한다. 새 관측 서버·대시보드는 만들지 않는다.

원본·기계 최초 판독·채택 근거·교정·승인 이력은 업무 데이터다. 이것을 FULL 진단 로그에만 저장한 뒤 로그 정리로 없애지 않는다. 모든 성공 Crop을 영구 저장할 필요는 없지만 원본과 영역으로 복원 가능해야 한다. 원본 미접근을 발견하면 근거 확인 불가를 알린다.

외부 AI에는 승인된 영역만 전송한다. 파일명 힌트·로컬 전체 경로·키·토큰을 넣지 않는다. 새 문서·새 항의 요청 문맥은 분리한다. 문서 안의 명령은 데이터이며 모델·범위·보존 정책을 바꿀 수 없다. AI JSON의 형식·길이·참조 영역을 검사하고 응답을 코드나 도구 명령으로 실행하지 않는다.

진단 공유는 기존 사용자 선택 동작으로 한정하고 자동 업로드하지 않는다. 원문에서 식별정보를 무조건 지우는 후처리를 제품명 판독에 적용하지 않는다. 민감한 자료의 외부 판독 자체가 금지되면 로컬 처리 또는 검토로 남긴다.

## 16. 검증과 성능 비교

### 16.1 테스트는 세 묶음으로 운영

| 묶음 | 실행 내용 | 사용 시점 |
|---|---|---|
| 빠른 계약·회귀 | 순수 함수, 저장된 PDF 토큰/OCR/AI 응답, Resolver·Validator·저장·가짜 API | 수정 영역 중심 실행, 안정 candidate에서 전체 로컬 회귀 |
| 실제 자료·판독 통합 | 원본 PDF, 실제 OCR/ODL, 승인된 AI/KOSHA 호출, Worker·취소·비용 | 관련 엔진·호출 정책 변경과 릴리스 검증 |
| 업무 수용·최종 평가 | 기존 GUI/Excel·재시작·교정·지연 응답·복구, 미사용 현장 자료군 | 운영 전환 전 |

테스트 묶음을 세 개로 줄여도 PRD AC-01~26은 모두 남긴다. Mock/저장 응답 테스트는 연결 계약 검증이며 실제 OCR·AI 정확도를 측정했다는 뜻이 아니다. 기존 테스트가 옛 정책을 강제하면 삭제로 숨기지 않고 의도된 변경·필요한 새 기대값·근거를 기록한다.

### 16.2 Golden v2

Golden v2에는 case_id, source_sha256, portable `source_root`+`relative_path`,
승인 상태·시점·근거, 값 기대 결과 또는 REVIEW/실패 기대 동작을 둔다. 절대
원본 경로는 저장하지 않고, 검증 실행 시에만 local source-root mapping으로 파일
존재와 hash를 확인한다. 성분 기대값은 원문 기재 순서가 있는 배열이고 공유
함유량 관계와 단위·상태·근거 위치를 포함한다. `chemical_name`은 필수 정답값이
아니다.

Golden v2 lifecycle은 `CANDIDATE → HUMAN_REVIEWED → APPROVED`다. history의 최종
stage는 case lifecycle과 정확히 일치해야 하며 APPROVED는 세 stage를 그 순서로
모두 가진다. CANDIDATE와 HUMAN_REVIEWED는 approved truth selector에서 제외하고,
형식이 깨진 APPROVED도 truth set에 넣지 않는다. APPROVED에는 reviewer
reference(개인 실명 필수 아님), 실제 calendar/offset을 갖는 timezone timestamp,
`DIRECT_SOURCE_PDF_REVIEW`, 원본 PDF 직접 확인 및 Section 1/3 확인이 있어야 한다.
승인 source asset은 portable `.pdf` reference, PDF signature, hash 일치가 모두
필요하며 불일치는 오류다. candidate의 미가용 asset은 검토 blocker로 남긴다. 자동
실행 또는 agent 판단은 사람 검토·승인으로 기록하지 않는다.

Golden의 사람이 읽은 원문 표기는 `source_transcription`으로 구분한다. 이는
product raw와 순서 있는 component-row raw 및 각각의 evidence를 가진 별도 lossless
구조이며, OCR이 반환한 `raw_reading`을 자동 복사하거나 문자 단위로 무조건 같게
요구하지 않는다. APPROVED의 transcription은 직접 human source-PDF review와 PDF
확인을 기록하고, component row와 source order의 `block_id`·CAS raw·content raw 및
source locator evidence가 1:1로 대응해야 한다. APPROVED의 transcription과
product·S1/S3·CAS·content·row evidence는 모두 `provenance_type`
`HUMAN_DIRECT_SOURCE_PDF_REVIEW`와 음수가 아닌 `page`를 가진 의미 있는 사람 원본
근거 object여야 한다. 빈 object, `null`, OCR-only `raw_reading`은 근거가 아니다.
이 승인 gate는 CANDIDATE/HUMAN_REVIEWED에 transcription을 강제하지 않는다. 정확한
결과·의미·출처를 비교하고 최초 판독 이력이 보존되는지는 별도 검사한다. 입력
문자열을 고정한 정규화 테스트에서는 raw 보존을 정확히 검사한다.

`schema.json`은 APPROVED 전사의 local shape와 locally expressible promotion gate,
즉 직접 human source 확인·method, non-empty human evidence, transcription row의
필드 형태, component가 있으면 non-empty `component_rows`를 검사한다. 허용 locator
(`page`/`bbox`/`region`)와 reviewer annotation은 보존하되 approved human evidence에는
OCR `raw_reading`을 둘 수 없다. JSON Schema Draft 2020-12는 서로 다른 두 배열의
임의 원소에 대한 exact equality를 표현할 수 없으므로, source transcription과
component의 순서·row coverage·raw value·locator exact match는 `validate_case`와
`validate_dataset` helper가 authoritative하게 검사한다. 이는 schema-expressible
constraint를 넘는 schema/Python 완전 동치 주장 없이 경계를 명시한 것이다.

ID 중복·해시 불일치·필수 원본 또는 fixture 누락·승인 미완료는 검증 미완료/실패로 처리한다. dict(CAS→함유량)로 축약하거나 테스트가 Golden·운영 코드·원본을 바꾸는 것은 금지한다. 실제 페이지와 허용 근거를 검사하되 엔진별 작은 bbox 차이를 모두 실패시키는 pixel-perfect 비교는 기본이 아니다.

REVIEW 사례는 허용 사유 하나가 나왔는지만 보는 것이 아니라 정상값으로 잘못 확정하지 않았는지, 보존할 부분이 남았는지, 불필요한 외부 호출을 하지 않았는지 확인한다. 1항·3항을 유지한 채 다른 항 숫자를 바꾸는 변형과 파일명 변경 검증을 포함한다. 변형은 별도 자료이며 원본을 덮어쓰지 않는다.

### 16.3 필요한 비교만 수행

기존 확인 자료의 단순 디지털·복잡 표·혼합형·스캔·다중페이지·반복/공통 함유량·실패 유형으로 시작한다. 모든 parser와 모든 모델의 조합을 전수 비교하지 않는다. ODL은 해당 유형의 on/off, OCR은 cold/warm/reuse, AI는 실제 fallback 대상, KOSHA는 cache hit/miss와 오류 경로에 집중한다.

자동 PASS 오류율, 자동 처리 비율, 문서 전체 일치, 누락/오추출·Pair 의미, REVIEW·실패 원인, 첫 표시·전체시간의 중앙값/상위 지연, 요청·재시도·실제 비용, 최대 RAM/필요 시 VRAM을 같은 표본·조건으로 함께 보고한다. 어떤 평균을 냈는지와 제외 자료 수를 공개한다.

선택 기능은 필수 정확도·보존 조건을 만족한 상태에서 특정 자료군의 정확도·자동 처리·속도·비용 중 실질적인 개선이 있고 추가 유지비가 수용 가능할 때만 채택한다. 전부 REVIEW로 보내 오류율만 개선한 결과는 성능 개선으로 인정하지 않는다. 수치 목표는 실측 후 승인하며 미확정 상태로 운영 전환 PASS를 선언하지 않는다.

## 17. 이행·복구와 검증 Gate

### 17.1 다섯 단계 이행

| 단계 | 작업 목적과 의존 관계 | 종료 근거 |
|---|---|---|
| M0 기준선·자료 | 실제 운영 코드·환경·사용 기능·원본·교정·Golden 확인·보존 | 사실/미확인 목록, 복구 가능한 백업 |
| M1 추출 핵심 | 계약·정규화·Fence·로컬 Resolver·Validator, 작은 실제 샘플 검증 | 외부 호출 없는 빠른 회귀와 금지 경로 검증 |
| M2 필요한 판독 보조 | OCR 수명·재사용, 제한 AI, 효과 확인 시 ODL | 실제 자료 비교, 호출·시간·자원·취소 결과 |
| M3 업무 연결 | 최소 저장·교정·승인·기존 UI/Excel, KOSHA 비동기·stale 보호 | 재추출·재시작·저장·보강·내보내기 수용 검증 |
| M4 최종 검증·전환 | Golden·미사용 현장 자료, 성능 기준, 제한 신구 비교·복구 | 사용자 운영 전환 승인 |

M1의 순수 계약과 M3의 저장 구조 초안은 함께 준비할 수 있지만 같은 공유 파일·DB를 동시에 WRITE하지 않는다. 작은 작업을 위해 Lead·Worker를 과도하게 나누지 않는다. 위 표는 기술 의존 순서이며 실행 작업지시서가 아니다.

### 17.2 Legacy와 복구

Legacy Adapter는 비교용 호환 계층이며 없는 근거·원문 순서·중복·상태를 만들어 새 자동 PASS로 승격하지 않는다. new 실패를 숨기고 Legacy 정답으로 바꾸는 자동 fallback은 없다. 승인된 시험에만 shadow_compare를 사용하며 모든 운영 문서를 이중 과금하지 않는다.

신구 차이는 의도된 정책 변경, 기존 오류 수정, 신규 회귀, 원본/Golden 재검토로 분류한다. 코드 rollback은 기존 경로로 복귀하는 것이고 새 사용자 교정 데이터를 지우는 작업이 아니다. 새 승인·교정은 안전한 파일/DB 백업으로 보존하고 옛 GUI가 해석할 수 없는 새 데이터를 조용히 버리지 않는다.

앱 비정상 종료 후 미완료 run은 INTERRUPTED 사유와 부분 상태로 복원한다. OCR/ODL·AI 호출을 자동으로 무제한 재개하지 않는다. 실행 도중 원본이 바뀌지 않았는지도 확인한다. 완료된 결과는 보존하고 작업 전용 임시 자료·프로세스만 정리한다.

### 17.3 PRD Gate와의 일치

Gate 0은 PRD 요구 기준 승인, Gate 1은 착수 기준선, Gate 2는 본 TRD·검증 계획 승인, Gate 3은 정책·회귀, Gate 4는 운영 수용성, Gate 5는 운영 전환 승인이다. TRD v1.0의 Gate 0에 TRD 승인을 함께 넣었던 표기는 PRD와 맞춰 정리한다.

개발 단계에는 관련 focused test를, 안정 candidate에는 필요한 전체 회귀를 수행한다. 운영 전환에는 독립 검토자가 같은 변경 작성자의 주장만 보지 않고 원본·결과·보존·복구 근거를 확인한다. 코드·운영 DB 변경·배포·유료 호출은 해당 실행 작업지시서와 필요한 승인 범위에서만 수행한다.

## 18. 승인 시 고정할 것과 남길 변수

고정 대상은 1항·3항 값 격리, CAS 중심·원문 순서·복수 CAS 공통 함유량, 최초값·근거·교정 보존, 단일 판정 책임, 필요한 때만 OCR, 비동기 KOSHA의 원문 불변, 기존 UI/출력 의미, 제한된 점진 이행이다.

모델명·버전·해상도·ODL 적용 자료군·유한한 timeout/retry/cost 값·정량 합격 수치·보존 기간은 실측과 운영 설정으로 확정한다. 이를 정하기 위해 범용 라우터나 추가 플랫폼부터 만들지 않는다. ODL의 안전한 Fence 입력을 저비용으로 만들 수 있는지, OCR 완전 누락을 얼마나 탐지하는지, 스캔 AI 단일 판독의 실제 오확정률은 검증이 남아 있는 주요 위험이다.

본 문서 승인만으로 운영 배포·DB migration·Legacy 삭제를 수행하지 않는다. 후속 작업지시서는 구현 범위·수정 금지·권한·검증·복구·cleanup을 별도 버전으로 명시한다.


## 19. PRD 요구사항 추적성

61개 요구사항을 각각 연결한다. 아래는 검증 설계의 연결이며 실제 테스트 통과 수를 뜻하지 않는다. §20의 AC는 PRD ID를 유지하고, TC는 이번 보완의 추가 기술 검사다.

| PRD ID | TRD 절 | 구현·검토 책임 | 연결 검증 |
|---|---|---|---|
| GOV-01 | §1, 18 | 문서 우선순위·승인 경계 | AC-25, AC-26 |
| GOV-02 | §1, 17, 18 | 설계와 실행 승인 분리 | AC-26 |
| GOV-03 | §19, 20 | 요구사항·수용 시나리오 대응 | AC-01~26 |
| IN-01 | §5, 8 | 항별 capability·OCR 조건 | AC-02 |
| IN-02 | §3, 10 | 미지원·오류 격리 | AC-03 |
| IN-03 | §4, 11 | 원본 해시·별도 실행 | AC-01, AC-14 |
| FNC-01 | §5, 7 | SectionInput·ODL 파생 입력 | AC-01, AC-04; TC-01 |
| FNC-02 | §5, 8 | 정찰 토큰 내부 재사용 | AC-02, AC-21; TC-02 |
| FNC-03 | §5, 9 | 다중페이지·이어지는 행 | AC-04, AC-08 |
| FNC-04 | §5, 14 | 경계 실패 차단·예산 | AC-04, AC-21 |
| FNC-05 | §3, 10 | 항별 정상 부분 보존 | AC-13 |
| PN-01 | §4, 6 | 출처·표시값·비교값 분리 | AC-01, AC-06 |
| PN-02 | §6 | Hard Gate·경쟁 후보 | AC-05 |
| PN-03 | §6, 14 | 제한 AI·근거·호출 예산 | AC-05, AC-24 |
| PN-04 | §6, 10 | 제품명 미확인·다른 항 보존 | AC-05, AC-13 |
| CAS-01 | §4, 6, 9 | 포함·제외·미해결 후보 | AC-07, AC-12 |
| CAS-02 | §9 | 체크디지트와 원문 확인 | AC-10 |
| CAS-03 | §4, 9, 12 | mention 단위·조회 재사용 | AC-09, AC-19 |
| CAS-04 | §9 | 공통 함유량·연속 관계 | AC-08 |
| CAS-05 | §6, 9 | CAS 없는 행·주변 숫자 배제 | AC-07, AC-10 |
| CON-01 | §4, 10, 13 | 상태·표시값 분리 | AC-11 |
| CON-02 | §8, 9 | 실제 부재 확인 | AC-07, AC-11 |
| CON-03 | §4, 9 | 끝점·부등호·수치 보존 | AC-11 |
| CON-04 | §4, 9, 13 | 단위 근거·환산 금지 | AC-11, AC-20 |
| CON-05 | §4, 9 | 잔량·100% 초과·조건식 | AC-11 |
| DAT-01 | §4, 15 | 원본/최초 판독/채택값 | AC-14; TC-05 |
| DAT-02 | §4, 9, 13 | 구조화 기재·표시 경계 | AC-09, AC-20 |
| DAT-03 | §4, 5, 7 | 원본 좌표·ODL 좌표 변환 | AC-14; TC-01 |
| DAT-04 | §4, 11, 15 | 실행 버전·불변 결과 | AC-14, AC-15 |
| RUN-01 | §3, 8 | OCR 지연 로딩·배치 종료 | AC-02, AC-21; TC-02 |
| RUN-02 | §5~9 | 선택 보조·범위·재사용 | AC-04, AC-05, AC-08 |
| RUN-03 | §3, 7, 14 | deadline·취소·finite 예산 | AC-13, AC-21; TC-03, TC-06 |
| RUN-04 | §3~5, 14, 15 | run·입력 digest·문맥 격리 | AC-14, AC-24 |
| VAL-01 | §9, 10, 12 | 단일 결정 책임·불변 검증 | AC-10, AC-17 |
| VAL-02 | §6, 9 | 독립성 가정·다수결 금지 | AC-05, AC-10 |
| VAL-03 | §9, 10 | 완전성·유력 미해결 | AC-12 |
| VAL-04 | §10 | 실행·단계·품질 분리 | AC-03, AC-12, AC-13 |
| REV-01 | §11 | 세 층·필드 단위 교정 | AC-15 |
| REV-02 | §11, 12 | 재추출·원본 변경·stale 보호 | AC-15, AC-18 |
| REV-03 | §10, 11 | 자동/사람·저장/승인 구분 | AC-16 |
| REV-04 | §11, 13 | Draft·Approved·배치 내보내기 | AC-16, AC-20 |
| KOS-01 | §12, 16 | 기존 비동기 활용·시간 분해 | AC-17 |
| KOS-02 | §12 | null·실패 원인·개정 검사 | AC-17, AC-18 |
| KOS-03 | §12 | 캐시·같은 요청 재사용 | AC-19 |
| UX-01 | §13, 17 | 기존 동작 점검·최소 연결 | AC-03, AC-15, AC-20 |
| UX-02 | §13 | 구조화 승인본·셀 형식 | AC-20 |
| UX-03 | §11, 15, 17 | 정리 분리·백업·복구 | AC-15, AC-26; TC-04, TC-05 |
| NFR-01 | §7, 12, 16 | 공동 지표·효과 판정 | AC-23 |
| NFR-02 | §16, 18 | 자료군·실측 후 기준 승인 | AC-23 |
| NFR-03 | §3, 8, 14 | 불필요 OCR 0·자원 정리 | AC-02, AC-21; TC-03 |
| GLD-01 | §16, 17 | 기존 후보 재검증 | AC-22 |
| GLD-02 | §16 | 원본·순서·검수 이력 | AC-14, AC-22 |
| GLD-03 | §16 | REVIEW·holdout·변형 | AC-01, AC-23 |
| GLD-04 | §11, 16 | 자동 Golden 갱신 금지 | AC-22, AC-26 |
| SEC-01 | §5, 7, 14, 15 | 전송 allowlist·ODL hybrid 금지 | AC-24; TC-01 |
| SEC-02 | §6, 15 | 문서 명령 무시·응답 검사 | AC-24 |
| SEC-03 | §15 | 비밀 제거·선택 공유 | AC-24; TC-05 |
| MIG-01 | §1, 17 | 로컬 실제 기준선 | AC-25, AC-26 |
| MIG-02 | §17 | 작은 교체·차이 분류 | AC-25 |
| MIG-03 | §11, 17 | 구형 근거 UNKNOWN | AC-25 |
| MIG-04 | §16, 17 | 격리 시험·명시 전환·복구 | AC-26 |

## 20. 수용 시나리오와 추가 기술 검사

### 20.1 PRD AC-01~26 유지

| ID | 필수 기대 결과 | TRD 절 |
|---|---|---|
| AC-01 | 같은 원본의 파일명 변경 또는 다른 항 값 변경으로 1항 제품명·3항 Pair가 달라지지 않는다. | §5, 6, 16 |
| AC-02 | 1항 디지털·3항 이미지 문서는 필요한 영역만 OCR 처리한다. 순수 디지털 대상은 OCR을 로딩하지 않는다. | §5, 8 |
| AC-03 | 손상·비MSDS·미지원 입력은 정상 0건과 구분되고 다음 파일은 계속 처리된다. | §3, 10 |
| AC-04 | Fence 미확정 시 전체 문서 값 추출로 우회하지 않는다. 다중페이지 3항의 마지막 기재도 처리한다. | §5, 9 |
| AC-05 | 명확한 로컬 제품명만 자동 확정하고 후보 경쟁은 제한된 AI 판독 또는 REVIEW로 전환한다. | §6, 14 |
| AC-06 | 제품명 모델번호·등급·농도·기호를 보존하고 파일명·회사명으로 대체하지 않는다. | §4, 6 |
| AC-07 | CAS 없는 행의 함유량은 제외되고 이웃 CAS로 이동하지 않는다. CAS만 있는 행은 유지된다. | §6, 8, 9 |
| AC-08 | 두 줄 CAS와 공통 함유량은 각 CAS에 동일 적용하되 공통 범위가 불명확하면 REVIEW가 된다. | §9 |
| AC-09 | 원문의 동일 CAS 복수행은 보존하고, 같은 행을 두 판독기가 읽었다고 결과 행을 늘리지 않는다. | §4, 9 |
| AC-10 | 체크디지트 실패를 다른 항·외부 DB의 유사 CAS로 수정하지 않는다. 통과 후보도 출처를 확인한다. | §9 |
| AC-11 | 부등호·단위·잔량·100% 초과 원문을 보존한다. 숫자 미판독은 NOT_STATED로 바뀌지 않는다. | §4, 9 |
| AC-12 | 원문 CAS 10건 중 2건만 처리한 상태는 전체 PASS가 아니다. 확인된 정상 0건과 실패를 구분한다. | §9, 10 |
| AC-13 | 한 항 실패 시 다른 항의 정상 결과는 남는다. 시간 초과·취소·검토 상태가 서로 구분된다. | §3, 10 |
| AC-14 | 결과에서 원본 해시·실제 페이지·기재 영역·판독값·변환 이력을 다시 확인할 수 있다. | §4, 7, 15 |
| AC-15 | 수동 수정 후 재추출·재시작·캐시 정리를 해도 교정값과 이전 기계 결과가 보존된다. | §11 |
| AC-16 | 일부 수정 저장만으로 전체 REVIEW가 해제되지 않는다. 검토용과 업무용 출력이 구분된다. | §10, 11, 13 |
| AC-17 | KOSHA 지연·실패 중에도 추출 결과를 확인·수정할 수 있고 미조회가 비대상으로 표시되지 않는다. | §12 |
| AC-18 | 사용자 CAS 수정 뒤 도착한 이전 KOSHA 응답이 최신 승인 결과를 덮어쓰지 않는다. | §11, 12 |
| AC-19 | API 조회를 재사용해도 원문 복수 CAS 기재와 기존 필수 보강정보는 유지된다. | §9, 12 |
| AC-20 | 기존 엑셀 매핑과 승인된 표시 형식을 보존하고 교정값을 구조화된 승인 결과에서 출력한다. | §13 |
| AC-21 | 배치 내 OCR Worker를 재사용하고 종료·오류·취소 후 작업 전용 자원을 정리한다. 상한을 준수한다. | §3, 8, 14 |
| AC-22 | Golden ID 중복·원본 해시 불일치·필수 파일 누락을 검증 오류로 처리하고 원장을 자동 갱신하지 않는다. | §16 |
| AC-23 | 정확값 사례와 안전한 REVIEW 사례를 모두 검증하고, 별도 최종 자료군에 정확도·처리 비율·비용을 함께 보고한다. | §16 |
| AC-24 | 외부 전송 금지·문서 내 지시문·진단 공유 경계가 지켜지고 비밀정보가 출력되지 않는다. | §14, 15 |
| AC-25 | 구형 결과에 없는 증거를 새로 꾸며 PASS로 만들지 않고, 정책상 정상 차이와 회귀를 구분한다. | §11, 17 |
| AC-26 | 검증 전후 운영 코드·원본·교정·Golden이 보존되고 전환 실패 시 기존 운영을 복구할 수 있다. | §11, 16, 17 |

### 20.2 이번 보완에 필요한 기술 검사

| ID | 검사와 차단 조건 | 연결 범위 |
|---|---|---|
| TC-01 | Fence 밖 sentinel·숨은 텍스트가 실제 ODL/AI 입력에서 제거되고, 회전·여백·다중페이지의 원본 좌표로 돌아오는지 검사. 실패하면 해당 adapter 비활성 | §4, 5, 7 |
| TC-02 | 순수 디지털은 OCR 로딩 0회, 정상 스캔 배치는 최초 1회 로딩·재사용. 품질이 충분한 정찰 영역에 중복 OCR/렌더 호출이 없는지 검사 | §3, 5, 8 |
| TC-03 | ODL/OCR hang·취소·native crash에서 deadline·현재 요청 상태·소유 프로세스 종료를 검사. 타 작업 종료와 취소→일반 성공/미기재 변환 금지 | §3, 7, 14 |
| TC-04 | 교정·승인 transaction 중 저장 실패/비정상 종료를 주입해 반쪽 승인·이전값 손실이 없고 백업 복구가 되는지 검사 | §11, 17 |
| TC-05 | SUMMARY 정리 후에도 최초 판독·채택 근거·교정 이력이 남는지 검사. source 미접근은 명시하며 다른 PDF로 대체하지 않음 | §4, 11, 15 |
| TC-06 | ODL 미설치·사용 비활성, AI 예산/전송권한 미설정, API 큐 포화에서 숨은 호출·무제한 재시도 없이 기본 경로/검토 상태를 유지하는지 검사 | §7, 12, 14 |

TC를 별도 테스트 플랫폼으로 만들지 않는다. 같은 기존 단위·계약·통합 테스트에서 조건을 추가하면 된다. 실제 ODL·OCR 검증과 저장 응답 기반 검증은 결과 보고서에서 구분한다.

## 21. 작성 근거·제한과 변경 이력

### 21.1 기준 파일

| 코드 | 기준 자료 | 식별 정보 |
|---|---|---|
| B1 | MSDS_Extraction_PRD_v1.1.md / Word 동반본 | Markdown SHA-256: b0a26d180c62233af0bbf13d72d5dfbd94f87c71f2c4062e9d16a21ca79987fe |
| B2 | MSDS_Extraction_TRD_v1.0.md / Word 동반본 | Markdown SHA-256: ba4019926b7483afa0fde591152fe980f6167a74ced1c9c2c0f15089a8c7b76f |
| B3 | 기존 ODL 브릿지와 폴더 | repository commit fd47657fd561ccb22cc2d80feeafc0c5fe724e44; bridge blob f9bc72cd64c911d92ff334e3e793aa4f20a2f14d |

B3 경로: `opendataloader/pdf/__init__.py`. 원문 참조: https://github.com/jgkang2365-afk/MSDS_Extraction_GPT/blob/fd47657fd561ccb22cc2d80feeafc0c5fe724e44/opendataloader/pdf/__init__.py

### 21.2 기술 참고자료

공식 문서는 2026-09-06에 확인했다. 현재 설치 버전의 동작은 착수 시 별도로 확인하며, 아래 자료를 이유로 라이브러리를 최신 버전으로 일괄 업그레이드하지 않는다. Qt 문서는 스레드/위젯의 기본 책임 경계를 참고한 것으로 기존 PyQt5를 Qt6으로 교체한다는 뜻이 아니다.

| 코드 | 자료와 참고 범위 | 출처 |
|---|---|---|
| S1 | OpenDataLoader PDF 공식 README — local/hybrid 구분, JSON 좌표, JVM 호출 비용 | https://github.com/opendataloader-project/opendataloader-pdf |
| S2 | PyMuPDF OCR — OCR 결과 재사용 | https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html |
| S3 | PyMuPDF Multiprocessing — 다중 스레드 제약·프로세스 분리 | https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html |
| S4 | PyMuPDF Page — Crop과 내용 제거(redaction)의 구분 | https://pymupdf.readthedocs.io/en/latest/page.html |
| S5 | Qt Threads and QObjects — GUI 스레드·queued signal | https://doc.qt.io/qt-6/threads-qobject.html |
| S6 | Python sqlite3 — transaction·연결 소유·backup | https://docs.python.org/3/library/sqlite3.html |
| S7 | SQLite WAL — 쓰기·네트워크 파일시스템 제약 | https://www.sqlite.org/wal.html |

### 21.3 개정 기록과 검증 범위

v1.1은 v1.0의 40절을 관련 책임별로 통합하고 ODL·실제 Fence 입력·정찰 재사용·후보 처분·최소 저장·KOSHA 호출 트리거·유한 예산을 보완했다. 정책의 핵심과 PRD 61개 요구사항 및 AC-01~26은 유지했다. 파일 개수나 문서 쪽수 자체를 성능 개선의 근거로 사용하지 않는다.

이번 작업은 설계 문서 개정이다. 운영 코드·설정·DB·원본·Golden은 수정하지 않았다. 실제 파일 처리의 정확도·속도·비용 개선, OCR/ODL 프로세스 동작, API 응답시간, 운영 수용 시나리오는 아직 실행 검증 대상이다.

**최종 원칙: 필요한 정확도·보존 경계는 남긴다. 불필요한 판독·중복 호출·상시 자원·확장 프레임워크는 만들지 않는다. 선택 기능은 효과를 확인한 범위에만 적용한다.**

### 21.4 2026-09-09 Phase 5 v1.1 기술 동기화

본 절은 TRD 버전을 v1.1로 유지한 채 Phase 5 구현 사실을 기록하는 최소 기술
동기화이다. 기준 코드 검토 대상은
`b7fed70abb481985766cc30d3ab24c71c3e9cb50`이다. PRD v1.1의 제품 정책은
변경하지 않는다. 이 절은 Golden v2 검토 corpus, Vision AI, ODL 연결,
KOSHA/MES, 사용자 교정·승인 결과, Legacy 이중 실행·cutover가 구현 또는
검증되었다고 주장하지 않는다.

#### 후보·결정·검증 경계

- Collector는 confirmed Section 1/3 입력에서 후보와 evidence만 수집한다.
  Resolver가 유일한 최종 선택 권한을 가지며, Validator는 확정 truth를
  변경하지 않고 `PASS` 또는 `REVIEW_REQUIRED` 및 finding만 반환한다.
- filename, 다른 section, KOSHA/MES, AI, DB의 fallback은 없다.
- `SectionInput.fence_status`의 타입은 `FenceStatus | None`이고 기본값은
  `None`이다. collector와 `resolve()`는 `FENCE_CONFIRMED`만 수용하며,
  `FENCE_PARTIAL`, `FENCE_NOT_FOUND`, `None`은 거부한다. Phase 2 TEXT builder와
  Phase 4 OCR builder가 confirmed status를 명시 설정하며 자동 기본 확인은 없다.

#### Section 3 원문·상태 계약

- `ContentFieldState`의 관측 상태 `ABSENT`, `EXPLICIT_BLANK`, `UNREADABLE`,
  `UNKNOWN`은 결과 상태 `ContentStatus.FOUND`, `NOT_STATED`, `NOT_READABLE`,
  `PAIR_AMBIGUOUS`와 별개다. TEXT에서 구조적으로 입증된 blank는
  `EXPLICIT_BLANK → NOT_STATED`가 될 수 있다. OCR token 부재는 blank가 아니라
  `UNKNOWN`이며, 이후의 명시적인 양성 evidence가 없으면
  `PAIR_AMBIGUOUS → REVIEW_REQUIRED`이다.
- `ContentResult`의 계약 필드는 정확히 `content_raw`, `content_normalized`,
  `content_status`, `unit_context_raw`, `unit_context_evidence`다. header `%`의
  bare `10`은 raw `10`과 context `%`를 유지한다. 직접 기재된 `10%`, `500 ppm`,
  `500ppm`, `10 wt%`, `10wt%`, `10 vol%`, `20vol%`는 `unit_context_raw=None`이다.
- 한 block에 content 후보가 여러 개면 `ContentStatus.PAIR_AMBIGUOUS` 및
  `PairStatus.PAIR_AMBIGUOUS`로 확정하고 최종 raw는 빈 값으로 둔다. synthetic
  join은 만들지 않는다. 후보 fact와 evidence는 `Section3Collection` 및
  `QualityFinding`에 보존한다.

#### CAS·빈 3항·품질 판정

- `CasCandidateValidity`는 관측한 유효성 상태를 보존한다. malformed/invalid
  CAS는 전체 source raw, 중복, source order와 evidence를 남기며 자동 교정하지
  않는다. 한 content가 여러 CAS에 source상 공유된 경우 그 관계도 보존한다.
- components가 0개인 Section 3은 `explicit_zero_target_evidence`가 있을 때만
  명시적 zero로 취급할 수 있다. 그렇지 않으면
  `FindingCode.SECTION3_EMPTY_UNVERIFIED`이다.
- 현재 `FindingCode` 이름은 `PRODUCT_NOT_FOUND`, `PRODUCT_CANDIDATE_CONFLICT`,
  `SECTION3_EMPTY_UNVERIFIED`, `CAS_READ_UNCERTAIN`, `CONTENT_NOT_READABLE`,
  `PAIR_AMBIGUOUS`이며, `QualityStatus`는 `PASS` 또는 `REVIEW_REQUIRED`다.

위 사실은 Phase 5 resolver/validator foundation의 현재 경계만 설명한다.
선택·보류 기능과 실제 corpus/외부 연동의 효과 검증은 기존 TRD의 향후 Gate에
남아 있다.

### 21.5 2026-09-09 Phase 6 Golden v2 계약 기반

본 절은 TRD 버전을 v1.1로 유지하는 최소 기술 동기화이며 PRD 제품 정책을
바꾸지 않는다. `golden/v2`에는 dependency-free schema/validator와 계약 테스트만
추가했다. `VALUE_TRUTH`, `SAFE_REVIEW`, `FAILURE_BEHAVIOR` case kind와 portable
source reference, lifecycle/approval history, approved-only selector를 정의했다.
Product raw/normalized/status/provenance, ordered duplicate-CAS component rows,
CAS/content/pair status, block/source relation, evidence, unit context를 Phase 5의
lossless result 계약에 맞춰 보존한다. 사람 원문 표기 `source_transcription`은 OCR
raw와 별도이며 승인본에서 direct human source-PDF review, 자체 evidence, component
source-order 1:1 raw/evidence 대응을 갖는 product/component-row 구조다. 승인본의
모든 evidence는 `HUMAN_DIRECT_SOURCE_PDF_REVIEW`와 page를 갖는 human provenance여야
하며 OCR-only/empty evidence는 승격할 수 없다. 직접 단위는 header unit context를 받지 않고, header-derived bare raw 및
`NOT_STATED`/`NOT_READABLE`/`PAIR_AMBIGUOUS`의 구분을 유지한다. PAIR_AMBIGUOUS
final raw/normalized는 빈 값이고 후보 원문은 evidence/transcription/finding에
보존한다.

`schema.json`은 local JSON 구조와 locally expressible promotion gate만 담당한다.
Draft 2020-12로 source transcription/component 두 배열의 임의 순서·row coverage·raw
value·locator가 정확히 일치하는지를 선언할 수 없으므로, 그 semantic cross-row
relation은 `validate_case`/`validate_dataset` helper가 authoritative하게 검사한다.
이는 schema-expressible 범위를 넘는 schema/Python 완전 동치 주장이 아니다.

이 단계는 사람 승인 corpus나 pilot PDF를 만들거나 승인하지 않았다. 승인 가능한
local source PDF가 이 worktree에 명확히 제공되지 않아 pilot CANDIDATE 생성도
보류했다. Golden v1 import/copy path, 운영 코드, OCR/AI/ODL/KOSHA/MES/DB/외부 호출,
배포는 이 단계 범위가 아니다. 실제 corpus 평가와 Gate 3 통과 주장은 후속의
사람 원본 검토와 승인 자료로만 가능하다.
