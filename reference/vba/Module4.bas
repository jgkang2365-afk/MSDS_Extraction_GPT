Attribute VB_Name = "Module4"
Sub I열_퍼센트제거()
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

    ' 기준목록 데이터 읽기 (A3부터 끝까지)
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

    ' 입력 시트 처리 (I열 기준)
    With wsInput
        ' I열 마지막 행 찾기
        lastRow = .Cells(.Rows.Count, "I").End(xlUp).Row

        ' I3부터 처리
        For rowNum = 3 To lastRow
            If .Cells(rowNum, "I").Value <> "" Then
                ' I열 데이터 분리
                chemicals = Split(.Cells(rowNum, "I").Value, "; ")
                ReDim processed(0 To UBound(chemicals))

                ' 기준목록 순서로 정렬
                Set sortedList = New Collection
                For i = 1 To UBound(criteriaList, 1)
                    critName = Trim(criteriaList(i, 1))
                    For j = 0 To UBound(chemicals)
                        If Not processed(j) Then
                            fullName = Trim(chemicals(j))
                            baseName = ExtractBaseName(fullName)
                            If baseName = critName Then
                                sortedList.Add fullName
                                processed(j) = True
                                Exit For
                            End If
                        End If
                    Next j
                Next i

                ' 기준목록에 없는 항목 추가 (원본 순서 유지)
                For j = 0 To UBound(chemicals)
                    If Not processed(j) Then sortedList.Add chemicals(j)
                Next j

                ' I열에 재정렬된 데이터 입력
                sortedString = JoinCollection(sortedList, "; ")
                .Cells(rowNum, "I").Value = sortedString

                ' 미일치 항목 강조 (빨간색)
                currentPosition = 1
                For Each item In Split(sortedString, "; ")
                    Dim currentItem As String
                    currentItem = CStr(item)
                    baseName = ExtractBaseName(currentItem)
                    If Not criteriaDict.Exists(baseName) Then
                        With .Cells(rowNum, "I").Characters(currentPosition, Len(currentItem)).Font
                            .Color = RGB(255, 0, 0)
                        End With
                    End If
                    currentPosition = currentPosition + Len(currentItem) + 2
                Next item
            End If
        Next rowNum
    End With

    MsgBox "%제거 완료!", vbInformation
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

' 컬렉션을 문자열로 변환
Function JoinCollection(col As Collection, delimiter As String) As String
    Dim result As String
    For Each item In col
        result = result & item & delimiter
    Next item
    If Len(result) > 0 Then result = Left(result, Len(result) - Len(delimiter))
    JoinCollection = result
End Function
