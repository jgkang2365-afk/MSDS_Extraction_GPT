import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import process_pdf

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\001_(O)002_MSDS(보통휘발유(Regular Unleaded Gasoline)_SOIL)(O).pdf"
print(f"[*] 테스트 파일: {pdf_path}")
res = process_pdf(pdf_path, log_func=print)
print("\n[최종 결과]")
print(res)
