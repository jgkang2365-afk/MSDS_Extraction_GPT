import sys

file_path = 'msds_engine_v5.py'
with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# 1. Fix the corrupted block in final_quality_control
start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if 'for v_cas in valid_text_cas:' in line and i > 300:
        start_idx = i
    if 'if cv:' in line and start_idx != -1 and i > start_idx:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    print(f"Found corruption between line {start_idx+1} and {end_idx+1}")
    new_block = [
        '                for v_cas in valid_text_cas:\n',
        '                    # 1글자만 틀린 경우 (AI 오타 방어)\n',
        '                    diff_count = sum(1 for a, b in zip(cas, v_cas) if a != b) if len(cas) == len(v_cas) else 99\n',
        '                    if diff_count <= 1:\n',
        '                        cas = v_cas\n',
        '                        break\n',
        '                else:\n',
        '                    if log_func: log_func(f" 🔴 [Fuzzy 방어] 3단계 퍼지 쉴드 붕괴. 환각 CAS 영구 폐기: {cas}")\n',
        '                    has_invalid = True\n',
        '                    continue \n',
        '\n'
    ]
    lines[start_idx:end_idx] = new_block
else:
    print("Error: Could not find markers for corruption fix.")

# 2. Update Version
for i, line in enumerate(lines):
    if 'VERSION =' in line:
        lines[i] = 'VERSION = "17.3.2.0" # 광대역 윈도우 스캔 및 [CAS-함량] 정밀 매칭 (성분명 추출 제외)\n'
        break

# 3. Update find_section3_pages for robustness
# Find the start of find_section3_pages
find_s3_idx = -1
for i, line in enumerate(lines):
    if 'def find_section3_pages(doc):' in line:
        find_s3_idx = i
        break

if find_s3_idx != -1:
    # We'll update the starting check to be more liberal
    for i in range(find_s3_idx, find_s3_idx + 20):
        if "if re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:구성성분|COMPOSITION|INGREDIENTS)', text, re.I):" in lines[i]:
            lines[i] = "            if re.search(r'(?:SECTION\s*)?[23][\s.:]*(?:구성성분|성분|성분\s?및\s?함량|COMPOSITION|INGREDIENTS)', text, re.I):\n"
            break

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Successfully applied fixes to msds_engine_v5.py")
