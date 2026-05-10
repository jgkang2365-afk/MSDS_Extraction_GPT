import fitz
import unicodedata

def _get_sorted_and_normalized_text(page):
    blocks = page.get_text("blocks")
    blocks.sort(key=lambda b: (b[1], b[0]))
    text_list = []
    for b in blocks:
        text_list.append(unicodedata.normalize("NFKC", b[4]))
    return "\n".join(text_list)

test_files = ["001_(-)SHIKIMIC ACID.PDF", "008_싸이클오일).pdf"]
with open("scratch/shikimic_text_output.txt", "w", encoding="utf-8") as f:
    for file_name in test_files:
        f.write(f"======= FILE: {file_name} =======\n")
        doc = fitz.open(f"TEST_File/{file_name}")
        for i in range(len(doc)):
            f.write(f"--- Page {i} ---\n")
            f.write(_get_sorted_and_normalized_text(doc[i]) + "\n")
        doc.close()
