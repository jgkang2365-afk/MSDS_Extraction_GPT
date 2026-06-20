# -*- coding: utf-8 -*-
import fitz
import re
import os

pdf_folder = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File"
files = [
    "007_MSDS(프로스테인)(O).pdf",
    "010_포름알데하이드_시그마.pdf"
]

for f in files:
    path = os.path.join(pdf_folder, f)
    if not os.path.exists(path):
        print(f"파일 없음: {path}")
        continue
    
    print(f"\n=== 파일 분석: {f} ===")
    doc = fitz.open(path)
    print(f"총 페이지 수: {len(doc)}")
    
    # 1페이지 및 각 페이지 텍스트 추출
    for i, page in enumerate(doc):
        text = page.get_text()
        print(f"\n--- {i+1} 페이지 ---")
        lines = text.split("\n")
        # 1섹션 제품명 주변 탐색
        for idx, line in enumerate(lines):
            if any(kw in line for kw in ["제품명", "Product Name", "1. 화학제품", "화학물질명"]):
                print(f"L{idx}: {line}")
            # CAS 주변 탐색
            if re.search(r'\d{2,7}-\d{2}-\d', line):
                print(f"L{idx} (CAS): {line}")
                # 주변 3줄 출력
                start = max(0, idx - 2)
                end = min(len(lines), idx + 3)
                print("   [주변 컨텍스트]")
                for context_idx in range(start, end):
                    print(f"     L{context_idx}: {lines[context_idx]}")
    doc.close()
