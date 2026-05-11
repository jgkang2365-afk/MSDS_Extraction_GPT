import fitz
import os

pdf_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\015_Bentone Gel ISD V _ MSDS (KO).pdf'
output_dir = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\scratch\015_images'

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

doc = fitz.open(pdf_path)
for i in range(min(5, len(doc))):
    page = doc[i]
    pix = page.get_pixmap()
    pix.save(os.path.join(output_dir, f"page_{i+1}.png"))
    print(f"Saved page_{i+1}.png")
