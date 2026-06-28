import os
import sys

def run_paddle_raw_inspection(pdf_path, page_num=2, ocr_engine=None):
    """[Test Case] PaddleOCR 사출 데이터 원형 전수 조사 단발성 스크립트"""
    print(f"📍 [물리 검문 시작] 대상 자재: {pdf_path} | 목표 탐색 레이어: {page_num}p")
    
    # 🛡️ 데이터 검증: 파일 실재 여부 선제 가드레일
    if not os.path.exists(pdf_path):
        print(f"🚨 [조업 중단] 파일이 지정된 경로 선반 위에 존재하지 않습니다: {pdf_path}")
        return
        
    try:
        from paddleocr import PaddleOCR
        import fitz  # PyMuPDF (환경에 배선 완료된 상태 확인)
        
        if ocr_engine is None:
            print("⚙️ [엔진 예열] 로컬 PaddleOCR 인공지능 모델을 상주 메모리에 탑재 중...")
            ocr_engine = PaddleOCR(lang='korean')
        
        # PDF 도면 개방
        doc = fitz.open(pdf_path)
        if page_num > len(doc) or page_num < 1:
            print(f"🚨 [범위 초과] 해당 문서는 총 {len(doc)}p 구성이며, {page_num}p는 궤도 바깥입니다.")
            return
            
        # 목표 페이지를 픽셀 이미지로 고속 휘발성 사출
        page = doc[page_num - 1]
        pix = page.get_pixmap(dpi=150)
        temp_img_path = f"__temp_inspect_p{page_num}.png"
        pix.save(temp_img_path)
        
        print(f"🚀 [{page_num}p 이미지 변환 완착] PaddleOCR 픽셀 압착 파싱 주행 시작...")
        # predict() 표준 메서드로 호출
        try:
            result = ocr_engine.predict(temp_img_path)
        except Exception:
            result = ocr_engine.ocr(temp_img_path)
        
        # 사용 완료된 임시 이미지 자재 즉시 소탕
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)
            
        res_dict = result[0] if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict) else (result if isinstance(result, dict) else {})
        print(f"\n🔑 [FOUND KEYS]: {list(res_dict.keys())}")
        
        # 구조 해석 및 정밀 점등
        print("\n" + "="*80)
        print(f"📊 [046번 자재 {page_num}p PaddleOCR 날것의 사출 장부 원형 명세]")
        print("="*80)
        
        # PaddleX Predict 결과 구조 파싱 (rec_text, rec_texts, text, ocr_res 등)
        texts = res_dict.get('rec_text') or res_dict.get('rec_texts') or res_dict.get('texts') or res_dict.get('text')
        scores = res_dict.get('rec_score') or res_dict.get('rec_scores') or res_dict.get('scores') or res_dict.get('score')
        boxes = res_dict.get('dt_polys') or res_dict.get('boxes') or res_dict.get('dt_boxes') or res_dict.get('polys')
        
        if texts is not None:
            if isinstance(texts, str):
                print(f"[단일 문맥 수거] {texts}")
            elif isinstance(texts, (list, tuple)):
                for idx, text in enumerate(texts, 1):
                    sc = scores[idx-1] if scores is not None and idx-1 < len(scores) else 0.0
                    bx = boxes[idx-1] if boxes is not None and idx-1 < len(boxes) else []
                    if hasattr(bx, 'tolist'): bx = bx.tolist()
                    print(f"[{idx:03d}번 자산] 글자: {str(text):<35} | 신뢰도: {float(sc):.4f} | 좌표포지션: {bx}")
        else:
            # 예상치 못한 구조인 경우 전체 키와 값 샘플 출력
            for k, v in res_dict.items():
                if k not in ('doc_preprocessor_res', 'rot_img', 'output_img', 'input_img', 'input_path'):
                    v_str = str(v)
                    print(f"  ├─ 키[{k}] (타입:{type(v).__name__}): {v_str[:200]}")
            
        print("="*80 + "\n")
        
    except ImportError as ie:
        print(f"🚨 [인프라 누락] 라이브러리 로드 실패 (가상환경 venv_312 선로를 확인하십시오): {ie}")
    except Exception as e:
        print(f"🚨 [런타임 크래시 방어 격리벽 격발] 시스템 상세 오류 사유: {e}")

if __name__ == "__main__":
    import glob
    from paddleocr import PaddleOCR
    
    # 소장님의 실제 조업 파일 주소 매칭 및 동적 가드레일
    TARGET_MSDS = "046_THF_MSDS.pdf"
    if not os.path.exists(TARGET_MSDS):
        # TEST_File 디렉토리 또는 전체 탐색 시도
        candidates = glob.glob("**/046_THF_MSDS.pdf", recursive=True) + glob.glob("**/*046*.pdf", recursive=True)
        if candidates:
            TARGET_MSDS = candidates[0]
            
    print("⚙️ [엔진 1회 예열] 상주 로컬 PaddleOCR 모델을 선제 탑재합니다...")
    global_ocr = PaddleOCR(lang='korean')
    
    # 2페이지와 3페이지의 날것의 수거 데이터 연속 점등 주행
    run_paddle_raw_inspection(TARGET_MSDS, page_num=2, ocr_engine=global_ocr)
    run_paddle_raw_inspection(TARGET_MSDS, page_num=3, ocr_engine=global_ocr)