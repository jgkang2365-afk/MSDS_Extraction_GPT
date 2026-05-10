import sys
import os
import re

# msds_engine_v5의 로직을 시뮬레이션
def _normalize_single_content_debug(content_str):
    raw = str(content_str).strip()
    if not raw: return "미기재%"

    # 1. 기초 정규화
    v = raw.replace(" ", "").replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')
    
    # 4. 숫자 추출
    v_shield = re.sub(r'\b20[0-2]\d[.\-/]\d{1,2}[.\-/]\d{1,2}\b', ' ', v)
    v_shield = re.sub(r'\b20[0-2]\d년?\b', ' ', v_shield)
    
    nums = re.findall(r'(\d+\.?\d*|\.\d+)', v_shield)
    if not nums: return "미기재%"
    
    raw_lower = v.lower()
    is_less = any(k in raw_lower for k in ["<", "미만", "below", "less"])
    is_le = any(k in raw_lower for k in ["≤", "이하", "max", "upto"])
    is_more = any(k in raw_lower for k in [">", "초과", "over", "above"])
    is_ge = any(k in raw_lower for k in ["≥", "이상", "min", "from", "+"])
    has_range_sep = any(k in raw_lower for k in ["~", "∼", "～", "-", "to"])

    pref = "≥" if is_ge else (">" if is_more else ("≤" if is_le else ("<" if is_less else "")))
    suff = "≤" if is_le else ("<" if is_less else "")

    if len(nums) == 1:
        v1 = nums[0]
        f1 = float(v1)
        n1 = int(f1) if f1.is_integer() else f1
        if (is_ge or is_more) and has_range_sep: return f"≥{n1}%"
        return f"{pref}{n1}%"
        
    if len(nums) >= 2:
        if not has_range_sep:
            f1 = float(nums[0])
            n1 = int(f1) if f1.is_integer() else f1
            return f"{pref}{n1}%"

        f1, f2 = float(nums[0]), float(nums[1])
        if f1 > f2: f1, f2 = f2, f1
        n1, n2 = (int(f1) if f1.is_integer() else f1), (int(f2) if f2.is_integer() else f2)
        
        if is_ge and is_le: return f"{n1}~{n2}%"
        if (is_ge or is_more) and not (is_le or is_less): return f"≥{n1}%"
        return f"{n1}~{suff}{n2}%"
    
    return "미기재%"

if __name__ == "__main__":
    test_cases = [
        "40~<50%",
        "20~<30%",
        "10~<20%",
        "<10%",
        "1~<10%",
        "1~<10%",
        "1~<10%",
        "1~<10%",
        "0.1~<1%"
    ]
    
    print(f"{'Input':<15} | {'Normalized'}")
    print("-" * 30)
    for tc in test_cases:
        res = _normalize_single_content_debug(tc)
        print(f"{tc:<15} | {res}")
