import re

def _normalize_single_content(content_str):
    raw = str(content_str).strip()
    if not raw: return "미기재%"

    v = raw.replace(" ", "").replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')
    v = re.sub(r'(min|max)\.', r'\1', v, flags=re.I)
    
    sym_less = "<" if re.search(r'(<|미\s*[만맊먄]|below|less)', v, re.I) else ("≤" if re.search(r'(≤|이\s*[하핚내]|up\s*to|max)', v, re.I) else "")
    sym_more = "≥" if re.search(r'(≥|이\s*상|above|from|min|\+)', v, re.I) else (">" if re.search(r'(>|초\s*과|more|over)', v, re.I) else "")

    nums = re.findall(r'(\d+\.?\d*|\.\d+)', v)
    if not nums: return raw

    if len(nums) >= 2:
        try:
            f1, f2 = float(nums[0]), float(nums[1])
            if f1 > f2: f1, f2 = f2, f1
            n1_s, n2_s = (int(f1) if f1.is_integer() else f1), (int(f2) if f2.is_integer() else f2)
            
            if sym_more and not sym_less and ("+" in v or "min" in v.lower()):
                return f"{sym_more}{n1_s}%"

            # [V17.3.3.3] 범위형 정규화 고도화 (주님 지침: 1% 기준 예외 적용)
            if n2_s > 1.0:
                return f"{n1_s}~{n2_s}%"
            else:
                p2 = sym_less if sym_less else ""
                return f"{n1_s}~{p2}{n2_s}%"
        except: pass
    elif len(nums) == 1:
        try:
            f1 = float(nums[0])
            if f1 <= 100:
                n1_s = int(f1) if f1.is_integer() else f1
                prefix = sym_less if sym_less else (sym_more if sym_more else "")
                return f"{prefix}{n1_s}%"
        except: pass

    return "미기재%"

test_cases = [
    ">= 35 - < 40 %",
    ">= 70 - < 75 %",
    "0 ~ < 1 %",
    "< 1 %",
    "1 - 5 %",
    "0.1 - 0.9 %"
]

print(f"{'Input':<20} | {'Output':<15}")
print("-" * 40)
for tc in test_cases:
    result = _normalize_single_content(tc)
    print(f"{tc:<20} | {result:<15}")
