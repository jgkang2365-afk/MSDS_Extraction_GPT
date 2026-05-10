# Project DevLog: MSDS_EXtaction_V3(v24+GUI통합)
* **📅 Date**: 2026-05-10
* **🏷️ Tags**: `#Project` `#DevLog` `#BugFix` `#Feature`

---

> 🎯 **Progress Summary**
> MSDS 추출 엔진 안정화 및 GUI 스마트 선택 추출(Selective Extraction) 기능 구현 완료.

### 🛠️ Execution Details & Changes
* **Git Commits**: (N/A)
* **Core File Modifications**:
  * 📄 `msds_engine_v5.py`: 수술적 정규화(Surgical Normalization) 도입 및 함량 파편 합성(Content Synthesis) 로직 적용. 범위형 데이터(`A 이상 ~ B 미만`) 유실 방지 및 단일 수치 매칭 안정화. 버전 17.3.3.4 업데이트.
  * 📄 `smu_gui.py`: 사용자가 제품명이나 CAS 필드를 지운 경우 해당 파일만 골라 재추출하는 '스마트 선택 추출' 로직 구현. 엔진 새로고침 시 캐시 보존 로직 추가.
* **Technical Implementation**:
  * `ExtractionWorker`가 수동 공란 데이터를 "강제 재추출" 신호로 인식하도록 캐시 로직 수정.
  * `run_extraction`에서 테이블 스캔을 통해 Partial Run 여부 결정 및 `add_result_to_table`에서 행 업데이트 지원.
  * 함량 파편들을 `join`하여 하나의 텍스트로 만든 후 정규화하는 `Content Synthesis` 기법 도입.

### 🚨 Troubleshooting (Mistake Log)
> 🐛 **Problem 1**: `AttributeError: 'SMUGUI' object has no attribute 'update_log_signal'`
> 💡 **Cause**: `ExtractionWorker` 시그널 패턴 오적용.
> 💡 **Solution**: `self.log()` 직접 호출로 수정.

> 🐛 **Problem 2**: 범위형 정규식 강화로 인한 단일 수치 매칭 누락
> 💡 **Cause**: 정규식에 구분자(`~` 등)와 두 번째 수치를 필수(`+`)로 지정하여 단일 수치(`≥40%`)가 매칭되지 않음.
> 💡 **Solution**: 정규식을 유연하게 복구하고, 발견된 모든 파편을 합쳐서 분석하는 **Content Synthesis** 방식으로 로직 전면 개편.
> 📌 **Lesson**: FTF(Forest-Tree-Forest) 프로토콜의 사전 분석 단계에서 클래스 멤버 변수/메서드 존재 여부를 반드시 재확인할 것.

### ⏭️ Next Steps
- [ ] 선택적 재추출 기능 사용 시 다중 선택(Multi-select) 지원 검토.
- [ ] 수술적 정규화 로직 적용 후 다른 복잡한 구조의 MSDS 파일에서 오탐지 여부 모니터링.
