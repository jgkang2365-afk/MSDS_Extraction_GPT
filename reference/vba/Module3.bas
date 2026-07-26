Attribute VB_Name = "Module3"
Sub 공정별측정대상물질추출()
    Dim wsInput As Worksheet, wsCriteria As Worksheet, wsOutput As Worksheet
    Dim dictProcess As Object, dictSubstance As Object
    Dim lastRow As Long, i As Long, j As Long
    Dim processName As String, remarks As String, substance As String
    Dim substances() As String, sortedList() As String
    Dim outputRow As Long

    ' 시트 참조 설정
    Set wsInput = ThisWorkbook.Sheets("화학물질입력_양식")
    Set wsCriteria = ThisWorkbook.Sheets("기준목록")

    ' 기존 출력 시트 삭제 (존재할 경우)
    Application.DisplayAlerts = False
    On Error Resume Next
    ThisWorkbook.Sheets("공정별 측정대상").Delete
    On Error GoTo 0
    Application.DisplayAlerts = True

    ' 새 시트 생성
    Set wsOutput = ThisWorkbook.Sheets.Add(After:=ThisWorkbook.Sheets(ThisWorkbook.Sheets.Count))
    wsOutput.Name = "공정별 측정대상"

    ' 헤더 생성
    wsOutput.Range("A1").Value = "공정명"
    wsOutput.Range("B1").Value = "측정대상 물질"

    ' 데이터 처리 준비
    Set dictProcess = CreateObject("Scripting.Dictionary")
    lastRow = wsInput.Cells(wsInput.Rows.Count, "C").End(xlUp).Row
    outputRow = 2

    ' 기준목록 읽기 (정렬 순서용)
    Dim criteriaList As Object
    Set criteriaList = CreateObject("Scripting.Dictionary")
    Dim critRow As Long, critLastRow As Long
    critLastRow = wsCriteria.Cells(wsCriteria.Rows.Count, "A").End(xlUp).Row
    For critRow = 2 To critLastRow
        criteriaList(Trim(wsCriteria.Cells(critRow, 1).Value)) = critRow
    Next critRow

    ' 메인 데이터 처리
    For i = 3 To lastRow
        processName = Trim(wsInput.Cells(i, 3).Value)  ' C열: 공정명
        remarks = Trim(wsInput.Cells(i, 9).Value)      ' I열: 비고

        If processName <> "" And remarks <> "" Then
            substances = Split(remarks, ";")

            ' 공정명별 사전 초기화
            If Not dictProcess.Exists(processName) Then
                Set dictSubstance = CreateObject("Scripting.Dictionary")
                dictProcess.Add processName, dictSubstance
            Else
                Set dictSubstance = dictProcess(processName)
            End If

            ' 물질 추가 (중복 자동 제거)
            For j = 0 To UBound(substances)
                substance = Trim(substances(j))
                If substance <> "" Then
                    dictSubstance(substance) = 1
                End If
            Next j
        End If
    Next i

    ' 결과 출력
    Dim processKeys() As Variant, substanceKeys() As Variant
    Dim k As Long, m As Long, n As Long
    Dim hasCriteria As Boolean, temp As String
    Dim colorStartIndex As Long, colorLength As Long
    Dim fullText As String

    processKeys = dictProcess.keys

    For k = 0 To UBound(processKeys)
        Set dictSubstance = dictProcess(processKeys(k))
        substanceKeys = dictSubstance.keys
        ReDim sortedList(1 To dictSubstance.Count)
        n = 1

        ' 기준목록에 있는 물질 먼저 정렬
        For m = 2 To critLastRow
            substance = Trim(wsCriteria.Cells(m, 1).Value)
            If dictSubstance.Exists(substance) Then
                sortedList(n) = substance
                n = n + 1
                dictSubstance.Remove substance
            End If
        Next m

        ' 남은 물질 알파벳 정렬
        substanceKeys = dictSubstance.keys
        If UBound(substanceKeys) >= 0 Then
            For m = 0 To UBound(substanceKeys) - 1
                For j = m + 1 To UBound(substanceKeys)
                    If substanceKeys(m) > substanceKeys(j) Then
                        temp = substanceKeys(m)
                        substanceKeys(m) = substanceKeys(j)
                        substanceKeys(j) = temp
                    End If
                Next j
            Next m

            ' 빨간색 처리 시작 위치 기록
            colorStartIndex = 0
            If n > 1 Then
                colorStartIndex = Len(Join(sortedList, ";")) + 1
            End If

            For m = 0 To UBound(substanceKeys)
                sortedList(n) = substanceKeys(m)
                n = n + 1
            Next m
        End If

        ' 시트에 출력
        fullText = Join(sortedList, "; ")
        wsOutput.Cells(outputRow, 1).Value = processKeys(k)
        wsOutput.Cells(outputRow, 2).Value = fullText

        ' 빨간색 글자 적용 (기준목록에 없는 물질만)
        If colorStartIndex > 0 And Len(fullText) > colorStartIndex Then
            colorLength = Len(fullText) - colorStartIndex + 1
            With wsOutput.Cells(outputRow, 2).Characters(Start:=colorStartIndex, Length:=colorLength).Font
                .Color = RGB(255, 0, 0) ' 빨간색
                .Bold = True
            End With
        ElseIf UBound(substanceKeys) >= 0 Then ' 기준목록이 없는 경우 전체 빨간색
            With wsOutput.Cells(outputRow, 2).Font
                .Color = RGB(255, 0, 0)
                .Bold = True
            End With
        End If

        outputRow = outputRow + 1
    Next k

    ' 컬럼 너비 자동 조정
    wsOutput.Columns("A:B").AutoFit

    MsgBox "공정별 측정대상 시트 생성 완료!", vbInformation
End Sub
