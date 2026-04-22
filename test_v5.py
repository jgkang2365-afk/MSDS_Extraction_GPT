import msds_engine_v5
import os

def test_v5():
    base_folder = os.path.join(os.getcwd(), "원료 MSDS_사용량 현황과 매칭")
    test_files = [
        "1014_Salicylic Acid_MSDS(K)_240509.pdf",
        "3011_HCO-60 MSDS KOR.pdf",
        "1007_GHS-MSDS(Sallitoin,KOR).pdf"
    ]
    
    for filename in test_files:
        pdf_path = os.path.join(base_folder, filename)
        
        if not os.path.exists(pdf_path):
            print(f"\n❌ 파일을 찾을 수 없습니다: {filename}")
            continue

        print(f"\n--- [V5.0 Engine Test: {filename}] ---")
        
        try:
            # 엔진 실행
            result = msds_engine_v5.process_pdf(pdf_path, log_func=None)
            
            print(f"제품명: {result.get('제품명')}")
            print(f"함유량: {result.get('함유량')}")
            print(f"신뢰도: {result.get('신뢰도')}")
            print(f"신호등: {result.get('신호등')}")
            print(f"추론근거: {result.get('추론근거')}")
            
        except Exception as e:
            print(f"테스트 중 오류 발생 ({filename}): {e}")

if __name__ == "__main__":
    test_v5()
