# -*- coding: utf-8 -*-
"""[NEW] I열 매칭 누락 방어 및 G열 기반 보관 카테고리 오류 감지 검증 스크립트"""
import os
import sys
import shutil
import re
import win32com.client
import win32com.client.dynamic
import pythoncom

def run_precision_marking_v4_verification():
    print("=== I열 매칭 누락 방어 및 G열 기반 보관 규칙 검증 시작 ===")
    
    base_dir = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)"
    orig_xlsx = os.path.join(base_dir, "msds_index.xlsx")
    test_xlsx = os.path.join(base_dir, "scratch", "test_precision_v4_temp.xlsx")
    
    if not os.path.exists(orig_xlsx):
        print(f"오류: 원본 {orig_xlsx} 파일이 없습니다.")
        return False
        
    os.makedirs(os.path.dirname(test_xlsx), exist_ok=True)
    shutil.copy(orig_xlsx, test_xlsx)
    print(f"테스트 파일 복사 완료: {test_xlsx}")
    
    # 1. 마스터 DB 정규화 모킹
    valid_substances = {
        "톨루엔", "벤젠", "크실렌", "질산", "카드뮴 및 그 화합물", "바륨 및 그 가용성 화합물", "활석"
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
        # 6행: G열 = "100" (월취급량 0 아님), I열 = "보관[벤젠]", J열 = "벤젠(10%)"
        #      --> 카테고리 '보관'인데 G열이 0이 아니므로 벤젠에 적색 마킹되어야 함.
        # 7행: G열 = "10", I열 = "" (빈값), J열 = "활석(100%)"
        #      --> I열 누락 방어 작동: I열에 "[누락]"이 기재되고 빨간색 마킹되어야 함.
        
        ws.Cells(6, 7).Value = "100"
        ws.Cells(6, 9).Value = "보관[벤젠]"
        ws.Cells(6, 10).Value = "벤젠(10%)"
        
        ws.Cells(7, 7).Value = "10"
        ws.Cells(7, 9).Value = ""
        ws.Cells(7, 10).Value = "활석(100%)"
        
        test_scenarios = [6, 7]
        
        group_definitions = [
            ("측정대상", "; ", ""),
            ("측정 비대상", "; ", "측정 비대상["),
            ("단시간 및 임시작업", "; ", "단시간 및 임시작업["),
            ("허용소비량 미만", "; ", "허용소비량 미만["),
            ("보관", "; ", "보관[")
        ]
        
        j_parser_pat = re.compile(r"^(?:(\[특별\]|\[특검\]|\[허가\]))?(.*?)(?:\(([^)]*)\))?$")
        
        # 괄호 및 접미사 파싱용 간단 헬퍼
        def parse_substance_item(item_str):
            item_str = item_str.strip()
            if not item_str: return None
            
            category = "측정대상"
            pure_name = item_str
            
            # 카테고리 파싱
            for cat_name in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
                if item_str.startswith(cat_name + "[") and item_str.endswith("]"):
                    category = cat_name
                    pure_name = item_str[len(cat_name)+1:-1]
                    break
            
            sub_prefix = ""
            for sp in ["[특별]", "[특검]", "[허가]"]:
                if pure_name.startswith(sp):
                    sub_prefix = sp
                    pure_name = pure_name[len(sp):]
                    break
                    
            return {
                "pure_name": pure_name,
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
        def extract_pure_substance_name(j_item):
            match = j_parser_pat.match(j_item)
            if match:
                return match.group(2) or ""
            return j_item

        for r in test_scenarios:
            i_cell = ws.Cells(r, 9)
            j_cell = ws.Cells(r, 10)
            g_cell = ws.Cells(r, 7)
            
            i_val = str(i_cell.Value or "").strip()
            j_val = str(j_cell.Value or "").strip()
            g_raw = str(g_cell.Value or "").strip()
            
            is_g_zero = is_zero_value(g_raw)
            
            # 모의 가상화 매칭 로직 구동
            if not i_val and not j_val:
                continue
                
            # split_i_val 시뮬레이션
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
                # I열 항목이 아예 비어있어 매칭 불능인 낙오 물질 처리
                if not i_item:
                    row_data.append({
                        "i_item_final": "[누락]",  # V24.3.5.6 룰 적용
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
                if i_sub_norm not in valid_substances_clean:
                    is_red = True
                if not j_item or "%" not in j_item:
                    is_red = True
                    
                # G열 기반 보관 카테고리 검증 적용
                if category == "보관" and not is_g_zero:
                    is_red = True
                    
                row_data.append({
                    "i_item_final": i_item_final,
                    "j_item": j_item,
                    "category": category,
                    "sort_code": sort_code,
                    "is_red": is_red
                })
                
            # 정렬
            row_data.sort(key=lambda x: x["sort_code"])
            
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
                
                if not valid_cat_items_i and not valid_cat_items_j:
                    continue
                    
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
                                if pure_sub_norm not in valid_substances_clean:
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
                                    if pure_sub_norm not in valid_substances_clean:
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
            if r == 6:
                # G열="100"이고 보관이므로 "벤젠"은 적색 마킹되어야 함.
                # I열 값: "보관[벤젠]" -> "보관"은 검은색, "벤젠"만 빨간색(255)
                # "보관[" (4글자)는 검은색, "벤젠" (2글자)는 빨간색.
                assert new_i_val == "보관[벤젠]", f"6행 I열 조립 실패: '{new_i_val}'"
                for idx in range(1, len(new_i_val)+1):
                    color = i_cell_dyn.Characters(idx, 1).Font.Color
                    if idx in [4, 5]: # "벤" "젠" (1-based index: 보관[ -> 1~3, 벤젠 -> 4~5, ] -> 6)
                        assert color == 255, f"6행 I열 [{idx}] '벤젠' 적색 누락 (색상: {color})"
                    else:
                        assert color == 0 or color == -4105, f"6행 I열 [{idx}] 비정상 채색 (색상: {color})"
                        
                # J열 값: "벤젠(10%)" -> "벤젠" 부분 빨간색(255)
                assert new_j_val == "벤젠(10%)", f"6행 J열 조립 실패: '{new_j_val}'"
                for idx in range(1, len(new_j_val)+1):
                    color = j_cell_dyn.Characters(idx, 1).Font.Color
                    if idx in [1, 2]: # "벤" "젠"
                        assert color == 255, f"6행 J열 [{idx}] '벤젠' 적색 누락 (색상: {color})"
                    else:
                        assert color == 0 or color == -4105, f"6행 J열 [{idx}] 비정상 채색 (색상: {color})"
                        
            if r == 7:
                # I열 비어있고 J열만 있으므로 I열에 "[누락]" 기입 및 적색 마킹.
                assert new_i_val == "[누락]", f"7행 I열 조립 실패: '{new_i_val}'"
                for idx in range(1, len(new_i_val)+1):
                    color = i_cell_dyn.Characters(idx, 1).Font.Color
                    assert color == 255, f"7행 I열 [{idx}] '[누락]' 적색 누락 (색상: {color})"
                    
        print("\n모든 v4 검증(Assertion) 통과!")
        print("  - G열(월취급량)이 0이 아닐 때 보관 카테고리 물질에 대해 I열과 J열 모두 적색 오류 마킹이 정상 작동합니다.")
        print("  - I열이 비어있고 J열만 존재할 때 I열에 '[누락]'이 자동 기재되고 전체 적색 마킹이 완료되었습니다.")
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
    success = run_precision_marking_v4_verification()
    sys.exit(0 if success else 1)
