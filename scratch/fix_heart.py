import os
import re

file_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v5.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# [심장 수술] process_pdf 내부 스나이퍼 강제 동기화

# 1. extract_section3_images 전 (L548-550 근처)
# Target: image_list, section3_text_for_omission = extract_section3_images(pdf_path, current_sniper, log_func=log_func)
pattern1 = r'(image_list, section3_text_for_omission = extract_section3_images\(pdf_path, current_sniper, log_func=log_func\))'
replacement1 = r'# 1. Section 3 이미지 추출 전 동기화\n    current_sniper = get_next_sniper()\n    \1'

# 2. extract_product_name_hybrid 전 (L572 근처)
# Target: hybrid_pn, _ = extract_product_name_hybrid(first_page_text, cover_img, current_sniper, log_func=log_func)
pattern2 = r'(hybrid_pn, _ = extract_product_name_hybrid\(first_page_text, cover_img, current_sniper, log_func=log_func\))'
replacement2 = r'# 2. 제품명 스캔 시작 전 최신 스나이퍼 호출\n    current_sniper = get_next_sniper()\n    \1'

# 3. call_gemini_2_5_flash 전 (이미 수술했지만 중복 방지 및 확인)
# (이미 get_next_sniper()가 추가되어 있는 상태)

temp_content = re.sub(pattern1, replacement1, content)
new_content = re.sub(pattern2, replacement2, temp_content)

if new_content != content:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully synchronized snipers in process_pdf")
else:
    print("Failed to synchronize. Checking literal match.")
    # Fallback to literal if regex fails
    if 'extract_section3_images' in content and 'extract_product_name_hybrid' in content:
         print("Found targets, but regex failed. Manual replace needed.")
    else:
         print("Targets not found.")
