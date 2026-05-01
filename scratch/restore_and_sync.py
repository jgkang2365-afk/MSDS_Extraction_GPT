import os
import re

file_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v5.py'

with open(file_path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

# 1. Normalize and de-bloat
# Replace all \r\n with \n
content = content.replace('\r\n', '\n').replace('\r', '\n')
lines = content.split('\n')

if len(lines) > 800: # Bloat detected
    new_lines = []
    # If the file has Code, Empty, Code, Empty...
    # We'll check if every other line is empty
    empty_count = sum(1 for l in lines[1::2] if not l.strip())
    if empty_count > len(lines) // 3:
        print(f"Bloat confirmed. Cleaning up {len(lines)} lines.")
        # Take only even lines if they follow the pattern
        # But wait, it might not be perfect. Let's just remove multiple empty lines.
        # Safer: just remove lines that are purely empty if they are between non-empty lines
        # OR just normalize the whole thing.
        # Let's try the simple "every other line" if it looks consistent.
        new_lines = lines[::2]
        content = '\n'.join(new_lines)
    else:
        # Just collapse multiple newlines
        content = re.sub(r'\n{3,}', '\n\n', content)

# 2. Re-apply Sniper Sync (Ensuring it's there once)
# Remove any existing [수술 2] or duplicates first to be safe
content = re.sub(r'# 1\. Section 3 이미지 추출 전 동기화\n\s*current_sniper = get_next_sniper\(\)\n\s*', '', content)
content = re.sub(r'# 2\. 제품명 스캔 시작 전 최신 스나이퍼 호출\n\s*current_sniper = get_next_sniper\(\)\n\s*', '', content)

# Apply fixes
# 1. Before extract_section3_images
content = re.sub(r'(image_list, section3_text_for_omission = extract_section3_images\(pdf_path, current_sniper, log_func=log_func\))', 
                 r'# 1. Section 3 이미지 추출 전 동기화\n    current_sniper = get_next_sniper()\n    \1', content)

# 2. Before extract_product_name_hybrid
content = re.sub(r'(hybrid_pn, _ = extract_product_name_hybrid\(first_page_text, cover_img, current_sniper, log_func=log_func\))', 
                 r'# 2. 제품명 스캔 시작 전 최신 스나이퍼 호출\n    current_sniper = get_next_sniper()\n    \1', content)

# 3. Before call_gemini_2_5_flash (already there or need update?)
# We already have [수술 2] in some places. Let's make it consistent.
if '# [수술 2] 호출 직전에 글로벌 탄창 상태를 반영하여 최신 스나이퍼를 다시 배정' not in content:
    content = re.sub(r'(# 3\. 1차 스나이퍼\(Flash\) 투입\s+)(if log_func: log_func\(f" 🎯 1차 고속 스나이퍼\(.*\) 투입"\))', 
                     r'\1# [수술 2] 호출 직전에 글로벌 탄창 상태를 반영하여 최신 스나이퍼를 다시 배정\n    current_sniper = get_next_sniper()\n    \2', content)

# 4. Final Cleanup: Ensure no backslash in sniper log
content = content.replace(r"current_sniper[\'alias\']", "current_sniper['alias']").replace(r"\'알수없음\'", "'알수없음'")

# Write back with Windows line endings
with open(file_path, 'w', encoding='utf-8', newline='\r\n') as f:
    f.write(content)

print(f"Successfully restored and synced engine. Lines: {len(content.splitlines())}")
