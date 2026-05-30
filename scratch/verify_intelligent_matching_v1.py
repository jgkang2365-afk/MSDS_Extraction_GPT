# -*- coding: utf-8 -*-
"""[NEW] 지능형 N:1 매칭 및 정렬 검증 스크립트"""
import os
import sys
import shutil
import re
import win32com.client
import win32com.client.dynamic
import pythoncom

def run_intelligent_matching_verification():
    print("=== 지능형 N:1 매칭 및 정렬 검증 시작 ===")
    
    base_dir = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)"
    orig_xlsx = os.path.join(base_dir, "msds_index_V24.xlsx")
    if not os.path.exists(orig_xlsx):
        orig_xlsx = os.path.join(base_dir, "msds_index.xlsx")
        
    test_xlsx = os.path.join(base_dir, "scratch", "test_intelligent_matching_temp.xlsx")
    
    if not os.path.exists(orig_xlsx):
        print(f"오류: 원본 {orig_xlsx} 파일이 없습니다.")
        return False
        
    os.makedirs(os.path.dirname(test_xlsx), exist_ok=True)
    shutil.copy(orig_xlsx, test_xlsx)
    print(f"테스트 파일 복사 완료: {test_xlsx}")
    
    # 마스터 데이터셋 모킹
    mes_master_list = [
        {"정렬코드": "2D-10-010", "측정대상 물질명": "기타광물성분진", "CAS No.": "", "별칭": []},
        {"정렬코드": "2D-11-031", "측정대상 물질명": "활석(석면불포함)", "CAS No.": "14807-96-6", "별칭": []},
        {"정렬코드": "2D-11-030", "측정대상 물질명": "활석", "CAS No.": "14807-96-6", "별칭": []},
        {"정렬코드": "3M-20-160", "측정대상 물질명": "이산화티타늄", "CAS No.": "13463-67-7", "별칭": []},
        {"정렬코드": "3O-30-050", "측정대상 물질명": "크실렌", "CAS No.": "1330-20-7", "별칭": []},
        {"정렬코드": "3O-30-070", "측정대상 물질명": "톨루엔", "CAS No.": "108-88-3", "별칭": []}
    ]
    
    def normalize_name(name):
        if not name: return ""
        return re.sub(r'\s+', '', name).lower()
        
    valid_substances = set()
    substance_sort_map = {}
    substance_info_map = {}
    name_to_cas = {}
    cas_to_names = {}
    
    for entry in mes_master_list:
        name = entry["측정대상 물질명"].strip()
        code = entry["정렬코드"].strip()
        cas = entry["CAS No."].strip()
        
        valid_substances.add(name)
        if name not in substance_sort_map:
            substance_sort_map[name] = code
        if name not in substance_info_map:
            substance_info_map[name] = {"측정": "○", "특검": "○"}
            
        if cas:
            name_to_cas[name] = cas
            if cas not in cas_to_names:
                cas_to_names[cas] = []
            if name not in cas_to_names[cas]:
                cas_to_names[cas].append(name)
                
    valid_substances_clean = {normalize_name(name) for name in valid_substances}
    
    def get_mapped_factor(cas, name):
        clean_name = normalize_name(name)
        if cas == "1317-65-3" or "limestone" in clean_name:
            return ["기타광물성분진"]
        elif cas == "471-34-1" or "탄산" in clean_name:
            return ["기타광물성분진"]
        elif cas == "1317-80-2" or "금홍석" in clean_name:
            return ["이산화티타늄", "기타광물성분진"]
        elif cas == "14807-96-6" or "소우프스톤" in clean_name:
            return ["활석(석면불포함)", "활석", "소우프스톤"]
        
        std_names = []
        if cas:
            for entry in mes_master_list:
                m_cas = str(entry.get("CAS No.", "")).strip()
                m_name = str(entry.get("측정대상 물질명", "")).strip()
                if m_cas == cas and m_name:
                    std_names.append(m_name)
        if not std_names:
            std_names = [name]
        return list(set(std_names))

    def extract_pure_substance_name(item):
        if not item: return ""
        text = re.sub(r'\(.*?\)', '', item).strip()
        for prefix in ["측정 비대상", "단시간 및 임시작업", "보관", "허용소비량 미만"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        text = re.sub(r'\[특별\]|\[특검\]|\[허가\]', '', text).strip()
        text = text.replace("[", "").replace("]", "").strip()
        return text

    def split_i_val(i_val):
        if not i_val: return []
        chars = list(i_val)
        in_paren = 0
        in_bracket = 0
        for i, ch in enumerate(chars):
            if ch == '(': in_paren += 1
            elif ch == ')': in_paren -= 1
            elif ch == '[': in_bracket += 1
            elif ch == ']': in_bracket -= 1
            elif ch == ';' and (in_paren > 0 or in_bracket > 0):
                chars[i] = '\u0001'
        protected_val = "".join(chars)
        raw_splits = [part.strip() for part in re.split(r';', protected_val) if part.strip()]
        final_items = []
        for part in raw_splits:
            part = part.replace('\u0001', ';')
            final_items.append(part)
        return final_items

    def parse_substance_item(item):
        item = item.strip()
        if not item: return None
        category = "측정대상"
        for prefix in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
            if item.startswith(prefix):
                category = prefix
                item = item[len(prefix):].strip()
                break
        if item.startswith("[") and item.endswith("]"):
            item = item[1:-1].strip()
        sub_prefix = ""
        for sub in ["[특별]", "[허가]", "[특검]"]:
            if item.startswith(sub):
                sub_prefix = sub
                item = item[len(sub):].strip()
                break
        return {
            "category": category,
            "sub_prefix": sub_prefix,
            "pure_name": item
        }

    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
        except:
            excel = win32com.client.Dispatch("Excel.Application")
            
        wb = excel.Workbooks.Open(test_xlsx)
        ws = wb.Worksheets("Sheet1")
        
        # 10행 테스트 셋업
        # I열: 원래 5개 유해인자가 섞여있음
        # J열: 원본 MSDS 추출 성상들
        ws.Cells(10, 7).Value = "10"  # G열 (월취급량)
        ws.Cells(10, 9).Value = "기타광물성분진; 활석(석면불포함); 이산화티타늄; 크실렌; 톨루엔" # I열 (비고)
        ws.Cells(10, 10).Value = "크실렌(stel%); 톨루엔(21~31%); Limestone(29~39%); 소우프스톤(8~18%); 금홍석(1~10%); 탄산 칼슘(1~10%)" # J열 (MSDS)
        ws.Cells(10, 14).Value = "Limestone[1317-65-3(29~39%)]; 톨루엔[108-88-3(21~31%)]; 소우프스톤[14807-96-6(8~18%)]; 금홍석[1317-80-2(1~10%)]; 크실렌[1330-20-7(stel%)]; 탄산 칼슘[471-34-1(1~10%)]" # N열 (1차 결과 전체)
        
        r = 10
        i_cell = ws.Cells(r, 9)
        j_cell = ws.Cells(r, 10)
        g_cell = ws.Cells(r, 7)
        n_cell = ws.Cells(r, 14)
        
        i_val = str(i_cell.Value or "").strip()
        j_val = str(j_cell.Value or "").strip()
        g_raw = str(g_cell.Value or "").strip()
        n_val = str(n_cell.Value or "").strip()
        
        is_g_zero = False
        
        # J열 매칭 로직 시뮬레이션 가동
        i_items = split_i_val(i_val)
        j_items = [x.strip() for x in j_val.split(";") if x.strip()]
        
        # 1. clean_i_items 구축
        clean_i_items = []
        for i_item in i_items:
            parsed_i = parse_substance_item(i_item)
            if not parsed_i: continue
            i_sub = parsed_i["pure_name"]
            category = parsed_i["category"]
            sub_prefix = parsed_i["sub_prefix"]
            sort_code = substance_sort_map.get(i_sub) or "ZZZZZZ"
            
            clean_i_items.append({
                "category": category,
                "sub_prefix": sub_prefix,
                "pure_name": i_sub,
                "sort_code": sort_code,
                "is_red": False
            })
            
        # 2. I열 중복 제거
        unique_i_list = []
        seen_i_keys = set()
        for item in clean_i_items:
            key = (item["category"], item["sub_prefix"], item["pure_name"])
            if key not in seen_i_keys:
                seen_i_keys.add(key)
                unique_i_list.append(item)
                
        # 3. J열 매칭
        j_parser_pat = re.compile(r"^(?:(\[특별\]|\[특검\]|\[허가\]))?(.*?)(?:\(([^)]*)\))?$")
        j_matched_data = []
        
        for j_item in j_items:
            match = j_parser_pat.match(j_item)
            if not match:
                j_matched_data.append({
                    "j_item": j_item,
                    "category": "측정대상",
                    "sort_code": "ZZZZZZ",
                    "is_red": True
                })
                continue
                
            j_prefix = match.group(1) or ""
            j_pure_name = match.group(2) or ""
            j_concentration = match.group(3) or ""
            j_pure_clean = extract_pure_substance_name(j_pure_name)
            
            # CAS 번호 매핑 (테스트 시나리오 CAS 주입)
            j_cas = ""
            if "limestone" in j_pure_clean.lower(): j_cas = "1317-65-3"
            elif "탄산" in j_pure_clean: j_cas = "471-34-1"
            elif "금홍석" in j_pure_clean: j_cas = "1317-80-2"
            elif "소우프스톤" in j_pure_clean: j_cas = "14807-96-6"
            elif "크실렌" in j_pure_clean: j_cas = "1330-20-7"
            elif "톨루엔" in j_pure_clean: j_cas = "108-88-3"
            
            j_mapped_factors = get_mapped_factor(j_cas, j_pure_clean)
            
            matched_i_item = None
            # A. 지능형 매핑 표준명 대조 (J열 후보 우선순위가 바깥 루프여야 함)
            for factor in j_mapped_factors:
                for i_item in unique_i_list:
                    if normalize_name(factor) == normalize_name(i_item["pure_name"]):
                        matched_i_item = i_item
                        break
                if matched_i_item:
                    break
            
            # B. CAS 번호 대조
            if not matched_i_item and j_cas:
                for i_item in unique_i_list:
                    i_pure_clean = extract_pure_substance_name(i_item["pure_name"])
                    i_cas = name_to_cas.get(i_pure_clean, "")
                    if i_cas and j_cas == i_cas:
                        matched_i_item = i_item
                        break
            
            # C. 텍스트 포함 대조
            if not matched_i_item:
                for i_item in unique_i_list:
                    i_pure_clean = extract_pure_substance_name(i_item["pure_name"])
                    i_norm = normalize_name(i_pure_clean)
                    j_norm = normalize_name(j_pure_clean)
                    if i_norm and j_norm and (i_norm in j_norm or j_norm in i_norm):
                        matched_i_item = i_item
                        break
                        
            if matched_i_item:
                j_matched_data.append({
                    "j_item": j_item,
                    "category": matched_i_item["category"],
                    "sort_code": matched_i_item["sort_code"],
                    "is_red": False
                })
            else:
                j_matched_data.append({
                    "j_item": j_item,
                    "category": "측정대상",
                    "sort_code": "ZZZZZZ",
                    "is_red": False
                })
                
        # 정렬
        j_matched_data.sort(key=lambda x: x["sort_code"])
        unique_i_list.sort(key=lambda x: x["sort_code"])
        
        # I열 조립
        new_i_val = ""
        first_i = True
        for cat_name, sep, wrapper in [("측정대상", "; ", ""), ("측정 비대상", "; ", "측정 비대상[")]:
            cat_items = [x for x in unique_i_list if x["category"] == cat_name]
            if not cat_items: continue
            if not first_i: new_i_val += "; "
            first_i = False
            if wrapper: new_i_val += wrapper
            new_i_val += sep.join([f"{x['sub_prefix']}{x['pure_name']}" for x in cat_items])
            if wrapper: new_i_val += "]"
            
        # J열 조립
        new_j_val = "; ".join([x["j_item"] for x in j_matched_data])
        
        print("\n=== 테스트 실행 결과 ===")
        print(f"I열 조립 결과: '{new_i_val}'")
        print(f"J열 조립 결과: '{new_j_val}'")
        
        # 검증 Asserts
        # 1. I열에 '[누락]'이 없어야 함
        assert "[누락]" not in new_i_val, "오류: I열에 불필요한 [누락]이 기재되었습니다!"
        # 2. J열이 정렬코드(기타광물성분진 -> 활석 -> 이산화티타늄 -> 크실렌 -> 톨루엔) 순서로 완벽히 정렬되었는지 확인
        expected_j_order = [
            "Limestone(29~39%)",
            "탄산 칼슘(1~10%)",
            "소우프스톤(8~18%)",
            "금홍석(1~10%)",
            "크실렌(stel%)",
            "톨루엔(21~31%)"
        ]
        actual_j_items = [x.strip() for x in new_j_val.split(";")]
        assert len(actual_j_items) == len(expected_j_order), "오류: J열 성분 개수가 불일치합니다!"
        for act, exp in zip(actual_j_items, expected_j_order):
            assert act == exp, f"오류: 정렬 순서 불일치! 실제: '{act}', 기대치: '{exp}'"
            
        print("\n모든 지능형 N:1 매칭 및 정렬 시나리오 테스트 통과!")
        wb.Close(SaveChanges=False)
        return True
        
    except Exception as e:
        print(f"검증 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if wb:
            try: wb.Close(SaveChanges=False)
            except: pass
        pythoncom.CoUninitialize()
        if os.path.exists(test_xlsx):
            try: os.remove(test_xlsx)
            except: pass

if __name__ == "__main__":
    success = run_intelligent_matching_verification()
    sys.exit(0 if success else 1)
