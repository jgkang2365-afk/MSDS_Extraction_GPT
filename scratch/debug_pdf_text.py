import fitz
import sys

# Set stdout to utf-8 to handle special characters in print
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

pdf_path = r"C:/Users/USER/Desktop/안티그래티비/MSDS_EXtaction_V3(v24+GUI통합)/TEST_File/001_(-)SHIKIMIC ACID.PDF"

try:
    doc = fitz.open(pdf_path)
    print(f"--- PDF Text Dump (First 3 Pages) ---")
    for i in range(min(3, len(doc))):
        page = doc[i]
        text = page.get_text()
        print(f"\n[Page {i+1}]\n{text}")
        print("-" * 50)
    doc.close()
except Exception as e:
    # Use repr to avoid encoding issues in the error message itself
    print(f"Error reading PDF: {repr(e)}")
