import sys
import os

# 모듈 경로 추가
sys.path.append(r'c:\Users\USER\Desktop\프로젝트\MSDS_EXtaction_V3(v24+GUI통합)')

from msds_engine_v6 import self_test_regression

print("[*] self_test_regression 유닛 테스트를 기동합니다.")
try:
    self_test_regression()
    print("\n🟢 [유닛 테스트 결과] 모든 회귀 테스트가 정상(True) 완료되었습니다.")
except Exception as e:
    import traceback
    traceback.print_exc()
    print("\n🔴 [유닛 테스트 결과] 테스트 중 오류가 발견되었습니다.")
