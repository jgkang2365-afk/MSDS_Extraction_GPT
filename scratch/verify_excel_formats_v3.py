# -*- coding: utf-8 -*-
"""[NEW] 세미콜론 노이즈 방어 및 2회차 검정 복귀, 파란색 마킹 정밀 검증 스크립트"""
import os
import sys
import shutil
import re
import win32com.client
import win32com.client.dynamic
import pythoncom

def run_precision_marking_v3_verification():
    print("=== 세미콜론 노이즈 방어 및 이전 마킹 리셋, 파란색 마킹 검증 시작 ===")
    
    base_dir = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)"
    orig_xlsx = os.path.join(base_dir, "msds_index.xlsx")
    test_xlsx = os.path.join(base_dir, "scratch", "test_precision_v3_temp.xlsx")
    
    if not os.path.exists(orig_xlsx):
        print(f"오류: 원본 {orig_xlsx} 파일이 없습니다.")
        return False
        
    os.makedirs(os.path.dirname(test_xlsx), exist_ok=True)
    shutil.copy(orig_xlsx, test_xlsx)
    print(f"테스트 파일 복사 완료: {test_xlsx}")
    
    # 1. 마스터 DB 정규화 모킹
    valid_substances = {
        "톨루엔", "벤젠", "크실렌", "질산", "카드뮴 및 그 화합물", "바륨 및 그 가용성 화합물", "활석(석면불포함)"
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
            
        # excel.Visible = False
        # excel.DisplayAlerts = False
        
        wb = excel.Workbooks.Open(test_xlsx)
        ws = wb.Worksheets("Sheet1")
        
        # 2. 테스트 시나리오 구성
        # 3행: I열/J열 다중 물질의 정렬 및 세미콜론 버그 방지 (중간에 ; ; 공백 생기지 않는지 검증)
        # 4행: 이전 에러 마킹색(255)이었던 셀이 마스터 DB 매칭 후 정상 검정색(0)으로 복귀하는지 검증
        # 5행: 1개 성분만 있는 경우 앞/뒤에 '; ' 구분자가 붙지 않는지 및 수식어 파란색 마킹 검증
        test_scenarios = [
            {
                "row": 3,
                "cat_items": [
                    {"category": "측정대상", "i_item_final": "톨루엔", "j_item": "톨루엔(1~10%)", "sort_code": "A_Toluene"},
                    {"category": "측정대상", "i_item_final": "크실렌", "j_item": "크실렌(2~4%)", "sort_code": "A_Xylene"},
                    {"category": "측정대상", "i_item_final": "", "j_item": "", "sort_code": "A_Empty"},  # 빈 고아 성분 시뮬레이션
                    {"category": "측정 비대상", "i_item_final": "[특별]벤젠", "j_item": "[특별]벤젠(0.1~0.7%)", "sort_code": "B_Benzene"}
                ]
            },
            {
                "row": 4,
                "cat_items": [
                    {"category": "측정대상", "i_item_final": "활석(석면불포함)", "j_item": "활석(석면불포함)(10%)", "sort_code": "A"}
                ]
            },
            {
                "row": 5,
                "cat_items": [
                    {"category": "측정대상", "i_item_final": "바륨 및 그 가용성 화합물", "j_item": "염화 바륨(98.5%)", "sort_code": "A"},
                    {"category": "측정 비대상", "i_item_final": "[특별]카드뮴 및 그 화합물", "j_item": "[특별]카드뮴(0.1%)", "sort_code": "B"}
                ]
            }
        ]
        
        group_definitions = [
            ("측정대상", "; ", ""),
            ("측정 비대상", "; ", "측정 비대상["),
            ("단시간 및 임시작업", "; ", "단시간 및 임시작업["),
            ("허용소비량 미만", "; ", "허용소비량 미만["),
            ("보관", "; ", "보관[")
        ]
        
        j_parser_pat = re.compile(r"^(?:(\[특별\]|\[특검\]|\[허가\]))?(.*?)(?:\(([^)]*)\))?$")
        
        # 4행 I열 셀에 사전 에러색(적색=255) 주입하여 2회차 복구 상황 시뮬레이션
        ws.Cells(4, 9).Font.Color = 255
        ws.Cells(4, 10).Font.Color = 255
        
        for sc in test_scenarios:
            r = sc["row"]
            cat_items_sc = sc["cat_items"]
            
            i_cell = ws.Cells(r, 9)
            j_cell = ws.Cells(r, 10)
            
            # 3. 실시간 오프셋 마킹 및 조립 구동
            new_i_val = ""
            new_j_val = ""
            red_marks_i = []
            red_marks_j = []
            blue_marks_i = []
            blue_marks_j = []
            
            # 셀 서식 백업
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
                # 이전 에러 마킹 색상(적색: 255, 청색: 16711680)은 복원하지 않고 검정으로 리셋
                if fmt["FontColor"] not in [0, 255, 16711680, -4105]:
                    cell.Font.Color = fmt["FontColor"]
                else:
                    cell.Font.Color = 0

            i_fmt = backup_cell_format(i_cell)
            j_fmt = backup_cell_format(j_cell)
            
            # 정렬코드로 통합 정렬
            cat_items_sc.sort(key=lambda x: x["sort_code"])
            
            first_i = True
            first_j = True
            for cat_name, sep, wrapper in group_definitions:
                cat_items = [x for x in cat_items_sc if x["category"] == cat_name]
                valid_cat_items_i = [x for x in cat_items if x["i_item_final"]]
                valid_cat_items_j = [x for x in cat_items if x["j_item"]]
                
                if not valid_cat_items_i and not valid_cat_items_j:
                    continue
                    
                # 1. I열 정교한 실시간 조립 및 오프셋 마킹 계산
                if valid_cat_items_i:
                    if not first_i:
                        new_i_val += "; "
                    first_i = False
                    
                    if wrapper:
                        new_i_val += wrapper
                        
                    for idx, item in enumerate(valid_cat_items_i):
                        if idx > 0:
                            new_i_val += sep
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
                                if pure_sub_norm not in valid_substances_clean:
                                    start_pos = len(new_i_val) + 1
                                    red_marks_i.append((start_pos, len(pure_sub_name)))
                                new_i_val += pure_sub_name
                                
                    if wrapper:
                        new_i_val += "]"
                        
                # 2. J열 정교한 실시간 조립 및 오프셋 마킹 계산 (I열 순서와 1:1 완벽 동기화)
                if valid_cat_items_j:
                    if not first_j:
                        new_j_val += "; "
                    first_j = False
                    
                    for idx, item in enumerate(valid_cat_items_j):
                        if idx > 0:
                            new_j_val += "; "
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
                                
            # 엑셀 값 대입 및 서식 복원
            i_cell.Value = new_i_val
            j_cell.Value = new_j_val
            restore_cell_format(i_cell, i_fmt)
            restore_cell_format(j_cell, j_fmt)
            
            # dynamic dispatch 래핑
            i_cell_dyn = win32com.client.dynamic.Dispatch(i_cell._oleobj_)
            i_cell_dyn._FlagAsMethod("Characters")
            j_cell_dyn = win32com.client.dynamic.Dispatch(j_cell._oleobj_)
            j_cell_dyn._FlagAsMethod("Characters")
            
            # 마킹 색상 적용
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
            
            # 4. 검증 Assertions
            # [3행 검증]: 세미콜론 중복 및 공백 구분자 오류 방지 검증
            if r == 3:
                # I열 값 기대치: "톨루엔; 크실렌; 측정 비대상[[특별]벤젠]"
                # "; ;" 형태나 끝에 ";"가 붙는 현상이 없어야 함
                assert new_i_val == "톨루엔; 크실렌; 측정 비대상[[특별]벤젠]", f"3행 I열 세미콜론 조립 버그: '{new_i_val}'"
                
                # J열 값 기대치: "톨루엔(1~10%); 크실렌(2~4%); [특별]벤젠(0.1~0.7%)"
                # 앞이나 끝에 ";"가 붙는 버그 방어 검사
                assert new_j_val == "톨루엔(1~10%); 크실렌(2~4%); [특별]벤젠(0.1~0.7%)", f"3행 J열 세미콜론 조립 버그: '{new_j_val}'"
                
                # J열의 "[특별]" 수식어 부분(22~25번째 문자)만 파란색(16711680)인지 검증
                for ch_idx in range(1, len(new_j_val) + 1):
                    color = j_cell_dyn.Characters(ch_idx, 1).Font.Color
                    if ch_idx in range(24, 28): # "[특별]"
                        assert color == 16711680, f"3행 J열 [{ch_idx}] 위치 파란색 누락 (색상: {color})"
                    else:
                        assert color == 0 or color == -4105, f"3행 J열 [{ch_idx}] 위치 비정상 채색 (색상: {color})"
                        
            # [4행 검증]: 2회차 재정리 시 이전 에러 색상(255)이 정상 물질에서 깨끗하게 검은색으로 복귀하는지 검증
            if r == 4:
                # 활석(석면불포함)은 마스터 DB에 있으므로 적색/청색 마킹이 없어야 하며,
                # 이전에 칠해진 빨간색(255)이 restore_cell_format에 의해 검은색(0)으로 복귀되었는지 확인
                for ch_idx in range(1, len(new_i_val) + 1):
                    color = i_cell_dyn.Characters(ch_idx, 1).Font.Color
                    assert color == 0 or color == -4105, f"4행 I열 [{ch_idx}] 위치 이전 빨간색이 리셋되지 않았습니다 (색상: {color})"
                    
            # [5행 검증]: 1개 성분 앞/뒤 구분자 노이즈 배제 및 수식어 파란색/미등록 물질 빨간색 개별 채색 검증
            if r == 5:
                # J열 값: "염화 바륨(98.5%); [특별]카드뮴(0.1%)"
                # 성분의 맨 앞이나 뒤에 "; "가 붙어 있지 않아야 함
                assert not new_j_val.startswith(";"), f"J열 맨 앞 세미콜론 버그 발생: '{new_j_val}'"
                assert not new_j_val.endswith(";"), f"J열 맨 뒤 세미콜론 버그 발생: '{new_j_val}'"
                
                # J열 파란색/적색 이원화 마킹 검증
                # "염화 바륨(98.5%); [특별]카드뮴(0.1%)"
                # 염화 바륨(1~5번째) -> 빨간색 (255)
                # [특별](17~20번째) -> 파란색 (16711680)
                # 카드뮴(21~23번째) -> 빨간색 (255)
                for ch_idx in range(1, len(new_j_val) + 1):
                    color = j_cell_dyn.Characters(ch_idx, 1).Font.Color
                    if ch_idx in range(1, 6): # "염화 바륨"
                        assert color == 255, f"5행 J열 [{ch_idx}] '염화 바륨' 적색 누락"
                    elif ch_idx in range(15, 19): # "[특별]"
                        assert color == 16711680, f"5행 J열 [{ch_idx}] '[특별]' 청색 누락"
                    elif ch_idx in range(19, 22): # "카드뮴"
                        assert color == 255, f"5행 J열 [{ch_idx}] '카드뮴' 적색 누락"
                    else:
                        assert color == 0 or color == -4105, f"5행 J열 [{ch_idx}] 위치 비정상 오염 (색상: {color})"
                        
        print("\n모든 정교한 v3 검증(Assertion) 전원 통과!")
        print("  - 세미콜론 중복 및 구분자 배치 오류가 완벽히 해결되었습니다.")
        print("  - 이전 경고색(적색/청색)을 가진 셀이 마스터 DB에 있는 정상 물질명 업데이트 시 검정색으로 자동 복귀되었습니다.")
        print("  - [특별], [특검] 수식어는 파란색으로, 미등록 물질은 빨간색으로 이원화되어 정확히 부분 채색되었습니다.")
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
    success = run_precision_marking_v3_verification()
    sys.exit(0 if success else 1)
