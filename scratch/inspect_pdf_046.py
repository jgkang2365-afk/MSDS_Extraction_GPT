import fitz
import sys

pdf_path = r"TEST_File/046_★THF_MSDS.pdf"
doc = fitz.open(pdf_path)

print(f"Total pages: {len(doc)}")
for i, page in enumerate(doc):
    text = page.get_text().strip()
    print(f"Page {i+1} characters length: {len(text)}")
    if text:
        print(f"--- Page {i+1} Text Sample (first 200 chars) ---")
        print(text[:200])
        print("------------------------------------------")
