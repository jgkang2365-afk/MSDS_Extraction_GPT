import sys
import os
import json
import time

sys.path.append(os.getcwd())
import msds_engine_v5

def final_unification_check():
    test_files = [
        r"TEST_File\013_[래디안]달팽이점액여과물(HD2)_영문 GHS MSDS(240429)삼정-씨엔티드림_요청 조성비 서류.pdf",
        r"TEST_File\017_RED(적색)227_MSDS(E)_190730.pdf",
        r"TEST_File\022_AMMONIUM ACETATE.PDF"
    ]
    
    print(f"[*] 통합 엔진(V17.4.0.9) 최종 단일화 테스트 시작...")
    
    results = []
    for pdf in test_files:
        print(f"\n{'-'*30}\n[*] 파일: {os.path.basename(pdf)}")
        try:
            res = msds_engine_v5.process_pdf(pdf, log_func=print)
            results.append({
                "file": os.path.basename(pdf),
                "engine": res.get("used_engine", "unknown"),
                "components": res.get("구성성분", ""),
                "status": res.get("신호등", "🔴")
            })
        except Exception as e:
            print(f"❌ 에러 발생: {e}")
            
    print("\n" + "="*80)
    print(f"{'파일명':<40} | {'엔진':<10} | {'신호등':<5} | {'결과'}")
    print("-" * 80)
    for r in results:
        print(f"{r['file'][:40]:<40} | {r['engine']:<10} | {r['status']:<5} | {r['components'][:40]}...")
    print("="*80)

if __name__ == "__main__":
    final_unification_check()
