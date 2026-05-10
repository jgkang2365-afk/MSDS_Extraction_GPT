import fitz
import json

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\013_[래디안]달팽이점액여과물(HD2)_영문 GHS MSDS(240429)삼정-씨엔티드림_요청 조성비 서류.pdf"

def analyze_pdf():
    doc = fitz.open(pdf_path)
    print(f"Total pages: {len(doc)}")
    
    # Extract text from all pages
    all_text = ""
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        print(f"--- Page {i+1} ---")
        print(text)
        all_text += f"--- Page {i+1} ---\n{text}\n"
        
        # Save a screenshot of each page for visual check
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        pix.save(f"page_{i+1}.png")
        
    with open("full_text_013.txt", "w", encoding="utf-8") as f:
        f.write(all_text)
    
    doc.close()

if __name__ == "__main__":
    analyze_pdf()
