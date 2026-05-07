import fitz
import re

pdf_path = "013_아이생각수성내부프로 (M-BASE)_GHS국문.pdf"
doc = fitz.open(pdf_path)
text = ""
for page in doc:
    text += page.get_text()

cas_pattern = re.compile(r'(?<![\d-])(\d{2,7}-\d{2}-\d)(?![\d-])')
all_cas = cas_pattern.findall(text)
print(f"Found {len(all_cas)} CAS numbers:")
for c in sorted(list(set(all_cas))):
    print(c)
