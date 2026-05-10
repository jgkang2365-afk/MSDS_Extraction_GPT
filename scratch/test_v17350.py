import re

def _mock_test():
    # 1. 시뮬레이션 데이터 설정 (주님께서 보여주신 033번 PDF 상황 재현)
    # [Component(x=50)] [CAS(x=300)] [Conc(x=500)]
    mock_words = [
        (500, 100, 550, 110, "함유량(%)"), # 헤더
        (50, 150, 100, 160, "Water"), (300, 150, 380, 160, "7732-18-5"), (500, 150, 550, 160, "40-50%"),
        (50, 180, 250, 190, "Methacrylic-2-ethylhexyl"), # 이름 속 숫자 '2' 포함
        (300, 180, 380, 190, "14807-96-6"), 
        (500, 180, 550, 190, "20~30%")
    ]
    
    # 2. V17.3.5.0 로직 가동: 함유량 열 식별
    content_anchors = [w for w in mock_words if any(k in w[4] for k in ["함유량", "함량", "%"])]
    target_anchor = max(content_anchors, key=lambda w: w[0])
    content_x_min = target_anchor[0] - 80
    content_x_max = target_anchor[2] + 120
    print(f"[*] 탐지된 함유량 열 범위: {content_x_min} ~ {content_x_max}")

    # 3. 노이즈 마스킹 가동
    sanitized_text_list = []
    cas_pattern = re.compile(r'(\d{2,7}-\d{2}-\d)')
    for w in mock_words:
        x0, y0, x1, y1, text_val = w
        if any(c.isdigit() for c in text_val):
            is_cas = cas_pattern.search(text_val)
            is_in_content_col = content_x_min - 20 <= x0 <= content_x_max + 20
            if not is_cas and not is_in_content_col:
                text_val = re.sub(r'\d', 'X', text_val)
        sanitized_text_list.append(text_val)
    
    combined_text = " ".join(sanitized_text_list)
    print(f"[*] 마스킹 후 텍스트: {combined_text}")

    # 4. 데이터 다이어트 가동 (성분명 제거)
    clean_text = combined_text.replace("7732-18-5", "[CAS_ANCHOR]") # Water용 테스트
    clean_text = clean_text.replace("함유량(%)", "")
    # 한글/영문 제거 로직
    clean_text = re.sub(r'[가-힣a-zA-Z](?!(?:이상|미만|%))', '', clean_text)
    
    print(f"[*] 다이어트 후 클린 텍스트: {clean_text}")

    # 5. 최종 추출 테스트
    cont_pattern = re.compile(r'(?<![a-zA-Z\d-])([<>≤≥~∼～-]?\s?\b\d+(?:\.\d+)?\b(?:\s*(?:이상|미만|~|∼|～|-|%)\s*)*[<>≤≥~∼～-]?\s*\b\d*(?:\.\d+)?\b\s*%?)', re.IGNORECASE)
    final_match = cont_pattern.findall(clean_text)
    print(f"[!] 최종 추출된 함량 조각들: {final_match}")

if __name__ == "__main__":
    _mock_test()
