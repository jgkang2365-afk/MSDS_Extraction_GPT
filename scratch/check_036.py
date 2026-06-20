import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import glob
from msds_engine_v5 import MSDSEngineV5

test_file_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "TEST_File")
files_036 = glob.glob(os.path.join(test_file_dir, "*036*.pdf"))
if files_036:
    file_path = files_036[0]
    print("대상 파일:", os.path.basename(file_path))
    engine = MSDSEngineV5()
    res = engine.process_msds_pipeline(file_path, log_func=print)
    print("\n--- v5 결과 ---")
    print("제품명:", res.get("제품명"))
    print("신호등:", res.get("신호등"))
    print("구성성분:", res.get("구성성분"))
else:
    print("036번 파일을 찾을 수 없습니다.")
