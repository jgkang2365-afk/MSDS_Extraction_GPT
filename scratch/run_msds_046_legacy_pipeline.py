import sys
import os
import json

# workspace root를 sys.path 최상단에 추가하여 로컬 모듈 및 패키지 로딩을 보장
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, workspace_root)

# msds_engine_v6.py를 읽고 Fast-Track 부분을 비활성화하여 임시 파일로 작성
with open(os.path.join(workspace_root, "msds_engine_v6.py"), "r", encoding="utf-8") as f:
    lines = f.readlines()

# 651라인부터 750라인까지를 주석 처리 (1-indexed이므로 index는 650부터 749까지)
for idx in range(650, 750):
    lines[idx] = "# " + lines[idx]

temp_engine_path = os.path.join(workspace_root, "msds_engine_v6_temp.py")
with open(temp_engine_path, "w", encoding="utf-8") as f:
    f.writelines(lines)

# 임시 엔진 모듈 임포트
from msds_engine_v6_temp import MSDSEngineV6

def log_func(msg):
    print(f"[ENGINE LOG] {msg}")

engine = MSDSEngineV6()
pdf_path = r"TEST_File/046_★THF_MSDS.pdf"
print(f"Starting legacy pipeline test for: {pdf_path}")
result = engine.process_msds_pipeline(pdf_path, log_func=log_func)

print("\n--- LEGACY PIPELINE EXTRACTION RESULT ---")
print(json.dumps(result, indent=2, ensure_ascii=False))

# 사용이 끝난 임시 파일 삭제
try:
    os.remove(temp_engine_path)
except Exception as e:
    pass
