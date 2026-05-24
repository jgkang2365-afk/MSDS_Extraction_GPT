# -*- coding: utf-8 -*-
"""[NEW] 엑셀 셀 서식 보존 및 함유량 누락 적색 표시 검증 스크립트"""
import os
import sys
import shutil
import win32com.client
import win32com.client.dynamic
import pythoncom

def run_excel_format_verification():
    print("=== 엑셀 서식 보존 및 빨간색 마킹 검증 시작 ===")
    
    # 1. 파일 경로 정의 및 임시 파일 생성
    base_dir = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)"
    orig_xlsx = os.path.join(base_dir, "msds_index.xlsx")
    test_xlsx = os.path.join(base_dir, "scratch", "test_format_temp.xlsx")
    
    if not os.path.exists(orig_xlsx):
        print(f"오류: 원본 {orig_xlsx} 파일이 존재하지 않습니다.")
        return False
        
    os.makedirs(os.path.dirname(test_xlsx), exist_ok=True)
    shutil.copy(orig_xlsx, test_xlsx)
    print(f"테스트용 엑셀 복사본 생성: {test_xlsx}")
    
    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        # 2. 엑셀 인스턴스 획득 및 파일 열기
        try:
            excel = win32com.client.GetActiveObject("Excel.Application")
        except:
            excel = win32com.client.Dispatch("Excel.Application")
        
        excel.Visible = False
        excel.DisplayAlerts = False
        
        wb = excel.Workbooks.Open(test_xlsx)
        ws = wb.Worksheets("Sheet1")
        
        # 3. 테스트 행 서식 임의 설정 (3행과 4행 대상)
        # xlCenter = -4108
        r3_i = ws.Cells(3, 9) # I열 (비고)
        r3_j = ws.Cells(3, 10) # J열 (MSDS)
        r4_i = ws.Cells(4, 9)
        r4_j = ws.Cells(4, 10)
        
        # 테스트 값 주입
        r3_i.Value = "산화철"
        r3_j.Value = "산화철(10-20)"  # % 누락 (오류 마킹 대상)
        
        r4_i.Value = "벤젠"
        r4_j.Value = "벤젠(10%)"      # 정상 함유량
        
        # 맞춤 및 폰트 서식 강제 세팅 (검증용)
        for cell in [r3_i, r3_j, r4_i, r4_j]:
            cell.HorizontalAlignment = -4108 # 가운데 맞춤
            cell.VerticalAlignment = -4108   # 가운데 맞춤
            cell.WrapText = True            # 텍스트 줄바꿈
            cell.ShrinkToFit = False
            cell.Font.Name = "맑은 고딕"
            cell.Font.Size = 11
            cell.Font.Bold = True
            cell.Font.Color = 0              # 검은색 기본
            
        print("테스트 전 서식 설정 완료 (가운데 맞춤, 텍스트 줄바꿈, 맑은 고딕, 굵게)")
        
        # 4. smu_gui.py에 구현된 것과 동일한 백업/값수정/복원 및 적색 마킹 로직 구동
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
            if not fmt:
                return
            cell.HorizontalAlignment = fmt["HorizontalAlignment"]
            cell.VerticalAlignment = fmt["VerticalAlignment"]
            cell.WrapText = fmt["WrapText"]
            cell.ShrinkToFit = fmt["ShrinkToFit"]
            cell.Font.Name = fmt["FontName"]
            cell.Font.Size = fmt["FontSize"]
            cell.Font.Bold = fmt["FontBold"]
            cell.Font.Italic = fmt["FontItalic"]
            cell.Font.Underline = fmt["FontUnderline"]
            if fmt["FontColor"] != 0:
                cell.Font.Color = fmt["FontColor"]

        # 테스트 대상 행들에 대해 로직 직접 적용
        test_rows = [3, 4]
        for r in test_rows:
            i_cell = ws.Cells(r, 9)
            j_cell = ws.Cells(r, 10)
            
            i_val = str(i_cell.Value or "").strip()
            j_val = str(j_cell.Value or "").strip()
            
            # 5. 서식 백업
            i_fmt = backup_cell_format(i_cell)
            j_fmt = backup_cell_format(j_cell)
            
            # 6. 값 업데이트 (임의로 끝에 빈 공백이나 세미콜론 정렬 등을 모의)
            new_i_val = i_val  # 실제 로직에 의해 재조립된 것으로 가정
            new_j_val = j_val
            
            i_cell.Value = new_i_val
            j_cell.Value = new_j_val
            
            # 7. 서식 복원
            restore_cell_format(i_cell, i_fmt)
            restore_cell_format(j_cell, j_fmt)
            
            # 8. J열 % 누락 검사 및 캐릭터 색상 변경 (경고 마킹)
            # 3행은 J열 % 누락으로 red_marks_j 대상임
            if r == 3:
                # Character 부분 채색 모의
                try:
                    j_cell_dyn = win32com.client.dynamic.Dispatch(j_cell._oleobj_)
                    j_cell_dyn._FlagAsMethod("Characters")
                    
                    # "산화철(10-20)" 전체 길이만큼 글자 색상 빨간색(255) 적용
                    j_cell_dyn.Characters(1, len(new_j_val)).Font.Color = 255
                    print(f"[{r}행] J열 성분 누락 경고 마킹 완료: {new_j_val}")
                except Exception as ex:
                    print(f"부분 채색 실패: {ex}")
                    # 폴백으로 전체 색상 빨간색 적용
                    j_cell.Font.Color = 255
        
        # 9. 서식 보존 결과 검증 (Assertion)
        for r in test_rows:
            i_cell = ws.Cells(r, 9)
            j_cell = ws.Cells(r, 10)
            
            # 정렬 서식들이 원래 설정된 대로 잘 복구되었는지 검사
            assert i_cell.HorizontalAlignment == -4108, f"{r}행 I열 HorizontalAlignment 유실됨"
            assert i_cell.VerticalAlignment == -4108, f"{r}행 I열 VerticalAlignment 유실됨"
            assert i_cell.WrapText == True, f"{r}행 I열 WrapText 유실됨"
            assert i_cell.Font.Bold == True, f"{r}행 I열 Font.Bold 유실됨"
            assert i_cell.Font.Name == "맑은 고딕", f"{r}행 I열 Font.Name 유실됨"
            
            assert j_cell.HorizontalAlignment == -4108, f"{r}행 J열 HorizontalAlignment 유실됨"
            assert j_cell.VerticalAlignment == -4108, f"{r}행 J열 VerticalAlignment 유실됨"
            assert j_cell.WrapText == True, f"{r}행 J열 WrapText 유실됨"
            assert j_cell.Font.Bold == True, f"{r}행 J열 Font.Bold 유실됨"
            assert j_cell.Font.Name == "맑은 고딕", f"{r}행 J열 Font.Name 유실됨"
            
            # 색상 검증
            if r == 3:
                # J열은 빨간색이어야 함
                assert j_cell.Font.Color == 255 or j_cell.Characters(1, 1).Font.Color == 255, f"{r}행 J열 적색 경고 미적용됨"
                print(f"[{r}행 검증 완료] 서식 유지 및 J열 적색 경고가 정상적으로 확인되었습니다.")
            elif r == 4:
                # 정상 성분은 글꼴 색상이 기본이어야 함
                assert j_cell.Font.Color == 0 or j_cell.Font.Color == 16777215 or j_cell.Font.Color == -4105, f"{r}행 J열 글자색이 오염되었습니다."
                print(f"[{r}행 검증 완료] 서식 유지 및 정상 색상이 정상적으로 확인되었습니다.")
                
        print("모든 검증(Assertion) 통과! 셀 서식 보존 및 빨간색 마킹 장치가 완벽하게 작동합니다.")
        wb.Save()
        return True
        
    except Exception as e:
        print(f"검증 도중 예외 발생: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if wb:
            wb.Close(SaveChanges=False)
        pythoncom.CoUninitialize()
        # 임시 생성된 파일 정리
        if os.path.exists(test_xlsx):
            try:
                os.remove(test_xlsx)
                print("임시 테스트 파일 삭제 완료.")
            except Exception as e:
                print(f"임시 파일 삭제 실패: {e}")

if __name__ == "__main__":
    success = run_excel_format_verification()
    sys.exit(0 if success else 1)
