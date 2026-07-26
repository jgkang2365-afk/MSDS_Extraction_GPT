Attribute VB_Name = "Module5"
Sub 비고검토()

    Dim wsInput As Worksheet
    Dim wsMaster As Worksheet
    Dim lastRowInput As Long
    Dim lastRowMaster As Long
    Dim i As Long, j As Long
    Dim masterData As Object
    Dim specialHazards As Variant
    Dim cellValue As String
    Dim sortedValue As String

    ' 시트 설정
    Set wsInput = ThisWorkbook.Sheets("화학물질입력_양식")
    Set wsMaster = ThisWorkbook.Sheets("통합 유해인자 자료")

    ' 마지막 행 찾기
    lastRowInput = wsInput.Cells(wsInput.Rows.Count, "I").End(xlUp).Row
    lastRowMaster = wsMaster.Cells(wsMaster.Rows.Count, "C").End(xlUp).Row

    ' '통합 유해인자 자료' 시트의 C열 데이터를 Dictionary에 로드 (검색 속도 향상)
    Set masterData = CreateObject("Scripting.Dictionary")
    For i = 3 To lastRowMaster
        masterData(wsMaster.Cells(i, "C").Value) = True
    Next i

    ' 파란색으로 강조할 특별 유해인자 목록 설정 (오타 수정됨)
    specialHazards = Array( _
        "1,2-디클로로프로판", "2-메톡시에틸아세테이트", "벤젠", "사염화탄소", "1,2-에폭시프로판", _
        "에피클로로히드린", "트리클로로에틸렌", "1,2,3-트리클로로프로판", "퍼클로로에틸렌", "2-메톡시에탄올", _
        "2-에톡시에탄올", "2-에톡시에틸아세테이트", "1-브로모프로판", "2-브로모프로판", "N,N-디메틸아세트아미드", _
        "디메틸포름아미드", "페놀", "스토다드솔벤트", "1,2-디클로로에탄", "황산디메틸", "1,3-부타디엔", _
        "아크릴로니트릴", "2,3-에폭시-1-프로판올", "디니트로톨루엔", "에틸렌이민", "프로필렌이민", "포름알데히드", _
        "아크릴아미드", "히드라진", "납", "납 및 그 무기화합물", "크롬산연(as Pb)", "니켈(불용성)", "삼산화안티몬", _
        "카드뮴", "6가크롬", "크롬산연(as Cr)", "수은", "황산(pH2.0이하)", "산화에틸렌", "베릴륨", "비소", _
        "나프틸아민", "벤조트리클로라이드", "염화비닐", "디아니시딘", "디클로로벤지딘", "톨리딘", "크롬광 가공", _
        "황화니켈", "크롬산아연", "콜타르피치" _
    )

    ' '화학물질입력_양식' 시트의 I열을 순회
    For i = 3 To lastRowInput
        With wsInput.Cells(i, "I")
            cellValue = Trim(.Value)
            .Interior.ColorIndex = xlNone ' 셀 배경색 초기화

            If cellValue = "" Then GoTo NextCell

            ' --- 정렬 로직 시작 ---
            Dim mainPart As String ' 괄호 앞의 주된 부분 (예: 특별관리물질, 허용소비량 미만)
            Dim bracketContent As String ' 괄호 안의 내용 (정렬 대상)
            Dim bracketType As String ' 괄호의 종류 ("square", "round", "")
            Dim isMultiHazardListInBracket As Boolean ' 괄호 안에 여러 유해인자 목록이 있는지 여부

            isMultiHazardListInBracket = False ' 초기값

            Dim firstOpenBracket As Long: firstOpenBracket = InStr(cellValue, "[")
            Dim firstCloseBracket As Long: firstCloseBracket = InStr(cellValue, "]")
            Dim firstOpenParen As Long: firstOpenParen = InStr(cellValue, "(")
            Dim firstCloseParen As Long: firstCloseParen = InStr(cellValue, ")")

            ' 1. 대괄호 안에 여러 유해인자가 있는 경우 (예: 특별관리물질[A; B])
            If firstOpenBracket > 0 And firstCloseBracket > firstOpenBracket Then
                Dim contentInsideSquare As String
                contentInsideSquare = Mid(cellValue, firstOpenBracket + 1, firstCloseBracket - firstOpenBracket - 1)
                If InStr(contentInsideSquare, ";") > 0 Then ' 괄호 안에 세미콜론이 있다면 목록으로 간주
                    mainPart = Trim(Left(cellValue, firstOpenBracket - 1))
                    bracketContent = contentInsideSquare
                    bracketType = "square"
                    isMultiHazardListInBracket = True
                End If
            End If

            ' 2. 소괄호 안에 여러 유해인자가 있는 경우 (예: 허용소비량 미만(A; B))
            If Not isMultiHazardListInBracket And firstOpenParen > 0 And firstCloseParen > firstOpenParen Then
                Dim contentInsideParen As String
                contentInsideParen = Mid(cellValue, firstOpenParen + 1, firstCloseParen - firstOpenParen - 1)
                If InStr(contentInsideParen, ";") > 0 Then ' 괄호 안에 세미콜론이 있다면 목록으로 간주
                    mainPart = Trim(Left(cellValue, firstOpenParen - 1))
                    bracketContent = contentInsideParen
                    bracketType = "round"
                    isMultiHazardListInBracket = True
                End If
            End If

            ' 3. 괄호는 없지만 세미콜론으로 구분된 경우 (예: 톨루엔; 크실렌)
            If Not isMultiHazardListInBracket Then
                If InStr(cellValue, ";") > 0 Then
                    mainPart = "" ' 괄호 밖 메인 파트 없음
                    bracketContent = cellValue ' 전체 셀 값이 정렬할 내용
                    bracketType = "" ' 특정 괄호 타입 없음
                    isMultiHazardListInBracket = True
                Else ' 4. 단일 값 (괄호도 세미콜론도 없음) 또는 단일 값(설명) (예: 비대상, 산화철(분진, 흄))
                    mainPart = cellValue ' 전체 셀 값이 단일 항목
                    bracketContent = "" ' 정렬할 내용 없음
                    bracketType = ""
                    isMultiHazardListInBracket = False ' 명시적으로 단일 항목으로 설정
                End If
            End If

            ' bracketContent가 비어있지 않은 경우에만 정렬 로직 실행 (즉, isMultiHazardListInBracket가 True인 경우)
            If isMultiHazardListInBracket Then
                ' SortHazardList 함수를 사용하여 괄호 안의 내용을 정렬
                Dim sortedBracketContent As String
                sortedBracketContent = SortHazardList(bracketContent, masterData)

                ' 정렬된 값을 원래의 괄호 타입에 맞춰 재조합
                If bracketType = "square" Then
                    sortedValue = mainPart & "[" & sortedBracketContent & "]"
                ElseIf bracketType = "round" Then
                    sortedValue = mainPart & "(" & sortedBracketContent & ")"
                Else ' 괄호가 없었던 경우, 정렬된 내용만으로 구성
                    sortedValue = sortedBracketContent
                End If

                .Value = sortedValue ' 정렬된 값으로 셀 업데이트
            Else
                ' isMultiHazardListInBracket가 False인 경우 (단일 항목), 값은 그대로 유지
                sortedValue = cellValue
                .Value = sortedValue
            End If
            ' --- 정렬 로직 끝 ---


            ' --- 색상 강조 로직 시작 (정렬된 값 기준으로 다시 파싱) ---
            Dim currentCellValue As String
            currentCellValue = Trim(.Value)
            .Font.Color = RGB(0, 0, 0) ' 셀 전체 글꼴 색상 초기화 (검정)

            Dim partsToHighlight As Variant ' 강조 처리를 할 개별 유해인자 부분들 (Split 결과)
            Dim highlightContentStartOffset As Long ' 셀 내에서 강조 시작 위치의 오프셋
            Dim currentPartOffsetInCell As Long ' 셀 내에서 현재 파트의 시작 위치

            ' 강조할 내용의 시작 위치와 분리된 파트들 결정
            If isMultiHazardListInBracket Then ' 여러 유해인자 목록인 경우
                If bracketType = "square" Then
                    highlightContentStartOffset = InStr(currentCellValue, "[") + 1
                    partsToHighlight = Split(Mid(currentCellValue, highlightContentStartOffset, InStr(currentCellValue, "]") - highlightContentStartOffset), "; ")
                ElseIf bracketType = "round" Then
                    highlightContentStartOffset = InStr(currentCellValue, "(") + 1
                    partsToHighlight = Split(Mid(currentCellValue, highlightContentStartOffset, InStr(currentCellValue, ")") - highlightContentStartOffset), "; ")
                Else ' 세미콜론으로 구분되었지만 괄호가 없는 경우
                    highlightContentStartOffset = 1
                    partsToHighlight = Split(currentCellValue, "; ")
                End If
            Else ' 단일 항목 (세미colon 없음, 괄호가 있어도 설명용)
                highlightContentStartOffset = 1
                ReDim partsToHighlight(0 To 0)
                partsToHighlight(0) = currentCellValue
            End If

            currentPartOffsetInCell = highlightContentStartOffset ' 첫 파트의 시작 오프셋

            For Each partToHighlight In partsToHighlight
                If Trim(partToHighlight) = "" Then ' 빈 파트는 건너뛰기
                    currentPartOffsetInCell = currentPartOffsetInCell + Len(partToHighlight) + 2 ' "; "의 길이 2
                    GoTo NextPartToHighlightLoop
                End If

                Dim baseNameForLookup As String     ' 마스터 데이터/정렬에 사용될 이름
                Dim highlightableName As String     ' 실제 강조될 이름 부분 (예: "산화철", "6가크롬")
                Dim descriptionPart As String       ' 괄호 안의 설명 부분 (예: "(분진, 흄)")
                Dim highlightableNameRelativeStart As Long ' partToHighlight 내에서 강조될 이름의 시작 위치
                Dim highlightableNameRelativeLength As Long ' partToHighlight 내에서 강조될 이름의 길이
                Dim descriptionPartRelativeStart As Long ' partToHighlight 내에서 설명 부분의 시작 위치
                Dim descriptionPartRelativeLength As Long ' partToHighlight 내에서 설명 부분의 길이
                Dim hasValidHighlightableName As Boolean ' highlightableName이 유효한지 여부

                ' GetHazardNames 함수를 사용하여 이름 및 설명 부분 추출
                hasValidHighlightableName = GetHazardNames(partToHighlight, baseNameForLookup, highlightableName, descriptionPart, _
                                                           highlightableNameRelativeStart, highlightableNameRelativeLength, _
                                                           descriptionPartRelativeStart, descriptionPartRelativeLength)

                Dim colorToApply As Long
                colorToApply = RGB(0, 0, 0) ' 기본은 검정

                ' 새로운 로직: partToHighlight 전체가 specialHazards에 정확히 일치하는지 확인
                Dim isExactSpecialHazardMatch As Boolean
                isExactSpecialHazardMatch = False
                For Each specialHazard In specialHazards
                    If StrComp(Trim(partToHighlight), Trim(specialHazard), vbTextCompare) = 0 Then
                        isExactSpecialHazardMatch = True
                        Exit For
                    End If
                Next specialHazard

                If isExactSpecialHazardMatch Then
                    ' partToHighlight 전체가 specialHazards 목록에 정확히 일치하면 전체를 파란색으로 강조
                    .Characters(Start:=currentPartOffsetInCell, Length:=Len(partToHighlight)).Font.Color = RGB(0, 0, 255)
                ElseIf hasValidHighlightableName Then ' 유효한 강조 가능 이름이 있는 경우에만 기존 색상 로직 적용
                    Dim isSpecialHazard As Boolean
                    isSpecialHazard = False
                    For Each specialHazard In specialHazards
                        If StrComp(highlightableName, Trim(specialHazard), vbTextCompare) = 0 Then
                            isSpecialHazard = True
                            Exit For
                        End If
                    Next specialHazard

                    Dim isInMasterData As Boolean
                    isInMasterData = masterData.Exists(baseNameForLookup) ' baseNameForLookup 사용

                    If isSpecialHazard Then
                        colorToApply = RGB(0, 0, 255) ' 파란색
                    ElseIf Not isInMasterData Then
                        colorToApply = RGB(255, 0, 0) ' 적색
                    Else ' isInMasterData is True and not isSpecialHazard
                        colorToApply = RGB(0, 0, 0) ' 기본 검정
                    End If

                    ' 기본 유해인자 이름 부분에 색상 적용
                    If highlightableNameRelativeLength > 0 Then
                        .Characters(Start:=currentPartOffsetInCell + highlightableNameRelativeStart - 1, Length:=highlightableNameRelativeLength).Font.Color = colorToApply
                    End If

                    ' 설명 부분에 검정색 적용 (강조되지 않도록)
                    If descriptionPartRelativeLength > 0 Then
                        .Characters(Start:=currentPartOffsetInCell + descriptionPartRelativeStart - 1, Length:=descriptionPartRelativeLength).Font.Color = RGB(0, 0, 0)
                    End If
                Else ' highlightableName이 없는 경우 (예: "(분진, 흄)" 자체)
                    ' 전체를 검정색으로 강조하지 않음
                    .Characters(Start:=currentPartOffsetInCell, Length:=Len(partToHighlight)).Font.Color = RGB(0, 0, 0)
                End If

                ' 다음 파트의 시작 위치 업데이트 (현재 파트 길이 + "; " 길이)
                currentPartOffsetInCell = currentPartOffsetInCell + Len(partToHighlight) + 2
NextPartToHighlightLoop:
            Next partToHighlight
            ' --- 색상 강조 로직 끝 ---

        End With
NextCell:
    Next i

    ' 텍스트 맞춤 설정
    With wsInput.Range("I3:J" & lastRowInput)
        .HorizontalAlignment = xlCenter
        .VerticalAlignment = xlCenter
        .WrapText = False
        .ShrinkToFit = True
    End With

    MsgBox "정렬 및 색상 강조가 완료되었습니다.", vbInformation

End Sub

' Helper Function to extract base name for lookup/sorting and highlightable name/description for highlighting.
' fullHazardString: The complete hazard string (e.g., "산화철(분진, 흄)", "6가크롬(불용성)", "톨루엔").
' baseNameForLookup: The string to be used for checking against masterData and for sorting.
'                    For "산화철(분진, 흄)", this will be "산화철(분진, 흄)".
'                    For "6가크롬(불용성)", this will be "6가크롬(불용성)".
'                    For "톨루엔", this will be "톨루엔".
'                    For "특별관리물질[납]", this will be "납".
' highlightableName: The part of the string that should be highlighted (the actual chemical name).
'                    For "산화철(분진, 흄)", this will be "산화철".
'                    For "6가크롬(불용성)", this will be "6가크롬".
'                    For "톨루엔", this will be "톨루엔".
'                    For "특별관리물질[납]", this will be "납".
' descriptionPart: The descriptive part in parentheses/brackets (e.g., "(분진, 흄)", "(불용성)"). This will always be black.
' highlightableNameRelativeStart: Start position of highlightableName within fullHazardString (1-based).
' highlightableNameRelativeLength: Length of highlightableName.
' descriptionPartRelativeStart: Start position of descriptionPart within fullHazardString (1-based).
' descriptionPartRelativeLength: Length of descriptionPart.
' Returns True if a valid highlightableName was extracted, False if it's purely a description like "(분진, 흄)".
Private Function GetHazardNames(ByVal fullHazardString As String, _
                                ByRef baseNameForLookup As String, _
                                ByRef highlightableName As String, _
                                ByRef descriptionPart As String, _
                                ByRef highlightableNameRelativeStart As Long, _
                                ByRef highlightableNameRelativeLength As Long, _
                                ByRef descriptionPartRelativeStart As Long, _
                                ByRef descriptionPartRelativeLength As Long) As Boolean

    ' Initialize all output parameters
    baseNameForLookup = Trim(fullHazardString)
    highlightableName = Trim(fullHazardString)
    descriptionPart = ""
    highlightableNameRelativeStart = 1
    highlightableNameRelativeLength = Len(fullHazardString)
    descriptionPartRelativeStart = 0
    descriptionPartRelativeLength = 0
    GetHazardNames = True ' Assume highlightable initially

    Dim openParenPos As Long: openParenPos = InStr(fullHazardString, "(")
    Dim closeParenPos As Long: closeParenPos = InStr(fullHazardString, ")")
    Dim openBracketPos As Long: openBracketPos = InStr(fullHazardString, "[")
    Dim closeBracketPos As Long: closeBracketPos = InStr(fullHazardString, "]")

    Dim innermostOpenPos As Long
    Dim innermostClosePos As Long
    Dim innermostContent As String
    Dim prefixPart As String

    ' Find the innermost bracket/parentheses pair
    ' Prioritize parentheses if they are the innermost
    If openParenPos > 0 And closeParenPos > openParenPos Then
        innermostOpenPos = InStrRev(fullHazardString, "(", closeParenPos)
        innermostClosePos = closeParenPos
    End If
    ' Check if brackets are innermost or if no parentheses were found
    If openBracketPos > 0 And closeBracketPos > openBracketPos Then
        If innermostOpenPos = 0 Or openBracketPos > innermostOpenPos Then ' Brackets are innermost or only pair
            innermostOpenPos = InStrRev(fullHazardString, "[", closeBracketPos)
            innermostClosePos = closeBracketPos
        End If
    End If

    ' If an innermost pair is found
    If innermostOpenPos > 0 And innermostClosePos > innermostOpenPos Then
        innermostContent = Mid(fullHazardString, innermostOpenPos + 1, innermostClosePos - innermostOpenPos - 1)

        If innermostOpenPos > 1 Then
            prefixPart = Trim(Left(fullHazardString, innermostOpenPos - 1))
        Else
            prefixPart = ""
        End If

        ' Case A: Content inside contains a semicolon (e.g., "Category[Hazard1; Hazard2]")
        ' This means the prefix is the actual hazard name for lookup/highlighting, and the bracketed part is a complex description.
        If InStr(innermostContent, ";") > 0 Then
            baseNameForLookup = prefixPart
            highlightableName = prefixPart
            descriptionPart = Mid(fullHazardString, innermostOpenPos)
            highlightableNameRelativeStart = 1
            highlightableNameRelativeLength = Len(prefixPart)
            descriptionPartRelativeStart = innermostOpenPos
            descriptionPartRelativeLength = Len(descriptionPart)
            GetHazardNames = True ' Prefix is highlightable

        ' Case B: Content inside does NOT contain a semicolon (e.g., "HazardName(Description)" or "Category[SingleHazard]")
        Else
            ' Check if the prefixPart is a known "category" that implies the inner content is the hazard
            Dim isCategoryPrefix As Boolean
            isCategoryPrefix = False
            If InStr(prefixPart, "특별관리물질") > 0 Or _
               InStr(prefixPart, "단시간 및 임시작업") > 0 Or _
               InStr(prefixPart, "허용소비량 미만") > 0 Then
               isCategoryPrefix = True
            End If

            If isCategoryPrefix Then
                ' Pattern: Category[SingleHazard] or Category(SingleHazard)
                ' The *inner content* is the actual hazard.
                ' Example: "특별관리물질[납]", "허용소비량 미만(벤젠(pH2.0이하))"

                ' Recursively call GetHazardNames for the content inside to handle potential nested descriptions
                Dim innerBaseNameForLookup As String
                Dim innerHighlightableName As String
                Dim innerDescriptionPart As String
                Dim innerHighlightableNameRelativeStart As Long
                Dim innerHighlightableNameRelativeLength As Long
                Dim innerDescriptionPartRelativeStart As Long
                Dim innerDescriptionPartRelativeLength As Long

                Dim innerResult As Boolean
                innerResult = GetHazardNames(innermostContent, innerBaseNameForLookup, innerHighlightableName, innerDescriptionPart, _
                                             innerHighlightableNameRelativeStart, innerHighlightableNameRelativeLength, _
                                             innerDescriptionPartRelativeStart, innerDescriptionPartRelativeLength)

                baseNameForLookup = innerBaseNameForLookup
                highlightableName = innerHighlightableName
                descriptionPart = innerDescriptionPart ' This will be empty or a description from inner call
                GetHazardNames = innerResult ' Pass through the highlightable status from inner call

                ' Adjust positions relative to the fullHazardString
                highlightableNameRelativeStart = innermostOpenPos + innerHighlightableNameRelativeStart
                highlightableNameRelativeLength = innerHighlightableNameRelativeLength
                If innerDescriptionPartRelativeLength > 0 Then
                    descriptionPartRelativeStart = innermostOpenPos + innerDescriptionPartRelativeStart
                    descriptionPartRelativeLength = innerDescriptionPartRelativeLength
                End If

                ' The outer prefix and brackets are NOT part of highlightableName or descriptionPart.
                ' They will be colored black by default by the main loop's initial coloring.

            Else
                ' Pattern: HazardName(Description) or HazardName[Description]
                ' The prefix is the highlightable name, and the bracketed part is the description.
                ' Example: "산화철(분진, 흄)", "니켈(불용성)"
                baseNameForLookup = Trim(fullHazardString) ' Full string for lookup
                highlightableName = prefixPart ' Part before paren/bracket for highlighting
                descriptionPart = Mid(fullHazardString, innermostOpenPos) ' The paren/bracket part is description

                highlightableNameRelativeStart = 1
                highlightableNameRelativeLength = Len(prefixPart)
                descriptionPartRelativeStart = innermostOpenPos
                descriptionPartRelativeLength = Len(descriptionPart)
                GetHazardNames = True ' Prefix is highlightable
            End If
        End If
    End If
End Function


' Helper Function to sort a semicolon-separated list of hazards
Private Function SortHazardList(ByVal hazardListString As String, _
                                 ByVal masterData As Object) As String
    Dim partsToProcess() As String
    partsToProcess = Split(hazardListString, "; ")

    Dim tempHazardMap As Object ' BaseNameForLookup -> OriginalFullHazardString
    Set tempHazardMap = CreateObject("Scripting.Dictionary")

    Dim sortedBaseNames As Collection
    Set sortedBaseNames = New Collection

    Dim processedTempBaseNames As Object ' To track which base names have been added to sortedBaseNames
    Set processedTempBaseNames = CreateObject("Scripting.Dictionary")

    Dim part As Variant
    Dim baseNameForLookup As String
    Dim highlightableName As String ' Not used for sorting, but required by GetHazardNames
    Dim descriptionPart As String ' Not used for sorting, but required by GetHazardNames
    Dim dummyStart As Long, dummyLen As Long ' Dummy variables for GetHazardNames

    ' Populate tempHazardMap with base names for lookup and original full hazard strings
    For Each part In partsToProcess
        ' Use the helper function to get the base name for sorting
        ' This baseNameForLookup will be the full string including description if no semicolon inside parens/brackets
        Call GetHazardNames(part, baseNameForLookup, highlightableName, descriptionPart, _
                            dummyStart, dummyLen, dummyStart, dummyLen) ' Pass dummy variables for positions

        If baseNameForLookup <> "" Then
            ' If baseNameForLookup is extracted, use it as key
            ' If multiple items have the same baseNameForLookup, the last one will overwrite.
            tempHazardMap(baseNameForLookup) = part
        Else
            ' If no baseNameForLookup (e.g., "(분진, 흄)"), use a unique key to store the original part
            tempHazardMap("NO_BASE_NAME_" & part & "_" & Timer) = part
        End If
    Next part

    ' Sort based on masterData
    Dim masterValue As Variant
    For Each masterValue In masterData.keys ' Iterate through masterData keys directly
        If tempHazardMap.Exists(masterValue) Then
            If Not processedTempBaseNames.Exists(masterValue) Then
                sortedBaseNames.Add masterValue
                processedTempBaseNames(masterValue) = True
            End If
        End If
    Next masterValue

    ' Add any remaining items (not in masterData) to the end
    For Each tempBaseName In tempHazardMap.keys
        If Not processedTempBaseNames.Exists(tempBaseName) Then
            sortedBaseNames.Add tempBaseName
        End If
    Next tempBaseName

    ' Reconstruct the sorted list using original full hazard strings
    Dim sortedPartsArray() As String
    ReDim sortedPartsArray(1 To sortedBaseNames.Count)
    Dim idx As Long
    idx = 1
    For Each tempBaseName In sortedBaseNames
        sortedPartsArray(idx) = tempHazardMap(tempBaseName)
        idx = idx + 1
    Next tempBaseName

    SortHazardList = Join(sortedPartsArray, "; ")
End Function
