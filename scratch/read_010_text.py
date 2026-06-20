# 010번 자재의 PDF 텍스트를 추출하여 내용을 분석하는 스크립트입니다.
import os
import fitz

def 텍스트_추출():
    작업_디렉토리 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    대상_파일 = os.path.join(작업_디렉토리, "TEST_File", "010_포름알데하이드_시그마.pdf")
    
    if os.path.exists(대상_파일):
        문서 = fitz.open(대상_파일)
        print(f"총 페이지 수: {len(문서)}")
        for 페이지_번호 in range(len(문서)):
            텍스트 = 문서[페이지_번호].get_text("text")
            if "67-56-1" in 텍스트 or "Methanol" in 텍스트 or "메탄올" in 텍스트:
                print(f"--- 페이지 {페이지_번호 + 1} ---")
                print(텍스트)
        문서.close()
    else:
        print("대상 파일이 없습니다.")

if __name__ == "__main__":
    텍스트_추출()
