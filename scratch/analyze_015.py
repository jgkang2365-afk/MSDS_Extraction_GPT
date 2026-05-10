import fitz
import json
import os

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\015_Bentone Gel ISD V _ MSDS (KO).pdf"

def analyze_pdf():
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return

    doc = fitz.open(pdf_path)
    output_data = {
        "total_pages": len(doc),
        "pages": []
    }
    
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        
        output_data["pages"].append({
            "page_num": i + 1,
            "text": text
        })
        
        # Save a screenshot for visual check (first 5 pages)
        if i < 5:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            pix.save(f"scratch/015_page_{i+1}.png")
        
    with open("scratch/full_analysis_015.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    doc.close()
    print("Analysis completed successfully.")

if __name__ == "__main__":
    analyze_pdf()
