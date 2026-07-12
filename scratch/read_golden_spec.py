# -*- coding: utf-8: -*-
import json
import re

# 골든 데이터셋 파일 경로
golden_path = r"c:\Users\USER\Desktop\안티그래비티\MSDS_EXtaction_V3(v24+GUI통합)\golden\msds_golden_v1.json"

# 골든 데이터셋 로드
with open(golden_path, "r", encoding="utf-8") as f:
    golden_data = json.load(f)

target_ids = ["005", "037", "046"]
target_cases = []

for case in golden_data.get("cases", []):
    if case.get("id") in target_ids:
        target_cases.append(case)

print("=== 골든 데이터셋에서 3종 scanned 자재 정보 ===")
for case in target_cases:
    print(f"ID: {case['id']}")
    print(f"파일명: {case['file']}")
    print(f"제품명 (Expected): {case['product_name']['expected']}")
    print(f"성분 목록:")
    for comp in case.get("components", []):
        print(f"  - 화학물질명: {comp['chemical_name']}, CAS: {comp['cas']}, 함량(Raw): {comp['content_raw']}, 함량(Expected): {comp['content_expected']}")
    print("-" * 50)

# msds_engine_v6.py에서 모델명이나 gemini 설정 관련 부분 탐색
engine_path = r"c:\Users\USER\Desktop\안티그래비티\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v6.py"
with open(engine_path, "r", encoding="utf-8") as f:
    engine_content = f.read()

print("=== msds_engine_v6.py에서 모델 키워드 검색 ===")
lines = engine_content.splitlines()
for idx, line in enumerate(lines):
    if "gemini" in line.lower() or "flash" in line.lower() or "model" in line.lower():
        # 간단히 앞뒤 라인과 함께 출력
        print(f"{idx+1}: {line.strip()}")
