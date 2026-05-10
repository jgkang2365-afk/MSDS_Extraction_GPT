import msds_engine_v5 as engine
import fitz
import re

pdf_path = r"TEST_File/008_싸이클오일).pdf"

def test_file_008():
    print(f"--- [파일 008 테스트 시작] ---")
    res = engine.analyze_msds(pdf_path, log_func=print)
    print(f"제품명: {res.get('제품명')}")
    print(f"구성성분: {res.get('구성성분')}")
    
    # Expected: 64742-54-7(80~90%)
    # Current (predicted failure): 64742-54-7(미기재%) OR nothing.

if __name__ == "__main__":
    test_file_008()
