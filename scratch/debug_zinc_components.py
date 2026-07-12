import os
import sys
import glob

# 상위 디렉토리를 탐색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opendataloader.pdf import PDFParser
from msds_engine_v6 import MSDSEngineV6
import fitz

def debug_components():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_file_dir = os.path.join(base_dir, "TEST_File")
    pdf_files = glob.glob(os.path.join(test_file_dir, "*049*.pdf")) + glob.glob(os.path.join(test_file_dir, "*049*.PDF"))
    pdf_path = pdf_files[0]
    
    engine = MSDSEngineV6()
    
    # 3항 페이지 찾기
    doc = fitz.open(pdf_path)
    pages = engine.find_section3_pages(doc)
    doc.close()
    
    print(f"Section 3 Pages: {pages}")
    
    # ODL Parser 로드
    parser = PDFParser()
    odl_doc = parser.parse(pdf_path)
    
    # 1. extract_components_odl_robust의 실제 리턴값 인쇄
    odl_comps = engine.extract_components_odl_robust(odl_doc, pages, pdf_path)
    print("\n--- [1] ODL components output ---")
    for c in odl_comps:
        print(c)
        
    # 2. extract_table_by_density_clustering의 실제 리턴값 인쇄
    print("\n--- [2] Density Clustering components output ---")
    doc_dc = fitz.open(pdf_path)
    for p_idx in pages:
        p_comps = engine.extract_table_by_density_clustering(doc_dc[p_idx])
        for c in p_comps:
            print(f"Page {p_idx+1}: {c}")
    doc_dc.close()

if __name__ == "__main__":
    debug_components()
