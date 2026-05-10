import sys
import os
import json
import time

sys.path.append(os.getcwd())
import msds_engine_v5

def test_017_forced_ai():
    pdf_path = r"TEST_File\017_RED(적색)227_MSDS(E)_190730.pdf"
    print(f"[*] 17번 파일 AI 강제 투입 테스트 시작...")

    def log_print(msg):
        print(f"[*] {msg}")

    # process_pdf의 로직을 복사하되, AI를 강제로 타게 함
    # 실제로는 msds_engine_v5 내부의 is_scanned를 True로 간주하거나
    # ODL 결과를 무시하도록 테스트용 래퍼 작성
    
    # msds_engine_v5.py 내부의 process_pdf를 모방한 AI 전용 로직
    start_time = time.time()
    current_sniper = msds_engine_v5.get_next_sniper()
    alias = current_sniper["alias"]
    
    # 1. 이미지 및 텍스트 추출
    image_list, section3_text, pages = msds_engine_v5.extract_section3_images(pdf_path, current_sniper, log_func=log_print)
    
    # 2. 제품명 추출 (Hybrid)
    doc = msds_engine_v5.fitz.open(pdf_path)
    first_page_text = msds_engine_v5._get_sorted_and_normalized_text(doc[0])
    pix_cover = doc[0].get_pixmap(matrix=msds_engine_v5.fitz.Matrix(2.0, 2.0))
    import base64
    cover_img = [{"mimeType": "image/png", "data": base64.b64encode(pix_cover.tobytes("png")).decode("utf-8")}]
    doc.close()
    
    product_name, _ = msds_engine_v5.extract_product_name_hybrid(first_page_text, cover_img, current_sniper, log_func=log_print)
    
    # 3. AI Sniper 강제 투입
    print(f"[*] 🟡 AI Sniper({alias}) 강제 투입 중...")
    raw_prompt = f"{msds_engine_v5.VISION_EXTRACTOR_PROMPT}\n\n[Raw Text Context for Reference]:\n{section3_text[:2000]}"
    ai_res = msds_engine_v5.call_gemini_2_5_flash(image_list, raw_prompt, current_sniper, log_print)
    
    if ai_res is None:
        print("[*] ⚠️ Gemini 실패. GPT-4o-mini 복구 투입...")
        ai_res = msds_engine_v5.call_gpt_4o_mini(image_list, raw_prompt, log_func=log_print)
        
    # 4. 품질 관리 (QC)
    # grounding_text 구성
    grounding_text = str(first_page_text)
    doc_g = msds_engine_v5.fitz.open(pdf_path)
    for p_idx in pages:
        if p_idx != 0: grounding_text += "\n" + msds_engine_v5._get_sorted_and_normalized_text(doc_g[p_idx])
    doc_g.close()
    
    refined_list, has_invalid = msds_engine_v5.final_quality_control(ai_res.get("구성성분", []), grounding_text, log_func=log_print)
    
    comp_str = "; ".join([f"{c.get('cas_no', c.get('cas', ''))}({c.get('content', '')})" for c in refined_list])
    
    print("\n" + "="*50)
    print(f"제품명: {product_name}")
    print(f"구성성분: {comp_str}")
    print(f"신호등: {'🔴' if has_invalid else '🟡'}")
    print("="*50)

if __name__ == "__main__":
    test_017_forced_ai()
