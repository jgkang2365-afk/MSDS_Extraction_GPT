# -*- coding: utf-8 -*-
"""[NEW] 1차 결과 CAS 기반 적색 마킹 완화 검증 스크립트"""
import os
import sys
import shutil
import re
import win32com.client
import win32com.client.dynamic
import pythoncom

def run_precision_marking_v6_verification():
    print("=== 1차 결과 CAS 기반 적색 마킹 완화 검증 시작 ===")
    
    base_dir = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)"
    orig_xlsx = os.path.join(base_dir, "msds_index.xlsx")
    test_xlsx = os.path.join(base_dir, "scratch", "test_precision_v6_temp.xlsx")
    
    if not os.path.exists(orig_xlsx):
        print(f"오류: 원본 {orig_xlsx} 파일이 없습니다.")
        return False
        
    os.makedirs(os.path.dirname(test_xlsx), exist_ok=True)
    shutil.copy(orig_xlsx, test_xlsx)
    print(f"테스트 파일 복사 완료: {test_xlsx}")
    
    # 1. 마스터 DB 정규화 모킹 (여기에는 '염화 바륨'이 의도적으로 누락되어 있음)
    valid_substances = {
        "톨루엔", "벤젠", "크실렌", "질산", "바륨 및 그 가용성 화합물"
    }
    def normalize_name(name):
        if not name: return ""
        return re.sub(r'\s+', '', name).lower()
        
    valid_substances_clean = {normalize_name(name) for name in valid_substances}
    
    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
        except Exception as ex_err:
            excel = win32com.client.Dispatch("Excel.Application")
            
        wb = excel.Workbooks.Open(test_xlsx)
        ws = wb.Worksheets("Sheet1")
        
        # 테스트 시나리오 구성
        # 14행: G열="10", I열="바륨 및 그 가용성 화합물", J열="염화 바륨(98.5%)", N열="염화 바륨[10361-37-2(98.5%)]"
        #      --> 염화 바륨은 마스터 DB에 없지만 N열에 유효 CAS가 있으므로 적색 마킹되지 않고 검은색 보존되어야 함.
        # 15행: G열="10", I열="바륨 및 그 가용성 화합물", J열="염화 바륨(98.5%)", N열="염화 바륨[-(98.5%)]"
        #      --> N열에 유효 CAS가 없으므로 여전히 적색 마킹(255)이 작동해야 함.
        
        ws.Cells(14, 7).Value = "10"
        ws.Cells(14, 9).Value = "바륨 및 그 가용성 화합물"
        ws.Cells(14, 10).Value = "염화 바륨(98.5%)"
        ws.Cells(14, 14).Value = "염화 바륨[10361-37-2(98.5%)]"
        
        ws.Cells(15, 7).Value = "10"
        ws.Cells(15, 9).Value = "바륨 및 그 가용성 화합물"
        ws.Cells(15, 10).Value = "염화 바륨(98.5%)"
        ws.Cells(15, 14).Value = "염화 바륨[-(98.5%)]"
        
        test_scenarios = [14, 15]
        
        group_definitions = [
            ("측정대상", "; ", ""),
            ("측정 비대상", "; ", "측정 비대상["),
            ("단시간 및 임시작업", "; ", "단시간 및 임시작업["),
            ("허용소비량 미만", "; ", "허용소비량 미만["),
            ("보관", "; ", "보관[")
        ]
        
        j_parser_pat = re.compile(r"^(?:(\[특별\]|\[특검\]|\[허가\]))?(.*?)(?:\(([^)]*)\))?$")
        
        # 헬퍼 함수 정의
        def parse_substance_item(item_str):
            item_str = item_str.strip()
            if not item_str: return None
            
            category = "측정대상"
            for prefix in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
                if item_str.startswith(prefix):
                    category = prefix
                    item_str = item_str[len(prefix):].strip()
                    break
            
            if item_str.startswith("[") and item_str.endswith("]"):
                item_str = item_str[1:-1].strip()
                
            sub_prefix = ""
            for sp in ["[특별]", "[특검]", "[허가]"]:
                if item_str.startswith(sp):
                    sub_prefix = sp
                    item_str = item_str[len(sp):].strip()
                    break
                    
            return {
                "pure_name": item_str,
                "category": category,
                "sub_prefix": sub_prefix
            }

        # 엑셀 셀 서식 백업 및 복원
        def backup_cell_format(cell):
            return {
                "HorizontalAlignment": cell.HorizontalAlignment,
                "VerticalAlignment": cell.VerticalAlignment,
                "WrapText": cell.WrapText,
                "ShrinkToFit": cell.ShrinkToFit,
                "FontName": cell.Font.Name,
                "FontSize": cell.Font.Size,
                "FontBold": cell.Font.Bold,
                "FontItalic": cell.Font.Italic,
                "FontUnderline": cell.Font.Underline,
                "FontColor": cell.Font.Color
            }

        def restore_cell_format(cell, fmt):
            if not fmt: return
            cell.HorizontalAlignment = fmt["HorizontalAlignment"]
            cell.VerticalAlignment = fmt["VerticalAlignment"]
            cell.WrapText = fmt["WrapText"]
            cell.ShrinkToFit = fmt["ShrinkToFit"]
            cell.Font.Name = fmt["FontName"]
            cell.Font.Size = fmt["FontSize"]
            cell.Font.Bold = fmt["FontBold"]
            cell.Font.Italic = fmt["FontItalic"]
            cell.Font.Underline = fmt["FontUnderline"]
            if fmt["FontColor"] not in [0, 255, 16711680, -4105]:
                cell.Font.Color = fmt["FontColor"]
            else:
                cell.Font.Color = 0

        # G열 값 판별용 헬퍼 함수
        def is_zero_value(val_str):
            try:
                clean_val = val_str.replace(" ", "").replace(",", "")
                if not clean_val:
                    return False
                return float(clean_val) == 0.0
            except:
                return False

        # MSDS 성분 파싱용 헬퍼
        def extract_pure_substance_name(item):
            if not item:
                return ""
            text = re.sub(r'\(.*?\)', '', item).strip()
            for prefix in ["측정 비대상", "단시간 및 임시작업", "보관", "허용소비량 미만"]:
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
            text = re.sub(r'\[특별\]|\[특검\]|\[허가\]', '', text).strip()
            text = text.replace("[", "").replace("]", "").strip()
            return text

        def get_core_chemical_name(name):
            if not name:
                return ""
            core = name
            suffixes = [
                "및 그 가용성 화합물", "및 그 화합물", "및 화합물",
                " 및 그 가용성 화합물", " 및 그 화합물", " 및 화합물",
                "(석면불포함)", "석면불포함", " 계열", "계열",
                " 유기화합물", " 무기화합물"
            ]
            for suf in sorted(suffixes, key=len, reverse=True):
                if suf in core:
                    core = core.replace(suf, "")
            return core.strip()

        for r in test_scenarios:
            i_cell = ws.Cells(r, 9)
            j_cell = ws.Cells(r, 10)
            g_cell = ws.Cells(r, 7)
            n_cell = ws.Cells(r, 14)
            
            i_val = str(i_cell.Value or "").strip()
            j_val = str(j_cell.Value or "").strip()
            g_raw = str(g_cell.Value or "").strip()
            n_val = str(n_cell.Value or "").strip()
            
            is_g_zero = is_zero_value(g_raw)
            
            if not i_val and not j_val:
                continue
                
            # 1차 결과(N열) 파싱
            api_valid_substances = set()
            for m in re.finditer(r'([^[;]+)\[([^(\]]+)(?:\(([^)]*)\))?\]', n_val):
                sub_name = m.group(1).strip()
                cas_no = m.group(2).strip()
                if cas_no and re.match(r'^\d+-\d+-\d+$', cas_no):
                    api_valid_substances.add(normalize_name(sub_name))
            
            i_items = [x.strip() for x in i_val.split(";") if x.strip()]
            j_items = [x.strip() for x in j_val.split(";") if x.strip()]
            
            used_j_indices = set()
            paired_data = []
            
            for i_item in i_items:
                parsed_i = parse_substance_item(i_item)
                i_pure = parsed_i["pure_name"] if parsed_i else extract_pure_substance_name(i_item)
                matched_j_item = None
                matched_idx = -1
                
                # 1차 완전 일치
                for idx, j_item in enumerate(j_items):
                    if idx in used_j_indices: continue
                    j_pure = extract_pure_substance_name(j_item)
                    if i_pure == j_pure:
                        matched_j_item = j_item
                        matched_idx = idx
                        break
                        
                # 2차 부분 포함 일치
                if matched_j_item is None:
                    for idx, j_item in enumerate(j_items):
                        if idx in used_j_indices: continue
                        j_pure = extract_pure_substance_name(j_item)
                        if i_pure and j_pure and (i_pure in j_pure or j_pure in i_pure):
                            matched_j_item = j_item
                            matched_idx = idx
                            break
                            
                # 3차 핵심 단어 포함 검사
                if matched_j_item is None:
                    i_core = get_core_chemical_name(i_pure)
                    if i_core:
                        for idx, j_item in enumerate(j_items):
                            if idx in used_j_indices: continue
                            j_pure = extract_pure_substance_name(j_item)
                            j_core = get_core_chemical_name(j_pure)
                            if (i_core in j_pure) or (j_core in i_pure):
                                matched_j_item = j_item
                                matched_idx = idx
                                break
                
                if matched_j_item is not None:
                    used_j_indices.add(matched_idx)
                else:
                    matched_j_item = ""
                paired_data.append((i_item, matched_j_item))
                
            for idx, j_item in enumerate(j_items):
                if idx not in used_j_indices:
                    paired_data.append(("", j_item))
                    
            row_data = []
            for i_item, j_item in paired_data:
                if not i_item:
                    row_data.append({
                        "i_item_final": "[누락]",
                        "j_item": j_item,
                        "category": "측정대상",
                        "sort_code": "ZZZZZZ",
                        "is_red": True
                    })
                    continue
                    
                parsed_i = parse_substance_item(i_item)
                if not parsed_i: continue
                i_sub = parsed_i["pure_name"]
                category = parsed_i["category"]
                sub_prefix = parsed_i["sub_prefix"]
                
                i_item_final = f"{sub_prefix}{i_sub}"
                sort_code = "A"
                
                is_red = False
                i_sub_norm = normalize_name(i_sub)
                
                # 마스터 DB와 N열 CAS 목록 검증 병합 (완화 룰)
                if i_sub_norm not in valid_substances_clean and i_sub_norm not in api_valid_substances:
                    is_red = True
                    
                if not j_item or "%" not in j_item:
                    is_red = True
                    
                if category == "보관" and not is_g_zero:
                    is_red = True
                    
                row_data.append({
                    "i_item_final": i_item_final,
                    "j_item": j_item,
                    "category": category,
                    "sort_code": sort_code,
                    "is_red": is_red
                })
                
            # 조립
            new_i_val = ""
            new_j_val = ""
            red_marks_i = []
            red_marks_j = []
            blue_marks_i = []
            blue_marks_j = []
            
            i_fmt = backup_cell_format(i_cell)
            j_fmt = backup_cell_format(j_cell)
            
            first_i = True
            first_j = True
            for cat_name, sep, wrapper in group_definitions:
                cat_items = [x for x in row_data if x["category"] == cat_name]
                valid_cat_items_i = [x for x in cat_items if x["i_item_final"]]
                valid_cat_items_j = [x for x in cat_items if x["j_item"]]
                
                if not valid_cat_items_i and not valid_cat_items_j: continue
                    
                if valid_cat_items_i:
                    if not first_i: new_i_val += "; "
                    first_i = False
                    if wrapper: new_i_val += wrapper
                    
                    for idx, item in enumerate(valid_cat_items_i):
                        if idx > 0: new_i_val += sep
                        i_item_final = item["i_item_final"]
                        if i_item_final:
                            sub_prefix = ""
                            for sp in ["[특별]", "[특검]", "[허가]"]:
                                if i_item_final.startswith(sp):
                                    sub_prefix = sp
                                    break
                            pure_sub_name = i_item_final[len(sub_prefix):]
                            
                            if sub_prefix:
                                start_pos = len(new_i_val) + 1
                                blue_marks_i.append((start_pos, len(sub_prefix)))
                                new_i_val += sub_prefix
                                
                            if pure_sub_name:
                                pure_sub_norm = normalize_name(pure_sub_name)
                                is_i_red = False
                                if pure_sub_norm not in valid_substances_clean and pure_sub_norm not in api_valid_substances:
                                    is_i_red = True
                                if item.get("is_red", False):
                                    is_i_red = True
                                    
                                if is_i_red:
                                    start_pos = len(new_i_val) + 1
                                    red_marks_i.append((start_pos, len(pure_sub_name)))
                                new_i_val += pure_sub_name
                                
                    if wrapper: new_i_val += "]"
                    
                if valid_cat_items_j:
                    if not first_j: new_j_val += "; "
                    first_j = False
                    
                    for idx, item in enumerate(valid_cat_items_j):
                        if idx > 0: new_j_val += "; "
                        j_item = item["j_item"]
                        if j_item:
                            match = j_parser_pat.match(j_item)
                            if match:
                                sub_prefix = match.group(1) or ""
                                pure_sub_name = match.group(2) or ""
                                concentration = match.group(3) or ""
                                
                                if sub_prefix:
                                    start_pos = len(new_j_val) + 1
                                    blue_marks_j.append((start_pos, len(sub_prefix)))
                                    new_j_val += sub_prefix
                                    
                                if pure_sub_name:
                                    pure_sub_norm = normalize_name(pure_sub_name)
                                    is_sub_red = False
                                    if pure_sub_norm not in valid_substances_clean and pure_sub_norm not in api_valid_substances:
                                        is_sub_red = True
                                    if match.group(3) is None or not concentration.strip():
                                        is_sub_red = True
                                    if item.get("is_red", False):
                                        is_sub_red = True
                                        
                                    if is_sub_red:
                                        start_pos = len(new_j_val) + 1
                                        red_marks_j.append((start_pos, len(pure_sub_name)))
                                    new_j_val += pure_sub_name
                                    
                                if match.group(3) is not None:
                                    paren_content = f"({concentration})"
                                    is_conc_red = ("%" not in concentration or not concentration.strip())
                                    start_pos = len(new_j_val) + 1
                                    if is_conc_red:
                                        red_marks_j.append((start_pos, len(paren_content)))
                                    new_j_val += paren_content
                            else:
                                start_pos = len(new_j_val) + 1
                                red_marks_j.append((start_pos, len(j_item)))
                                new_j_val += j_item
            
            i_cell.Value = new_i_val
            j_cell.Value = new_j_val
            restore_cell_format(i_cell, i_fmt)
            restore_cell_format(j_cell, j_fmt)
            
            i_cell_dyn = win32com.client.dynamic.Dispatch(i_cell._oleobj_)
            i_cell_dyn._FlagAsMethod("Characters")
            j_cell_dyn = win32com.client.dynamic.Dispatch(j_cell._oleobj_)
            j_cell_dyn._FlagAsMethod("Characters")
            
            for start, length in red_marks_i:
                i_cell_dyn.Characters(start, length).Font.Color = 255
            for start, length in blue_marks_i:
                i_cell_dyn.Characters(start, length).Font.Color = 16711680
            for start, length in red_marks_j:
                j_cell_dyn.Characters(start, length).Font.Color = 255
            for start, length in blue_marks_j:
                j_cell_dyn.Characters(start, length).Font.Color = 16711680
                
            print(f"\n[{r}행] 조립 결과:")
            print(f"  I열 값: '{new_i_val}'")
            print(f"  J열 값: '{new_j_val}'")
            
            # Assertions 검증
            if r == 14:
                # 염화 바륨은 마스터 DB에 없지만 N열에 유효 CAS가 있어 적색 마킹되지 않아야 함 (검은색).
                for idx in range(1, len(new_j_val)+1):
                    color = j_cell_dyn.Characters(idx, 1).Font.Color
                    assert color == 0 or color == -4105, f"14행 J열 [{idx}] '염화 바륨' 적색 마킹 오류 (색상: {color})"
                    
            elif r == 15:
                # N열에 유효 CAS가 없으므로 여전히 적색 마킹(255)이 작동해야 함.
                # "염화 바륨(98.5%)" 중 "염화 바륨" 부분 (1~5번째 문자) 적색 검증
                for idx in range(1, 6):
                    color = j_cell_dyn.Characters(idx, 1).Font.Color
                    assert color == 255, f"15행 J열 [{idx}] '염화 바륨' 적색 마킹 누락 (색상: {color})"
                    
        print("\n모든 v6 검증(Assertion) 통과!")
        print("  - N열에 유효한 CAS 번호와 함께 추출된 물질(염화 바륨)은 적색 마킹 없이 정상 통과합니다.")
        print("  - N열에 CAS 번호가 유효하지 않은 경우, 여전히 적색 마킹 경고가 정상 작동합니다.")
        wb.Save()
        return True
        
    except Exception as e:
        print(f"검증 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if wb:
            wb.Close(SaveChanges=False)
        pythoncom.CoUninitialize()
        if os.path.exists(test_xlsx):
            try:
                os.remove(test_xlsx)
                print("임시 검증 파일 삭제 완료.")
            except:
                pass

if __name__ == "__main__":
    success = run_precision_marking_v6_verification()
    sys.exit(0 if success else 1)
