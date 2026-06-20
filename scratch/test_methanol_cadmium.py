# 파일 경로 확인 및 테스트 실행 스크립트
import os
import sys

# 상위 디렉토리를 경로에 추가하여 엔진 모듈을 불러올 수 있도록 합니다
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import process_pdf

def 단독_테스트_실행():
    작업_디렉토리 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    테스트_폴더 = os.path.join(작업_디렉토리, "TEST_File")
    
    카드뮴_파일 = os.path.join(테스트_폴더, "002_(O)011_SDS_ICP-08N-1(Cd).pdf")
    포름알데하이드_파일 = os.path.join(테스트_폴더, "010_포름알데하이드_시그마.pdf")
    메탄올_파일 = os.path.join(테스트_폴더, "031_Methanol.pdf")
    
    print("\n[테스트 1] 카드뮴 자재 단독 추출 결과 검증")
    if os.path.exists(카드뮴_파일):
        결과 = process_pdf(카드뮴_파일, log_func=print)
        print(f"카드뮴 결과 제품명: {결과.get('제품명')}")
        print(f"카드뮴 결과 구성성분: {결과.get('구성성분')}")
        print(f"카드뮴 결과 신호등: {결과.get('신호등')}")
    else:
        print("카드뮴 파일이 존재하지 않습니다.")

    print("\n[테스트 2] 포름알데하이드 자재 단독 추출 결과 검증")
    if os.path.exists(포름알데하이드_파일):
        결과 = process_pdf(포름알데하이드_파일, log_func=print)
        print(f"포름알데하이드 결과 제품명: {결과.get('제품명')}")
        print(f"포름알데하이드 결과 구성성분: {결과.get('구성성분')}")
        print(f"포름알데하이드 결과 신호등: {결과.get('신호등')}")
    else:
        print("포름알데하이드 파일이 존재하지 않습니다.")
        
    print("\n[테스트 3] 메탄올 자재 단독 추출 결과 검증")
    if os.path.exists(메탄올_파일):
        결과 = process_pdf(메탄올_파일, log_func=print)
        print(f"메탄올 결과 제품명: {결과.get('제품명')}")
        print(f"메탄올 결과 구성성분: {결과.get('구성성분')}")
        print(f"메탄올 결과 신호등: {결과.get('신호등')}")
    else:
        print("메탄올 파일이 존재하지 않습니다.")

if __name__ == "__main__":
    단독_테스트_실행()
