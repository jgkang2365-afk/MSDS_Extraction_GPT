import re

engine_file = r"c:\Users\USER\Desktop\안티그래비티\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v6.py"

with open(engine_file, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# clean_content_text 가 사용된 위치 찾기
matches = [m.start() for m in re.finditer(r'clean_content_text', content)]
print(f"clean_content_text found {len(matches)} times:")
for m in matches:
    # 해당 위치의 줄 번호 계산
    line_no = content[:m].count('\n') + 1
    # 주변 5줄 출력
    lines = content.split('\n')
    start_l = max(0, line_no - 4)
    end_l = min(len(lines), line_no + 4)
    print(f"--- Line {line_no} ---")
    for l_idx in range(start_l, end_l):
        print(f"{l_idx+1}: {lines[l_idx]}")

# normalize_text 가 사용된 위치 찾기
matches_norm = [m.start() for m in re.finditer(r'normalize_text', content)]
print(f"\nnormalize_text found {len(matches_norm)} times:")
for m in matches_norm:
    line_no = content[:m].count('\n') + 1
    lines = content.split('\n')
    start_l = max(0, line_no - 4)
    end_l = min(len(lines), line_no + 4)
    print(f"--- Line {line_no} ---")
    for l_idx in range(start_l, end_l):
        print(f"{l_idx+1}: {lines[l_idx]}")
