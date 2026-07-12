# -*- coding: utf-8 -*-
import sys
import os
import json
import shutil
import subprocess

# 표준 출력을 UTF-8로 설정하여 한글 및 특수기호 깨짐 방지
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 파일 경로 정의
engine_path = os.path.join(project_root, "msds_engine_v6.py")
engine_bak_path = os.path.join(project_root, "msds_engine_v6.py.bak")
cache_path = os.path.join(project_root, "msds_cache_registry.json")
cache_bak_path = os.path.join(project_root, "msds_cache_registry.json.bak")
golden_path = os.path.join(project_root, "golden", "msds_golden_v1.json")

# 임시 결과 파일 경로 정의
res_flash_path = os.path.join(project_root, "scratch", "res_flash.json")
res_lite_path = os.path.join(project_root, "scratch", "res_lite.json")
report_md_path = os.path.join(project_root, "scratch", "lite_comprehensive_test_report.md")

def print_step(step_num, title):
    print(f"\n==================================================")
    print(f"[진입] Step {step_num} - {title}")
    print(f"==================================================")

def backup_files():
    # 1. 엔진 파일 백업
    if os.path.exists(engine_path):
        shutil.copy2(engine_path, engine_bak_path)
        print(f"[+] msds_engine_v6.py 파일을 백업했습니다.")
    else:
        print(f"[-] 백업할 msds_engine_v6.py 파일이 존재하지 않습니다.")
        sys.exit(1)

    # 2. 캐시 장부 백업 및 임시 우회 (빈 캐시 파일 생성)
    if os.path.exists(cache_path):
        shutil.copy2(cache_path, cache_bak_path)
        print(f"[+] 기존 캐시 장부를 백업했습니다.")
        # 빈 캐시 장부로 덮어써서 우회 강제
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({}, f)
        print(f"[+] 캐시 장부를 빈 상태로 초기화하여 우회 경로를 확보했습니다.")
    else:
        print(f"[*] 캐시 장부가 존재하지 않아 빈 캐시 장부를 신규 생성합니다.")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({}, f)

def restore_files():
    # 1. 엔진 파일 복구
    if os.path.exists(engine_bak_path):
        shutil.copy2(engine_bak_path, engine_path)
        os.remove(engine_bak_path)
        print(f"[+] msds_engine_v6.py 파일이 원래대로 복구되었습니다.")
    
    # 2. 캐시 장부 복구
    if os.path.exists(cache_bak_path):
        shutil.copy2(cache_bak_path, cache_path)
        os.remove(cache_bak_path)
        print(f"[+] 기존 캐시 장부가 성공적으로 복구되었습니다.")
    elif os.path.exists(cache_path):
        os.remove(cache_path)
        print(f"[+] 임시 캐시 장부를 제거했습니다.")

def run_extraction_process(output_json):
    run_script = os.path.join(project_root, "scratch", "run_extraction.py")
    # subprocess를 실행할 때 현재 사용 중인 sys.executable을 사용하여 가상환경 상속을 강제함
    cmd = [sys.executable, run_script, output_json]
    print(f"[*] 실행 중인 명령어: {' '.join(cmd)}")
    
    # cp949 인코딩 문제 방지를 위해 utf-8 지정
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    print(result.stdout)
    if result.stderr:
        print(f"[-] 서브프로세스 에러 로그:\n{result.stderr}")
    return result.returncode == 0

def modify_engine_to_lite():
    print(f"[*] msds_engine_v6.py의 AI 모델을 'gemini-2.5-flash-lite'로 치환 설정 중...")
    with open(engine_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 하드코딩된 'gemini-2.5-flash' 문자열을 'gemini-2.5-flash-lite'로 치환
    target_str = "gemini-2.5-flash"
    replacement_str = "gemini-2.5-flash-lite"
    
    occurrences = content.count(target_str)
    print(f"[*] 치환 전 '{target_str}' 발견 횟수: {occurrences}회")
    
    new_content = content.replace(target_str, replacement_str)
    
    with open(engine_path, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    # 검증차 다시 로드하여 확인
    with open(engine_path, "r", encoding="utf-8") as f:
        verified_content = f.read()
    
    new_occurrences = verified_content.count(replacement_str)
    print(f"[+] 치환 후 '{replacement_str}' 발견 횟수: {new_occurrences}회")
    return new_occurrences > 0

def clean_compiled_caches():
    # 컴파일 캐시 꼬임 방지를 위해 pycache 제거
    pycache_path = os.path.join(project_root, "__pycache__")
    scratch_pycache = os.path.join(project_root, "scratch", "__pycache__")
    
    for p in [pycache_path, scratch_pycache]:
        if os.path.exists(p):
            try:
                shutil.rmtree(p)
                print(f"[+] 컴파일 캐시 제거 완료: {p}")
            except Exception as e:
                print(f"[-] 컴파일 캐시 제거 실패 ({p}): {e}")

def load_json_file(file_path):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_golden_components_str(components):
    # 골든 원장의 성분 데이터를 cas(content_expected); cas(content_expected) 형태로 빌드
    parts = []
    for c in components:
        cas = c.get("cas", "").strip()
        expected = c.get("content_expected", "").strip()
        if cas:
            parts.append(f"{cas}({expected})")
    return "; ".join(parts)

def evaluate_test_results():
    golden_data = load_json_file(golden_path)
    flash_results = load_json_file(res_flash_path)
    lite_results = load_json_file(res_lite_path)
    
    cases = golden_data.get("cases", [])
    target_ids = ["005", "037", "046"]
    
    comparison_report = []
    comparison_report.append("# MSDS 3종 Scanned 자재 Lite 모델 정합성 종합 검증 보고서")
    comparison_report.append(f"\n- **검증 대상 모델**: `gemini-2.5-flash-lite` (대조군: `gemini-2.5-flash`)")
    comparison_report.append(f"- **검증 대상 자재**: 3종 scanned 자재 (005, 037, 046)")
    comparison_report.append("\n## 1. 모델별 정합성 비교 대조표")
    comparison_report.append("\n| 자재 ID | 평가 항목 | 골든 정답 원장 | Gemini 2.5 Flash | Gemini 2.5 Flash Lite | Lite 판정 (PASS/FAIL) |")
    comparison_report.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    
    pass_count_pn = 0
    pass_count_comp = 0
    total_eval_items = len(target_ids)
    
    details_report = []
    details_report.append("\n## 2. 자재별 세부 대조 내역 및 오독 분석")
    
    for tid in target_ids:
        # 골든 원장 정보 찾기
        case_info = next((c for c in cases if c.get("id") == tid), None)
        if not case_info:
            print(f"[-] 골든 원장에서 ID {tid}를 찾을 수 없습니다.")
            continue
            
        g_pn = case_info.get("product_name", {}).get("expected", "").strip()
        g_comps = case_info.get("components", [])
        g_comps_str = build_golden_components_str(g_comps)
        
        # Flash 결과 정보 찾기
        f_info = flash_results.get(tid, {}).get("result", {})
        f_pn = f_info.get("제품명", "").strip()
        f_comps_str = f_info.get("구성성분", "").strip()
        
        # Lite 결과 정보 찾기
        l_info = lite_results.get(tid, {}).get("result", {})
        l_pn = l_info.get("제품명", "").strip()
        l_comps_str = l_info.get("구성성분", "").strip()
        
        # PASS/FAIL 판정 (1글자의 오차도 없는 완전 일치 조건)
        pn_pass = (g_pn == l_pn)
        comp_pass = (g_comps_str == l_comps_str)
        
        if pn_pass:
            pass_count_pn += 1
            pn_status = "🟢 PASS"
        else:
            pn_status = "🔴 FAIL"
            
        if comp_pass:
            pass_count_comp += 1
            comp_status = "🟢 PASS"
        else:
            comp_status = "🔴 FAIL"
            
        comparison_report.append(f"| **{tid}** | 제품명 | `{g_pn}` | `{f_pn}` | `{l_pn}` | {pn_status} |")
        comparison_report.append(f"| **{tid}** | 구성성분 | `{g_comps_str}` | `{f_comps_str}` | `{l_comps_str}` | {comp_status} |")
        
        # 세부 분석 보고서 생성
        details_report.append(f"\n### [자재 {tid}] {case_info.get('file', '')}")
        
        # 제품명 분석
        details_report.append(f"- **제품명 비교**:")
        details_report.append(f"  - 골든 원장 정답: `{g_pn}`")
        details_report.append(f"  - Gemini 2.5 Flash: `{f_pn}`")
        details_report.append(f"  - Gemini 2.5 Flash Lite: `{l_pn}`")
        if pn_pass:
            details_report.append(f"  - **제품명 판정 결과**: 🟢 PASS (일치)")
        else:
            reason = "오독"
            # 구체적인 원인 분석
            if not l_pn:
                reason = "추출 유실 (공란 반환)"
            elif l_pn != f_pn:
                reason = "Lite 모델의 환각 혹은 텍스트 경계 추론 오차"
            else:
                reason = "Flash 및 Lite 동시 오독 (전처리 혹은 비전 인식 한계)"
            details_report.append(f"  - **제품명 판정 결과**: 🔴 FAIL (불일치 - 사유: {reason})")
            
        # 성분 분석
        details_report.append(f"- **구성성분 비교 (CAS 및 함량)**:")
        details_report.append(f"  - 골든 원장 정답: `{g_comps_str}`")
        details_report.append(f"  - Gemini 2.5 Flash: `{f_comps_str}`")
        details_report.append(f"  - Gemini 2.5 Flash Lite: `{l_comps_str}`")
        if comp_pass:
            details_report.append(f"  - **성분 판정 결과**: 🟢 PASS (일치)")
        else:
            reason = "오독"
            if not l_comps_str or l_comps_str == "미기재%":
                reason = "성분 추출 완전 유실"
            elif l_comps_str != f_comps_str:
                reason = "Lite 모델의 함량 수치/부등호 오독 또는 CAS 번호 환각 및 누락"
            else:
                reason = "Flash 및 Lite 동시 수치 오독 (비전 분석 오인 또는 격자 라우팅 한계)"
            details_report.append(f"  - **성분 판정 결과**: 🔴 FAIL (불일치 - 사유: {reason})")
            
    # 종합 합격률 산출
    total_checks = total_eval_items * 2
    passed_checks = pass_count_pn + pass_count_comp
    pass_rate = (passed_checks / total_checks) * 100
    
    summary_section = []
    summary_section.append("\n## 3. 종합 검증 요약")
    summary_section.append(f"- **제품명 부문 합격률**: {pass_count_pn}/{total_eval_items} ({(pass_count_pn/total_eval_items)*100:.1f}%)")
    summary_section.append(f"- **구성성분 부문 합격률**: {pass_count_comp}/{total_eval_items} ({(pass_count_comp/total_eval_items)*100:.1f}%)")
    summary_section.append(f"- **전체 종합 합격률**: {passed_checks}/{total_checks} ({pass_rate:.1f}%)")
    
    # 보고서 내용 결합
    full_report = "\n".join(comparison_report) + "\n" + "\n".join(summary_section) + "\n" + "\n".join(details_report)
    
    # 보고서 파일 저장
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(full_report)
    print(f"\n[+] 종합 검증 보고서가 {report_md_path} 경로에 정상적으로 생성되었습니다.")
    
    # 화면에도 출력
    print(full_report)

def main():
    print("[*] MSDS Lite 모델 종합 검증 통합 테스트 가동...")
    
    try:
        # Step 1: 캐시 백업 및 Flash 모델 실행
        print_step(1, "캐시 백업 및 gemini-2.5-flash 모델 기반 3개 자재 MSDS 분석 실행")
        backup_files()
        clean_compiled_caches()
        
        print("[*] 1단계: 기존 'gemini-2.5-flash' 모델 기준 분석 실행 중 (수 분 소요될 수 있음)...")
        success = run_extraction_process(res_flash_path)
        if not success:
            print("[-] Flash 모델 기준 분석 실행 중 실패가 감지되었습니다. 계속 진행합니다.")
            
        # Step 2: 엔진 파일 내 모델명 수정
        print_step(2, "msds_engine_v6.py 파일 내 모델명을 gemini-2.5-flash-lite로 수정")
        modified = modify_engine_to_lite()
        if not modified:
            print("[-] msds_engine_v6.py 모델명 치환을 실패했습니다. 중단합니다.")
            restore_files()
            sys.exit(1)
            
        # Step 3: Lite 모델 실행
        print_step(3, "gemini-2.5-flash-lite 모델 기반 3개 자재 MSDS 분석 실행")
        clean_compiled_caches()
        
        # 🛡️ [캐시 장부 강제 우회 가드레일] 1단계(Flash) 분석 결과가 캐시 장부에 기재되어 Lite 분석 시 우회(Bypass)되는 것을 원천 차단
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({}, f)
            print("[+] 3단계 실행을 위해 임시 캐시 장부를 빈 상태로 다시 초기화했습니다.")
        except Exception as ce:
            print(f"[-] 3단계 캐시 초기화 예외 발생: {ce}")
        
        print("[*] 3단계: 'gemini-2.5-flash-lite' 모델 기준 분석 실행 중...")
        success = run_extraction_process(res_lite_path)
        if not success:
            print("[-] Lite 모델 기준 분석 실행 중 실패가 감지되었습니다. 계속 진행합니다.")
            
        # Step 4: 양 모델 결과와 골든 원장 비교 및 리포팅
        print_step(4, "수집된 두 모델 결과와 골든 원장 데이터 정밀 비교 및 종합 검증 리포트 파일 생성")
        evaluate_test_results()
        
    except Exception as ex:
        print(f"[-] 테스트 실행 중 예외 격발: {ex}")
    finally:
        # Step 5: 파일 원상복구
        print_step(5, "msds_engine_v6.py 파일 및 캐시 레지스트리 원상복구")
        restore_files()
        clean_compiled_caches()
        print("[*] 통합 테스트 프로세스 정상 완료.")

if __name__ == "__main__":
    main()
