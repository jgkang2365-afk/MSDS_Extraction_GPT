import sys
import os
import json
import time
import base64

sys.path.append(os.getcwd())
import msds_engine_v5

def test_017_gpt_direct():
    pdf_path = r"TEST_File\017_RED(적색)227_MSDS(E)_190730.pdf"
    print(f"[*] 17번 파일 GPT 직접 투입 테스트 (Gemini 429 우회)...")

    def log_print(msg):
        print(f"[*] {msg}")

    # 1. 이미지 및 텍스트 추출
    current_sniper = msds_engine_v5.get_next_sniper()
    image_list, section3_text, pages = msds_engine_v5.extract_section3_images(pdf_path, current_sniper, log_func=log_print)
    
    # 2. GPT 직접 호출 (Gemini 생략)
    print(f"[*] 🤖 GPT-4o-mini 직접 호출 중...")
    raw_prompt = f"{msds_engine_v5.VISION_EXTRACTOR_PROMPT}\n\n[Raw Text Context for Reference]:\n{section3_text[:2000]}"
    ai_res = msds_engine_v5.call_gpt_4o_mini(image_list, raw_prompt, log_func=log_print)
    
    if not ai_res:
        print("❌ GPT 호출 실패")
        return

    # 3. 제품명 추출 (테스트용 간략화)
    doc = msds_engine_v5.fitz.open(pdf_path)
    first_page_text = msds_engine_v5._get_sorted_and_normalized_text(doc[0])
    doc.close()

    # 4. 품질 관리 (QC)
    refined_list, has_invalid = msds_engine_v5.final_quality_control(ai_res.get("구성성분", []), section3_text, log_func=log_print)
    
    comp_str = "; ".join([f"{c.get('cas_no', c.get('cas', ''))}({c.get('content', '')})" for c in refined_list])
    
    print("\n" + "="*50)
    print(f"추출 결과: {comp_str}")
    print(f"부등호(>) 포함 여부: {'✅ 포함됨' if '>' in comp_str else '❌ 누락됨'}")
    print(f"신호등: {'🔴' if has_invalid else '🟡'}")
    print("="*50)

if __name__ == "__main__":
    test_017_gpt_direct()
