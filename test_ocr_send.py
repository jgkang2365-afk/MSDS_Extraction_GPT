import os
import requests
import fitz

# 1. 환경 설정 (전송 경로 및 파일 위치 확정)
SERVER_URL = "https://inclusive-work-reserves-mls.trycloudflare.com/ocr_process"
FILE_PATH = r"C:\Users\USER\Desktop\안티그래비티\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\005_★SUPER WAY LUBE 32.pdf"

print(f"[파일 검증] {FILE_PATH} 존재 여부 확인 중...")

# 2. 파일 물리적 존재 검증
if not os.path.exists(FILE_PATH):
    print("[실패] 지정한 경로에 피디에프 파일이 존재하지 않습니다. 경로명을 다시 확인해 주세요.")
else:
    print("[성공] 파일 실물 확인 완료. 전송 준비를 개시합니다.")
    try:
        # 피디에프 문서 열기
        doc = fitz.open(FILE_PATH)
        total_pages = len(doc)
        print(f"[문서 분석] 총 {total_pages}개의 쪽이 탐색되었습니다. 순차 전송을 개시합니다.")
        
        # 각 쪽을 이미지로 변환하여 깡통 컴퓨터로 전송
        for i in range(total_pages):
            page = doc[i]
            print(f"[처리 중] {i+1}번째 쪽 이미지 변환 및 전송 준비 중...")
            
            # 해상도를 조절하여 변환 (연산량 감축을 통한 시간 초과 방지)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
            img_bytes = pix.tobytes("png")
            
            # 다중 부분 양식 데이터 포장 (이미지 전용 형식 지정)
            files = {"image_file": (f"page_{i+1}.png", img_bytes, "image/png")}
            print(f"[전송] 수송 주소 {SERVER_URL} 로 {i+1}번째 쪽 이미지 전송 중...")
            
            # 제한 시간 백팔십 초 설정
            response = requests.post(SERVER_URL, files=files, timeout=180)
            response.raise_for_status()
            
            res_json = response.json()
            if res_json.get("status") == "SUCCESS":
                print(f"[성공] {i+1}번째 쪽 판독 결과가 성공적으로 수납되었습니다.")
                print("=" * 80)
                print(res_json.get("raw_data", ""))
                print("=" * 80)
            else:
                print(f"[실패] {i+1}번째 쪽 서버 처리 오류: {res_json.get('reason')}")
        
        doc.close()
        print("[완료] 모든 쪽에 대한 오씨알 판독 전송이 종료되었습니다.")
        
    except requests.exceptions.Timeout:
        print("[통신 실패] 깡통 컴퓨터가 백팔십 초 이내에 분석 결과를 반환하지 못했습니다. (시간 초과)")
    except requests.exceptions.ConnectionError:
        print("[통신 실패] 터널 통로가 차단되었습니다. 깡통 컴퓨터에서 실행 프로그램이 정상 작동 중인지 확인하세요.")
    except Exception as e:
        print(f"[오작동] 데이터 수송 중 오류가 발생했습니다: {e}")
