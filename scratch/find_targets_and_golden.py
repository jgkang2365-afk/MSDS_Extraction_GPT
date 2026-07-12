# -*- coding: utf-8 -*-
import sys
import os
import json

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# 3종 자재 파일 검색
search_dirs = [".", "TEST_File", "MSDS_Extraction_Clean"]
target_files = [
    "005_★SUPER WAY LUBE 32.pdf",
    "037_Sodium Cacodylate Buffer, 0.2M, pH 7.4.pdf",
    "046_★THF_MSDS.pdf"
]

print("=== 3종 PDF 파일 경로 검색 ===")
found_paths = {}
for root, dirs, files in os.walk("."):
    for file in files:
        for tf in target_files:
            # 부분 일치로 찾기 (한글 인코딩 등 방지)
            tf_clean = tf.replace("★", "")
            file_clean = file.replace("★", "")
            if tf_clean in file_clean or file_clean in tf_clean or (file.startswith("005_") and file.endswith(".pdf")) or (file.startswith("037_") and file.endswith(".pdf")) or (file.startswith("046_") and file.endswith(".pdf")):
                full_path = os.path.join(root, file)
                print(f"발견: {file} -> {full_path}")
                found_paths[file[:3]] = os.path.abspath(full_path)

# 골든 데이터셋의 3종 상세 정보 UTF-8 파일로 저장 및 출력
golden_path = r"golden\msds_golden_v1.json"
with open(golden_path, "r", encoding="utf-8") as f:
    golden_data = json.load(f)

print("\n=== 3종 자재 골든 원장 세부 정보 (UTF-8) ===")
for case in golden_data.get("cases", []):
    if case.get("id") in ["005", "037", "046"]:
        print(f"ID: {case['id']}")
        print(f"파일명: {case['file']}")
        print(f"제품명: {case['product_name']['expected']}")
        print("성분 정보:")
        for c in case.get("components", []):
            print(f"  - CAS: {c['cas']} | 함량: {c['content_expected']} | 물질명: {c['chemical_name']}")
        print("-" * 50)
