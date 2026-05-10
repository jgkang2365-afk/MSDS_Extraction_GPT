import re

def _normalize_single_content(raw):
    raw = raw.replace(" ", "")
    nums = re.findall(r'\d+(?:\.\d+)?', raw)
    if not nums: return "미기재%"
    if len(nums) >= 2:
        return f"{nums[0]}~{nums[1]}%"
    return f"{nums[0]}%"

def _final_test_v2():
    # 실제 엔진처럼 CAS를 [CAS_ANCHOR]로 치환한 상태
    protected_text = "[CAS_ANCHOR] Methacrylic-X-ethylhexyl 20~30%"
    
    # 데이터 다이어트
    clean_text = protected_text.replace("[CAS_ANCHOR]", "___CAS_ID___")
    clean_text = re.sub(r'[가-힣a-zA-Z](?!(?:___CAS_ID___|이상|미만|%))', '', clean_text)
    clean_text = clean_text.replace("___CAS_ID___", "[CAS_ANCHOR]")
    
    print(f"[*] Cleaned: {clean_text}")

    # 정규식 매칭
    cont_pattern = re.compile(r'(?<![a-zA-Z\d-])([<>≤≥~∼～-]?\s?\b\d+(?:\.\d+)?\b(?:\s*(?:이상|미만|~|∼|～|-|%)\s*)*[<>≤≥~∼～-]?\s*\b\d*(?:\.\d+)?\b\s*%?)', re.IGNORECASE)
    all_conts = cont_pattern.findall(clean_text)
    
    print(f"[*] Matches: {all_conts}")
    
    if all_conts:
        result = _normalize_single_content(" ".join(all_conts))
        print(f"[!] Result: {result}")

if __name__ == "__main__":
    _final_test_v2()
