import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import process_pdf

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\002_(O)011_SDS_ICP-08N-1(Cd).pdf"
print(f"[*] 테스트 파일: {pdf_path}")
res = process_pdf(pdf_path, log_func=print)
print("\n[최종 결과]")
print(res)
