import sys
import os

# 부모 디렉토리를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import process_pdf

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\021_RED(적색)227_MSDS(E)_190730.pdf"

print("==================================================")
print(f"[*] 21번 파일 테스트 격발: {os.path.basename(pdf_path)}")
print("==================================================")

try:
    res = process_pdf(pdf_path, log_func=print)
    print("\n================== [최종 결과] ==================")
    print(f"제품명   : {res.get('제품명')}")
    print(f"신호등   : {res.get('신호등')}")
    print(f"매칭엔진 : {res.get('used_engine')}")
    print(f"무결성 점수 : {res.get('integrity_score')}점")
    print(f"무결성 사유 : {res.get('integrity_reason')}")
    print(f"구성성분 : {res.get('구성성분')}")
    print("==================================================")
except Exception as e:
    import traceback
    traceback.print_exc()
