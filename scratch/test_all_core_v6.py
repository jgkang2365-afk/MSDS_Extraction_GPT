# msds_core.py 메인 구동축을 직접 격발하는 9개 전수 자재 통합 테스트 러너
import os
import sys
import glob
import time
import json

# 상위 경로를 모듈 패스에 추가하여 msds_core 임포트 보장
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from msds_core import MSDSCore

def run_production_core_race():
    print("==================================================")
    print("[*] 가동: msds_core.py 기반 9개 전수 자재 레이스 시작")
    print("==================================================")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_file_dir = os.path.join(base_dir, "TEST_File")
    
    # 9개 전수 대상 자재 패턴 매칭 정의 (001~007번, 015번, 036번)
    patterns = ["*001*.pdf", "*002*.pdf", "*003*.pdf", "*004*.pdf", "*005*.pdf", "*006*.pdf", "*007*.pdf", "*015*.pdf", "*036*.pdf"]
    target_files = []
    
    for p in patterns:
        matched = glob.glob(os.path.join(test_file_dir, p))
        if matched:
            target_files.extend(matched)
            
    target_files = sorted(list(set(target_files)))
    if not target_files:
        print("❌ [오류] 9개 테스트 PDF 자재를 수집하지 못했습니다.")
        sys.exit(1)
        
    print(f"[*] 총 {len(target_files)}권의 자재가 핵심 라인에 진입합니다.")
    
    core = MSDSCore()
    all_results = []
    
    for idx, f_path in enumerate(target_files, 1):
        filename = os.path.basename(f_path)
        print(f"\n[{idx}/9] Core 격발 대상: {filename}")
        
        start_time = time.time()
        try:
            # 1단계: MSDSCore.extract_from_pdf 직접 격발 (msds_engine_v6 연동)
            ext_res = core.extract_from_pdf(f_path, log_func=print)
            
            # 2단계: MSDSCore.validate_with_kosha 연쇄 검증
            val_res = core.validate_with_kosha(ext_res.get("구성성분", ""))
            
            elapsed = time.time() - start_time
            print("  [성공 완료 리포트]")
            print(f"  ├─ 제품명: {ext_res.get('제품명')}")
            print(f"  ├─ 신호등: {ext_res.get('신호등', '🟢')}")
            print(f"  ├─ 매칭 엔진: {ext_res.get('used_engine')}")
            print(f"  ├─ 무결성 점수: {ext_res.get('integrity_score')}점")
            print(f"  ├─ 구성성분: {ext_res.get('구성성분')}")
            print(f"  └─ 소요 시간: {elapsed:.2f}초")
            
            all_results.append({
                "file": filename,
                "product_name": ext_res.get("제품명"),
                "traffic_light": ext_res.get("신호등", "🟢"),
                "engine": ext_res.get("used_engine"),
                "score": ext_res.get("integrity_score"),
                "components": ext_res.get("구성성분"),
                "status": "SUCCESS"
            })
            
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"  ❌ 치명적 크래시 예외 포착 (무정차 격리 바이패스): {e}")
            all_results.append({
                "file": filename,
                "product_name": "격리수거 자재",
                "traffic_light": "🔴",
                "engine": "error_isolation",
                "score": 0,
                "components": "",
                "status": f"FAILED: {str(e)}"
            })
            
    print("\n==================================================")
    print("📋 [최종 레이스 완주 성적표]")
    print("==================================================")
    for idx, r in enumerate(all_results, 1):
        print(f"[{idx}/9] {r['file']} ➔ {r['traffic_light']} ({r['product_name']}) | 엔진: {r['engine']} | 점수: {r['score']}점 | 상태: {r['status']}")
    print("==================================================")

if __name__ == "__main__":
    run_production_core_race()
