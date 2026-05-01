import os

file_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v5_utf8.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """    # 2. 추출 데이터도 중복으로 찢어진 행을 감안해 고유 CAS 종류만 카운트
    if isinstance(extracted_data, list):
        # [V15.8.10 핵심 수술] 'cas'와 'cas_no' Key를 모두 포용하여 자폭 버그 해결
        extracted_cas_set = set([c.get("cas") or c.get("cas_no") for c in extracted_data if c.get("cas") or c.get("cas_no")])
        extracted_cas_count = len(extracted_cas_set)
    else:
        extracted_cas_set = set([c.get("cas_no") for c in extracted_data.get("구성성분", []) if c.get("cas_no")])
        extracted_cas_count = len(extracted_cas_set)"""

replacement = """    # 2. 추출 데이터도 중복으로 찢어진 행을 감안해 고유 CAS 종류만 카운트
    if isinstance(extracted_data, list):
        # [V15.8.10 핵심 수술] 'cas'와 'cas_no' Key를 모두 포용하여 자폭 버그 해결
        extracted_cas_set = set([c.get("cas") or c.get("cas_no") for c in extracted_data if c.get("cas") or c.get("cas_no")])
        extracted_cas_count = len(extracted_cas_set)
    else:
        extracted_cas_set = set([c.get("cas_no") for c in extracted_data.get("구성성분", []) if c.get("cas_no")])
        extracted_cas_count = len(extracted_cas_set)"""

if target in content:
    new_content = content.replace(target, replacement)
    with open(r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v5.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Replacement successful.")
else:
    print("Target content not found in UTF-8 converted file.")
    # Show what we found around that area
    import re
    match = re.search(r'# 2\. 추출 데이터도 중복으로 찢어진 행을 감안해 고유 CAS 종류만 카운트', content)
    if match:
        start = max(0, match.start() - 100)
        end = min(len(content), match.end() + 500)
        print(f"Found area:\n{content[start:end]}")
