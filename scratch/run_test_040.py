# -*- coding: utf-8 -*-
import os
import sys
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(override=True)

# 한국어 출력 보장
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# 모듈 로드
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import msds_engine_v5

pdf_path = os.path.join("TEST_File", "040_Giemsa SDS.pdf")
print(f"[*] 테스트 자재 가동 시작: {pdf_path}")
res = msds_engine_v5.process_pdf(pdf_path, log_func=print)
print("\n[*] 최종 결과 객체:")
print(res)
