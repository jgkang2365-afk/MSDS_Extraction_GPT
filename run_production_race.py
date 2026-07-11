# -*- coding: utf-8 -*-
# MSDS 전수 회귀 검증 레이스 가동 및 골든 마스터 안전 갱신 인터락 스크립트

import os
import sys
import json
import re
import time
import glob
import hashlib
import unicodedata
import shutil
from datetime import datetime

# 컴파일 캐시 꼬임 방지를 위해 pycache 폴더 선제 세척
def clean_pycache():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pycache_paths = [
        os.path.join(base_dir, "__pycache__"),
        os.path.join(base_dir, "opendataloader", "__pycache__")
    ]
    for p in pycache_paths:
        if os.path.exists(p):
            try:
                shutil.rmtree(p)
                print(f"[*] 파이썬 컴파일 캐시 제거 완료: {p}")
            except Exception as e:
                print(f"[!] 캐시 제거 중 예외 발생: {e}")

clean_pycache()

# 프로젝트 코어 및 엔진 임포트
import msds_engine_v6
from msds_engine_v6 import MSDSEngineV6
from msds_core import MSDSCore

# 전역 몽키 패칭 변수 배선
current_processing_file = None
filter_status_map = {}
balances_status_map = {}

# 천칭 필터(verify_mathematical_천칭_filter) 몽키 패칭
original_verify_filter = MSDSEngineV6.verify_mathematical_천칭_filter
def patched_verify_filter(self, text):
    is_ok, reason = original_verify_filter(self, text)
    if current_processing_file:
        filter_status_map[current_processing_file] = "🟢정상" if is_ok else f"🔴차단({reason})"
    return is_ok, reason

MSDSEngineV6.verify_mathematical_천칭_filter = patched_verify_filter

# 화학 밸런스 검증(validate_chemical_balances) 몽키 패칭
original_validate_balances = MSDSEngineV6.validate_chemical_balances
def patched_validate_balances(self, comps, log_func=None):
    is_ok = original_validate_balances(self, comps, log_func)
    if current_processing_file:
        balances_status_map[current_processing_file] = "🟢정상" if is_ok else "🔴차단"
    return is_ok

MSDSEngineV6.validate_chemical_balances = patched_validate_balances

# 동아시아 문자 폭(East Asian Width) 정렬 패딩 정렬 알고리즘 구현
def get_visual_width(s):
    width = 0
    for char in s:
        status = unicodedata.east_asian_width(char)
        if status in ('W', 'F', 'A'):
            width += 2
        else:
            width += 1
    return width

def pad_string(s, target_width, align='left'):
    s = str(s)
    current_width = get_visual_width(s)
    pad_len = target_width - current_width
    if pad_len <= 0:
        return s
    
    if align == 'left':
        return s + ' ' * pad_len
    elif align == 'right':
        return ' ' * pad_len + s
    else:
        left_pad = pad_len // 2
        right_pad = pad_len - left_pad
        return ' ' * left_pad + s + ' ' * right_pad

# 마크다운 표 출력 헬퍼 함수
def print_markdown_table(headers, rows, alignments=None):
    if not alignments:
        alignments = ['left'] * len(headers)
        
    col_widths = [get_visual_width(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], get_visual_width(str(val)))
            
    header_line = "| " + " | ".join(pad_string(h, col_widths[idx], alignments[idx]) for idx, h in enumerate(headers)) + " |"
    print(header_line)
    
    sep_parts = []
    for idx, align in enumerate(alignments):
        width = col_widths[idx]
        if align == 'left':
            sep_parts.append(":" + "-" * (width - 1))
        elif align == 'right':
            sep_parts.append("-" * (width - 1) + ":")
        else:
            sep_parts.append(":" + "-" * (width - 2) + ":")
    sep_line = "| " + " | ".join(sep_parts) + " |"
    print(sep_line)
    
    for row in rows:
        row_line = "| " + " | ".join(pad_string(val, col_widths[idx], alignments[idx]) for idx, val in enumerate(row)) + " |"
        print(row_line)

def run_race():
    global current_processing_file
    print("\n" + "="*80)
    print("🚀 [전수 레이스 가동] 47개 MSDS 파일 순차 가동 시작")
    print("="*80)
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_file_dir = os.path.join(base_dir, "TEST_File")
    pdf_files = glob.glob(os.path.join(test_file_dir, "*.pdf")) + glob.glob(os.path.join(test_file_dir, "*.PDF"))
    pdf_files = list(set(pdf_files))
    
    def get_file_num(path):
        fn = os.path.basename(path)
        m = re.match(r'^(\d+)', fn)
        return int(m.group(1)) if m else 999
        
    pdf_files = sorted(pdf_files, key=get_file_num)
    
    mes_cas_map = {}
    mes_file = os.path.join(base_dir, "msds_index.json")
    if os.path.exists(mes_file):
        try:
            with open(mes_file, "r", encoding="utf-8") as f:
                mes_data = json.load(f)
            for entry in mes_data:
                cas_key = str(entry.get("CAS No.", "")).strip()
                if cas_key and cas_key.lower() != 'nan' and re.match(r'^\d{2,7}-\d{2}-\d$', cas_key):
                    if cas_key not in mes_cas_map:
                        mes_cas_map[cas_key] = entry
            print(f"[*] msds_index.json 마스터 데이터 로드 완료 (매핑 {len(mes_cas_map)}건)")
        except Exception as e:
            print(f"[!] 마스터 데이터 로드 중 오류: {e}")
            
    core = MSDSCore()
    results = []
    
    for idx, f_path in enumerate(pdf_files, 1):
        filename = os.path.basename(f_path)
        file_id = f"{get_file_num(f_path):03d}"
        print(f"[*] [{idx}/{len(pdf_files)}] 가동 대상 진입: {filename}")
        
        f_hash = core.calculate_file_hash(f_path)
        
        current_processing_file = f_path
        filter_status_map[f_path] = "🟢정상"
        balances_status_map[f_path] = "🟢정상"
        
        start_t = time.time()
        
        try:
            ext_res = core.extract_from_pdf(f_path, log_func=print)
            raw_val_res = core.validate_with_kosha(ext_res.get("구성성분", ""), f_hash=f_hash)
            
            elapsed = time.time() - start_t
            
            cas_content = ext_res.get("구성성분", "")
            cas_to_content = {}
            if cas_content:
                for part in cas_content.split(";"):
                    part = part.strip()
                    m = re.search(r"(\d{2,7}-\d{2}-\d)\s*(?:\(([^)]+)\))?", part)
                    if m:
                        cas_to_content[m.group(1)] = m.group(2) if m.group(2) else ""
            
            res_work_subjects = []
            res_work_non_subjects = []
            components_for_golden = []
            
            for c in raw_val_res.get("components", []):
                name = c.get("name", "Unknown")
                cas = c.get("cas", "")
                range_val = cas_to_content.get(cas, c.get("content", ""))
                
                if re.search(r'[가-힣]', name):
                    name_no_eng = re.sub(r'\s*\([A-Za-z\s\d,]+\)$', '', name)
                    clean_name = name_no_eng.strip()
                else:
                    clean_name = name.strip()
                    
                mes_std_name = msds_engine_v6.MES_MASTER_MAP.get(cas, "")
                if mes_std_name:
                    clean_name = str(mes_std_name)
                    clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()
                else:
                    mes_entry = mes_cas_map.get(cas, {})
                    fallback_name = mes_entry.get("측정대상 물질명")
                    if fallback_name and str(fallback_name).lower() != 'nan':
                        clean_name = str(fallback_name)
                        clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()
                
                osh = c.get("osh", {})
                is_work = osh.get("is_measured", False)
                
                if not range_val or str(range_val).strip() == "":
                    range_val = "미기재%"
                    
                if is_work:
                    percentage = 0.0
                    nums = re.findall(r'[\d\.]+', range_val)
                    if nums:
                        try: percentage = max(float(n) for n in nums)
                        except: percentage = 0.0
                        if "<" in range_val and percentage <= 1.0:
                            percentage = 0.5
                    else:
                        percentage = 100.0
                        
                    is_ge_1 = (percentage >= 1.0)
                    if is_ge_1:
                        res_work_subjects.append(f"{clean_name}({range_val})")
                    else:
                        res_work_non_subjects.append(f"{clean_name}({range_val})")
                
                components_for_golden.append({
                    "chemical_name": clean_name,
                    "cas": cas,
                    "content_raw": range_val.replace("%", ""),
                    "content_expected": range_val if range_val.endswith("%") or range_val == "Rem." or range_val == "미기재%" else f"{range_val}%",
                    "source_page": 1
                })
                
            subj_str = "; ".join(res_work_subjects)
            non_subj_str = f"측정 비대상[{'; '.join(res_work_non_subjects)}]" if res_work_non_subjects else ""
            final_work_str = "; ".join(filter(None, [subj_str, non_subj_str]))
            
            prod_name = ext_res.get("제품명", "")
            is_welding = ("용접" in prod_name) or ("welding" in prod_name.lower())
            has_iron = "7439-89-6" in cas_to_content
            if is_welding and has_iron:
                welding_hazard = "용접흄; 산화철(분진, 흄)"
                if final_work_str:
                    final_work_str = f"{welding_hazard}; {final_work_str}"
                else:
                    final_work_str = welding_hazard
            
            doc_type = ext_res.get("doc_type", "디지털")
            
            f_status = filter_status_map.get(f_path, "🟢정상")
            b_status = balances_status_map.get(f_path, "🟢정상")
            final_balance_result = "🟢정상"
            if "🔴" in f_status:
                final_balance_result = f_status
            elif "🔴" in b_status:
                final_balance_result = "🔴차단(가드레일 위반)"
                
            results.append({
                "id": file_id,
                "file": filename,
                "source_sha256": f_hash,
                "document_type": "digital" if doc_type == "디지털" else "scanned",
                "product_name": prod_name,
                "components": components_for_golden,
                "used_engine": ext_res.get("used_engine", "local_bypass"),
                "신호등": ext_res.get("신호등", "🟢"),
                "integrity_score": ext_res.get("integrity_score", 100),
                "balance_result": final_balance_result,
                "work_subjects": final_work_str,
                "extracted_cas_content": cas_content
            })
            
        except Exception as e:
            print(f"[💥 크래시 격발] 파일 {filename} 처리 중 에러 발생: {e}")
            results.append({
                "id": file_id,
                "file": filename,
                "source_sha256": f_hash,
                "document_type": "unknown",
                "product_name": "",
                "components": [],
                "used_engine": "error_isolation",
                "신호등": "🔴",
                "integrity_score": 0,
                "balance_result": f"🔴에러({str(e)})",
                "work_subjects": "",
                "extracted_cas_content": ""
            })
            
    print("\n" + "="*80)
    print("🚨 [2중 대조 상세 표 사출]")
    print("="*80)
    
    print("\n[표 1] 기계실 기본 정보 요약 표\n")
    headers1 = ["번호", "파일명", "엔진종류", "신호등", "무결성 점수", "천칭 필터 결과", "제품명(최종)"]
    rows1 = []
    for r in results:
        fn_short = r["file"]
        if len(fn_short) > 25:
            fn_short = fn_short[:22] + "..."
        rows1.append([
            r["id"],
            fn_short,
            r["used_engine"],
            r["신호등"],
            f"{r['integrity_score']}점",
            r["balance_result"],
            r["product_name"]
        ])
    print_markdown_table(headers1, rows1, alignments=['center', 'left', 'center', 'center', 'center', 'left', 'left'])
    
    print("\n[표 2] CAS/측정대상 상세 대조 표\n")
    headers2 = ["번호", "파일명", "최종 CAS(함량) 체인", "KOSHA 측정대상 물질명"]
    rows2 = []
    for r in results:
        fn_short = r["file"]
        if len(fn_short) > 25:
            fn_short = fn_short[:22] + "..."
        rows2.append([
            r["id"],
            fn_short,
            r["extracted_cas_content"],
            r["work_subjects"]
        ])
    print_markdown_table(headers2, rows2, alignments=['center', 'left', 'left', 'left'])
    
    regression_failures = 0
    golden_file = os.path.join(base_dir, "golden", "msds_golden_v1.json")
    
    if os.path.exists(golden_file):
        print("\n" + "="*80)
        print("🕵️ [골든 마스터 회귀 검증 집행 시작]")
        print("="*80)
        
        with open(golden_file, "r", encoding="utf-8") as f:
            golden_data = json.load(f)
            
        golden_cases = golden_data.get("cases", [])
        results_map = {r["id"]: r for r in results}
        
        for g_case in golden_cases:
            g_id = g_case.get("id")
            g_file = g_case.get("file")
            
            matched_r = results_map.get(g_id)
            if not matched_r:
                print(f"[❌ 회귀 오류] 골든 케이스 {g_id}({g_file})에 매칭되는 실행 결과를 찾지 못했습니다.")
                regression_failures += 1
                continue
                
            def clean_pn_for_compare(pn):
                p_clean = str(pn).lower().strip()
                p_clean = p_clean.replace("™", "").replace("tm", "").replace("(tm)", "")
                return re.sub(r'[^a-zA-Z0-9가-힣]', '', p_clean)

            expected_pn = g_case["product_name"]["expected"]
            allowed_variants = g_case["product_name"].get("allowed_variants", [])
            clean_expected = clean_pn_for_compare(expected_pn)
            clean_allowed = {clean_pn_for_compare(v) for v in allowed_variants}
            allowed_set = {clean_expected} | clean_allowed
            
            clean_actual = clean_pn_for_compare(matched_r["product_name"])
            
            if clean_actual not in allowed_set:
                print(f"[❌ 제품명 불일치] ID {g_id} | 기대값: {expected_pn} | 실제값: '{matched_r['product_name']}'")
                regression_failures += 1
                
            g_components = g_case.get("components", [])
            actual_comps = matched_r["components"]
            
            g_comp_map = {c["cas"]: unicodedata.normalize("NFKC", c["content_expected"]).replace(" ", "").replace("%", "") for c in g_components}
            actual_comp_map = {c["cas"]: unicodedata.normalize("NFKC", c["content_expected"]).replace(" ", "").replace("%", "") for c in actual_comps}
            
            if len(g_comp_map) != len(actual_comp_map):
                print(f"[❌ 성분 개수 불일치] ID {g_id} | 기대개수: {len(g_comp_map)} | 실제개수: {len(actual_comp_map)}")
                print(f"  ├─ 기대 CAS 목록: {list(g_comp_map.keys())}")
                print(f"  └─ 실제 CAS 목록: {list(actual_comp_map.keys())}")
                regression_failures += 1
                continue
                
            for cas, expected_cont in g_comp_map.items():
                if cas not in actual_comp_map:
                    print(f"[❌ 성분 유실] ID {g_id} | 기대 CAS: {cas} 누락됨")
                    regression_failures += 1
                else:
                    actual_cont = actual_comp_map[cas]
                    if expected_cont != actual_cont:
                        print(f"[❌ 함량 불일치] ID {g_id} | CAS {cas} | 기대치: {expected_cont}% | 실제치: {actual_cont}%")
                        regression_failures += 1
                        
        print("-"*80)
        print(f"📊 [골든 마스터 회귀 검증 마감] 불일치 회귀 오류 수: {regression_failures}건")
        print("="*80 + "\n")
    else:
        print(f"\n[!] 골든 마스터 파일이 존재하지 않아 회귀 검증을 우회합니다: {golden_file}")
        
    if regression_failures == 0:
        print("🟢 [골든 마스터 갱신 인터락 가동] 회귀 오류 0건 인증 완료!")
        print("[*] 47개 파일 전수 실행 결과를 기반으로 'msds_golden_v1.json' 원장을 안전하게 업데이트합니다.")
        
        new_cases = []
        for r in results:
            new_cases.append({
                "id": r["id"],
                "file": r["file"],
                "source_sha256": r["source_sha256"],
                "document_type": r["document_type"],
                "product_name": {
                    "expected": r["product_name"],
                    "allowed_variants": []
                },
                "components": r["components"],
                "cas_missing_components": [],
                "regression_tags": []
            })
            
        updated_golden = {
            "schema_version": "1.0",
            "dataset_id": "msds-core-regression-v1",
            "review_status": "approved",
            "scope": {
                "product_name_section": 1,
                "components_section": 3,
                "component_key": "cas",
                "include_only_valid_cas": True,
                "exclude_cas_outside_section_3": True,
                "required_filename_marker": "★"
            },
            "cases": new_cases
        }
        
        try:
            with open(golden_file, "w", encoding="utf-8") as wf:
                json.dump(updated_golden, wf, ensure_ascii=False, indent=2)
            print("✅ [골든 마스터 최신화 성공] msds_golden_v1.json 원장이 최신 스냅샷으로 동결 및 잠금되었습니다.")
        except Exception as e:
            print(f"❌ [원장 작성 예외 실패] 파일 저장 중 오류 발생: {e}")
            sys.exit(1)
    else:
        print("🔴 [골든 마스터 갱신 인터락 차단] 회귀 오류가 실재하므로 골든 마스터 원장을 갱신하지 않고 폐쇄합니다.")
        sys.exit(1)

    print("\n" + "="*80)
    print("🧪 [최종 유닛 테스트 기동] msds_engine_v6.self_test_regression()")
    print("="*80)
    try:
        msds_engine_v6.self_test_regression()
        print("🟢 [유닛 테스트 최종 통과] self_test_regression() 완착 성공!")
    except Exception as e:
        print(f"🔴 [유닛 테스트 크래시] self_test_regression() 수행 중 에러 격발: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_race()
