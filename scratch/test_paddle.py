import sys
import os
import gc

_OCR_ENGINE = None

def get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from paddleocr import PaddleOCR
        _OCR_ENGINE = PaddleOCR(lang='korean')
    return _OCR_ENGINE

def test():
    engine = get_ocr_engine()
    print("[*] PaddleOCR loaded successfully.")
    
    import numpy as np
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    
    # 더미 이미지에 글자가 없으므로 빈 리스트가 나올 수 있지만, 구조를 확인하기 위해 헬퍼 출력
    res = engine.predict(dummy_img)
    print("[*] OCR Result type:", type(res))
    print("[*] OCR Result:", res)
    
    gc.collect()
    print("[*] Garbage collection completed.")

if __name__ == "__main__":
    test()
