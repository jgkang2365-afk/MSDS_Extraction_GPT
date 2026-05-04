
import re

def _normalize_single_content(content_str):
    raw = str(content_str).strip()
    if not raw: return "미기재%"

    # 현재 로직: 숫자 + 알파벳이 있고 %가 없으면 기각
    if re.search(r'\d\s*[a-zA-Z]+', raw) and '%' not in raw and not any(k in raw.lower() for k in ["rem", "balance"]):
        return "미기재% (Rejected by Value Guard)"

    v = raw.replace(" ", "").replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')
    
    nums = re.findall(r'(\d+\.?\d*|\.\d+)', v)
    if nums:
        return f"{nums[0]}% (Extracted)"
    
    return "미기재%"

test_cases = ["10 GP", "20 EP", "15 %", "77.08g", "0.1~1미만", "GP 10", "EP 20"]

for tc in test_cases:
    print(f"입력: {tc} -> 결과: {_normalize_single_content(tc)}")
