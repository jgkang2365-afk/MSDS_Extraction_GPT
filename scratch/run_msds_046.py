import sys
import os
import json

# engine_v6를 임포트하기 위해 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from msds_engine_v6 import MSDSEngineV6

def log_func(msg):
    print(f"[ENGINE LOG] {msg}")

engine = MSDSEngineV6()
pdf_path = r"TEST_File/046_★THF_MSDS.pdf"
print(f"Starting test for: {pdf_path}")
result = engine.process_msds_pipeline(pdf_path, log_func=log_func)

print("\n--- EXTRACTION RESULT ---")
print(json.dumps(result, indent=2, ensure_ascii=False))
