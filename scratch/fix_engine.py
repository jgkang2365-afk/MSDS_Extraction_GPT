import os
import re

file_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v5.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# [수술 2] Sniper sync
# 🎯 1차 고속 스나이퍼(alias) 투입
pattern = r'(# 3\. 1차 스나이퍼\(Flash\) 투입\s+)(if log_func: log_func\(f" 🎯 1차 고속 스나이퍼\(\{alias\}\) 투입"\))'
replacement = r'\1# [수술 2] 호출 직전에 글로벌 탄창 상태를 반영하여 최신 스나이퍼를 다시 배정\n    current_sniper = get_next_sniper()\n    if log_func: log_func(f" 🎯 1차 고속 스나이퍼({current_sniper[\'alias\'] if current_sniper else \'알수없음\'}) 투입")'

new_content = re.sub(pattern, replacement, content)

if new_content == content:
    print("Match not found with regex. Trying literal match.")
    # Fallback to a simpler match
    literal_target = '    if log_func: log_func(f" 🎯 1차 고속 스나이퍼({alias}) 투입")'
    literal_replacement = '    # [수술 2] 호출 직전에 글로벌 탄창 상태를 반영하여 최신 스나이퍼를 다시 배정\n    current_sniper = get_next_sniper()\n    if log_func: log_func(f" 🎯 1차 고속 스나이퍼({current_sniper[\'alias\'] if current_sniper else \'알수없음\'}) 투입")'
    new_content = content.replace(literal_target, literal_replacement)

if new_content != content:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully updated msds_engine_v5.py")
else:
    print("Failed to update file.")
