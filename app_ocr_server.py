import os
import gc
import asyncio
from fastapi import FastAPI, UploadFile, File
import uvicorn
import numpy as np
from paddleocr import PPStructureV3
from PIL import Image
import io

# 🛡️ [데이터 검증 및 에러 예외 처리 - 12기가바이트 맞춤형 자원 격리]
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"

app = FastAPI(title="MSDS 12기가바이트 로컬 비전 인공지능 가속 서버")
processing_lock = asyncio.Lock()

print("[*] [선제 상시 예열] 12기가바이트 메모리 영토에 패들오씨알(PaddleOCR) 신경망 주입 중...")
GLOBAL_PADDLE_ENGINE = PPStructureV3(
    lang='korean',
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_seal_recognition=False,
    use_formula_recognition=False,
    use_chart_recognition=False,
)
print("🟢 [준비 완료] 비전 인공지능 엔진 예열 완료. 정밀 사진 조각 수송선 대기 중.")

@app.post("/ocr_process")
async def ocr_process(image_file: UploadFile = File(...)):
    # 6인 동시 인입 시 안전 대기열 락 격발 (한 명씩 차례대로 조업)
    async with processing_lock:
        try:
            # 🛡️ [데이터 무결성 - 파일 스트림 공란 가드]
            img_bytes = await image_file.read()
            if not img_bytes:
                return {"status": "ERROR", "reason": "인입된 파일 스트림이 공란입니다. (수납 무결성 실패)"}
                
            image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            img_np = np.array(image)
            
            # 내 컴퓨터가 정밀하게 조준 재단해 보낸 이미지 조각 그대로 표 구조 복구 격발
            results = GLOBAL_PADDLE_ENGINE.predict(
                img_np, 
                use_table_recognition=True,
                use_wired_table_cells_trans_to_html=True,
                use_wireless_table_cells_trans_to_html=True
            )
            
            html_results = []
            for res in results:
                html_dict = getattr(res, 'html', {}) or {}
                for table_key, html_str in html_dict.items():
                    if html_str and html_str.strip():
                        html_results.append(html_str)
            
            combined_html = "\n".join(html_results)
            return {"status": "SUCCESS", "raw_data": combined_html}
            
        except Exception as e:
            return {"status": "ERROR", "reason": f"원격 가속 서버 내부 장애 발생: {str(e)}"}
            
        finally:
            # 가비지 컬렉터 강제 구동으로 12기가바이트 깡통컴 메모리 잔상 원천 세척
            gc.collect()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
