# -*- coding: utf-8 -*-
import sys
import os
import traceback

sys.path.append(os.getcwd())

from msds_engine_v6 import MSDSEngineV6

pdf_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\005_★SUPER WAY LUBE 32.pdf"
engine = MSDSEngineV6()

try:
    print("[*] 005번 자재 단독 테스트 시작")
    # 예외를 catch하지 않고 그대로 던지도록 process_msds_pipeline의 원본 구현 호출
    # process_msds_pipeline은 try-except로 감싸져있으므로 _process_msds_pipeline_impl을 직접 호출
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    res = engine._process_msds_pipeline_impl(pdf_path, pdf_bytes, log_func=print)
    print("[*] 결과 성공:", res)
except Exception as e:
    print("[CRITICAL] 예외 격발:")
    traceback.print_exc()
