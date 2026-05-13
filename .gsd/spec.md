# Specification: MSDS Extraction Engine V23 Upgrade

## 1. 개요
`msds_engine_v5.py`의 추출 성능 고도화를 위해 V23.0.0.0 지능형 하이브리드 엔진을 이식하고 시스템 버전을 업데이트한다.

## 2. 변경 사항
### 2.1 버전 정보 수정
- **파일**: `msds_engine_v5.py`
- **대상**: `VERSION` 변수 (Line 125 부근)
- **변경**: `"22.2.0.0"` -> `"23.0.0.0"`

### 2.2 extract_from_text_regex 함수 전체 교체
- **위치**: Line 532 ~ 730 부근
- **주요 특징**:
    - **Topological Barrier**: 020번 가짜 볼드체 및 유령 텍스트 병합 로직 강화.
    - **Intelligent Header Scanner**: 문서 헤더에서 단위(%) 상속 여부 및 좌우 배열(CAS vs Content) 컨텍스트 파악.
    - **Enhanced Score Logic**: 헤더 컨텍스트 기반의 가중치(Score) 시스템 적용.
    - **Safe Recovery**: CAS 기반 자동 매핑의 신뢰도 향상.

## 3. 검증 계획 (GSD2 Verify)
1. **문법 검사**: 수정 후 `python -m py_compile msds_engine_v5.py`를 통해 구문 오류가 없는지 확인.
2. **구조 검증**: `extract_from_text_regex` 함수가 기존의 다른 함수들과 적절히 연결되는지 확인.
3. **로직 확인**: 버전 정보가 정상적으로 반영되었는지 확인.

## 4. 주의 사항
- 1,000줄 이상의 파일이므로 전체 재작성이 아닌 **정밀 부분 교체(replace_file_content)** 방식을 사용한다.
- 들여쓰기(Indentation) 오류가 발생하지 않도록 4-space 규칙을 엄격히 준수한다.
