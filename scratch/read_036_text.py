# -*- coding: utf-8 -*-
import fitz
import glob
import os

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_file_dir = os.path.join(base_dir, "TEST_File")
    files = glob.glob(os.path.join(test_file_dir, "*036*.pdf"))
    if not files:
        print("036 파일을 찾을 수 없습니다.")
        return
    
    pdf_path = files[0]
    print(f"대상 파일: {pdf_path}")
    
    doc = fitz.open(pdf_path)
    # 1페이지부터 3페이지까지만 출력 (인덱스 0, 1, 2)
    for i in range(min(3, len(doc))):
        print(f"--- 페이지 {i+1} ---")
        text = doc[i].get_text("text")
        print(text)
    doc.close()

if __name__ == "__main__":
    main()
