import os
import re

file_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v5.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix bloated newlines (multiple \n\n or \r\r\n)
# This usually happens when \r\n is read as \n and written as \r\n again or similar.
# We'll normalize to single \n first.
normalized = content.replace('\r\n', '\n').replace('\r', '\n')
# Remove triple+ newlines and replace double newlines that look like bloat
# Actually, let's just replace all sequences of 2+ newlines with \n\n (standard)
# But wait, the previous view showed lines like 1, 3, 5, 7 having code and 2, 4, 6, 8 being empty.
# This means every line got an extra newline.
lines = normalized.split('\n')
if len(lines) > 1000: # Heuristic for bloat
    new_lines = []
    for i in range(len(lines)):
        # If line is empty and previous line was not empty, and next line is not empty... 
        # Actually, let's just take non-empty lines and add \n where appropriate? 
        # No, let's just remove the "bloat" newlines.
        # If we have [Code, Empty, Code, Empty...], we want [Code, Code...]
        if i % 2 == 0:
            new_lines.append(lines[i])
        else:
            if lines[i].strip() != "": # If the "empty" line actually has content, something is wrong
                new_lines.append(lines[i])
    fixed_content = '\n'.join(new_lines)
else:
    fixed_content = normalized

# 2. Fix the backslash issue in the sniper log
# Target: current_sniper[\'alias\']
fixed_content = fixed_content.replace(r"current_sniper[\'alias\']", "current_sniper['alias']")
fixed_content = fixed_content.replace(r"\'알수없음\'", "'알수없음'")

# 3. Final cleanup: normalize line endings to \r\n for Windows
final_content = fixed_content.replace('\n', '\r\n')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(final_content)

print(f"Successfully fixed msds_engine_v5.py. New line count: {len(final_content.splitlines())}")
