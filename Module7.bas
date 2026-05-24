Attribute VB_Name = "Module7"
' 모듈 레벨에 함수 정의
Function ProcessSpecialPatterns(inputText As String) As String
    Dim result As String
    result = inputText
    
    ' 정규식을 이용한 패턴 처리 (성능 개선 및 패턴 강화)
    Dim regEx As Object
    Set regEx = CreateObject("VBScript.RegExp")
    regEx.Global = True
    ' 괄호([]) 내부의 세미콜론이 쪼개지지 않도록 보호할 패턴 정의 (중첩 괄호 1단계 지원)
    regEx.Pattern = "((단시간 및 임시작업|보관|허용소비량 미만|특별관리물질)(\[[^\]]+\]|\([^()]*(?:\([^()]*\)[^()]*)*\)))"
    
    Dim matches As Object, match As Object
    Set matches = regEx.Execute(result)
    
    ' 뒤에서부터 처리하여 인덱스 유지
    Dim i As Long
    For i = matches.Count - 1 To 0 Step -1
        Set match = matches(i)
        Dim fullMatch As String
        fullMatch = match.Value
        
        ' 괄호 시작/끝 위치 찾기 (먼저 나오는 괄호를 기준으로 짝을 맞춤)
        Dim firstParen As Long, firstBracket As Long
        firstParen = InStr(1, fullMatch, "(")
        firstBracket = InStr(1, fullMatch, "[")
        
        Dim openPos As Long, closePos As Long
        If firstParen > 0 And (firstBracket = 0 Or firstParen < firstBracket) Then
            openPos = firstParen
            closePos = InStrRev(fullMatch, ")")
        ElseIf firstBracket > 0 Then
            openPos = firstBracket
            closePos = InStrRev(fullMatch, "]")
        Else
            openPos = 0
            closePos = 0
        End If
        
        If openPos > 0 And closePos > openPos Then
            Dim innerContent As String
            Dim prefix As String, suffix As String
            prefix = Left(fullMatch, openPos)
            suffix = Mid(fullMatch, closePos)
            innerContent = Mid(fullMatch, openPos + 1, closePos - openPos - 1)
            
            ' 내부 세미콜론을 임시 식별자로 치환하여 Split 방지
            innerContent = Replace(innerContent, ";", "|SEMICOLON|")
            
            Dim newStr As String
            newStr = prefix & innerContent & suffix
            
            ' 원본 문자열 대체
            result = Left(result, match.FirstIndex) & newStr & Mid(result, match.FirstIndex + Len(fullMatch) + 1)
        End If
    Next i
    
    ProcessSpecialPatterns = result
End Function

' 예외 항목(단시간, 보관 등)을 카테고리별로 그룹화하고 중복을 제거하는 함수
Function FormatGroupedChems(chemList As String) As String
    If Trim(chemList) = "" Then
        FormatGroupedChems = "-"
        Exit Function
    End If

    Dim dictGroups As Object
    Set dictGroups = CreateObject("Scripting.Dictionary")
    
    ' 세미콜론 보호하기 (괄호 내부의 세미콜론을 임시 문자로 치환하여 Split 방지)
    Dim protectedList As String
    protectedList = chemList
    
    Dim inParen As Integer, inBracket As Integer
    Dim ch As String, k As Integer
    For k = 1 To Len(protectedList)
        ch = Mid(protectedList, k, 1)
        If ch = "(" Then inParen = inParen + 1
        If ch = ")" Then inParen = inParen - 1
        If ch = "[" Then inBracket = inBracket + 1
        If ch = "]" Then inBracket = inBracket - 1
        
        ' 괄호가 열려있는 동안 등장하는 세미콜론은 Chr(1)로 일시 치환
        If (inParen > 0 Or inBracket > 0) And ch = ";" Then
            Mid(protectedList, k, 1) = Chr(1)
        End If
    Next k

    Dim arrItems() As String
    arrItems = Split(protectedList, ";")
    
    Dim i As Integer, item As String
    Dim category As String, content As String
    
    For i = LBound(arrItems) To UBound(arrItems)
        ' 임시 문자 복원
        item = Trim(Replace(arrItems(i), Chr(1), ";"))
        If item <> "" Then
            ' 카테고리와 내용 추출 시도 - 가장 먼저 열리는 괄호 기준
            Dim firstParen As Long, firstBracket As Long
            firstParen = InStr(1, item, "(")
            firstBracket = InStr(1, item, "[")
            
            Dim openPos As Long, closePos As Long
            If firstParen > 0 And (firstBracket = 0 Or firstParen < firstBracket) Then
                openPos = firstParen
                closePos = InStrRev(item, ")")
            ElseIf firstBracket > 0 Then
                openPos = firstBracket
                closePos = InStrRev(item, "]")
            Else
                openPos = 0
                closePos = 0
            End If
            
            If openPos > 0 Then
                category = Trim(Left(item, openPos - 1))
                If closePos > openPos Then
                    content = Mid(item, openPos + 1, closePos - openPos - 1)
                Else
                    content = Mid(item, openPos + 1)
                End If
                
                ' 카테고리별로 물질명 모으기 (중복 제거 포함)
                If Not dictGroups.Exists(category) Then
                    Set dictGroups(category) = CreateObject("Scripting.Dictionary")
                End If
                
                ' 내부 물질이 또 세미콜론으로 나뉘어 있을 수 있음
                Dim subChems() As String, sc As Variant
                subChems = Split(content, ";")
                For Each sc In subChems
                    If Trim(sc) <> "" Then
                        If Not dictGroups(category).Exists(Trim(sc)) Then
                            dictGroups(category).Add Trim(sc), 1
                        End If
                    End If
                Next sc
            Else
                ' 카테고리 형식이 아닌 일반 물질
                If Not dictGroups.Exists("기타") Then
                    Set dictGroups("기타") = CreateObject("Scripting.Dictionary")
                End If
                If Not dictGroups("기타").Exists(item) Then
                    dictGroups("기타").Add item, 1
                End If
            End If
        End If
    Next i
    
    ' 결과 문자열 조립
    Dim result As String, catKey As Variant
    result = ""
    
    For Each catKey In dictGroups.keys
        Dim chems As String
        chems = Join(dictGroups(catKey).keys, "; ")
        
        If catKey = "기타" Then
            result = result & chems & "; "
        Else
            result = result & catKey & "(" & chems & "); "
        End If
    Next catKey
    
    If Len(result) > 2 Then
        result = Left(result, Len(result) - 2)
    End If
    
    FormatGroupedChems = result
End Function

Sub 측정계획자동화()
    On Error GoTo ErrorHandler
    Dim startTime As Double
    startTime = Timer
    
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual
    Application.EnableEvents = False
    
    ' 변수 선언
    Dim wsSource As Worksheet, wsInput As Worksheet, wsOutput As Worksheet
    Dim dictMethod As Object, dictProcess As Object, dictOrder As Object, dictMissing As Object
    Dim dictLValue As Object, dictEValue As Object
    Dim lastRow As Long, r As Long, c As Long, m As Long, idx As Long
    Dim processName As String, chemName As String, method As String
    Dim chemList As String, arrChems() As String
    Dim outputRow As Long, key As Variant, subKey As Variant
    Dim chemCount As Integer, newMethod As String
    Dim chem As Variant, chemDict As Object, methodGroup As Object
    Dim orderA As Long, orderB As Long, tmp As String
    Dim isSingleMethod As Boolean, hasMissing As Boolean
    Dim tempList As String
    Dim priorityA As Long, priorityB As Long
    Dim methodPriority As Object
    Dim sourceData As Variant, inputData As Variant
    
    ' 시트 설정
    Set wsSource = ThisWorkbook.Sheets("통합 유해인자 자료")
    Set wsInput = ThisWorkbook.Sheets("화학물질입력_양식")
    Set wsOutput = ThisWorkbook.Sheets("측정계획(양식)")
    
    ' 기존 출력 데이터 삭제
    With wsOutput
        lastRow = .Cells(.Rows.Count, "B").End(xlUp).Row
        If lastRow < 4 Then lastRow = 4 ' 최소 4행부터 시작
        .Range("B4:C" & lastRow).ClearContents
        .Range("I4:K" & lastRow).ClearContents
        .Range("B4:K" & lastRow).Font.Color = RGB(0, 0, 0)
    End With
    
    ' 1. 배열을 이용한 데이터 읽기 (성능 개선)
    ' 통합 유해인자 자료 처리
    Set dictMethod = CreateObject("Scripting.Dictionary")
    Set dictOrder = CreateObject("Scripting.Dictionary")
    Set dictLValue = CreateObject("Scripting.Dictionary")
    Set dictEValue = CreateObject("Scripting.Dictionary")
    
    With wsSource
        lastRow = .Cells(.Rows.Count, "C").End(xlUp).Row
        If lastRow < 2 Then GoTo NoData
        sourceData = .Range("A2:L" & lastRow).Value
    End With
    
    For r = LBound(sourceData, 1) To UBound(sourceData, 1)
        chemName = Trim(sourceData(r, 3))   ' C열
        method = Trim(sourceData(r, 9))     ' I열
        If chemName <> "" And method <> "" Then
            If Not dictMethod.Exists(chemName) Then
                dictMethod.Add chemName, method
                dictOrder.Add chemName, r
                dictLValue.Add chemName, Trim(sourceData(r, 12)) ' L열
                dictEValue.Add chemName, Trim(sourceData(r, 5))  ' E열
            End If
        End If
    Next r
    
    ' 2. 화학물질 입력 데이터 처리 (배열 사용)
    Set dictProcess = CreateObject("Scripting.Dictionary")
    Set dictMissing = CreateObject("Scripting.Dictionary")
    hasMissing = False
    
    With wsInput
        lastRow = .Cells(.Rows.Count, "C").End(xlUp).Row
        If lastRow < 3 Then GoTo NoData
        inputData = .Range("A3:J" & lastRow).Value
    End With
    
    For r = LBound(inputData, 1) To UBound(inputData, 1)
        processName = Trim(inputData(r, 3)) ' C열
        chemList = Trim(inputData(r, 9))     ' I열
        
        If processName <> "" And chemList <> "" Then
            ' 패턴 처리
            tempList = ProcessSpecialPatterns(chemList)
            
            ' 정규식을 이용한 특별관리물질 패턴 처리 (성능 개선, 중첩 괄호 가능성 지원)
            Dim regEx2 As Object
            Set regEx2 = CreateObject("VBScript.RegExp")
            regEx2.Global = True
            regEx2.Pattern = "특별관리물질(?:\[([^\]]+)\]|\(([^()]*(?:\([^()]*\)[^()]*)*)\))"

            ' 보관[...]인 경우는 원문 그대로 유지
            If InStr(tempList, "보관[") > 0 Then
                ' 단, 괄호 안 내용은 유지하도록 처리
                tempList = regEx2.Replace(tempList, "특별관리물질($1$2)")
            Else
                ' 일반 케이스는 괄호 안 내용만 남김
                tempList = regEx2.Replace(tempList, "$1$2")
            End If

            
            ' 물질 분할
            arrChems = Split(tempList, ";")
            
            ' 임시 대체된 세미콜론 복원
            For c = LBound(arrChems) To UBound(arrChems)
                arrChems(c) = Replace(Trim(arrChems(c)), "|SEMICOLON|", ";")
            Next c
            
            ' 공정별 딕셔너리 생성
            If Not dictProcess.Exists(processName) Then
                Set chemDict = CreateObject("Scripting.Dictionary")
                dictProcess.Add processName, chemDict
                Set missingDict = CreateObject("Scripting.Dictionary")
                dictMissing.Add processName, missingDict
            Else
                Set chemDict = dictProcess(processName)
                Set missingDict = dictMissing(processName)
            End If
            
            ' 물질 처리
            For c = LBound(arrChems) To UBound(arrChems)
                chemName = Trim(arrChems(c))
                If chemName <> "" Then
                    If InStr(chemName, "단시간 및 임시작업") > 0 Or _
                       InStr(chemName, "보관") > 0 Or _
                       InStr(chemName, "허용소비량 미만") > 0 Then
                        If Not missingDict.Exists(chemName) Then
                            missingDict.Add chemName, 1
                            hasMissing = True
                        End If
                    ElseIf dictMethod.Exists(chemName) Then
                        If Not chemDict.Exists(chemName) Then chemDict.Add chemName, 1
                    Else
                        If Not missingDict.Exists(chemName) Then
                            missingDict.Add chemName, 1
                            hasMissing = True
                        End If
                    End If
                End If
            Next c
        End If
    Next r
    
    ' 3. 데이터 분류 및 출력 준비
    outputRow = 4
    
    ' 분석방법 우선순위 정의
    Set methodPriority = CreateObject("Scripting.Dictionary")
    Dim priorityList As Variant
    priorityList = Array( _
        "누적소음계", "중량분석법", "중량분석법(호)", "중량분석법(흡)", "FTIR법(다)", _
        "위상차현미경법", "중량분석법(단)", "ICP법(다)", "ICP법(다)호", "IC법(단)-금", _
        "ICP법(단)흡", "ICP법(단)", "GC법(다)", "GC법(다)2", "GC법(다)3", "GC법(다)4", _
        "GC법(다)5", "GC법(다)6", "GC법(다)7", "GC법(다)8", "GC법(단)", "HPLC법(다)", _
        "HPLC법(다)2", "HPLC법(다)3", "HPLC법(다)4", "HPLC법(단)", _
        "IC법(다)-산알", "IC법(다)2-산알", "UV법(다)", "IC법(단)-산알", _
        "UV법(단)", "GC법(NPD)(단)", "IC법(다)3-가스", "IC법(단)-가스", "VIS(다)", "추출법", _
        "GC법(단)-C", "HPLC법(단)-C", "ICP법(다)-C", "UV법(단)-C", _
        "직독식", "WBGT" _
    )
    
    For m = LBound(priorityList) To UBound(priorityList)
        methodPriority.Add priorityList(m), m
    Next m
    
    ' 공정별 처리
    Dim outputData As Collection
    Set outputData = New Collection
    
    For Each key In dictProcess.keys
        processName = key
        Set chemDict = dictProcess(key)
        
        ' 분석방법별 분류
        Set methodGroup = CreateObject("Scripting.Dictionary")
        For Each chem In chemDict.keys
            method = dictMethod(chem)
            If methodGroup.Exists(method) Then
                methodGroup(method) = methodGroup(method) & ";" & chem
            Else
                methodGroup.Add method, chem
            End If
        Next chem
        
        ' 분석방법 정렬 (배열 정렬)
        If methodGroup.Count > 0 Then
            Dim methods() As String, values() As String
            ReDim methods(0 To methodGroup.Count - 1)
            ReDim values(0 To methodGroup.Count - 1)
            
            idx = 0
            For Each subKey In methodGroup.keys
                methods(idx) = subKey
                values(idx) = methodGroup(subKey)
                idx = idx + 1
            Next subKey
            
            ' 정렬 수행
            SortMethods methods, values, methodPriority
            
            ' 정렬된 순서대로 출력 데이터 수집
            For m = LBound(methods) To UBound(methods)
                subKey = methods(m)
                arrChems = Split(values(m), ";")
                chemCount = UBound(arrChems) - LBound(arrChems) + 1
                
                ' 물질 정렬 (삽입정렬 사용)
                SortChemicals arrChems, dictOrder
                
                ' 분석방법 유형 확인
                isSingleMethod = (InStr(1, subKey, "(단)") > 0)
                
                ' (단) 메서드 처리
                If isSingleMethod Then
                    For c = LBound(arrChems) To UBound(arrChems)
                        outputData.Add Array( _
                            processName, _
                            Trim(arrChems(c)), _
                            IIf(dictLValue.Exists(Trim(arrChems(c))), dictLValue(Trim(arrChems(c))), "-"), _
                            IIf(dictEValue.Exists(Trim(arrChems(c))), dictEValue(Trim(arrChems(c))), "-"), _
                            subKey _
                        )
                    Next c
                Else
                    ' (다) 메서드 처리
                    newMethod = subKey
                    If chemCount = 1 And InStr(1, newMethod, "(다)") > 0 Then
                        newMethod = Replace(newMethod, "(다)", "(단)")
                    End If
                    
                    firstChem = Trim(arrChems(LBound(arrChems)))
                    outputData.Add Array( _
                        processName, _
                        Join(arrChems, "; "), _
                        IIf(dictLValue.Exists(firstChem), dictLValue(firstChem), "-"), _
                        IIf(dictEValue.Exists(firstChem), dictEValue(firstChem), "-"), _
                        newMethod _
                    )
                End If
            Next m
        End If
    Next key
    
    ' 4. 출력 데이터 일괄 기록 (성능 개선)
    If outputData.Count > 0 Then
        Dim outputArray() As Variant
        ReDim outputArray(1 To outputData.Count, 1 To 5)
        
        For idx = 1 To outputData.Count
            outputArray(idx, 1) = outputData(idx)(0) ' 공정명
            outputArray(idx, 2) = outputData(idx)(1) ' 물질명
            outputArray(idx, 3) = outputData(idx)(2) ' L값
            outputArray(idx, 4) = outputData(idx)(3) ' E값
            outputArray(idx, 5) = outputData(idx)(4) ' 분석방법
        Next idx
        
        wsOutput.Range("B4").Resize(outputData.Count, 1).Value = Application.Index(outputArray, 0, 1)
        wsOutput.Range("C4").Resize(outputData.Count, 1).Value = Application.Index(outputArray, 0, 2)
        wsOutput.Range("I4").Resize(outputData.Count, 1).Value = Application.Index(outputArray, 0, 3)
        wsOutput.Range("J4").Resize(outputData.Count, 1).Value = Application.Index(outputArray, 0, 4)
        wsOutput.Range("K4").Resize(outputData.Count, 1).Value = Application.Index(outputArray, 0, 5)
        
        outputRow = outputRow + outputData.Count
    End If
    
    ' 5. 누락된 물질 출력
    If hasMissing Then
        wsOutput.Cells(outputRow, "B").Value = ""
        outputRow = outputRow + 1
        
        For Each key In dictMissing.keys
            processName = key
            Set missingDict = dictMissing(key)
            
            If missingDict.Count > 0 Then
                Dim missingChems As String
                missingChems = ""
                
                For Each chem In missingDict.keys
                    missingChems = missingChems & chem & "; "
                Next chem
                
                ' 그룹화 및 중복 제거 적용
                missingChems = FormatGroupedChems(missingChems)
                
                With wsOutput
                    .Cells(outputRow, "B").Value = processName
                    .Cells(outputRow, "C").Value = missingChems
                    .Cells(outputRow, "I").Value = "-"
                    .Cells(outputRow, "J").Value = "-"
                    .Cells(outputRow, "K").Value = "분석방법 없음"
                    .Range("B" & outputRow & ":K" & outputRow).Font.Color = RGB(255, 0, 0)
                End With
                outputRow = outputRow + 1
            End If
        Next key
    End If
    
    ' 완료 메시지
    Application.ScreenUpdating = True
    Application.Calculation = xlCalculationAutomatic
    Application.EnableEvents = True
    
    MsgBox "측정계획에 반영되었습니다!", vbInformation
    
    Exit Sub
    
NoData:
    MsgBox "처리할 데이터가 없습니다.", vbExclamation
    GoTo CleanUp
    
ErrorHandler:
    MsgBox "오류 발생: " & Err.Description, vbCritical
    
CleanUp:
    Application.ScreenUpdating = True
    Application.Calculation = xlCalculationAutomatic
    Application.EnableEvents = True
End Sub

' 분석방법 정렬 (단순 버블 정렬)
Sub SortMethods(ByRef methods() As String, ByRef values() As String, ByRef priorityDict As Object)
    Dim i As Long, j As Long
    Dim tempMethod As String, tempValue As String
    
    For i = LBound(methods) To UBound(methods) - 1
        For j = i + 1 To UBound(methods)
            Dim prioI As Long, prioJ As Long
            prioI = GetPriority(methods(i), priorityDict)
            prioJ = GetPriority(methods(j), priorityDict)
            
            If prioI > prioJ Then
                ' Swap methods
                tempMethod = methods(i)
                methods(i) = methods(j)
                methods(j) = tempMethod
                
                ' Swap values
                tempValue = values(i)
                values(i) = values(j)
                values(j) = tempValue
            End If
        Next j
    Next i
End Sub

' 화학물질 정렬 (삽입 정렬)
Sub SortChemicals(ByRef arr() As String, ByRef orderDict As Object)
    Dim i As Long, j As Long
    Dim key As String
    
    For i = LBound(arr) + 1 To UBound(arr)
        key = arr(i)
        j = i - 1
        
        ' Do While 루프로 변경 (Exit Do 사용)
        Do While j >= LBound(arr)
            Dim order1 As Long, order2 As Long
            order1 = GetOrder(Trim(arr(j)), orderDict)
            order2 = GetOrder(key, orderDict)
            
            If order1 <= order2 Then Exit Do
            arr(j + 1) = arr(j)
            j = j - 1
        Loop
        
        arr(j + 1) = key
    Next i
End Sub

' 우선순위 조회 함수
Function GetPriority(method As String, priorityDict As Object) As Long
    If priorityDict.Exists(method) Then
        GetPriority = priorityDict(method)
    Else
        GetPriority = 99999 ' 없는 경우 최저 우선순위
    End If
End Function

' 순서 조회 함수
Function GetOrder(chemName As String, orderDict As Object) As Long
    If orderDict.Exists(chemName) Then
        GetOrder = orderDict(chemName)
    Else
        GetOrder = 999999 ' 없는 경우 최후순위
    End If
End Function

Sub 매체_업데이트()

    '// 화면 업데이트 및 자동 계산 일시 중지
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual

    '// 1. 변수 및 객체 선언
    Dim wsSource As Worksheet, wsOutput As Worksheet
    Dim dictMethod As Object, dictOrder As Object, dictLValue As Object, dictEValue As Object
    Dim masterDict As Object, methodPriority As Object

    Dim lastSourceRow As Long, lastOutputRow As Long, r As Long, i As Long, j As Long
    Dim processName As String, chemList As String, method As String, chemName As String
    Dim firstChem As String, tmp As String

    Dim arrChems() As String, arrMethods() As String, arrSortedChems() As String
    Dim priorityA As Long, priorityB As Long, orderA As Long, orderB As Long
    Dim outputRow As Long

    Dim pKey As Variant, mKey As Variant
    Dim methodDict As Object, chemDict As Object

    '// 2. 시트 및 딕셔너리 초기 설정
    Set wsSource = ThisWorkbook.Sheets("통합 유해인자 자료")
    Set wsOutput = ThisWorkbook.Sheets("측정계획(양식)")

    Set dictMethod = CreateObject("Scripting.Dictionary")
    Set dictOrder = CreateObject("Scripting.Dictionary")
    Set dictLValue = CreateObject("Scripting.Dictionary")
    Set dictEValue = CreateObject("Scripting.Dictionary")
    Set masterDict = CreateObject("Scripting.Dictionary")

    '// 3. '통합 유해인자 자료'에서 참조 정보 불러오기
    lastSourceRow = wsSource.Cells(wsSource.Rows.Count, "C").End(xlUp).Row
    For r = 2 To lastSourceRow
        chemName = Trim(wsSource.Cells(r, "C").Value)
        If chemName <> "" Then
            If Not dictMethod.Exists(chemName) Then
                dictMethod.Add chemName, Trim(wsSource.Cells(r, "I").Value)
                dictOrder.Add chemName, r
                dictLValue.Add chemName, Trim(wsSource.Cells(r, "L").Value)
                dictEValue.Add chemName, Trim(wsSource.Cells(r, "E").Value)
            End If
        End If
    Next r

    '// 4. 분석방법 우선순위 정의
    Set methodPriority = CreateObject("Scripting.Dictionary")
    Dim priorityList As Variant
    priorityList = Array( _
        "누적소음계", "중량분석법", "중량분석법(호)", "중량분석법(흡)", "FTIR법(다)", _
        "위상차현미경법", "중량분석법(단)", "ICP법(다)", "ICP법(다)호", "IC법(단)-금", _
        "ICP법(단)흡", "ICP법(단)", "GC법(다)", "GC법(다)2", "GC법(다)3", "GC법(다)4", _
        "GC법(다)5", "GC법(다)6", "GC법(다)7", "GC법(다)8", "GC법(단)", "HPLC법(다)", _
        "HPLC법(다)2", "HPLC법(다)3", "HPLC법(다)4", "HPLC법(단)", _
        "IC법(다)-산알", "IC법(다)2-산알", "UV법(다)", "IC법(단)-산알", _
        "UV법(단)", "GC법(NPD)(단)", "IC법(다)3-가스", "IC법(단)-가스", "VIS(다)", "추출법", _
        "GC법(단)-C", "HPLC법(단)-C", "ICP법(다)-C", "UV법(단)-C", _
        "직독식", "WBGT" _
        )
    For i = LBound(priorityList) To UBound(priorityList)
        methodPriority.Add priorityList(i), i
    Next i

    '// 5. '측정계획(양식)'의 현재 데이터를 읽어 메모리에서 재구성
    lastOutputRow = wsOutput.Cells(wsOutput.Rows.Count, "B").End(xlUp).Row
    If lastOutputRow < 4 Then lastOutputRow = 4

    For r = 4 To lastOutputRow
        If Trim(wsOutput.Cells(r, "C").Value) <> "" And Trim(wsOutput.Cells(r, "B").Value) = "" Then
            MsgBox "공정명(B열)이 비어 있는 행이 있습니다. 확인 후 다시 실행해주세요." & vbCrLf & _
                "문제가 있는 행 번호: " & r, vbExclamation, "입력 오류"
            Exit Sub
        End If
    Next r

    For r = 4 To lastOutputRow
        processName = Trim(wsOutput.Cells(r, "B").Value)
        chemList = Trim(wsOutput.Cells(r, "C").Value)

        If processName <> "" And chemList <> "" Then
            ' 패턴 처리 함수 호출 추가 (단시간 및 임시작업 등 보호)
            chemList = ProcessSpecialPatterns(chemList)
            arrChems = Split(chemList, ";")

            For i = LBound(arrChems) To UBound(arrChems)
                ' 임시 대체된 세미콜론 복원 및 공백 제거
                chemName = Replace(Trim(arrChems(i)), "|SEMICOLON|", ";")
                If chemName <> "" Then
                    If dictMethod.Exists(chemName) And dictMethod(chemName) <> "" Then
                        method = dictMethod(chemName)
                    Else
                        method = "분석방법 없음"
                    End If

                    If Not masterDict.Exists(processName) Then
                        Set methodDict = CreateObject("Scripting.Dictionary")
                        masterDict.Add processName, methodDict
                    End If

                    If Not masterDict(processName).Exists(method) Then
                        Set chemDict = CreateObject("Scripting.Dictionary")
                        masterDict(processName).Add method, chemDict
                    End If

                    If Not masterDict(processName)(method).Exists(chemName) Then
                        masterDict(processName)(method).Add chemName, 1
                    End If
                End If
            Next i
        End If
    Next r

    '// 6. 기존 B:C열, I:K열 출력 데이터 삭제
    With wsOutput
        Dim clearRowB As Long
        clearRowB = .Cells(.Rows.Count, "B").End(xlUp).Row
        If clearRowB < 4 Then clearRowB = 4

        Dim clearRowI As Long
        clearRowI = .Cells(.Rows.Count, "I").End(xlUp).Row
        If clearRowI < 4 Then clearRowI = 4

        ' B4부터 B열 마지막 행까지 내용 삭제
        .Range("B4:C" & clearRowB).ClearContents

        ' I4부터 I열 마지막 행까지 내용 삭제
        .Range("I4:K" & clearRowI).ClearContents

        ' B열부터 K열까지의 글꼴 색상 초기화 (4행부터 시작)
        Dim fontRow As Long
        fontRow = .Cells(.Rows.Count, "B").End(xlUp).Row
        If fontRow < 4 Then fontRow = 4
        .Range("B4:K" & fontRow).Font.Color = RGB(0, 0, 0)
    End With

    '// 6-1. '분석방법 없음' 항목을 저장할 리스트
    Dim noMethodList As Collection
    Set noMethodList = New Collection

    '// 7. 재구성된 데이터를 정렬하여 시트에 다시 쓰기
    outputRow = 4
    For Each pKey In masterDict.keys
        processName = pKey
        Set methodDict = masterDict(pKey)

        ReDim arrMethods(0 To methodDict.Count - 1)
        i = 0
        For Each mKey In methodDict.keys
            arrMethods(i) = mKey
            i = i + 1
        Next mKey

        For i = 0 To UBound(arrMethods) - 1
            For j = i + 1 To UBound(arrMethods)
                priorityA = IIf(methodPriority.Exists(arrMethods(i)), methodPriority(arrMethods(i)), 9999)
                priorityB = IIf(methodPriority.Exists(arrMethods(j)), methodPriority(arrMethods(j)), 9999)
                If priorityA > priorityB Then
                    tmp = arrMethods(i)
                    arrMethods(i) = arrMethods(j)
                    arrMethods(j) = tmp
                End If
            Next j
        Next i

        For i = 0 To UBound(arrMethods)
            method = arrMethods(i)
            Set chemDict = methodDict(method)

            ReDim arrSortedChems(0 To chemDict.Count - 1)
            j = 0
            For Each mKey In chemDict.keys
                arrSortedChems(j) = mKey
                j = j + 1
            Next mKey

            For j = 0 To UBound(arrSortedChems) - 1
                For r = j + 1 To UBound(arrSortedChems)
                    orderA = dictOrder(arrSortedChems(j))
                    orderB = dictOrder(arrSortedChems(r))
                    If orderA > orderB Then
                        tmp = arrSortedChems(j)
                        arrSortedChems(j) = arrSortedChems(r)
                        arrSortedChems(r) = tmp
                    End If
                Next r
            Next j

            firstChem = arrSortedChems(0)

            If method = "분석방법 없음" Then
                ' 컬렉션에 정보 저장
                Dim noItem As Variant
                Set noItem = CreateObject("Scripting.Dictionary")
                noItem("Process") = processName
                ' 그룹화 및 중복 제거 적용
                noItem("Chems") = FormatGroupedChems(Join(arrSortedChems, "; "))
                noItem("LValue") = IIf(dictLValue.Exists(firstChem), dictLValue(firstChem), "-")
                noItem("EValue") = IIf(dictEValue.Exists(firstChem), dictEValue(firstChem), "-")
                noItem("Method") = method
                noMethodList.Add noItem

            ElseIf InStr(1, method, "(단)") > 0 Then
                For j = LBound(arrSortedChems) To UBound(arrSortedChems)
                    wsOutput.Cells(outputRow, "B").Value = processName
                    wsOutput.Cells(outputRow, "C").Value = arrSortedChems(j)
                    wsOutput.Cells(outputRow, "I").Value = IIf(dictLValue.Exists(arrSortedChems(j)), dictLValue(arrSortedChems(j)), "-")
                    wsOutput.Cells(outputRow, "J").Value = IIf(dictEValue.Exists(arrSortedChems(j)), dictEValue(arrSortedChems(j)), "-")
                    wsOutput.Cells(outputRow, "K").Value = method
                    outputRow = outputRow + 1
                Next j

            Else
                wsOutput.Cells(outputRow, "B").Value = processName
                wsOutput.Cells(outputRow, "C").Value = Join(arrSortedChems, "; ")
                wsOutput.Cells(outputRow, "I").Value = IIf(dictLValue.Exists(firstChem), dictLValue(firstChem), "-")
                wsOutput.Cells(outputRow, "J").Value = IIf(dictEValue.Exists(firstChem), dictEValue(firstChem), "-")
                If UBound(arrSortedChems) = 0 And InStr(1, method, "(다)") > 0 Then
                    wsOutput.Cells(outputRow, "K").Value = Replace(method, "(다)", "(단)")
                Else
                    wsOutput.Cells(outputRow, "K").Value = method
                End If
                outputRow = outputRow + 1
            End If
        Next i
    Next pKey

    '// 8. 분석방법 없음 항목들 출력 (C열 기준 마지막 행 + 2 줄 아래부터)
    Dim startRow As Long
    startRow = wsOutput.Cells(wsOutput.Rows.Count, "C").End(xlUp).Row + 2

    For Each noItem In noMethodList
        With wsOutput
            .Cells(startRow, "B").Value = noItem("Process")
            .Cells(startRow, "C").Value = noItem("Chems")
            .Cells(startRow, "I").Value = noItem("LValue")
            .Cells(startRow, "J").Value = noItem("EValue")
            .Cells(startRow, "K").Value = noItem("Method")
            .Range("B" & startRow & ":K" & startRow).Font.Color = RGB(255, 0, 0)
        End With
        startRow = startRow + 1
    Next noItem

    '// 9. 완료 처리
    Application.ScreenUpdating = True
    Application.Calculation = xlCalculationAutomatic

    MsgBox "재정렬 및 업데이트가 완료되었습니다!", vbInformation

End Sub



Sub 측정계획_자동화_워크플로우()
    Dim response As VbMsgBoxResult

    ' 1. 병합 여부 확인 (B열 4행 데이터가 있고 D/E열이 병합되지 않은 경우 자동 병합)
    ' 여기서는 복잡한 조건 체크 대신, 사용자에게 단계별로 진행을 유도합니다.
    
    response = MsgBox("병합을 진행하고 근로자 수를 입력하시겠습니까?" & vbCrLf & _
                      "(이미 병합했다면 '아니오'를 눌러 번호 부여 단계로 이동하세요)", vbYesNoCancel + vbQuestion, "측정계획 워크플로우")
    
    If response = vbYes Then
        ' 1단계: 병합 처리
        Call B열기준_병합_처리
        MsgBox "병합되었습니다. 근로자 수와 측정 건수를 입력하신 후" & vbCrLf & _
               "다시 워크플로우 버튼을 눌러 번호를 부여해 주세요.", vbInformation
        Exit Sub
    ElseIf response = vbNo Then
        ' 3단계: 번호 자동 부여
        response = MsgBox("입력된 근로자 수 기준으로 번호를 부여할까요?", vbYesNo + vbQuestion)
        If response = vbYes Then
            Call 번호자동부여
            MsgBox "번호 부여가 완료되었습니다.", vbInformation
        End If
    End If
End Sub

' =========================================
' 1단계: B열 기준 병합 (D, E, F, G, M열)
' =========================================
Sub B열기준_병합_처리()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Sheets("측정계획(양식)")

    Dim startRow As Long
    Dim endRow As Long
    Dim currentRow As Long
    Dim currentValue As Variant
    Dim targetCols As Variant
    Dim col As Variant

    Application.ScreenUpdating = False
    Application.DisplayAlerts = False

    targetCols = Array("D", "E", "F", "G", "M")
    startRow = 4
    currentRow = startRow

    Do While currentRow <= ws.Cells(ws.Rows.Count, "B").End(xlUp).Row
        currentValue = ws.Cells(currentRow, "B").Value
        endRow = currentRow

        ' 같은 값의 연속 범위 찾기
        Do While ws.Cells(endRow + 1, "B").Value = currentValue And ws.Cells(endRow + 1, "B").Value <> ""
            endRow = endRow + 1
        Loop

        ' 병합 처리 (유효 범위일 경우만)
        If endRow >= currentRow Then
            For Each col In targetCols
                With ws.Range(ws.Cells(currentRow, col), ws.Cells(endRow, col))
                    If .MergeCells Then .UnMerge
                    .Merge
                    .HorizontalAlignment = xlCenter
                    .VerticalAlignment = xlCenter
                End With
            Next col
        End If

        currentRow = endRow + 1
    Loop

    Application.DisplayAlerts = True
    Application.ScreenUpdating = True

    ' MsgBox "1단계: 병합이 완료되었습니다!", vbInformation
End Sub


' =========================================
' 3단계: E열 숫자 기준으로 F, G열에 번호 부여
' =========================================
Sub 번호자동부여()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Sheets("측정계획(양식)")

    Dim lastRow As Long
    Dim currentRow As Long
    Dim groupStartRow As Long
    Dim groupEndRow As Long
    Dim currentGroup As String
    Dim nextGroup As String
    Dim counter As Long
    Dim r As Long, i As Long
    Dim val As Variant
    Dim textOut As String
    Dim skipGroup As Boolean
    Dim col As Variant
    Dim hVal As Variant
    Dim lineCount As Long
    Dim totalHeight As Double
    Dim eachRowHeight As Double
    Dim heightPerLine As Double
    Dim rowCount As Long
    Dim cHeightSum As Double

    Application.EnableEvents = False
    Application.ScreenUpdating = False

    counter = 1
    lastRow = ws.Cells(ws.Rows.Count, "C").End(xlUp).Row
    currentRow = 4

    Do While currentRow <= lastRow
        groupStartRow = currentRow
        currentGroup = ws.Cells(currentRow, "B").Value

        ' 그룹 끝 찾기
        Do
            currentRow = currentRow + 1
            nextGroup = ws.Cells(currentRow, "B").Value
        Loop While currentRow <= lastRow And nextGroup = currentGroup

        groupEndRow = currentRow - 1
        rowCount = groupEndRow - groupStartRow + 1

        ' ?? 수정된 조건: 빈칸은 포함 (번호 부여)
        skipGroup = True
        For r = groupStartRow To groupEndRow
            hVal = Trim(ws.Cells(r, "H").Value)
            If hVal <> "횟수조정" And hVal <> "0" Then
                skipGroup = False
                Exit For
            End If
        Next r

        If Not skipGroup Then
            ' 병합된 E열 값에서 번호 수 추출
            val = ws.Cells(groupStartRow, "E").MergeArea.Cells(1, 1).Value
            If IsNumeric(val) And val > 0 Then
                ' 번호 사이 빈 줄 및 상하단 여백을 위한 텍스트 생성
                textOut = vbLf ' 상단 여백
                For r = 1 To val
                    textOut = textOut & " " & counter & ")" & vbLf & vbLf
                    counter = counter + 1
                Next r
                ' 마지막 빈 줄 하나를 제거하여 대칭 여백 유지
                textOut = Left(textOut, Len(textOut) - 1)

                ' F, G 열에 병합 및 텍스트 입력
                For Each col In Array("F", "G")
                    With ws.Range(col & groupStartRow & ":" & col & groupEndRow)
                        .UnMerge
                        .Merge
                        .Value = textOut
                        .WrapText = True
                        .HorizontalAlignment = xlLeft
                        .VerticalAlignment = xlCenter
                    End With
                Next col

                ' 행 높이 계산 (폰트 16pt 기준 줄당 25pt)
                heightPerLine = 25
                lineCount = (2 * val) + 1
                totalHeight = heightPerLine * lineCount

                ' C열 내용(물질명)이 잘리지 않도록 전체 높이 계산
                cHeightSum = 0
                On Error Resume Next
                For i = groupStartRow To groupEndRow
                    ws.Rows(i).AutoFit
                    cHeightSum = cHeightSum + ws.Rows(i).RowHeight
                Next i
                On Error GoTo 0
                
                If cHeightSum > totalHeight Then totalHeight = cHeightSum
                
                ' 최소 높이 보장 및 균등 배분
                If totalHeight < (25 * rowCount) Then totalHeight = 25 * rowCount
                eachRowHeight = totalHeight / rowCount
                
                ' Excel 최대 높이 제한
                If eachRowHeight > 409 Then eachRowHeight = 409

                For i = groupStartRow To groupEndRow
                    ws.Rows(i).RowHeight = eachRowHeight
                Next i
            End If
        Else
            ' 번호 미부여 그룹 처리
            For Each col In Array("F", "G")
                With ws.Range(col & groupStartRow & ":" & col & groupEndRow)
                    .UnMerge
                    .Merge
                    .Value = ""
                    .WrapText = False
                End With
            Next col

            For i = groupStartRow To groupEndRow
                If ws.Rows(i).RowHeight < 25 Then
                    ws.Rows(i).RowHeight = 25
                End If
            Next i
        End If

        currentRow = groupEndRow + 1
    Loop

    Application.EnableEvents = True
    Application.ScreenUpdating = True
End Sub



Sub 예비조사_참고()
    Dim wsPlan As Worksheet
    Dim wsRef As Worksheet
    Dim lastRow As Long, i As Long, outputRow As Long
    Dim dict As Object
    Dim processName As String
    Dim factors As String
    Dim factorArr() As String
    Dim uniqueFactors As Object
    Dim factor As Variant
    Dim key As Variant
    Dim targetRow As Long
    
    ' "측정계획(양식)" 시트 접근
    Set wsPlan = ThisWorkbook.Sheets("측정계획(양식)")
    
    ' "예비조사_참고" 시트 접근
    On Error Resume Next
    Set wsRef = ThisWorkbook.Sheets("예비조사_참고")
    On Error GoTo 0
    
    ' 예비조사_참고 시트가 없는 경우 생성
    If wsRef Is Nothing Then
        Set wsRef = ThisWorkbook.Sheets.Add(After:=ThisWorkbook.Sheets(ThisWorkbook.Sheets.Count))
        wsRef.Name = "예비조사_참고"
    End If
    
    ' 기존 데이터 삭제 (A3부터)
    If wsRef.Range("A3").Value <> "" Then
        wsRef.Range("A3:B" & wsRef.Cells(wsRef.Rows.Count, "A").End(xlUp).Row).ClearContents
    End If
    
    ' 마지막 행 찾기 (C열 기준)
    lastRow = wsPlan.Cells(wsPlan.Rows.Count, "C").End(xlUp).Row
    If lastRow < 4 Then lastRow = 4
    
    ' 데이터 저장을 위한 Dictionary 생성
    Set dict = CreateObject("Scripting.Dictionary")
    
    ' 데이터 처리
    For i = 4 To lastRow
        processName = Trim(wsPlan.Range("B" & i).Value)
        factors = Trim(wsPlan.Range("C" & i).Value)
        
        ' 빈 셀 체크 (C열이 빈 경우)
        If factors = "" Then Exit For
        
        ' 공정명이 없는 경우 건너뜀
        If processName = "" Then GoTo NextRow
        
        ' 기존 구분자 변경 (; -> ,)
        factors = Replace(factors, "; ", ", ")
        
        ' 공정명별로 데이터 저장
        If dict.Exists(processName) Then
            dict(processName) = dict(processName) & ", " & factors
        Else
            dict.Add processName, factors
        End If
        
NextRow:
    Next i
    
    ' 중복 제거 및 결과 출력
    outputRow = 3 ' A3부터 시작
    For Each key In dict.keys
        ' 중복 요소 제거
        Set uniqueFactors = CreateObject("Scripting.Dictionary")
        factorArr = Split(dict(key), ", ")
        
        For Each factor In factorArr
            factor = Trim(factor)
            If factor <> "" Then
                If Not uniqueFactors.Exists(factor) Then
                    uniqueFactors.Add factor, Nothing
                End If
            End If
        Next
        
        ' 결과 작성 (A3, B3부터)
        wsRef.Cells(outputRow, "A").Value = key
        wsRef.Cells(outputRow, "B").Value = Join(uniqueFactors.keys, ", ")
        
        ' B열에 자동 줄바꿈 설정
        wsRef.Cells(outputRow, "B").WrapText = True
        
        ' 행 높이 설정 (최소 25)
        wsRef.Rows(outputRow).RowHeight = 25
        
        outputRow = outputRow + 1
    Next key
    
    ' 행 높이 자동 조정 (최소 높이 25 유지)
    For targetRow = 3 To outputRow - 1
        ' AutoFit 실행 (내용에 맞게 높이 조정)
        wsRef.Rows(targetRow).AutoFit
        
        ' 최소 높이 25 유지
        If wsRef.Rows(targetRow).RowHeight < 25 Then
            wsRef.Rows(targetRow).RowHeight = 25
        End If
    Next targetRow
    
    ' 컬럼 너비 자동 조정
    wsRef.Columns("A:B").AutoFit
    
    ' 완료 메시지
    MsgBox "데이터 취합이 완료되었습니다!", vbInformation, "완료"
End Sub

Sub 초기화()
    Dim ws As Worksheet
    Dim targetRange As Range
    Dim nonBColumns As Range
    Dim colA As Range
    Dim colCtoM As Range
    Dim i As Long
    
    ' 현재 활성 시트 사용
    Set ws = ActiveSheet

    ' 작업 범위 설정 (A4:L295)
    Set targetRange = ws.Range("A4:L295")

    ' 1. 데이터 및 병합 셀 초기화
    targetRange.ClearContents
    targetRange.UnMerge

    ' 2. 글꼴 기본 설정
    With targetRange.Font
        .Name = "굴림"
        .Size = 16
        .Color = RGB(0, 0, 0)
    End With

    ' 3. 채우기색 제거
    targetRange.Interior.Pattern = xlNone

    ' 4. 셀 맞춤 설정
    With targetRange
        .HorizontalAlignment = xlCenter
        .VerticalAlignment = xlCenter
        .ShrinkToFit = True
    End With

    ' 5. B열 제외한 표시형식 초기화 및 A열 사용자 지정 서식
    Set colA = ws.Range("A4:A295")
    Set colCtoM = ws.Range("C4:L295")

    ' 전체 범위를 한번에 지정
    Set nonBColumns = Union(colA, colCtoM)

    ' 전체 범위의 형식을 General로 초기화
    nonBColumns.NumberFormat = "General"

    ' A열에 사용자 지정 서식 지정 (항상 월/일 형태로 표시)
    colA.NumberFormat = "@"

    ' 6. 테두리 설정 (모든 테두리를 선 없음으로)
    With targetRange.Borders
        .LineStyle = xlNone
    End With

    ' 각 테두리별로 명시적으로 선 없음 설정
    With targetRange
        .Borders(xlEdgeTop).LineStyle = xlNone
        .Borders(xlEdgeBottom).LineStyle = xlNone
        .Borders(xlEdgeLeft).LineStyle = xlNone
        .Borders(xlEdgeRight).LineStyle = xlNone
        .Borders(xlInsideVertical).LineStyle = xlNone
        .Borders(xlInsideHorizontal).LineStyle = xlNone
    End With

    ' 7. 행 높이 초기화 (4행부터 295행까지 높이 30으로)
    For i = 4 To 295
        ws.Rows(i).RowHeight = 30
    Next i
End Sub




' 공정별 테두리 정리
Sub 공정별_테두리정리()

    Application.ScreenUpdating = False
    SetConditionalBorders
    Application.ScreenUpdating = True

    MsgBox "테두리 설정이 완료되었습니다.", vbInformation

End Sub


' ============================================================================================================
'   ▣ C열 연속 데이터(중간 공백까지) 기준 마지막 행 자동 계산 + B열 공정별 테두리 처리 + 전체 테두리 처리
' ============================================================================================================
Sub SetConditionalBorders()

    Dim ws As Worksheet
    Dim lastRow As Long
    Dim i As Long, startRow As Long, endRow As Long
    Dim currentValue As Variant
    Dim remainingRange As Range
    Dim r As Long

    Set ws = ActiveSheet

    ' ---------------------------------------------------------------------------------------
    ' 1. C열: C4부터 연속된 데이터가 있는 마지막 행까지 lastRow 자동 결정
    ' ---------------------------------------------------------------------------------------
    lastRow = 4

    For r = 4 To ws.Rows.Count
        If ws.Cells(r, "C").Value = "" Then
            lastRow = r - 1
            Exit For
        End If
    Next r

    ' 만약 C열이 끝까지 값이 있고 빈 셀을 못 만난 경우 보정
    If lastRow < 4 Then lastRow = 4

    ' ---------------------------------------------------------------------------------------
    ' 2. A4:L(lastRow) 전체 기본 테두리 설정
    ' ---------------------------------------------------------------------------------------
    With ws.Range("A4:L" & lastRow).Borders
        .LineStyle = xlContinuous
        .Color = RGB(0, 0, 0)
        .Weight = xlThin
    End With

    ' B열도 기본 세로 테두리 유지
    With ws.Range("B4:B" & lastRow).Borders
        .LineStyle = xlContinuous
        .Color = RGB(0, 0, 0)
        .Weight = xlThin
    End With

    ' ---------------------------------------------------------------------------------------
    ' 3. B열 동일 값 그룹별 테두리 적용
    ' ---------------------------------------------------------------------------------------
    i = 4
    Do While i <= lastRow

        currentValue = ws.Cells(i, 2).Value

        If currentValue = "" Then
            i = i + 1
        Else
            startRow = i

            Do While i <= lastRow And ws.Cells(i, 2).Value = currentValue
                i = i + 1
            Loop

            endRow = i - 1

            ApplyGroupBorders ws.Range("B" & startRow & ":B" & endRow)
        End If
    Loop

    ' ---------------------------------------------------------------------------------------
    ' 4. A열 + C~L열은 내부/외곽 테두리 전체 유지
    ' ---------------------------------------------------------------------------------------
    Set remainingRange = Union(ws.Range("A4:A" & lastRow), ws.Range("C4:L" & lastRow))

    With remainingRange.Borders
        .LineStyle = xlContinuous
        .Color = RGB(0, 0, 0)
        .Weight = xlThin
    End With

    With remainingRange
        .Borders(xlInsideHorizontal).LineStyle = xlContinuous
        .Borders(xlInsideHorizontal).Color = RGB(0, 0, 0)
        .Borders(xlInsideHorizontal).Weight = xlThin

        .Borders(xlInsideVertical).LineStyle = xlContinuous
        .Borders(xlInsideVertical).Color = RGB(0, 0, 0)
        .Borders(xlInsideVertical).Weight = xlThin
    End With

End Sub


' ============================================================================================================
'   ▣ 동일 그룹(B열) 범위 테두리 정리
' ============================================================================================================
Sub ApplyGroupBorders(rng As Range)

    ' 안쪽 가로 테두리 제거
    With rng.Borders(xlInsideHorizontal)
        .LineStyle = xlNone
    End With

    ' 첫 번째 행: 위쪽 테두리 유지
    With rng.Cells(1, 1)
        .Borders(xlEdgeTop).LineStyle = xlContinuous
        .Borders(xlEdgeTop).Color = RGB(0, 0, 0)
        .Borders(xlEdgeTop).Weight = xlThin
    End With

    ' 마지막 행: 아래쪽 테두리 유지
    With rng.Cells(rng.Rows.Count, 1)
        .Borders(xlEdgeBottom).LineStyle = xlContinuous
        .Borders(xlEdgeBottom).Color = RGB(0, 0, 0)
        .Borders(xlEdgeBottom).Weight = xlThin
    End With

    ' 중간 행: 위/아래 제거
    If rng.Rows.Count > 2 Then

        Dim middleRange As Range
        Set middleRange = rng.Offset(1, 0).Resize(rng.Rows.Count - 2, 1)

        With middleRange
            .Borders(xlEdgeTop).LineStyle = xlNone
            .Borders(xlEdgeBottom).LineStyle = xlNone
        End With

    ElseIf rng.Rows.Count = 2 Then

        With rng.Cells(2, 1)
            .Borders(xlEdgeTop).LineStyle = xlNone
        End With

    End If

    ' 좌우 테두리는 유지
    With rng.Borders(xlEdgeLeft)
        .LineStyle = xlContinuous
        .Color = RGB(0, 0, 0)
        .Weight = xlThin
    End With

    With rng.Borders(xlEdgeRight)
        .LineStyle = xlContinuous
        .Color = RGB(0, 0, 0)
        .Weight = xlThin
    End With

End Sub

Sub 건강디딤돌_단가_파일열기_읽기전용()
    Dim wb As Workbook
    Dim ws As Worksheet
    Dim filePath As String

    filePath = "Z:\data\측정팀\측정보고서\2026년\상반기\(((예비조사표 작성 요령)))\건강디딤돌 단가 확인(25년).xlsx"

    ' 읽기 전용으로 열기
    Set wb = Workbooks.Open(filePath, ReadOnly:=True)
    Set ws = wb.Sheets(1)


    ' 저장은 하지 않음
    ' wb.Close SaveChanges:=False

End Sub



