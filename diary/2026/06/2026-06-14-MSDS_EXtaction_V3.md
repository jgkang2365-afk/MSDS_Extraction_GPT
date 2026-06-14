# Project DevLog: MSDS_EXtaction_V3(v24+GUI통합)
* **📅 Date**: 2026-06-14
* **🏷️ Tags**: `#Project` `#DevLog` `#Parser` `#Feature` `#Wako` `#Ammonia`
* **📌 Version**: `V24.4.3.15` (이전 버전 `V24.4.3.14` 계승 및 업데이트)

---

> 🎯 **Progress Summary**
> 와코(Wako) 및 암모니아수 등 변칙 부등호 수치 및 세로 나열형 구조에서의 파싱 오류 정합성 전면 정상화.

### 🛠️ Execution Details & Changes
* **Git Commits**: 완료 (최종 수술 완료 후 작업 확정 커밋 완료)
* **Core File Modifications**:
  * 📄 `msds_engine_v5.py`:
    * 와코사 변칙 부등호 교정 추가 및 세로형 지형 성분 분리 차단막, 대제목 유령 숫자 배제 가드레일을 적용하였습니다.
* **Technical Implementation**:
  * **와코식 변칙 부등호(=<, =>) 정규화:** `_normalize_single_content` 내 정규화 단계에 `=<`와 `=>` 치환 로직을 추가하여 와코사의 부등호 수치를 표준 부등호(`≤`, `≥`)로 정상 변환되도록 처리했습니다.
  * **대제목(Section 3) 유령 숫자 '3' 배제 가드레일:** 물리적 행 분석 도중 `SECTION 3` 등의 대제목 라인을 사전에 감지하여 예외 처리(`if re.search(r'SECTION\s*[3456]', row_text, re.I): continue`)함으로써 부서 번호 '3' 등이 함량 수치로 오독되는 오류를 완전히 종결하였습니다.
  * **세로형/리스트형 지형 분리 차단막:** 텍스트 분석 과정에서 `ingredient name`, `ingredient`, `component`, `물질명`, `성분명`, `chemical name` 등 다음 성분을 알리는 명칭 라인이 감지될 경우, 이전 행으로 텍스트가 강제 병합(흡수)되는 것을 차단하였습니다.
  * **노이즈 필터링 강화:** `weak_noises` 목록에 `ingredient`, `component`, `composition` 키워드를 보완하여 함량 기호(%)가 없는 숫자가 인접 헤더 텍스트 노이즈에 의해 가짜 함량으로 오독되는 오탐 현상을 원천 방어하였습니다.

### 🚨 Troubleshooting (Mistake Log)
> 🐛 **Problem 1 (와코 문서)**: `=<100` 수식 기호 누락으로 인해 와코사의 100% 수치가 누락되거나 미기재로 분석되는 현상.
> 💡 **Cause**: `_normalize_single_content` 내에서 전각 기호 등은 변환하고 있었으나 와코 특유의 `=<` 등 변칙 기호가 치환 대상에서 빠져 있어 부등호 인식 파이프라인에서 수치가 거부됨.
> 💡 **Solution**: 변칙 부등호 치환 로직을 명시적으로 추가하여 이를 해결함.
>
> 🐛 **Problem 2 (암모니아수 문서)**: 세로 나열식 지형의 성분 텍스트가 이전 행으로 무단 흡수되어 함량 배달 사고가 발생하고 미기재%가 되는 현상.
> 💡 **Cause**: 표 구조가 아닌 세로 리스트형 문서에서 아래쪽 성분의 지시어가 Y축 40픽셀 울타리 내에 들어와 이전 성분 행에 잘못 병합됨.
> 💡 **Solution**: 새로운 성분명이 발견되면 무조건 병합을 중단하도록 단절 조건을 주입하여 성분 구역을 독립 격리함.

### ⏭️ Next Steps
- [x] v24.4.3.15 수술 도면 적용 및 회귀 테스트 100% 통과 확인.
- [ ] 실제 GUI 및 업무 기동 환경에서 대규모 PDF 묶음 정밀 검증 진행 대기.
