import sys
import os

# 모듈 경로 추가
sys.path.append(r'c:\Users\USER\Desktop\프로젝트\MSDS_EXtaction_V3(v24+GUI통합)')

from msds_engine_v6 import process_pdf

pdf_path = r'c:\Users\USER\Desktop\프로젝트\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\011_GHS MK WD-40 (REV30, 240722)(O).pdf'
print("[*] 011 PDF 분석을 시작합니다.")
try:
    res = process_pdf(pdf_path, log_func=print)
    print("\n[추출 완료 리포트]")
    print("제품명:", res.get("제품명"))
    print("used_engine:", res.get("used_engine"))
    print("신호등:", res.get("신호등"))
    print("구성성분:", res.get("구성성분"))
except Exception as e:
    import traceback
    traceback.print_exc()
