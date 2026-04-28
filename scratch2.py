import fitz

pdf_path = r"C:\Users\USER\Documents\★ 강종구-측정계획 및 견적서\TEST_농업기술센터-스마트농업과-농기계임대센터(동)\012_엔진오일(5w-30).pdf"
doc = fitz.open(pdf_path)

print(f"Total pages: {len(doc)}")
for i in range(len(doc)):
    text = doc[i].get_text("text")
    has_section3 = "구성" in text or "3." in text
    has_cas = any(x in text for x in ["36878", "64742", "68037", "CAS"])
    print(f"\n--- Page {i} (has_section3={has_section3}, has_cas={has_cas}) ---")
    print(text[:500])
