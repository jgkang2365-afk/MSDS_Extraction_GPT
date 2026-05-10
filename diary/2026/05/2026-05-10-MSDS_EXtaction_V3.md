# Project DevLog: MSDS_EXtaction_V3(v24+GUI통합)
* **📅 Date**: 2026-05-10
* **🏷️ Tags**: `#Project` `#DevLog` `#BugFix` `#Feature`

---

> 🎯 **Progress Summary**
> MSDS 추출 엔진 안정화 및 GUI 스마트 선택 추출(Selective Extraction) 기능 구현 완료.

### 🛠️ Execution Details & Changes
* **Git Commits**: (N/A)
* **Core File Modifications**:
  * 📄 `msds_engine_v5.py`: 수술적 정규화(Surgical Normalization) 도입. CAS 번호 내 숫자 사이 하이픈 공백(`123 - 45 - 6`)을 자동 제거하여 인식률 극대화. 버전 17.3.3.3 업데이트.
  * 📄 `smu_gui.py`: 사용자가 제품명이나 CAS 필드를 지운 경우 해당 파일만 골라 재추출하는 '스마트 선택 추출' 로직 구현.
* **Technical Implementation**:
  * `ExtractionWorker`가 수동 공란 데이터를 "강제 재추출" 신호로 인식하도록 캐시 로직 수정.
  * `run_extraction`에서 테이블 스캔을 통해 Partial Run 여부 결정 및 `add_result_to_table`에서 행 업데이트 지원.

### 🚨 Troubleshooting (Mistake Log)
> 🐛 **Problem Encountered**: `AttributeError: 'SMUGUI' object has no attribute 'update_log_signal'`
> 💡 **Cause**: `ExtractionWorker`에서 사용하던 시그널 패턴을 메인 GUI 클래스(`SMUGUI`)에 그대로 복사하여 사용함. 메인 클래스는 시그널을 emit하는 주체가 아니라 `self.log()` 메서드를 통해 직접 출력해야 함.
> 💡 **Solution**: `self.update_log_signal.emit()`을 `self.log()`로 교체하여 즉각 해결.
> 📌 **Lesson**: FTF(Forest-Tree-Forest) 프로토콜의 사전 분석 단계에서 클래스 멤버 변수/메서드 존재 여부를 반드시 재확인할 것.

### ⏭️ Next Steps
- [ ] 선택적 재추출 기능 사용 시 다중 선택(Multi-select) 지원 검토.
- [ ] 수술적 정규화 로직 적용 후 다른 복잡한 구조의 MSDS 파일에서 오탐지 여부 모니터링.
