import re

def _normalize_single_content(v):
    nums = re.findall(r'[\d\.]+', v)
    if not nums: return "미기재%"
    
    if len(nums) == 1:
        f1 = float(nums[0])
        n1 = int(f1) if f1.is_integer() else f1
        return f"{n1}%"
    elif len(nums) >= 2:
        f1, f2 = float(nums[0]), float(nums[1])
        if f1 > f2: f1, f2 = f2, f1
        n1, n2 = (int(f1) if f1.is_integer() else f1), (int(f2) if f2.is_integer() else f2)
        
        parts = re.split(r'\s*(?:~|∼|～|\-|to)\s*', v, maxsplit=1)
        s_sym = ""
        if len(parts) == 2:
            v_right = parts[1]
            if any(k in v_right for k in ["<", "≤", "below", "미만"]): 
                s_sym = "≤" if "≤" in v_right or "이하" in v_right else "<"
        
        # 1% 기준 보정
        if n2 > 1.0: s_sym = ""
        
        if not s_sym: return f"{n1}~{n2}%"
        return f"{n1}~{s_sym}{n2}%"
    return "미기재%"

# Test cases based on Joo's requirements
print(f"Test 1 (40~<50%): {_normalize_single_content('40~<50%')}")
print(f"Test 2 (0.1~<1%): {_normalize_single_content('0.1~<1%')}")
print(f"Test 3 (>=95 - <= 100 %): {_normalize_single_content('>=95 - <= 100 %')}")
print(f"Test 4 (100%): {_normalize_single_content('100%')}")
