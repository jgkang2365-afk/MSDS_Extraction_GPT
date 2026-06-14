import os

path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\smu_gui.py"
output_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\scratch\find_render_rows.txt"

with open(path, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

# add_result_to_table(self, data) 함수 위치(5500라인)부터 150줄 저장
with open(output_path, 'w', encoding='utf-8') as out:
    for idx in range(5499, min(len(lines), 5650)):
        out.write(f"Line {idx+1}: {lines[idx]}")

print("Done")
