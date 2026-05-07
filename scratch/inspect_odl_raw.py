import os
import sys

# 부모 디렉토리를 경로에 추가하여 opendataloader를 찾을 수 있게 함
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opendataloader.pdf import PDFParser

# 인코딩 설정
import io
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pdf_path = os.path.join(base_dir, "013_아이생각수성내부프로 (M-BASE)_GHS국문.pdf")

if not os.path.exists(pdf_path):
    print(f"파일이 없습니다: {pdf_path}")
    sys.exit(1)

try:
    parser = PDFParser()
    doc = parser.parse(pdf_path)
    
    print(f"\n--- [ODL 원본 데이터 분석: {pdf_path}] ---")
    for p_idx in range(min(6, len(doc.pages))):
        page = doc.pages[p_idx]
        print(f"\n[Page {p_idx}]")
        tables = [el for el in getattr(page, 'elements', []) if getattr(el, 'type', '') == "TABLE"]
        if not tables:
            print("  (표 없음)")
        else:
            for t_idx, table in enumerate(tables):
                print(f"  [Table {t_idx}]")
                for r_idx, row in enumerate(table.rows):
                    if r_idx >= 20: 
                        print(f"    ... (생략: 총 {len(table.rows)}행)")
                        break
                    row_texts = [c.text or "" for c in row.cells]
                    print(f"    Row {r_idx}: {row_texts}")
except Exception as e:
    print(f"오류 발생: {e}")
