# -*- coding: utf-8 -*-
import os
import sys
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(override=True)

# 한국어 인코딩 설정
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import msds_engine_v5

# 1. 40번 자재 검증
pdf_path_40 = os.path.join("TEST_File", "040_Giemsa SDS.pdf")
print("==================================================")
print(f"[*] [검증 1] 40번 자재 가동 시작: {pdf_path_40}")
res_40 = msds_engine_v5.process_pdf(pdf_path_40, log_func=print)
print("\n[40번 최종 결과]")
print(f"├─ 제품명: {res_40.get('제품명')}")
print(f"├─ 신호등: {res_40.get('신호등')}")
print(f"└─ 구성성분: {res_40.get('구성성분')}")
print("==================================================")

# 2. 41번 자재 검증
pdf_path_41 = os.path.join("TEST_File", "041_페놀(PHENOL).pdf")
print(f"\n[*] [검증 2] 41번 자재 가동 시작: {pdf_path_41}")
res_41 = msds_engine_v5.process_pdf(pdf_path_41, log_func=print)
print("\n[41번 최종 결과]")
print(f"├─ 제품명: {res_41.get('제품명')}")
print(f"├─ 신호등: {res_41.get('신호등')}")
print(f"└─ 구성성분: {res_41.get('구성성분')}")
print("==================================================")
