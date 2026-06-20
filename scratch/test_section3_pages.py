import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
from msds_engine_v6 import MSDSEngineV6

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\001_(O)002_MSDS(보통휘발유(Regular Unleaded Gasoline)_SOIL)(O).pdf"
doc = fitz.open(pdf_path)

engine = MSDSEngineV6()
pages = engine.find_section3_pages(doc)
print(f"[*] find_section3_pages 반환 값: {pages}")
