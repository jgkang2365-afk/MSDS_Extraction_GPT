# [Spec] HTML 델리게이트 다중 행 편집기(QTextEdit) 기능 이식

## 1. 개요
`smu_gui.py`의 `HTMLDelegate` 클래스를 고도화하여, 셀 편집 시 단일 행이 아닌 다중 행(`QTextEdit`) 편집기를 사용하도록 하고, 화면 표시 시에도 강제 줄바꿈(`<br>`)을 적용하여 가독성을 극대화합니다.

## 2. 변경 목표
- `QTextEdit` 기반의 `createEditor`, `setEditorData`, `setModelData` 메서드 추가.
- `_get_doc` 메서드에서 `;` 구분자 뒤에 `<br>` 태그를 삽입하여 시각적 줄바꿈 강제.
- `HTMLDelegate` 클래스 전체 교체.

## 3. 상세 수정 계획

### smu_gui.py - HTMLDelegate 클래스 (라인 206-268)
- **변경 사항**: 사용자 제공 코드로 클래스 본문 완전 교체.
- **주요 로직**:
    - `createEditor`: `QTextEdit` 생성 및 스타일 설정.
    - `setEditorData`: 모델 데이터를 플레인 텍스트로 에디터에 로드.
    - `setModelData`: 에디터의 텍스트를 모델에 저장.
    - `_get_doc`: `';<br>'.join(html_parts)`를 사용하여 줄바꿈 시각화.

## 4. 검증 계획 (FTF Protocol)
1. **Forest (사전 분석)**: `smu_gui.py` 내 `HTMLDelegate` 위치 및 상속 관계 확인. (이미 확인 완료)
2. **Tree (정밀 수정)**: 클래스 전체를 오타 없이 정확히 교체.
3. **Forest (사후 검증)**:
    - 파이썬 구문 오류 확인.
    - `smu_gui.py` 실행 시 테이블 셀 더블클릭 시 다중 행 편집기가 뜨는지 확인.
    - 셀 내 데이터가 `;` 기준 줄바꿈되어 표시되는지 확인.
