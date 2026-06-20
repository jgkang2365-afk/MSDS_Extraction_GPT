import fitz
import glob
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
test_file_dir = os.path.join(base_dir, "TEST_File")
files_036 = glob.glob(os.path.join(test_file_dir, "*036*.pdf"))

if not files_036:
    print("No 036 PDF found.")
else:
    pdf_path = files_036[0]
    doc = fitz.open(pdf_path)
    out_path = os.path.join(base_dir, "scratch", "out_036.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        for i, page in enumerate(doc):
            f.write(f"--- Page {i+1} ---\n")
            f.write(page.get_text("text"))
            f.write("\n")
    print(f"Done. Saved to {out_path}")
