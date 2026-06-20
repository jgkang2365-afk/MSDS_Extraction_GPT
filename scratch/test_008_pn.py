import fitz
import re
import unicodedata

def test():
    pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\008_msds_사라퐁(O).pdf"
    doc = fitz.open(pdf_path)
    page = doc[0]
    blocks = page.get_text("blocks")
    blocks.sort(key=lambda b: (b[1], b[0]))
    text_list = []
    for b in blocks:
        text_list.append(unicodedata.normalize("NFKC", b[4]))
    raw_text = "\n".join(text_list)
    print("=== RAW TEXT ===")
    print(raw_text[:1500])

if __name__ == "__main__":
    test()
