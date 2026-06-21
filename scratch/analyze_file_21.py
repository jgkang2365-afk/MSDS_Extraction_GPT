import fitz
import re

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\021_RED(적색)227_MSDS(E)_190730.pdf"
doc = fitz.open(pdf_path)

print(f"Total Pages: {len(doc)}")
for i, page in enumerate(doc):
    text = page.get_text()
    if "3567-66-6" in text or "85" in text or "Concentration" in text:
        print(f"--- Page {i+1} ---")
        print(text)
        print("------------------")
