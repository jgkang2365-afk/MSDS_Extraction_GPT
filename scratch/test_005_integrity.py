# -*- coding: utf-8 -*-
import sys
import os
import glob
import traceback

# 가상환경 venv_312의 파이썬 인터프리터를 상속하기 위해 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v5 import process_pdf

def test_005_file():
    pdf_files = glob.glob("TEST_File/*005*.pdf")
    if not pdf_files:
        print("❌ TEST_File 폴더 내에 005번 자재 PDF 파일을 찾을 수 없습니다.")
        return
        
    pdf_path = pdf_files[0]
    print(f"🎯 005번 자재 테스트 실행 대상: {pdf_path}")
    
    try:
        res = process_pdf(pdf_path, log_func=print)
        print("\n=== [테스트 결과 추출물] ===")
        if res is None:
            print("결과가 None입니다.")
        else:
            print(f"파일명: {res.get('filename')}")
            print(f"제품명: {res.get('product_name')}")
            print(f"신호등: {res.get('신호등')}")
            print(f"매칭엔진: {res.get('used_engine')}")
            print(f"무결성 점수: {res.get('integrity_score')}")
            print(f"성분 내용:")
            for comp in res.get("components", []):
                print(f"  - {comp.get('name') or comp.get('chemical_name')} / CAS: {comp.get('cas') or comp.get('cas_no')} / 함량: {comp.get('content') or comp.get('percentage')}")
    except Exception as e:
        print("❌ [예외 크래시 발생]")
        traceback.print_exc()

if __name__ == "__main__":
    test_005_file()
