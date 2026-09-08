# Phase 05 — Resolver / Validator Foundation

## 구현 범위

- `resolver.py`가 Phase 3의 `ProductCollection`과 `Section3Collection`만 받아
  최종 `ProductResult`와 `ComponentPair`를 결정한다. 파일명, 다른 section,
  legacy, Golden, 외부 DB/API, AI 및 자동 보정 경로는 추가하지 않았다.
- 명확한 S1 후보 하나(동일 제품의 반복 관측 포함)는 `FOUND`로, 서로 다른
  제품 후보는 첫 후보를 선택하지 않고 `REVIEW`로 남긴다. 같은 source fact의
  evidence만 중복 제거하며 모든 관측 evidence를 보존한다.
- S3는 source row/block 관계만 사용한다. CAS 하나와 content 하나는
  `PAIRED`, CAS 여러 개와 공유 content 하나는 source 순서대로 각각 pair가
  된다. 중복 CAS 행도 그대로 보존한다. content 후보가 없다는 사실만으로
  `NOT_STATED`가 되지 않는다.
- `ContentFieldState`로 `ABSENT`, `EXPLICIT_BLANK`, `UNREADABLE`, `UNKNOWN`을
  구분했다. explicit header가 확인된 빈 content cell만 `NOT_STATED`이고,
  unreadable 원문은 `NOT_READABLE`, 나머지 부재/미확정 관계는
  `PAIR_AMBIGUOUS`이다. raw concentration, range/operator, `Balance`, `Rem.`,
  ppm/wt/vol 및 100 초과 값은 수정하지 않았다. header unit context는 raw와
  별도 evidence로 유지한다.
- `models.py`에 단일 typed finding 계약(`FindingCode`, `FindingSeverity`,
  `FindingContext`, `QualityFinding`, `QualityReport`)을 추가했다. Validator는
  immutable final result를 바꾸지 않고 `PASS` 또는 `REVIEW_REQUIRED`와
  finding만 반환한다.

## 검증 결과

| Command | Result |
| --- | --- |
| `python -m pytest tests/rebaseline/test_resolver.py tests/rebaseline/test_validation.py -q` | 31 passed (P5-R-01~19, P5-V-01~12) |
| `python -m pytest tests/rebaseline/test_collectors.py tests/rebaseline/test_resolver.py tests/rebaseline/test_validation.py -q` | 67 passed |
| `python -m pytest tests/rebaseline -q` | 251 passed |
| `python -m pytest tests/test_common_normalization.py -q` (managed terminal) | 6 passed |
| `python -m compileall -q src/msds golden/v2` | PASS |
| import smoke (`models normalization pdf_io sections collectors ocr resolver validation`) | PASS |
| `git diff --check` | PASS |

모든 pytest 실행에는 기존 `.pytest_cache` 쓰기 권한 warning 1건이 있었으며
테스트 assertion 실패와는 별개다.

## 실행 메타데이터

| Role | Model / effort | Runtime / orchestration |
| --- | --- | --- |
| Phase 5 implementation | gpt-5.6-terra / high | managed Codex terminal `term_781f2734-6bfc-4b91-ba86-afbe961fd2e6`에서 실제 TUI runtime 관측; serial 수행. |
| Fresh Verifier | Not run | 사용자 지시에 따라 Coordinator가 후속 처리한다. |

외부 네트워크, API, 실제 OCR/AI, DB, Golden/legacy 또는 production route는 이
Phase에서 실행하지 않았다.
