Attribute VB_Name = "Module2"
'I열과 J열의 세미콜론을 쉼표로 변환(검토 최종 끝내고 마지막으로 실행하는 문서 편집)

Sub 세미콜론을쉼표로변환()
    Dim inputSheet As Worksheet
    Dim lastRowI As Long, lastRowJ As Long
    Dim cell As Range

    Set inputSheet = ThisWorkbook.Sheets("화학물질입력_양식")

    ' I열 마지막 행 찾기
    lastRowI = inputSheet.Cells(inputSheet.Rows.Count, "I").End(xlUp).Row
    ' J열 마지막 행 찾기
    lastRowJ = inputSheet.Cells(inputSheet.Rows.Count, "J").End(xlUp).Row

    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual

    ' I열 처리 (I3 ~ 마지막행)
    For Each cell In inputSheet.Range("I3:I" & lastRowI)
        If cell.Value <> "" Then
            cell.Value = Replace(cell.Value, "; ", ", ")
        End If
    Next cell

    ' J열 처리 (J3 ~ 마지막행)
    For Each cell In inputSheet.Range("J3:J" & lastRowJ)
        If cell.Value <> "" Then
            cell.Value = Replace(cell.Value, "; ", ", ")
        End If
    Next cell

    Application.ScreenUpdating = True
    Application.Calculation = xlCalculationAutomatic

    MsgBox "I,J열 세미콜론→쉼표 변환 완료!", vbInformation
End Sub
