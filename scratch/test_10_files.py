# 10개의 MSDS PDF 파일을 순차적으로 테스트하고 결과를 수집하여 예쁘게 출력하는 디버그 스크립트입니다.
import os
import sys

# 엔진 모듈 로드를 위해 상위 경로를 시스템 경로에 이식합니다.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v6 import process_pdf

def 십대_자재_검증_레이스():
    작업_디렉토리 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    테스트_폴더 = os.path.join(작업_디렉토리, "TEST_File")
    
    # 001번부터 010번까지의 파일 목록을 정의합니다.
    파일_목록 = [
        "001_(O)002_MSDS(보통휘발유(Regular Unleaded Gasoline)_SOIL)(O).pdf",
        "002_(O)011_SDS_ICP-08N-1(Cd).pdf",
        "003_(O)018_[K.S.PEARL] MSDS - Iron Oxide Red 3AS (KR).pdf",
        "004_(-)SHIKIMIC ACID.PDF",
        "005_★SUPER WAY LUBE 32.pdf",
        "006_MSDS(순앤수 우드스테인 BASE)(O).pdf",
        "007_MSDS(프로스테인)(O).pdf",
        "008_msds_사라퐁(O).pdf",
        "009_수피아물비누-MSDS(O).pdf",
        "010_포름알데하이드_시그마.pdf"
    ]
    
    결과_저장소 = []
    
    print("=" * 60)
    print("    [10대 자재 무결성 레이스 가동]    ")
    print("=" * 60)
    
    for 순번, 파일명 in enumerate(파일_목록, 1):
        파일_경로 = os.path.join(테스트_폴더, 파일명)
        print(f"\n[{순번}/10] 현재 처리 중: {filename if 'filename' in locals() else 파일명}")
        
        if not os.path.exists(파일_경or_경로 := 파일_경로):
            print(f" ❌ 오류: 파일이 존재하지 않습니다: {파일명}")
            continue
            
        try:
            추출_결과 = process_pdf(파일_경로, log_func=None)
            결과_저장소.append({
                "번호": f"{순번:03d}",
                "파일명": 파일명,
                "제품명": 추출_결과.get("제품명", "미상"),
                "신호등": 추출_결과.get("신호등", "⚪"),
                "엔진": 추출_결과.get("used_engine", "오류"),
                "구성성분": 추출_결과.get("구성성분", "미기재")
            })
            print(f" 🟢 완료: {추출_결과.get('제품명')} -> {추출_결과.get('신호등')}")
        except Exception as 예외:
            print(f" 🔴 크래시 발생: {예외}")
            결과_저장소.append({
                "번호": f"{순번:03d}",
                "파일명": 파일명,
                "제품명": "크래시 오류",
                "신호등": "🔴",
                "엔진": "error_isolation",
                "구성성분": str(예외)
            })
            
    print("\n" + "=" * 80)
    print("    [최종 10대 자재 추출 종합 결과 리포트]    ")
    print("=" * 80)
    템플릿 = "{:<6} | {:<20} | {:<4} | {:<10} | {}"
    print(템플릿.format("번호", "제품명(축약)", "신호", "엔진", "구성성분"))
    print("-" * 80)
    for 결과 in 결과_저장소:
        제품명_출력 = 결과["제품명"][:20]
        구성성분_출력 = 결과["구성성분"][:35] + "..." if len(결과["구성성분"]) > 35 else 결과["구성성분"]
        print(템플릿.format(결과["번호"], 제품명_출력, 결과["신호등"], 결과["엔진"], 구성성분_출력))
    print("=" * 80)

if __name__ == "__main__":
    십대_자재_검증_레이스()
