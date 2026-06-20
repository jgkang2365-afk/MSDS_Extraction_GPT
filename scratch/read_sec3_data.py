# -*- coding: utf-8 -*-
import os
import sys
import json

def main():
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

    json_path = os.path.join("scratch", "010_formaldehyde_odl.json")
    if not os.path.exists(json_path):
        print("[-] JSON 파일이 없습니다.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ODL의 kids들을 재귀적으로 탐색하면서 모든 요소를 리스트로 플래티닝(Flatting)합니다.
    all_elements = []

    def collect_elements(kids):
        for kid in kids:
            all_elements.append(kid)
            if "kids" in kid and kid.get("type", "").upper() not in ["TABLE", "TABLE ROW", "TABLE CELL"]:
                collect_elements(kid["kids"])

    collect_elements(data.get("kids", []))

    # 3섹션의 시작과 끝을 감지하기 위한 플래그
    in_section_3 = False
    section_3_elements = []

    # 3섹션을 나타내는 키워드 패턴들
    sec3_starts = ["3. 구성성분의 명칭 및 함유량", "3. 구성성분의 명칭", "구성성분의 명칭 및 함유량", "COMPOSITION / INFORMATION ON INGREDIENTS"]
    # 4섹션을 나타내는 키워드 패턴들 (3섹션 종료 조건)
    sec4_starts = ["4. 응급조치 요령", "4. 응급조치", "FIRST AID MEASURES"]

    for idx, elem in enumerate(all_elements):
        etype = elem.get("type", "").upper()
        content = ""
        
        if etype in ["PARAGRAPH", "HEADING", "TEXT"]:
            content = elem.get("content", "").strip()
            # 만약 kids가 있다면 kids 안의 텍스트도 모음
            if "kids" in elem:
                texts = []
                def _collect(ks):
                    for k in ks:
                        if "content" in k: texts.append(k["content"])
                        if "kids" in k: _collect(k["kids"])
                _collect(elem["kids"])
                if texts:
                    content = " ".join(texts).strip()
        elif etype == "TABLE":
            # 테이블인 경우 행과 열을 텍스트로 합쳐서 키워드 매칭용으로 사용
            table_texts = []
            for row in elem.get("rows", []):
                for cell in row.get("cells", []):
                    cell_texts = []
                    def _extract(ks):
                        for k in ks:
                            if "content" in k: cell_texts.append(k["content"])
                            if "kids" in k: _extract(k["kids"])
                    if "kids" in cell:
                        _extract(cell["kids"])
                    table_texts.append(" ".join(cell_texts).strip())
            content = " | ".join(table_texts)

        # 3섹션 시작 판정
        if not in_section_3:
            for start_keyword in sec3_starts:
                if start_keyword in content:
                    in_section_3 = True
                    print(f"[!] 3섹션 시작 감지: {content} (페이지 {elem.get('page number', '?')})")
                    break

        if in_section_3:
            # 4섹션 시작 판정 시 종료
            is_end = False
            for end_keyword in sec4_starts:
                if end_keyword in content and "3." not in content: # 3. 이 포함되어있는데 4. 도 포함된 오경보 방지
                    is_end = True
                    break
            if is_end:
                print(f"[!] 3섹션 종료 감지: {content} (페이지 {elem.get('page number', '?')})")
                break
            
            section_3_elements.append(elem)

    print("\n" + "="*50)
    print("O D L  추 출  3 섹 션  데 이 터 (Raw)")
    print("="*50)
    
    for elem in section_3_elements:
        etype = elem.get("type", "").upper()
        p_num = elem.get("page number", "?")
        
        if etype in ["PARAGRAPH", "HEADING", "TEXT"]:
            content = elem.get("content", "").strip()
            if "kids" in elem:
                texts = []
                def _collect(ks):
                    for k in ks:
                        if "content" in k: texts.append(k["content"])
                        if "kids" in k: _collect(k["kids"])
                _collect(elem["kids"])
                if texts:
                    content = " ".join(texts).strip()
            print(f"[Text] (P.{p_num}): {content}")
            
        elif etype == "TABLE":
            print(f"\n[Table] (P.{p_num})")
            for r_idx, row in enumerate(elem.get("rows", [])):
                row_cells = []
                for cell in row.get("cells", []):
                    cell_texts = []
                    def _extract(ks):
                        for k in ks:
                            if "content" in k: cell_texts.append(k["content"])
                            if "kids" in k: _extract(k["kids"])
                    if "kids" in cell:
                        _extract(cell["kids"])
                    row_cells.append(" ".join(cell_texts).strip())
                print(" | ".join(row_cells))
            print()

if __name__ == "__main__":
    main()
