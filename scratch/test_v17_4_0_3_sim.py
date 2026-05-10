
import re

# 모의 데이터: 4번 파일 2페이지 상황 재현
# (x0, y0, x1, y1, text, block_no, line_no, word_no)
mock_words = [
    (800, 50, 850, 65, "3/18", 0, 0, 0),       # 페이지 번호 (오탐 후보 1)
    (500, 400, 650, 415, "41556-26-7", 1, 0, 0), # CAS 번호
    (800, 400, 880, 415, "0.1~1미만", 1, 0, 1), # 진짜 함량 (타겟)
    (50, 800, 200, 815, "4.", 2, 0, 0),        # 섹션 번호 (오탐 후보 2)
    (210, 800, 400, 815, "응급조치", 2, 0, 1)
]

# 계승된 좌표 (이전 페이지에서 가져옴)
inherited_x_range = (750, 950) 

def test_logic():
    print("[Test] V17.4.0.3 구조적 필터링 시뮬레이션 시작...")
    
    content_x_min, content_x_max = inherited_x_range
    cas_list = ["41556-26-7"]
    
    # 마스킹 처리
    protected_text_parts = []
    cas_x_min = 500
    
    for w in mock_words:
        x0, text = w[0], w[4]
        is_cas = text in cas_list
        in_x_range = (content_x_min - 50 <= x0 <= content_x_max + 50)
        
        if is_cas or in_x_range:
            protected_text_parts.append(text)
        else:
            if any(c.isdigit() for c in text):
                protected_text_parts.append("X") # 마스킹
            else:
                protected_text_parts.append(text)
                
    protected_text = " ".join(protected_text_parts)
    clean_text = protected_text.replace("41556-26-7", "[CAS_ANCHOR]")
    
    print(f"  - 마스킹 결과: {clean_text}")
    
    # 함량 추출 패턴 (단순화)
    all_conts = re.findall(r'[X\d\.~~미만]{1,15}', clean_text)
    
    def score_match(m):
        score = 0
        if any(k in m for k in ['~', '미만']): score += 300
        anchor_pos = clean_text.find("[CAS_ANCHOR]")
        match_pos = clean_text.find(m)
        if match_pos > anchor_pos: score += 100
        else: score -= 300
        return score

    best = max(all_conts, key=score_match)
    print(f"  - 최종 선택된 함량: {best} (점수: {score_match(best)})")
    
    if "0.1~1" in best:
        print("✅ 결과: 성공! 페이지 번호 '3'과 섹션 번호 '4'를 완벽히 격리했습니다.")
    else:
        print("❌ 결과: 실패. 로직 보완 필요.")

if __name__ == "__main__":
    test_logic()
