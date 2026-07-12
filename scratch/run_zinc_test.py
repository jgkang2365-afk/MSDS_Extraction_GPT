import os
import sys
import glob

# 상위 디렉토리를 탐색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import MSDSEngineV6

def run_test():
    engine = MSDSEngineV6()
    
    # 049번 PDF 자재 탐색
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_file_dir = os.path.join(base_dir, "TEST_File")
    pdf_files = glob.glob(os.path.join(test_file_dir, "*049*.pdf")) + glob.glob(os.path.join(test_file_dir, "*049*.PDF"))
    pdf_files = list(set(pdf_files))
    
    if not pdf_files:
        print("❌ 049번 PDF 파일을 찾을 수 없습니다!")
        return
        
    pdf_path = pdf_files[0]
    print(f"🚀 테스트 대상 파일: {os.path.basename(pdf_path)}")
    
    # 파이프라인 격발
    result = engine.process_msds_pipeline(pdf_path)
    
    print("\n" + "="*80)
    print("📋 [분석 결과 스냅샷]")
    print(f"제품명: {result.get('제품명')}")
    print(f"신호등: {result.get('신호등')}")
    print(f"성분정보: {result.get('구성성분')}")
    print(f"used_engine: {result.get('used_engine')}")
    print(f"무결성점수: {result.get('integrity_score')}점")
    print(f"무결성사유: {result.get('integrity_reason')}")
    print("="*80)

if __name__ == "__main__":
    run_test()
