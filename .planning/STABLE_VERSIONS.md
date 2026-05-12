# Stable Milestones & Rollback Points

이 문서는 MSDS 추출 엔진의 주요 안정화 버전을 기록하며, 회귀(Regression) 발생 시 복구 지점으로 활용됩니다.

## 🏆 Current Gold Standard
- **Version**: `17.4.2.11`
- **Date**: 2026-05-12
- **Key Features**:
    - **3-Tier Defense**: ODL -> Regex -> Vision (Sniper)
    - **Vertical Section Guard**: 섹션 3(구성성분) 외 위/아래 노이즈(섹션 1 전화번호 등) 물리적 절단
    - **Phone Number Trap Fix**: 함량 데이터 내 하이픈 오인 기각 로직 정밀화
    - **Self-Overwrite Protection**: 섹션 8 등 타 섹션 데이터에 의한 함량 강등(미기재%) 방어
    - **Word Boundary/OCR Fix**: `미맊` 오타 교정 및 지시어 앞 공백 주입으로 수치 절단 방지
    - **Standardized Prompt Loading**: 버전리스(`prompt_*.txt`) 파일 우선 채택 및 GUI 종료 버그 해결

## 🔄 Previous Stable Versions
- `17.4.2.3`: Header parsing logic restoration milestone.
- `17.3.3.6`: Recon/Extraction model split optimization point.

## 📂 Backup Location
- Physical backups are stored in `archive/msds_engine_v5_[VERSION]_STABLE.py`.
