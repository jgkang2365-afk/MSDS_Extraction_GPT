# MSDS Extraction V3 (V24+GUI) 아키텍처 및 규칙 가이드

## 1. 아키텍처 개요
본 프로젝트는 PDF 형식의 물질안전보건자료(MSDS)에서 제품명과 구성성분(CAS 번호, 함유량)을 자동으로 추출하는 시스템입니다.

- **Core Engine (`msds_engine_v5.py`)**: 
  - V24 정규식 기반 추출 로직 (1단계)
  - OpenAI GPT-4o-mini 기반 AI 검수 엔진 (2단계)
  - PDF 파싱: `fitz` (PyMuPDF), `opendataloader` 사용
- **GUI (`smu_gui.py`)**: 
  - 추출 결과를 테이블로 표시하고 PDF 미리보기를 제공하는 인터페이스

## 2. 주요 규칙 및 프로토콜
- **FTF (Forest-Tree-Forest)**: 사전 분석 -> 정밀 수정 -> 사후 검증 3단계 준수
- **페이지 트래킹**: 사용자가 테이블 행 클릭 시 해당 구성성분이 있는 PDF 페이지로 자동 이동해야 함. (현재 1페이지로 고정되어 있음)
- **체크섬 검증**: CAS 번호의 수학적 유효성을 항상 검증함.

## 3. 기술적 제약
- `msds_engine_v5.py`의 `process_pdf` 함수는 최종적으로 `result_data` 딕셔너리를 반환하며, 여기에 `page` 키가 포함되어야 함.
- PDF 스캔은 성능을 위해 최대 7페이지까지만 수행함.
