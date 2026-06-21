import fitz

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\021_RED(적색)227_MSDS(E)_190730.pdf"
doc = fitz.open(pdf_path)

for page in doc:
    text = page.get_text()
    for line in text.split('\n'):
        if "Concentration" in line:
            print("Line text:", line)
            print("Chars and code points:")
            for char in line:
                print(f"'{char}' -> U+{ord(char):04X}")
