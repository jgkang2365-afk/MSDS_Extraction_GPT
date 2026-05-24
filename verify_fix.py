# -*- coding: utf-8 -*-
"""[NEW] 간접 CAS 및 msds_index.json 마스터 DB 매칭 검증 스크립트"""
import sys
import os
import json
from PyQt5.QtWidgets import QApplication

# PyQt5 앱 초기화 (GUI 스레드 컨텍스트 제공)
app = QApplication(sys.argv)

try:
    from smu_gui import SMUGUI
except Exception as e:
    print(f"smu_gui 임포트 실패: {e}")
    sys.exit(1)

# SMUGUI 인스턴스 생성 (화면에 띄우지 않음)
window = SMUGUI()

# 1. msds_index.json 마스터 DB 로드
print("=== msds_index.json 로드 시작 ===")
window.load_mes_master()
print(f"로드된 마스터 리스트 수: {len(window.mes_master_list)}")
print(f"CAS 매핑 등록 수: {len(window.mes_cas_map)}")

print("\n=== 간접 CAS 매칭 검증 ===")

# 2. 염화 바륨 (10361-37-2) 후보 검색 검증
# redirect: 10361-37-2 -> 7440-39-3 (바륨)
cands_barium = window.find_mes_candidates("10361-37-2")
print(f"\n염화 바륨(10361-37-2) 매칭 후보군 수: {len(cands_barium)}")
for idx, c in enumerate(cands_barium):
    print(f"  [{idx+1}] 정렬코드: {c.get('정렬코드')} / 측정대상 물질명: {c.get('측정대상 물질명')} / CAS: {c.get('CAS No.')}")

# 3. 질산 은 (7761-88-8) 후보 검색 검증
# redirect: 7761-88-8 -> 7440-22-4 (은)
cands_silver = window.find_mes_candidates("7761-88-8")
print(f"\n질산 은(7761-88-8) 매칭 후보군 수: {len(cands_silver)}")
for idx, c in enumerate(cands_silver):
    print(f"  [{idx+1}] 정렬코드: {c.get('정렬코드')} / 측정대상 물질명: {c.get('측정대상 물질명')} / CAS: {c.get('CAS No.')}")

print("\n=== 검증 완료 ===")
sys.exit(0)
