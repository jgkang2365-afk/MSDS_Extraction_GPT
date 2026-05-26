# -*- coding: utf-8 -*-
"""[NEW] I열/J열 정교한 문자 단위 적색 마킹 검증 스크립트"""
import os
import sys
import shutil
import re
import win32com.client
import pythoncom

def run_precision_marking_verification():
    print("=== 정교한 문자 단위 적색 마킹 검증 시작 ===")
    
    # 1. 테스트 디렉토리 및 파일 복사
    base_dir = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)"
    orig_xlsx = os.path.join(base_dir, "msds_index.xlsx")
    test_xlsx = os.path.join(base_dir, "scratch", "test_precision_temp.xlsx")
    
    if not os.path.exists(orig_xlsx):
        print(f"오류: 원본 {orig_xlsx} 파일이 없습니다.")
        return False
        
    os.makedirs(os.path.dirname(test_xlsx), exist_ok=True)
    shutil.copy(orig_xlsx, test_xlsx)
    print(f"테스트 파일 생성 완료: {test_xlsx}")
    
    # 2. 마스터 DB 정규화 모킹
    valid_substances = {
        "톨루엔", "벤젠", "크실렌", "질산", "카드뮴 및 그 화합물", "바륨 및 그 가용성 화합물", "산화철(분진, 흄)"
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
            excel = win32com.client.GetActiveObject("Excel.Application")
        except:
            excel = win32com.client.Dispatch("Excel.Application")
            
        excel.Visible = False
        excel.DisplayAlerts = False
        
        wb = excel.Workbooks.Open(test_xlsx)
        ws = wb.Worksheets("Sheet1")
        
        # 3. 테스트 데이터 및 기대 마킹 결과 설계
        # (I열 입력값, J열 입력값, row_data 가상 매칭 목록)
        test_scenarios = [
            {
                "row": 3,
                "cat_items": [
                    {"category": "측정대상", "i_item_final": "톨루엔", "j_item": "톨루엔(1~10%)", "sort_code": "A"},
                    {"category": "측정 비대상", "i_item_final": "[특별]벤젠", "j_item": "[특별]벤젠(0.1~0.7%)", "sort_code": "B"},
                    {"category": "단시간 및 임시작업", "i_item_final": "크실렌", "j_item": "크실렌(2~4%)", "sort_code": "C"}
                ]
            },
            {
                "row": 4,
                "cat_items": [
                    {"category": "측정대상", "i_item_final": "질산", "j_item": "질산(2%)", "sort_code": "A"},
                    {"category": "측정 비대상", "i_item_final": "[특별]카드뮴 및 그 화합물", "j_item": "[특별]카드뮴(0.1%)", "sort_code": "B"}
                ]
            },
            {
                "row": 5,
                "cat_items": [
                    {"category": "측정대상", "i_item_final": "바륨 및 그 가용성 화합물", "j_item": "염화 바륨(98.5%)", "sort_code": "A"}
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
        
        for sc in test_scenarios:
            r = sc["row"]
            cat_items_sc = sc["cat_items"]
            
            i_cell = ws.Cells(r, 9)
            j_cell = ws.Cells(r, 10)
            
            # 셀 초기 설정
            i_cell.Value = ""
            j_cell.Value = ""
            i_cell.Font.Color = 0
            j_cell.Font.Color = 0
            
            # 4. 실시간 조립 및 적색 마킹 계산 로직 작동
            new_i_val = ""
            new_j_val = ""
            red_marks_i = []
            red_marks_j = []
            
            first_group = True
            for cat_name, sep, wrapper in group_definitions:
                cat_items = [x for x in cat_items_sc if x["category"] == cat_name]
                if not cat_items:
                    continue
                    
                if not first_group:
                    new_i_val += "; "
                    new_j_val += "; "
                first_group = False
                
                # I열 조립
                if wrapper:
                    new_i_val += wrapper
                    
                for idx, item in enumerate(cat_items):
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
                            red_marks_i.append((start_pos, len(sub_prefix)))
                            new_i_val += sub_prefix
                            
                        if pure_sub_name:
                            pure_sub_norm = normalize_name(pure_sub_name)
                            if pure_sub_norm not in valid_substances_clean:
                                start_pos = len(new_i_val) + 1
                                red_marks_i.append((start_pos, len(pure_sub_name)))
                            new_i_val += pure_sub_name
                            
                if wrapper:
                    new_i_val += "]"
                    
                # J열 조립
                for idx, item in enumerate(cat_items):
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
                                red_marks_j.append((start_pos, len(sub_prefix)))
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
                            
            # 엑셀 셀에 값 주입
            i_cell.Value = new_i_val
            j_cell.Value = new_j_val
            
            # 부분 적색 마킹 적용 (동적 래핑 및 Characters 제어)
            try:
                i_cell_dyn = win32com.client.dynamic.Dispatch(i_cell._oleobj_)
                i_cell_dyn._FlagAsMethod("Characters")
                j_cell_dyn = win32com.client.dynamic.Dispatch(j_cell._oleobj_)
                j_cell_dyn._FlagAsMethod("Characters")
            except:
                i_cell_dyn = i_cell
                j_cell_dyn = j_cell
                
            for start, length in red_marks_i:
                i_cell_dyn.Characters(start, length).Font.Color = 255
            for start, length in red_marks_j:
                j_cell_dyn.Characters(start, length).Font.Color = 255
                
            print(f"\n[{r}행] 조립 텍스트 출력:")
            print(f"  I열: {new_i_val}")
            print(f"  I열 마킹 목록: {red_marks_i}")
            print(f"  J열: {new_j_val}")
            print(f"  J열 마킹 목록: {red_marks_j}")
            
            # 5. 서식 및 색상 마킹 정밀 검증
            # 3행 검증
            if r == 3:
                # I열: "톨루엔; 측정 비대상[[특별]벤젠]; 단시간 및 임시작업[크실렌]"
                # "측정 비대상[[특별]" 의 13번째부터 4글자인 "[특별]"만 빨간색이어야 함
                for ch_idx in range(1, len(new_i_val) + 1):
                    color = i_cell_dyn.Characters(ch_idx, 1).Font.Color
                    if ch_idx in range(13, 17): # "[특별]"
                        assert color == 255, f"3행 I열 [{ch_idx}] 위치 빨간색 누락"
                    else:
                        assert color == 0 or color == -4105, f"3행 I열 [{ch_idx}] 위치 검은색 오염 (색상코드: {color})"
                
                # J열: "톨루엔(1~10%); [특별]벤젠(0.1~0.7%); 크실렌(2~4%)"
                # "[특별]" 부분(13~16번째)만 빨간색이어야 함
                for ch_idx in range(1, len(new_j_val) + 1):
                    color = j_cell_dyn.Characters(ch_idx, 1).Font.Color
                    if ch_idx in range(13, 17): # "[특별]"
                        assert color == 255, f"3행 J열 [{ch_idx}] 위치 빨간색 누락"
                    else:
                        assert color == 0 or color == -4105, f"3행 J열 [{ch_idx}] 위치 검은색 오염 (색상코드: {color})"
                        
            # 4행 검증
            if r == 4:
                # I열: "질산; 측정 비대상[[특별]카드뮴 및 그 화합물]"
                # "[특별]"만 빨간색이어야 하고, "카드뮴 및 그 화합물"은 마스터 DB에 있으므로 검은색이어야 함
                for ch_idx in range(1, len(new_i_val) + 1):
                    color = i_cell_dyn.Characters(ch_idx, 1).Font.Color
                    if ch_idx in range(12, 16): # "[특별]"
                        assert color == 255, f"4행 I열 [{ch_idx}] 위치 빨간색 누락"
                    else:
                        assert color == 0 or color == -4105, f"4행 I열 [{ch_idx}] 위치 검은색 오염 (색상코드: {color})"
                
                # J열: "질산(2%); [특별]카드뮴(0.1%)"
                # "[특별]"과 "카드뮴"(표준명 불일치)이 빨간색이어야 함. 
                # [특별] 은 9번째부터 4글자, 카드뮴은 13번째부터 3글자. 총 9~15번째 글자
                for ch_idx in range(1, len(new_j_val) + 1):
                    color = j_cell_dyn.Characters(ch_idx, 1).Font.Color
                    if ch_idx in range(9, 16): # "[특별]카드뮴"
                        assert color == 255, f"4행 J열 [{ch_idx}] 위치 빨간색 누락"
                    else:
                        assert color == 0 or color == -4105, f"4행 J열 [{ch_idx}] 위치 검은색 오염 (색상코드: {color})"
                        
            # 5행 검증
            if r == 5:
                # I열: "바륨 및 그 가용성 화합물" (정상 - 검은색)
                for ch_idx in range(1, len(new_i_val) + 1):
                    color = i_cell_dyn.Characters(ch_idx, 1).Font.Color
                    assert color == 0 or color == -4105, f"5행 I열 [{ch_idx}] 위치 오염"
                    
                # J열: "염화 바륨(98.5%)" ("염화 바륨"만 빨간색, 1~5번째 글자)
                for ch_idx in range(1, len(new_j_val) + 1):
                    color = j_cell_dyn.Characters(ch_idx, 1).Font.Color
                    if ch_idx in range(1, 6): # "염화 바륨"
                        assert color == 255, f"5행 J열 [{ch_idx}] 위치 빨간색 누락"
                    else:
                        assert color == 0 or color == -4105, f"5행 J열 [{ch_idx}] 위치 검은색 오염 (색상코드: {color})"
                        
        print("\n모든 정교한 마킹 검증(Assertion) 통과! 의도한 범위만 완벽하게 빨간색으로 칠해집니다.")
        wb.Save()
        return True
        
    except Exception as e:
        print(f"검증 도중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if wb:
            wb.Close(SaveChanges=False)
        pythoncom.CoUninitialize()
        # 임시 파일 정리
        if os.path.exists(test_xlsx):
            try:
                os.remove(test_xlsx)
                print("임시 검증 파일 정리 완료.")
            except Exception as ex:
                print(f"임시 파일 정리 실패: {ex}")

if __name__ == "__main__":
    success = run_precision_marking_verification()
    sys.exit(0 if success else 1)
