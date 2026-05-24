# Project DevLog: MSDS_EXtaction_V3(v24+GUI통합)
* **📅 Date**: 2026-05-23
* **🏷️ Tags**: `#Project` `#DevLog` `#DataMerge` `#Feature` `#Highlight`
* **📌 Version**: `V24.3.2.0` (이전 버전 `V24.3.1.0` 계승 및 업데이트)

---

> 🎯 **Progress Summary**
> 마스터 데이터셋(`msds_index.xlsx`)과 JSON 규제 데이터(`MES_MASTER_LOOKUP.json`)의 복합 병합 및 검증 하이라이팅 완료.

### 🛠️ Execution Details & Changes
* **Git Commits**: `msds_index.xlsx_업데이트` 완료
* **Core File Modifications**:
  * 📄 `msds_index.xlsx`: 마스터 데이터가 병합 완료된 최종 버전으로 교체되었습니다.
* **Technical Implementation**:
  * **물리적 인자 배제:** 소음, 고열 등의 물리적 인자는 TWA 및 규제 매칭 정보 기재 대상에서 안전하게 제외 조치.
  * **이름 기반 보정 매칭 (Exact/Fallback Name Match):** CAS 번호가 비어 있는 분진류(목재분진, 기타분진 등)와 6가크롬에 대해 `FALLBACK_NAME_MAP`을 구축하여 이름 정밀/대체 대조를 통한 100% 매칭률 확보.
  * **중복 CAS 성상 구별 필터 (Fuzzy Multi-CAS Filter):** 알루미늄(CAS: `7429-90-5`) 등 동일한 CAS를 공유하지만 성상별로 규제 수치(10, 5, 2 mg/m³)가 상이한 물질들에 대해 이름 유사 분석을 적용하여 정확한 정보 매칭 성공.
  * **수동 검증용 하이라이트 도입 (openpyxl Styling):** 대체 매핑 및 유사 필터링이 적용된 28개 행의 `노출기준(TWA)` 셀에 연한 노란색(`FFF2CC`) 채우기 패턴을 적용하여 사용자의 수동 검증 편의성 극대화.

### 🚨 Troubleshooting (Mistake Log)
> 🐛 **Problem**: 동일 CAS 번호를 가지는 다중 물질(알루미늄 등)에 대한 단순 CAS 1순위 덮어쓰기 문제.
> 💡 **Cause**: `7429-90-5` CAS 매칭 시 마지막 JSON 레코드 기준으로 엑셀의 모든 알루미늄 행들이 일괄 덮어씌워져 수치 불일치 발생.
> 💡 **Solution**: 매칭 우선순위를 이름 대조로 재정립하고 중복 CAS에 대한 이름 유사 필터를 추가하여 성상별 기준(10, 5, 2 mg/m³)을 완벽하게 개별 매핑함.

### ⏭️ Next Steps
- [ ] 노란색 하이라이트된 28개 성상에 대해 사용자 최종 정합성 육안 체크 완료 후 파일 반영 대기.
- [ ] 추후 MSDS 파싱 시 업데이트된 `msds_index.xlsx` 기반의 규제 검증 연동 정상 작동 확인.
