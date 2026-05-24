# Stable Milestones & Rollback Points

이 문서는 MSDS 추출 엔진의 주요 안정화 버전을 기록하며, 회귀(Regression) 발생 시 복구 지점으로 활용됩니다.

## 🏆 Current Gold Standard
- **Version**: `24.3.5.4`
- **Date**: 2026-05-24
- **Key Features**:
    - **Excel Cell Formatting Preservation**: 화학물질 정리 및 교정 시 엑셀 셀의 기존 맞춤(가운데 맞춤, 줄 바꿈, 셀 크기에 맞춤 등) 및 폰트 서식 속성을 완벽하게 백업하고 복원하여 서식 유실 원천 방지
    - **J-Column Concentration Verification**: J열의 성분 함유량 정보가 비어 있거나 퍼센트(`%`) 기호가 누락된 경우 명백한 입력 누락 오류로 인지하여 엑셀 상에 빨간색(적색) 하이라이트 글자색 마킹 적용

## 🔄 Previous Stable Versions
- `24.3.5.3`: J열 함유량 누락 오류 검증(빨간색 마킹) 및 활석/소우프스톤(CAS 14807-96-6) 계열 자동교정 예외처리/수동 팝업 강제화
- `24.3.5.2`: 활석/소우프스톤 계열(CAS: 14807-96-6) 자동 교정 예외처리 및 팝업 강제화
- `24.3.5.1`: 활석(소우프스톤 이명 간섭 방어) 포함 필터 조건 적용
- `24.3.5.0`: 바륨 부모-자식 자동 교정 및 물질 DB 조회 필터 탑재
- `24.3.4.1`: 오타 교정 다이얼로그 내 '감지된 명칭' 값 파란색 진한 글씨 강조 적용
- `24.3.3.0`: 마스터 DB 공백 무관 정규화 대조를 통한 괄호 오분리 및 중복 누적 완벽 방어 및 I/J열 정렬 동기화
- `24.3.2.0`: 블록 기반 격리 영역 고도화 및 헤더 복구 적용
- `17.4.2.11`: 3-Tier Defense 및 노이즈 필터 가드 안정화 기점
- `17.4.2.3`: Header parsing logic restoration milestone.
- `17.3.3.6`: Recon/Extraction model split optimization point.

## 📂 Backup Location
- Physical backups are stored in `archive/msds_engine_v5_[VERSION]_STABLE.py`.
