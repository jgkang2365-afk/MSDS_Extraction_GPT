import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))
import fitz

pdf_path = r"TEST_File/035_아이생각수성내부프로 (M-BASE)_GHS국문.pdf"
doc = fitz.open(pdf_path)
page = doc[0]
raw_words = page.get_text("words")
raw_words.sort(key=lambda w: (w[1], w[0]))

def group_lines_improved(words):
    if not words: return []
    physical_lines = []
    
    current_line_words = [words[0]]
    line_top = words[0][1]    
    line_bottom = words[0][3] 
    init_line_height = line_bottom - line_top # 최초 줄 높이 고정

    for i in range(1, len(words)):
        curr_w = words[i]
        curr_top = curr_w[1]
        curr_bottom = curr_w[3]
        curr_height = curr_bottom - curr_top

        overlap = max(0, min(line_bottom, curr_bottom) - max(line_top, curr_top))

        # line_height가 무한히 팽창하는 것을 막기 위해 고정된 init_line_height를 기준으로 삼거나,
        # 현재 단어의 높이(curr_height)를 기준으로 임계치 비교
        # 팽창 한계 가드: line_bottom - line_top이 글자 크기(init_line_height)의 2.5배를 초과하면 무조건 새 라인으로 분리
        is_height_safe = (line_bottom - line_top) < (init_line_height * 2.5)

        if is_height_safe and (overlap > (init_line_height * 0.2) or abs(curr_top - line_top) <= (init_line_height * 0.8) or abs(curr_bottom - line_bottom) <= (init_line_height * 0.8)):
            current_line_words.append(curr_w)
            line_bottom = max(line_bottom, curr_bottom)
            line_top = min(line_top, curr_top)
            # line_height 갱신을 하더라도 임계치 팽창 비교는 init_line_height를 기준으로 함
        else:
            current_line_words.sort(key=lambda w: w[0])
            physical_lines.append({
                "y": line_top,
                "text": " ".join([w[4] for w in current_line_words]),
            })
            current_line_words = [curr_w]
            line_top = curr_w[1]
            line_bottom = curr_w[3]
            init_line_height = line_bottom - line_top

    if current_line_words:
        current_line_words.sort(key=lambda w: w[0])
        physical_lines.append({
            "y": line_top,
            "text": " ".join([w[4] for w in current_line_words]),
        })
    return physical_lines

lines = group_lines_improved(raw_words)
# 500 ~ 800 부근의 라인들 덤프
print("--- 개선된 줄 분리 결과 ---")
for pl in lines:
    if 500 <= pl["y"] <= 800:
        print(f"Y={pl['y']:.1f} | {pl['text']}")
doc.close()
