import sys

file_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\smu_gui.py"
output_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\scratch\find_buttons_output.txt"

encodings = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'utf-16']
correct_encoding = None
lines = []

for enc in encodings:
    try:
        with open(file_path, 'r', encoding=enc) as f:
            lines = f.readlines()
            correct_encoding = enc
            print(f"Successfully read with {enc}")
            break
    except Exception as e:
        print(f"Failed to read with {enc}: {e}")

if not correct_encoding:
    print("Failed to read with all encodings.")
    sys.exit(1)

with open(output_path, 'w', encoding='utf-8') as out:
    out.write(f"Encoding: {correct_encoding}\n")
    for i, line in enumerate(lines, 1):
        line_lower = line.lower()
        # QPushButton, 새로, 초기화, refresh, reload, reset
        match = False
        if "qpushbutton" in line_lower:
            match = True
        for k in ["새로", "초기화", "refresh", "reload", "reset", "새로고침"]:
            if k in line:
                match = True
                break
        
        if match:
            out.write(f"Line {i}: {line.strip()}\n")

print("Finished. Results written to scratch/find_buttons_output.txt")
