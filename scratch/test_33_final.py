import sys
import os
import re

def _normalize_single_content_v17_4_9(content_str):
    raw = str(content_str).strip()
    if not raw: return "미기재%"
    v = raw.replace(" ", "").replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')
    
    # 숫자 추출
    nums = re.findall(r'(\d+\.?\d*|\.\d+)', v)
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
        return f"{pref}{n1}%"
        
    if len(nums) >= 2:
        if not has_range_sep:
            return f"{pref}{nums[0]}%"

        f1, f2 = float(nums[0]), float(nums[1])
        if f1 > f2: f1, f2 = f2, f1
        n1, n2 = (int(f1) if f1.is_integer() else f1), (int(f2) if f2.is_integer() else f2)
        
        # [V17.4.0.9] 신규 분할 로직 시뮬레이션
        parts = re.split(r'(?:~|∼|～|\-|to)', v, maxsplit=1)
        p_sym, s_sym = "", ""
        if len(parts) == 2:
            v_left, v_right = parts[0], parts[1]
            if any(k in v_left for k in [">", "≥", "above", "이상"]): p_sym = "≥" if "≥" in v_left or "이상" in v_left else ">"
            if any(k in v_right for k in ["<", "≤", "below", "미만"]): s_sym = "≤" if "≤" in v_right or "이하" in v_right else "<"
        
        if not p_sym and not s_sym:
            if is_ge and is_le: return f"{n1}~{n2}%"
            if is_ge or is_more: return f"≥{n1}~{n2}%"
            if is_le or is_less: return f"{n1}~{suff}{n2}%"
            return f"{n1}~{n2}%"
        
        return f"{p_sym}{n1}~{s_sym}{n2}%"
    
    return "미기재%"

if __name__ == "__main__":
    test_cases = [
        "40~<50%",
        "20~<30%",
        "<10%",
        "0.1~<1%",
        ">10~<20%",
        ">=1~<=5%"
    ]
    
    print(f"{'Input':<15} | {'V17.4.0.9 Result'}")
    print("-" * 40)
    for tc in test_cases:
        res = _normalize_single_content_v17_4_9(tc)
        print(f"{tc:<15} | {res}")
