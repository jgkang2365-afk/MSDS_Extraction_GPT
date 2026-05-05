
import re
import os

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def get_no_val(fn):
    match_no = re.match(r"^(\d+)", fn)
    if match_no:
        return f"{int(match_no.group(1)):03d}"
    else:
        return "999"

# Test Case 1: Unordered list of filenames
test_files = [
    "10_Hydrochloric_acid.pdf",
    "2_Dinitrophenyl.pdf",
    "001_Dolphin_detergent.pdf",
    "5_Something.pdf",
    "20_Another.pdf"
]

print("--- 원본 목록 ---")
for f in test_files:
    print(f)

# Simulation: Sort like the new GUI logic
sorted_files = sorted(test_files, key=lambda x: natural_sort_key(os.path.basename(x)))

print("\n--- Natural Sort 결과 (GUI 목록) ---")
for f in sorted_files:
    print(f)

print("\n--- No열 추출 결과 (제로 패딩) ---")
for f in sorted_files:
    print(f"[{f}] -> No: {get_no_val(f)}")

# Simulation: Table sorting by No column
table_items = []
for f in sorted_files:
    table_items.append({
        "no": get_no_val(f),
        "filename": f
    })

# String sorting on "no" field
final_sorted_table = sorted(table_items, key=lambda x: x["no"])

print("\n--- 최종 테이블 정렬 결과 (No열 기준) ---")
for item in final_sorted_table:
    print(f"No: {item['no']} | File: {item['filename']}")
