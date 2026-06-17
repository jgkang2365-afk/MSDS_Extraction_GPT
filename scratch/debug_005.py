import sys
import os
import re

# msds_engine_v5 임포트가 가능하도록 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from msds_engine_v5 import run_flexible_sandwich_pipeline, get_paddle_structure_engine, verify_mathematical_천칭_filter
import glob

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
test_file_dir = os.path.join(base_dir, "TEST_File")
files_005 = glob.glob(os.path.join(test_file_dir, "*005*.pdf"))

if files_005:
    pdf_path = files_005[0]
    paddle_ocr_instance = get_paddle_structure_engine(log_func=print)
    
    print("--- 005번 자재 파이프라인 수동 구동 ---")
    res = run_flexible_sandwich_pipeline(pdf_path, paddle_ocr_instance, log_func=print)
    print("결과 status:", res.get("status"))
    print("결과 engine:", res.get("engine"))
    
    # 005번 자재의 실제 로컬 OCR 원본 텍스트 확인을 위해 PDF로부터 텍스트 수집하는 부분 직접 실행
    import fitz
    import base64
    from msds_engine_v5 import extract_table_via_local_ocr
    doc = fitz.open(pdf_path)
    page = doc[0]
    w, h = page.rect.width, page.rect.height
    crop_rect = fitz.Rect(0, 190, w, 525)  # 005번 자재 샌드위치 재단 높이
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=crop_rect)
    cropped_bytes = pix.tobytes("png")
    cropped_b64 = base64.b64encode(cropped_bytes).decode("utf-8")
    cropped_image_list = [{"data": cropped_b64, "mime_type": "image/png"}]
    local_raw_text = extract_table_via_local_ocr(cropped_image_list, log_func=print)
    doc.close()
    
    print("\n--- 005번 자재 실제 로컬 OCR 텍스트 ---")
    print(repr(local_raw_text))
    
    is_clean, reason = verify_mathematical_천칭_filter(local_raw_text)
    print("\nverify_mathematical_천칭_filter 결과:", is_clean, f"({reason})")
else:
    print("005번 자재가 없습니다.")
