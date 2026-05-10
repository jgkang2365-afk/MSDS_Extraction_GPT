import os
import fitz
import re
import sys
import unicodedata
from opendataloader.pdf import PDFParser

# 현재 경로 추가
sys.path.append(os.getcwd())
import msds_engine_v5

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\033_아이생각수성내부프로 (M-BASE)_GHS국문.pdf"

def debug_extraction():
    print(f"\n=== [DEBUG] 엔진 내부 데이터 분석: {os.path.basename(pdf_path)} ===")
    
    # 1. ODL 결과 분석 (표 데이터)
    print("\n[1. ODL 원본 데이터 분석]")
    parser = PDFParser()
    try:
        odl_doc = parser.parse(pdf_path)
        for p_idx, page in enumerate(odl_doc.pages):
            if p_idx > 2: break # 3페이지까지만
            print(f"\n--- Page {p_idx+1} Tables ---")
            for t_idx, table in enumerate(page.tables):
                print(f"  Table {t_idx} (Rows: {len(table.rows)})")
                for r_idx, row in enumerate(table.rows):
                    cells = [c.text.strip().replace('\n', ' ') for c in row.cells]
                    print(f"    Row {r_idx}: {cells}")
    except Exception as e:
        print(f"  ODL 분석 오류: {e}")

    # 2. Regex-Recovery 내부 텍스트 분석
    print("\n[2. Regex-Recovery 논리 행 분석]")
    doc = fitz.open(pdf_path)
    page = doc[0] # 보통 1페이지에 성분 정보
    
    # msds_engine_v5 내부 로직 시뮬레이션
    lines = []
    words = page.get_text("words")
    for w in words:
        lines.append({"x": w[0], "y": w[1], "text": unicodedata.normalize("NFKC", w[4])})
    
    lines.sort(key=lambda x: (x["y"], x["x"]))
    
    current_y = -1
    row_texts = []
    current_row = ""
    for l in lines:
        if abs(l["y"] - current_y) > 3.0:
            if current_row: row_texts.append({"y": current_y, "text": current_row})
            current_row = l["text"]
            current_y = l["y"]
        else:
            current_row += " " + l["text"]
    if current_row: row_texts.append({"y": current_y, "text": current_row})

    # 3. 논리 행 합성 결과 출력
    print("\n[3. 논리 행 합성 결과 (Line Merge Check)]")
    logical_rows = []
    for rt in row_texts:
        cas_list = re.findall(r'(?<![\d-])(\d{2,7}\s*-\s*\d{2}\s*-\s*\d)(?![\d-])', rt["text"])
        if cas_list:
            logical_rows.append({"cas_list": cas_list, "combined_text": rt["text"], "last_y": rt["y"]})
        elif logical_rows:
            if abs(rt["y"] - logical_rows[-1]["last_y"]) < 35.0:
                logical_rows[-1]["combined_text"] += " |MERGED| " + rt["text"]
                logical_rows[-1]["last_y"] = rt["y"]

    for row in logical_rows:
        if "7732-18-5" in row["cas_list"]:
            print(f"  Water 논리 행 합성 결과: {row['combined_text']}")
            
            if all_conts:
                for c in all_conts:
                    start_idx = protected.find(c)
                    prefix = protected[:start_idx]
                    paren_open = prefix.count('(')
                    paren_close = prefix.count(')')
                    has_anchor = "[CAS_ANCHOR]" in prefix
                    print(f"      - 매칭 '{c}': prefix_paren({paren_open}/{paren_close}), anchor_in_prefix({has_anchor})")

    doc.close()

if __name__ == "__main__":
    debug_extraction()
