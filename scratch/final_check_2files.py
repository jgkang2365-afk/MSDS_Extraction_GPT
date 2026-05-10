import sys
import os
import json
sys.path.append(os.getcwd())
from msds_engine_v5 import process_pdf

def test_final_check():
    # 1. 17번 파일 (전각 부등호 및 공백 테스트)
    # 2. 13번 파일 (CAS 필수 필터링 유지 여부 테스트)
    target_files = [
        r"TEST_File\017_RED(적색)227_MSDS(E)_190730.pdf",
        r"TEST_File\013_[래디안]달팽이점액여과물(HD2)_영문 GHS MSDS(240429)삼정-씨엔티드림_요청 조성비 서류.pdf"
    ]
    
    results = []
    for f in target_files:
        print(f"[*] 테스트 중: {f}...")
        res = process_pdf(f)
        results.append({
            "file": os.path.basename(f),
            "status": res.get("신호등", "🔴"),
            "components": res.get("구성성분", ""),
            "product": res.get("제품명", "")
        })

    print("\n" + "="*80)
    print(f"{'파일명':<40} | {'상태':<5} | {'구성성분'}")
    print("-"*100)
    for r in results:
        print(f"{r['file'][:40]:<40} | {r['status']:<5} | {r['components']}")
    print("="*100)

if __name__ == "__main__":
    test_final_check()
