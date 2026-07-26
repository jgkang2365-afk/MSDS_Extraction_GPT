Attribute VB_Name = "Module1"
'K열 MSDS 자료 L열에 리스트 정리 및 검토

Sub 리스트정렬()
    Dim wsInput As Worksheet, wsCriteria As Worksheet
    Dim criteriaDict As Object, criteriaList As Variant
    Dim lastRow As Long, rowNum As Long, i As Long, j As Long
    Dim chemicals() As String, processed() As Boolean
    Dim sortedList As Collection, sortedString As String
    Dim currentPosition As Long, item As Variant
    Dim baseName As String, fullName As String, critName As String

    ' 시트 설정
    Set wsInput = ThisWorkbook.Sheets("화학물질입력_양식")
    Set wsCriteria = ThisWorkbook.Sheets("기준목록")

    ' 기준목록 데이터 읽기
    With wsCriteria
        lastRow = .Cells(.Rows.Count, "A").End(xlUp).Row
        criteriaList = .Range("A3:A" & lastRow).Value
    End With

    ' 기준목록 사전 생성 (Key: 화학물질명, Value: 순서)
    Set criteriaDict = CreateObject("Scripting.Dictionary")
    For i = 1 To UBound(criteriaList, 1)
        critName = Trim(criteriaList(i, 1))
        If Not criteriaDict.Exists(critName) Then
            criteriaDict(critName) = i
        End If
    Next i

    ' 입력 시트 처리
    With wsInput
        lastRow = .Cells(.Rows.Count, "D").End(xlUp).Row
        For rowNum = 3 To lastRow
            If .Cells(rowNum, "L").Value <> "" Then
                ' 화학물질 분리
                chemicals = Split(.Cells(rowNum, "L").Value, "; ")
                ReDim processed(0 To UBound(chemicals))

                ' 기준순으로 정렬 (기준목록 순서 우선)
                Set sortedList = New Collection
                For i = 1 To UBound(criteriaList, 1)
                    critName = Trim(criteriaList(i, 1))
                    For j = 0 To UBound(chemicals)
                        If Not processed(j) Then
                            fullName = Trim(chemicals(j))
                            baseName = ExtractBaseName(fullName)
                            ' 기준명과 정확히 일치하는 경우만 처리
                            If baseName = critName Then
                                sortedList.Add fullName
                                processed(j) = True
                                Exit For
                            End If
                        End If
                    Next j
                Next i

                ' 기준외 항목 추가 (원본 순서 유지)
                For j = 0 To UBound(chemicals)
                    If Not processed(j) Then sortedList.Add chemicals(j)
                Next j

                ' ▶▶▶ 수정: L열 → K열로 변경 ◀◀◀
                ' K열에 결과 입력
                sortedString = JoinCollection(sortedList, "; ")
                .Cells(rowNum, "K").Value = sortedString  ' "L" → "K"

                ' 미일치 항목 강조 설정
                currentPosition = 1
                For Each item In Split(sortedString, "; ")
                    Dim currentItem As String
                    currentItem = CStr(item)
                    baseName = ExtractBaseName(currentItem)
                    If Not criteriaDict.Exists(baseName) Then
                        ' ▶▶▶ 수정: L열 → K열로 변경 ◀◀◀
                        With .Cells(rowNum, "K").Characters(currentPosition, Len(currentItem)).Font  ' "L" → "K"
                            .Color = RGB(255, 0, 0)

                        End With
                    End If
                    currentPosition = currentPosition + Len(currentItem) + 2
                Next item
            End If
        Next rowNum
    End With

    MsgBox "기준목록DB를 바탕으로 리스트 정리를 마쳤습니다!" & vbCrLf & vbCrLf & _
           "적색으로 표시 인자는 재검토 바랍니다!"


End Sub

' 화학물질명에서 (*%) 제거 함수 (정확한 기준명 추출)
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

' 컬렉션을 문자열로 변환하는 함수
Function JoinCollection(col As Collection, delimiter As String) As String
    Dim result As String
    For Each item In col
        result = result & item & delimiter
    Next item
    If Len(result) > 0 Then result = Left(result, Len(result) - Len(delimiter))
    JoinCollection = result
End Function
