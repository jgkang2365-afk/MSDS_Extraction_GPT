# -*- coding: utf-8 -*-
import os
import sys
import re
import time
import json
import shutil
import hashlib
import glob
import traceback

# 1. 3.12 가상환경 절대 경로 격리 및 sys.path 결착
def sanitize_paths():
    path_env = os.environ.get("PATH", "")
    if path_env:
        paths = path_env.split(os.pathsep)
        clean_paths = [p for p in paths if "python313" not in p.lower() and "python3.13" not in p.lower()]
        os.environ["PATH"] = os.pathsep.join(clean_paths)
    
    pythonpath = os.environ.get("PYTHONPATH", "")
    if pythonpath:
        paths = pythonpath.split(os.pathsep)
        clean_paths = [p for p in paths if "python313" not in p.lower() and "python3.13" not in p.lower()]
        os.environ["PYTHONPATH"] = os.pathsep.join(clean_paths)

    sys.path = [p for p in sys.path if "python313" not in p.lower() and "python3.13" not in p.lower()]

sanitize_paths()

sys.path.append(os.getcwd())
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.executable = r"C:\Users\USER\venv_312\Scripts\python.exe"

import msds_core
from msds_core import MSDSCore
import msds_engine_v6 as engine

VERSION = "24.6.0.0"

# 알파벳 열 이름을 숫자 인덱스로 변환하는 헬퍼 함수
def c2i(col_str):
    if not col_str:
        return 0
    col_str = col_str.upper().strip()
    exp = 0
    idx = 0
    for char in reversed(col_str):
        idx += (ord(char) - ord('A') + 1) * (26 ** exp)
        exp += 1
    return idx

# [주님 가이드라인] 함량 검문소
def validate_composition_limits(text):
    if not text:
        return True, "데이터 없음"
    # CAS 번호 패턴 소거
    text_clean = re.sub(r'[0-9a-zA-Z]{2,7}-[0-9a-zA-Z]{2}-[0-9a-zA-Z]{1}', '', text)
    
    # 1. 개별 성분 저울: 100% 초과 숫자 검출
    nums = re.findall(r'[\d\.]+', text_clean)
    for n in nums:
        try:
            val = float(n)
            if val > 100.0:
                return False, f"개별 성분 함량 초과 모순 ({val}%)"
        except:
            pass
            
    # 2. 범위 최대치 합계 저울
    # 범위 기호(~) 기준 최대값 산출
    ranges = re.findall(r'[\d\.]+\s*[~-]\s*([\d\.]+)', text_clean)
    max_vals = []
    for r in ranges:
        try: max_vals.append(float(r))
        except: pass
        
    # 단독 수치 산출
    text_no_ranges = re.sub(r'[\d\.]+\s*[~-]\s*[\d\.]+', '', text_clean)
    singles = re.findall(r'[\d\.]+', text_no_ranges)
    for s in singles:
        try: max_vals.append(float(s))
        except: pass
        
    total_max = sum(max_vals)
    if total_max > 110.0:
        return False, f"성분 합계 110% 초과 모순 ({total_max}%)"
        
    return True, "정상"

class DatasetGenerator:
    def __init__(self):
        self.core = MSDSCore()
        self.cache_file = "smu_cache.json"
        self.cache = {}
        self.mes_master_list = []
        self.mes_cas_map = {}
        
        self.load_cache()
        self.load_mes_master()

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                print(f"[*] 캐시 로드 완료: {len(self.cache)}건")
            except Exception as e:
                print(f"[!] 캐시 로드 실패: {e}")

    def save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[!] 캐시 저장 실패: {e}")

    def load_mes_master(self):
        mes_file = "msds_index.json"
        if not os.path.exists(mes_file):
            print(f"[!] {mes_file} 파일을 찾을 수 없습니다. 마스터 데이터셋 생략.")
            return
        try:
            with open(mes_file, "r", encoding="utf-8") as f:
                self.mes_master_list = json.load(f)
            
            for entry in self.mes_master_list:
                cas_key = str(entry.get("CAS No.", "")).strip()
                if cas_key and cas_key.lower() != 'nan' and re.match(r'^\d{2,7}-\d{2}-\d$', cas_key):
                    if cas_key not in self.mes_cas_map:
                        self.mes_cas_map[cas_key] = entry
            print(f"[*] MES 마스터 로드 완료: {len(self.mes_master_list)}행 (CAS 매핑: {len(self.mes_cas_map)}건)")
        except Exception as e:
            print(f"[!] MES 마스터 로드 실패: {e}")

    def clean_measure_duplicates(self, measure_raw):
        if not measure_raw: return ""
        target_text = str(measure_raw).strip()
        if not target_text: return ""
        
        master_names = set()
        for entry in self.mes_master_list:
            name = entry.get("측정대상 물질명")
            if name and str(name).lower() != 'nan':
                master_names.add(str(name).strip())
                
        clean_tokens = []
        seen = set()
        
        sorted_masters = sorted(list(master_names), key=len, reverse=True)
        for m_name in sorted_masters:
            if m_name in target_text:
                norm_key = re.sub(r'\s+', '', m_name).lower()
                if norm_key not in seen:
                    seen.add(norm_key)
                    clean_tokens.append(m_name)
                    target_text = target_text.replace(m_name, " [MASK] ")
                    
        remaining_parts = [p.strip() for p in re.split(r'[;\n/]+', target_text) if p.strip()]
        for p in remaining_parts:
            p_clean = p.replace("[MASK]", "").strip()
            if not p_clean: continue
            norm_key = re.sub(r'\s+', '', p_clean).lower()
            if norm_key not in seen:
                seen.add(norm_key)
                clean_tokens.append(p_clean)
                
        return "; ".join(clean_tokens)

    def process_file(self, path, idx, total):
        fn = os.path.basename(path)
        print(f"[{idx}/{total}] 분석 시작: {fn}")
        
        f_hash = self.core.calculate_file_hash(path)
        if not f_hash:
            f_hash = f"fallback_{idx}_{fn}"
            
        use_cache = False
        cached_data = {}
        if f_hash in self.cache:
            cached_data = self.cache[f_hash]
            cached_version = cached_data.get("engine_version", "unknown")
            manual = cached_data.get("manual_data", {})
            
            if cached_version == VERSION:
                if not (not manual and (cached_data.get("product_name") == "제품명 확인 필요" or "오류" in cached_data.get("status", ""))):
                    if not (manual.get("product_name") == "" or manual.get("raw_content") == ""):
                        use_cache = True
        
        ext_res = {}
        if use_cache:
            print(f"  └─ [*] 캐시 발견 (재추출 건너뜀)")
            manual = cached_data.get("manual_data", {})
            final_product = manual.get("product_name", cached_data.get("product_name", "미확인"))
            final_content = manual.get("raw_content", cached_data.get("raw_content", ""))
            
            ext_res = {
                "product_name": final_product,
                "reliability": cached_data.get("reliability", "N/A"),
                "신호등": cached_data.get("신호등", "⚪"),
                "구성성분": final_content,
                "used_engine": cached_data.get("used_engine", "regex"),
                "integrity_score": cached_data.get("integrity_score", 100),
                "integrity_reason": cached_data.get("integrity_reason", ""),
                "doc_type": cached_data.get("doc_type", "디지털"),
                "product_engine": cached_data.get("product_engine", "제미나이"),
                "comp_engine": cached_data.get("comp_engine", "정규식")
            }
        else:
            print(f"  └─ [*] 엔진 가동하여 추출 진행...")
            try:
                ext_res = self.core.extract_from_pdf(path, log_func=print)
            except Exception as e:
                print(f"  └─ [!] 1단계 추출 실패 예외 발생: {e}")
                ext_res = {
                    "제품명": "제품명 확인 필요",
                    "신뢰도": "N/A",
                    "신호등": "🔴",
                    "구성성분": "오류 발생으로 추출 실패",
                    "used_engine": "failed",
                    "integrity_score": 0,
                    "integrity_reason": f"크래시 발생: {str(e)}"
                }
            
            ext_res = {
                "product_name": ext_res.get("제품명", "미확인"),
                "reliability": ext_res.get("신뢰도", "N/A"),
                "신호등": ext_res.get("신호등", "⚪"),
                "구성성분": ext_res.get("구성성분", ext_res.get("구성성분 및 함유량", "")),
                "used_engine": ext_res.get("used_engine", "regex"),
                "integrity_score": ext_res.get("integrity_score", 100),
                "integrity_reason": ext_res.get("integrity_reason", ""),
                "doc_type": ext_res.get("doc_type", "디지털"),
                "product_engine": ext_res.get("product_engine", "제미나이"),
                "comp_engine": ext_res.get("comp_engine", "정규식")
            }
            
            self.cache[f_hash] = {
                "f_hash": f_hash,
                "product_name": ext_res["product_name"],
                "reliability": ext_res["reliability"],
                "신호등": ext_res["신호등"],
                "raw_content": ext_res["구성성분"],
                "measure_target": "",
                "full_path": path,
                "page": 1,
                "used_engine": ext_res["used_engine"],
                "engine_version": VERSION,
                "integrity_score": ext_res["integrity_score"],
                "integrity_reason": ext_res["integrity_reason"],
                "doc_type": ext_res["doc_type"],
                "product_engine": ext_res["product_engine"],
                "comp_engine": ext_res["comp_engine"]
            }
            self.save_cache()

        cas_content = ext_res.get("구성성분", "")
        prod = ext_res.get("product_name", "Unknown")
        
        cas_to_content = {}
        preserved_non_cas = []
        
        for item in str(cas_content).split(";"):
            item = item.strip()
            if not item: continue
            
            match = re.search(r'(\d{2,7}-\d{2}-\d)', item)
            if match:
                cas = match.group(1)
                content_match = re.search(r'\(([^)]+)\)', item)
                content_val = content_match.group(1) if content_match else ""
                
                if content_val and "%" not in content_val and re.search(r'\d', content_val):
                    content_val = f"{content_val}%"
                cas_to_content[cas] = content_val
            else:
                preserved_non_cas.append(item)
                
        pure_cas_list = list(cas_to_content.keys())
        pure_cas_str = "; ".join(pure_cas_list) if pure_cas_list else cas_content
        
        print(f"  └─ [*] KOSHA API 및 CSV 노출기준 조회 검증 가동...")
        raw_val_res = self.core.validate_with_kosha(pure_cas_str, log_func=None, full=False, f_hash=f_hash)
        
        res_1st_list = []
        res_2nd_list = []
        res_work_subjects = []
        res_work_non_subjects = []
        
        if raw_val_res.get("status") == "Cache-Hit":
            cached_comps = self.cache.get(f_hash, {}).get("components", [])
            if cached_comps:
                for c in cached_comps:
                    cas = c.get("cas", "")
                    if cas in cas_to_content:
                        c["content"] = cas_to_content[cas]
            
            for c in cached_comps:
                name = c.get("name", "Unknown")
                cas = c.get("cas", "")
                range_val = c.get("content", "")
                
                if re.search(r'[가-힣]', name):
                    name_no_eng = re.sub(r'\s*\([A-Za-z\s\d,]+\)$', '', name)
                    clean_name = name_no_eng.strip()
                else:
                    clean_name = name.strip()
                    
                mes_std_name = engine.MES_MASTER_MAP.get(cas, "")
                if mes_std_name:
                    clean_name = str(mes_std_name)
                    clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()
                else:
                    mes_entry = self.mes_cas_map.get(cas, {})
                    fallback_name = mes_entry.get("측정대상 물질명")
                    if fallback_name and str(fallback_name).lower() != 'nan':
                        clean_name = str(fallback_name)
                        clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()
                
                osh = c.get("osh", {})
                is_work = osh.get("is_measured", False)
                is_spec = osh.get("is_special", False)
                is_mgmt = osh.get("is_special_mgmt", False)
                is_permit = osh.get("is_permit", False)
                
                prefix = ""
                if is_mgmt: prefix = "[특별]"
                elif is_permit: prefix = "[허가]"
                elif is_spec and not is_work: prefix = "[특검]"
                
                if not range_val or str(range_val).strip() == "":
                    range_val = "미기재%"
                c_str = f"({range_val})"
                
                res_1st_list.append(f"{prefix}{clean_name}[{cas}{c_str}]")
                if is_work or is_spec:
                    res_2nd_list.append(f"{prefix}{clean_name}{c_str}")
                    
                if is_work:
                    percentage = 0.0
                    nums = re.findall(r'[\d\.]+', range_val)
                    if nums:
                        try: percentage = max(float(n) for n in nums)
                        except: percentage = 0.0
                        if "<" in range_val and percentage <= 1.0: percentage = 0.5
                    else: percentage = 100.0
                    
                    if percentage >= 1.0:
                        res_work_subjects.append(f"{clean_name}({range_val})")
                    else:
                        res_work_non_subjects.append(f"{clean_name}({range_val})")
        else:
            comps = raw_val_res.get("components", [])
            for c in comps:
                name = c.get("name", "Unknown")
                cas = c.get("cas", "")
                range_val = cas_to_content.get(cas, c.get("content", ""))
                c["content"] = range_val
                
                if re.search(r'[가-힣]', name):
                    name_no_eng = re.sub(r'\s*\([A-Za-z\s\d,]+\)$', '', name)
                    clean_name = name_no_eng.strip()
                else:
                    clean_name = name.strip()
                    
                mes_std_name = engine.MES_MASTER_MAP.get(cas, "")
                if mes_std_name:
                    clean_name = str(mes_std_name)
                    clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()
                else:
                    mes_entry = self.mes_cas_map.get(cas, {})
                    fallback_name = mes_entry.get("측정대상 물질명")
                    if fallback_name and str(fallback_name).lower() != 'nan':
                        clean_name = str(fallback_name)
                        clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()
                        
                osh = c.get("osh", {})
                is_work = osh.get("is_measured", False)
                is_spec = osh.get("is_special", False)
                is_mgmt = osh.get("is_special_mgmt", False)
                is_permit = osh.get("is_permit", False)
                
                prefix = ""
                if is_mgmt: prefix = "[특별]"
                elif is_permit: prefix = "[허가]"
                elif is_spec and not is_work: prefix = "[특검]"
                
                if not range_val or str(range_val).strip() == "":
                    range_val = "미기재%"
                c_str = f"({range_val})"
                
                res_1st_list.append(f"{prefix}{clean_name}[{cas}{c_str}]")
                if is_work or is_spec:
                    res_2nd_list.append(f"{prefix}{clean_name}{c_str}")
                    
                if is_work:
                    percentage = 0.0
                    nums = re.findall(r'[\d\.]+', range_val)
                    if nums:
                        try: percentage = max(float(n) for n in nums)
                        except: percentage = 0.0
                        if "<" in range_val and percentage <= 1.0: percentage = 0.5
                    else: percentage = 100.0
                    
                    if percentage >= 1.0:
                        res_work_subjects.append(f"{clean_name}({range_val})")
                    else:
                        res_work_non_subjects.append(f"{clean_name}({range_val})")
            
            if f_hash in self.cache:
                self.cache[f_hash]["components"] = comps
                self.save_cache()

        subj_str = "; ".join(res_work_subjects)
        non_subj_str = f"측정 비대상[{'; '.join(res_work_non_subjects)}]" if res_work_non_subjects else ""
        final_work_str = "; ".join(filter(None, [subj_str, non_subj_str]))

        # 용접 보정 로직
        is_welding = ("용접" in prod) or ("welding" in prod.lower())
        has_iron = "7439-89-6" in cas_to_content
        
        if is_welding and has_iron:
            iron_content = cas_to_content.get("7439-89-6", "")
            iron_str = f"철({iron_content})"
            if iron_str not in res_2nd_list:
                res_2nd_list.append(iron_str)
            
            welding_hazard = "용접흄; 산화철(분진, 흄)"
            if final_work_str:
                final_work_str = f"{welding_hazard}; {final_work_str}"
            else:
                final_work_str = welding_hazard
                
        if not res_1st_list: res_1st_list = [""]
        if not res_2nd_list: res_2nd_list = [""]

        cas_sum = cas_content
        reg1_sum = "; ".join(res_1st_list)
        reg2_sum = "; ".join(res_2nd_list)
        measure_sum = self.clean_measure_duplicates(final_work_str)

        traffic_light = ext_res.get("신호등", "⚪")
        if "🟢" in traffic_light or str(traffic_light).lower() == "green":
            traffic_str = "🟢 초록"
        elif "🟡" in traffic_light or str(traffic_light).lower() == "yellow":
            traffic_str = "🟡 노랑"
        elif "🔴" in traffic_light or str(traffic_light).lower() == "red":
            traffic_str = "🔴 빨강"
        else:
            traffic_str = traffic_light

        score_val = ext_res.get("integrity_score", 100)
        score_str = f"{score_val}점 (청정)" if score_val == 100 else f"{score_val}점 (불량)"

        result_row = {
            "filename": fn,
            "product_name": prod,
            "no": f"{idx:03d}",
            "cas_sum": cas_sum,
            "measure": measure_sum,
            "reg1": reg1_sum,
            "reg2": reg2_sum,
            "traffic_light": traffic_str,
            "matching_engine": ext_res.get("used_engine", "regex"),
            "integrity_score": score_str,
            "score_num": score_val,
            "raw_light": traffic_light
        }
        return result_row

def main():
    print("[실행] run_dataset_generator.py CLI 버전 가동")
    
    # 1. 경로 수집
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdf_folder = os.path.join(base_dir, "TEST_File")
    
    pdf_paths = []
    for ext in ["*.pdf", "*.PDF"]:
        pdf_paths.extend(glob.glob(os.path.join(pdf_folder, ext)))
    
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]
    
    pdf_paths = sorted(list(set(pdf_paths)), key=lambda x: natural_sort_key(os.path.basename(x)))
    
    if not pdf_paths:
        print(f"[ERROR] PDF 파일을 찾지 못했습니다. 경로: {pdf_folder}")
        sys.exit(1)
        
    print(f"[*] 총 {len(pdf_paths)}개의 MSDS PDF 자재 탐색 완료.")
    
    # 2. 엑셀 템플릿 복사
    excel_source = os.path.join(base_dir, "msds_index_V24.xlsx")
    excel_target = os.path.join(pdf_folder, "result_47.xlsx")
    
    if not os.path.exists(excel_source):
        print(f"[ERROR] 원본 엑셀 템플릿 없음: {excel_source}")
        sys.exit(1)
        
    if os.path.exists(excel_target):
        try: os.remove(excel_target)
        except Exception as e:
            print(f"[!] 기존 파일 삭제 오류: {e}")
            
    shutil.copy(excel_source, excel_target)
    print(f"[*] 엑셀 복사본 생성 완료: {excel_target}")
    
    # 3. 데이터셋 제너레이터 실행
    gen = DatasetGenerator()
    results = []
    
    start_time = time.time()
    for idx, path in enumerate(pdf_paths, 1):
        try:
            res_row = gen.process_file(path, idx, len(pdf_paths))
            results.append(res_row)
        except Exception as file_err:
            print(f"[!] 파일 {os.path.basename(path)} 분석 중 크래시 발생:")
            traceback.print_exc()
            results.append({
                "filename": os.path.basename(path),
                "product_name": "제품명 확인 필요",
                "no": f"{idx:03d}",
                "cas_sum": "추출 오류",
                "measure": "",
                "reg1": "",
                "reg2": "",
                "traffic_light": "🔴 빨강",
                "matching_engine": "failed",
                "integrity_score": "0점 (불량)",
                "score_num": 0,
                "raw_light": "🔴"
            })
            
    # 4. 엑셀에 데이터 기입 (win32com.client 활용)
    print("\n[*] 엑셀 장부 기입 작업 시작 (win32com 활용)...")
    
    config_path = os.path.join(base_dir, "config.json")
    mapping = {}
    st_row = 3
    sheet_name = "Sheet1"
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                raw_mapping = cfg.get("mapping", {})
                mapping = {k: c2i(v) for k, v in raw_mapping.items()}
                sheet_name = cfg.get("clean_sheet_name", "Sheet1")
                st_row = int(cfg.get("start_row", "3"))
        except Exception as e:
            print(f"[!] config.json 파싱 오류: {e}, 기본값 사용")
            mapping = {
                "순번/No": 1, "제품명": 4, "파일명": 16, "CAS 원본": 15,
                "측정대상1": 9, "2차 결과(규제)": 10, "1차 결과(전체)": 11
            }
            
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    
    excel = None
    saved_count = 0
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        
        wb = excel.Workbooks.Open(os.path.abspath(excel_target))
        ws = wb.Sheets(sheet_name)
        
        for idx, res in enumerate(results):
            curr_row = st_row + idx
            
            for key, c_idx in mapping.items():
                if not c_idx or c_idx < 1: continue
                
                val = None
                if key == "제품명": val = res.get("product_name")
                elif key == "파일명": val = res.get("filename")
                elif key == "CAS 원본": val = res.get("cas_sum")
                elif key == "측정대상1" or key == "측정대상2": val = res.get("measure")
                elif key == "2차 결과(규제)": val = res.get("reg2")
                elif key == "1차 결과(전체)": val = res.get("reg1")
                elif key == "순번/No": val = res.get("no")
                elif key == "신호등": val = res.get("traffic_light")
                elif key == "매칭 엔진": val = res.get("matching_engine")
                elif key == "무결성 점수": val = res.get("integrity_score")
                
                if val is not None:
                    if key in ["CAS 원본", "1차 결과(전체)", "2차 결과(규제)"]:
                        val = str(val).replace('\n', ' ').replace('\r', '').strip()
                        val = re.sub(r'\s{2,}', ' ', val)
                        
                    try: ws.Cells(curr_row, c_idx).NumberFormat = "@"
                    except: pass
                    ws.Cells(curr_row, c_idx).Value = str(val)
            saved_count += 1
            
        wb.Save()
        wb.Close()
        excel.Quit()
        print(f"[*] 엑셀 저장 완료: {saved_count}건의 데이터가 result_47.xlsx에 성공적으로 기입되었습니다.")
    except Exception as exc_err:
        print(f"[!] win32com 엑셀 저장 중 오류 발생: {exc_err}")
        if excel:
            try: excel.Quit()
            except: pass
        
        print("[*] 백업 엔진(openpyxl)을 통한 저장 재시도...")
        try:
            import openpyxl
            wb = openpyxl.load_workbook(excel_target)
            ws = wb[sheet_name]
            
            for idx, res in enumerate(results):
                curr_row = st_row + idx
                for key, c_idx in mapping.items():
                    if not c_idx or c_idx < 1: continue
                    val = None
                    if key == "제품명": val = res.get("product_name")
                    elif key == "파일명": val = res.get("filename")
                    elif key == "CAS 원본": val = res.get("cas_sum")
                    elif key == "측정대상1" or key == "측정대상2": val = res.get("measure")
                    elif key == "2차 결과(규제)": val = res.get("reg2")
                    elif key == "1차 결과(전체)": val = res.get("reg1")
                    elif key == "순번/No": val = res.get("no")
                    elif key == "신호등": val = res.get("traffic_light")
                    elif key == "매칭 엔진": val = res.get("matching_engine")
                    elif key == "무결성 점수": val = res.get("integrity_score")
                    
                    if val is not None:
                        if key in ["CAS 원본", "1차 결과(전체)", "2차 결과(규제)"]:
                            val = str(val).replace('\n', ' ').replace('\r', '').strip()
                            val = re.sub(r'\s{2,}', ' ', val)
                        cell = ws.cell(row=curr_row, column=c_idx)
                        cell.number_format = '@'
                        cell.value = str(val)
            wb.save(excel_target)
            wb.close()
            print("[*] openpyxl 백업 저장 완료.")
        except Exception as xl_err:
            print(f"[ERROR] 백업 엑셀 저장도 실패: {xl_err}")
    finally:
        pythoncom.CoUninitialize()

    # 5. 요약 성적표 JSON 저장
    end_time = time.time()
    elapsed = end_time - start_time
    
    success_count = sum(1 for r in results if r.get("product_name") != "제품명 확인 필요")
    
    report = {
        "elapsed_time_sec": elapsed,
        "total_files": len(pdf_paths),
        "success_count": success_count,
        "failed_files": [r.get("no") for r in results if r.get("product_name") == "제품명 확인 필요"],
        "materials": []
    }
    
    for r in results:
        report["materials"].append({
            "no": r.get("no"),
            "filename": r.get("filename"),
            "engine": r.get("matching_engine"),
            "light": r.get("raw_light"),
            "integrity_score": int(r.get("integrity_score").split("점")[0]),
            "excel_in": "성공" if r.get("product_name") != "제품명 확인 필요" else "실패",
            "gui_prod": r.get("product_name"),
            "gui_cas": r.get("cas_sum"),
            "gui_measure": r.get("measure"),
            "match_status": "OK" if r.get("product_name") != "제품명 확인 필요" else "MISMATCH"
        })
        
    report_target = os.path.join(base_dir, "scratch", "scratch_race_report_47.json")
    try:
        with open(report_target, "w", encoding="utf-8") as rf:
            json.dump(report, rf, ensure_ascii=False, indent=4)
        print(f"[*] 요약 리포트 저장 완료: {report_target}")
    except Exception as j_err:
        print(f"[!] JSON 리포트 저장 오류: {j_err}")

    # 6. 대조 테이블 콘솔 출력 (East Asian Width 정렬 적용)
    import unicodedata
    
    def get_visible_width(s):
        if s is None: return 0
        s = str(s)
        width = 0
        for char in s:
            if unicodedata.east_asian_width(char) in ('F', 'W', 'A'): width += 2
            else: width += 1
        return width

    def pad_string(s, target_width, align='left'):
        if s is None: s = ""
        s = str(s)
        current_width = get_visible_width(s)
        if current_width >= target_width: return s
        
        pad_len = target_width - current_width
        if align == 'left': return s + ' ' * pad_len
        elif align == 'right': return ' ' * pad_len + s
        else:
            left_pad = pad_len // 2
            right_pad = pad_len - left_pad
            return ' ' * left_pad + s + ' ' * right_pad

    materials = report.get("materials", [])
    if materials:
        print("\n" + "=" * 125)
        print(" " * 32 + "★ [표 1] 기계실 검문 및 제품명 대조 요약 표 (기본 정보 + 제품명 대조) ★")
        print("=" * 125)
        
        headers1 = ["순번", "신호등", "엔진 구분", "정합성", "입고", "GUI 제품명", "매칭"]
        widths1 = [6, 8, 18, 8, 8, 56, 8]
        
        header_line = "| " + " | ".join(pad_string(h, w, 'center') for h, w in zip(headers1, widths1)) + " |"
        print(header_line)
        
        separator_line = "|-" + "-|-".join('-' * w for w in widths1) + "-|"
        print(separator_line)
        
        for m in materials:
            row_data = [
                m.get("no", ""),
                m.get("light", ""),
                m.get("engine", ""),
                f"{m.get('integrity_score', 0)}점",
                m.get("excel_in", ""),
                m.get("gui_prod", ""),
                m.get("match_status", "")
            ]
            row_line = "| " + " | ".join(pad_string(d, w, 'left' if idx == 5 else 'center') for idx, (d, w) in enumerate(zip(row_data, widths1))) + " |"
            print(row_line)
        print("=" * 125)
        
        print("\n" + "=" * 125)
        print(" " * 28 + "★ [표 2] GUI 및 엑셀 데이터 1:1 상세 대조 표 (CAS 및 측정대상 물질 정보 상세 대조) ★")
        print("=" * 125)
        
        headers2 = ["순번", "GUI CAS 정보", "GUI 측정물질", "매칭"]
        widths2 = [6, 52, 52, 8]
        
        header_line2 = "| " + " | ".join(pad_string(h, w, 'center') for h, w in zip(headers2, widths2)) + " |"
        print(header_line2)
        
        separator_line2 = "|-" + "-|-".join('-' * w for w in widths2) + "-|"
        print(separator_line2)
        
        for m in materials:
            row_data2 = [
                m.get("no", ""),
                m.get("gui_cas", ""),
                m.get("gui_measure", ""),
                m.get("match_status", "")
            ]
            row_line2 = "| " + " | ".join(pad_string(d, w, 'left' if idx in (1, 2) else 'center') for idx, (d, w) in enumerate(zip(row_data2, widths2))) + " |"
            print(row_line2)
        print("=" * 125)

if __name__ == "__main__":
    main()
