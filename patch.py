import re

filepath = r"msds_engine_v5.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

old = """        # 4번 항이 나오면 탐색 종료 (3번 항이 여러 페이지일 경우 대비)
        elif pages and re.search(r'4\\.\\s*응급|SECTION\\s*4|4\\s*:\\s*FIRST', text, re.I):
            break"""

new = """        # 4번 항이 나오면 해당 페이지까지 포함 후 탐색 종료
        # (Section 3 제목이 이전 페이지, 표 본체가 이 페이지에 있는 경우 대비)
        if pages and re.search(r'4\\.\\s*응급|SECTION\\s*4|4\\s*:\\s*FIRST', text, re.I):
            if i not in pages:
                pages.append(i)
            break"""

if old in content:
    content = content.replace(old, new)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: patch applied")
else:
    print("FAIL: old text not found")
    # Debug: show lines around 230
    lines = content.split('\n')
    for idx in range(228, 235):
        if idx < len(lines):
            print(f"Line {idx+1}: {repr(lines[idx])}")
