import os
import sys
import time
from msds_engine_v5 import process_pdf, VERSION

def run_bulk_test():
    print(f"\n" + "="*50)
    print(f"🚀 MSDS Engine {VERSION} Bulk Test (33 Files)")
    print("="*50)
    
    # TEST_File 폴더 내의 PDF 리스트 추출
    test_dir = "TEST_File"
    if not os.path.exists(test_dir):
        print(f"❌ {test_dir} 폴더를 찾을 수 없습니다.")
        return
        
    all_files = [os.path.join(test_dir, f) for f in os.listdir(test_dir) if f.lower().endswith('.pdf')]
    target_files = sorted(all_files)
    
    if not target_files:
        print("❌ 테스트 대상 PDF 파일을 찾을 수 없습니다.")
        return

    success_count = 0
    results = []

    for f in target_files:
        try:
            print(f"[*] 테스트 중: {f}...")
            res = process_pdf(f)
            status = res.get("신호등", "🔴")
            p_name = res.get("제품명", "미추출")
            
            if status == "🟢":
                success_count += 1
            
            results.append({
                "file": f,
                "status": status,
                "name": p_name
            })
        except Exception as e:
            results.append({
                "file": f,
                "status": "🔴",
                "name": f"Error: {str(e)}"
            })

    print("\n" + "="*50)
    print(f"{'파일명':<40} | {'상태':<5} | {'제품명'}")
    print("-"*70)
    for r in results:
        print(f"{r['file'][:40]:<40} | {r['status']:<5} | {r['name'][:30]}")
    
    print("="*70)
    print(f"📊 최종 결과: {success_count}/{len(target_files)} 성공 (성공률: {success_count/len(target_files)*100:.1f}%)")
    print("="*70)

if __name__ == "__main__":
    run_bulk_test()
