import fitz

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\001_(O)002_MSDS(보통휘발유(Regular Unleaded Gasoline)_SOIL)(O).pdf"
doc = fitz.open(pdf_path)

with open(r"scratch\001_text.txt", "w", encoding="utf-8") as f:
    f.write(f"총 페이지 수: {len(doc)}\n")
    for i in range(len(doc)):
        f.write(f"\n================ PAGE {i+1} ================\n")
        f.write(doc[i].get_text("text"))

print("[*] 001_text.txt 쓰기 완료!")
