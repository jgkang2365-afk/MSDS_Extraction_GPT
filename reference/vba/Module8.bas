Attribute VB_Name = "Module8"

'PDF저장

Sub PDF저장()
    Dim savePath As String
    Dim fileName As String

    ' 현재 통합문서의 경로 가져오기
    savePath = ThisWorkbook.Path & Application.PathSeparator

    ' 파일 이름 생성
    fileName = "견적서(26년상)_" & Cells(5, "F").Value & ".pdf"

    ' 전체 파일 경로 생성
    savePath = savePath & fileName

    ' 파일이 이미 존재하는 경우 덮어쓰기 여부 확인 (선택 사항)
    If Dir(savePath) <> "" Then
        If MsgBox("동일한 이름의 파일이 이미 존재합니다. 덮어쓰시겠습니까?", vbYesNo) = vbNo Then Exit Sub
    End If

    ' "견적서" 시트를 PDF로 저장
    ActiveWorkbook.Sheets("견적서").ExportAsFixedFormat Type:=xlTypePDF, fileName:=savePath, Quality:=xlQualityStandard

    MsgBox "PDF 파일이 성공적으로 저장되었습니다."

End Sub


Sub SetPrintAreaByColumnC() '측정계획(양식)시트 인쇄영역 자동설정 매크로
    Dim ws As Worksheet
    Dim i As Long
    Dim lastRow As Long
    Dim dataStartRow As Long

    ' 1. 시트 지정 (이름이 정확히 일치해야 합니다. 뒤에 띄어쓰기가 숨어있으면 안 됩니다.)
    On Error Resume Next
    Set ws = ThisWorkbook.Sheets("측정계획(양식)")
    On Error GoTo 0

    If ws Is Nothing Then
        MsgBox "'측정계획(양식)' 시트를 찾을 수 없습니다. 시트 이름 탭을 더블클릭해서 숨겨진 띄어쓰기가 없는지 확인해 주세요.", vbCritical
        Exit Sub
    End If

    ' 2. 데이터 시작 행 강제 지정
    ' 올려주신 이미지를 보면 상단 결재란과 제목들이 많은 자리를 차지하고 있습니다.
    ' 엑셀이 헤더의 빈칸에 속지 않도록, 실제 숫자 '1'이 시작되는 행을 직접 숫자로 적어주는 것이 가장 안전합니다.
    ' (이미지상 대략 7행으로 보이나, 실제 엑셀 파일에서 '1'이 적힌 행 번호를 확인 후 아래 숫자를 수정해 주세요.)
    dataStartRow = 7

    i = dataStartRow

    ' 3. C열(3번째 열)에서 빈 셀이 나올 때까지 탐색
    Do While Trim(ws.Cells(i, 3).Value) <> ""
        i = i + 1
    Loop

    lastRow = i - 1

    ' 만약 데이터가 없으면 제목줄까지만 잡기
    If lastRow < dataStartRow Then lastRow = dataStartRow - 1

    ' 4. 인쇄 영역 설정
    ws.PageSetup.PrintArea = "A1:L" & lastRow


End Sub


Private Sub Workbook_BeforePrint(Cancel As Boolean)
    ' 특정 시트에서 인쇄할 때만 매크로가 작동하도록 조건문을 설정합니다.
    ' 모든 시트에서 작동하게 하려면 If ~ End If 구문을 지우면 됩니다.

    If ActiveSheet.Name = "측정계획(양식)" Then

        ' 이전 단계에서 만든 매크로를 호출하여 인쇄 영역을 먼저 자동 설정합니다.
        Call SetPrintAreaByColumnC

    End If
End Sub
