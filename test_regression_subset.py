import os
import sys
import json
from msds_engine_v5 import process_pdf, VERSION

def run_subset_test():
    target_files = [
        r"TEST_File\013_[래디안]달팽이점액여과물(HD2)_영문 GHS MSDS(240429)삼정-씨엔티드림_요청 조성비 서류.pdf",
        r"TEST_File\015_Bentone Gel ISD V _ MSDS (KO).pdf",
        r"TEST_File\001_(-)SHIKIMIC ACID.PDF",
        r"TEST_File\033_아이생각수성내부프로 (M-BASE)_GHS국문.pdf"
    ]
    
    results = []
    for f in target_files:
        if not os.path.exists(f): continue
        print(f"[*] 테스트 중: {f}...")
        res = process_pdf(f)
        results.append({
            "file": os.path.basename(f),
            "status": res.get("신호등", "🔴"),
            "components": res.get("구성성분", ""),
            "product": res.get("제품명", "")
        })

    print("\n" + "="*80)
    print(f"{'파일명':<40} | {'상태':<5} | {'제품명':<20} | {'구성성분'}")
    print("-"*100)
    for r in results:
        print(f"{r['file'][:40]:<40} | {r['status']:<5} | {r['product'][:20]:<20} | {r['components']}")
    print("="*100)

if __name__ == "__main__":
    run_subset_test()
