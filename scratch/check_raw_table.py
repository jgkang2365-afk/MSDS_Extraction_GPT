import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))
import fitz

# 인코딩 강제
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

pdf_path = r"TEST_File/035_아이생각수성내부프로 (M-BASE)_GHS국문.pdf"
doc = fitz.open(pdf_path)
page = doc[0]
words = page.get_text("words")

# 표 영역 전체 덤프 (100 ~ 800)
table_words = [w for w in words if 100 <= w[1] <= 800]
table_words.sort(key=lambda w: (w[1], w[0]))

print("--- 표 영역 단어 상세 덤프 (y, x0, x1, text) ---")
for w in table_words:
    print(f"y_center={((w[1]+w[3])/2):.1f} | x_range=({w[0]:.1f}~{w[2]:.1f}) | {w[4]}")
doc.close()
