Attribute VB_Name = "Module6"
'K열 값을 J열에 그대로 복사, I열엔 (*%) 제거한 후 복사
Sub ProcessMColumnData()
    Dim ws As Worksheet
    Dim lastRow As Long, i As Long, j As Long
    Dim chemicals() As String, cleanedItems() As String
    Dim originalString As String, cleanedString As String

    ' 작업 시트 설정
    Set ws = ThisWorkbook.Sheets("화학물질입력_양식")

    With ws
        ' K열 마지막 행 찾기
        lastRow = .Cells(.Rows.Count, "L").End(xlUp).Row

        ' K3부터 K열 끝까지 반복
        For i = 3 To lastRow
            If .Cells(i, "K").Value <> "" Then
                ' 원본 데이터 읽기 (K열)
                originalString = .Cells(i, "K").Value

                ' ▶▶▶ J열: L열 값을 그대로 복사 ◀◀◀
                .Cells(i, "J").Value = originalString

                ' ▶▶▶ I열: (*%) 제거 ◀◀◀
                chemicals = Split(originalString, "; ")
                ReDim cleanedItems(0 To UBound(chemicals))

                For j = 0 To UBound(chemicals)
                    cleanedItems(j) = ExtractBaseName(Trim(chemicals(j)))
                Next j

                cleanedString = Join(cleanedItems, "; ")
                .Cells(i, "I").Value = cleanedString
            End If
        Next i
    End With

    MsgBox "MSDS 편집 셀 값을 비고와 MSDS에 복사하고, MSDS 값을 % 값을 제거 했습니다."

End Sub

' (*%) 제거 함수
Function ExtractBaseName(ByVal fullName As String) As String
    Dim pos As Long
    pos = InStrRev(fullName, "(")
    If pos > 0 Then
        If InStr(Mid(fullName, pos), "%") > 0 Or InStr(Mid(fullName, pos), "미만") > 0 Then
            ExtractBaseName = Trim(Left(fullName, pos - 1))
            Exit Function
        End If
    End If
    ExtractBaseName = Trim(fullName)
End Function
