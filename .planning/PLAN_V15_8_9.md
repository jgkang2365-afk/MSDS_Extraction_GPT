# V15.8.9 회귀 방지 및 5대 참사 진압 구현 계획

## 1. 개요
MSDS 추출 엔진의 안정성을 확보하고, 과거에 해결했던 문제들이 재발(Regression)하지 않도록 자가 검증 시스템 및 방어 로직을 강화합니다.

## 2. 주요 작업 내역 (FTF 프로토콜 적용)

### [Phase 1] 누락 탐지기(check_omission) 고유값 검증 복원
- **수술 부위**: `msds_engine_v5.py` -> `check_omission()`
- **내용**: 중복 CAS 번호에 의한 가짜 누락 알람 폭주를 방어하기 위해 `set()`을 사용하여 고유 CAS 개수만 비교하도록 원상 복구합니다.
- **버전 업데이트**: `VERSION = "15.8.9"`

### [Phase 2] 네트워크 장애 즉시 대응 로직 강화
- **수술 부위**: `msds_engine_v5.py` -> `call_gemini_with_retry()`
- **내용**: `requests.exceptions.RequestException` 발생 시 지수 백오프 대기 없이 즉시 해당 키를 블랙리스트(`mark_sniper_cooldown`) 처리하고 다음 키로 스와핑합니다.

### [Phase 3] 함유량 정규화 및 환각 필터링 고도화
- **수술 부위**: `msds_engine_v5.py` -> `_normalize_single_content()`
- **내용**: 
    - 양방향 부등호(`≥95%≤100%`)를 범위(`95~100%`)로 변환.
    - 함유량에 알파벳(g, mg 등)이 포함된 경우 분자량 환각으로 간주하여 `미기재%`로 처리.
    - 한글 부등호(미만, 이하 등) 정제 로직 강화.

### [Phase 4] 엔진 자가 검증(Unit Test) 블록 이식
- **수술 부위**: `msds_engine_v5.py` 파일 최하단
- **내용**: 엔진 로드 시 핵심 로직(환각 필터, 세포 분열, 영업비밀 보존)을 자동 검증하는 `self_test_regression()` 블록을 추가합니다.

## 3. 검증 계획
- [ ] GUI 실행 시 콘솔에 "🛡️ 엔진 자가 검증(Unit Test) 통과" 메시지 확인.
- [ ] `py_compile`을 통한 문법 오류 확인.
