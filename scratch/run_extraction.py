# -*- coding: utf-8 -*-
import sys
import os
import json
import glob

# 표준 출력을 UTF-8로 재설정하여 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# 프로젝트 루트 디렉토리를 sys.path에 추가하여 msds_engine_v6 모듈 임포트 가능케 함
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from msds_engine_v6 import MSDSEngineV6
except ImportError as e:
    print(f"[-] msds_engine_v6 임포트 실패: {e}")
    sys.exit(1)

# 특정 번호의 PDF 파일 경로를 glob 패턴으로 안전하게 획득
def find_pdf_path(number_prefix):
    search_pattern = os.path.join(project_root, "TEST_File", f"{number_prefix}*.pdf")
    matches = glob.glob(search_pattern)
    if not matches:
        # 대소문자 매칭 시도
        search_pattern_upper = os.path.join(project_root, "TEST_File", f"{number_prefix}*.PDF")
        matches = glob.glob(search_pattern_upper)
    
    if matches:
        return matches[0]
    return None

def main():
    if len(sys.argv) < 2:
        print("[-] 사용법: python run_extraction.py [출력 JSON 파일 경로]")
        sys.exit(1)
        
    output_path = sys.argv[1]
    target_ids = ["005", "037", "046"]
    
    print("[*] MSDSEngineV6 인스턴스 초기화 중...")
    engine = MSDSEngineV6()
    
    results = {}
    
    for tid in target_ids:
        pdf_path = find_pdf_path(tid)
        if not pdf_path:
            print(f"[-] 자재 ID {tid}에 해당하는 PDF 파일을 찾을 수 없습니다.")
            continue
            
        print(f"[*] 자재 ID {tid} 분석 실행 시작: {os.path.basename(pdf_path)}")
        try:
            # log_func에 간단한 진행 상황 프린트 함수 등록
            def log_progress(msg):
                print(f"    [엔진 로그] {msg}")
                
            res = engine.process_msds_pipeline(pdf_path, log_func=log_progress)
            results[tid] = {
                "file_path": pdf_path,
                "file_name": os.path.basename(pdf_path),
                "result": res
            }
            print(f"[+] 자재 ID {tid} 분석 완료!")
        except Exception as ex:
            print(f"[-] 자재 ID {tid} 분석 중 예외 발생: {ex}")
            results[tid] = {
                "file_path": pdf_path,
                "file_name": os.path.basename(pdf_path),
                "error": str(ex)
            }
            
    # 결과를 지정된 파일로 저장
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"[+] 결과를 {output_path} 파일에 정상적으로 저장했습니다.")
    except Exception as ex:
        print(f"[-] 결과 파일 저장 실패: {ex}")
        sys.exit(1)

if __name__ == "__main__":
    main()
