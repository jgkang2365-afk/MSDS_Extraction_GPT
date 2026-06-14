import os

path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v5.py"
output_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\scratch\find_retry_func.txt"

with open(path, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

with open(output_path, 'w', encoding='utf-8') as out:
    for i, line in enumerate(lines, 1):
        if "def call_gemini_with_retry" in line:
            out.write(f"Line {i}: {line.strip()}\n")
            # 함수 내용 약 40줄 쓰기
            for idx in range(i - 1, min(len(lines), i + 40)):
                out.write(f"  [{idx+1}] {lines[idx]}")

print("Done")
