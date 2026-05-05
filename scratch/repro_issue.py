
import re

def _normalize_single_content(content_str):
    raw = str(content_str).strip()
    if not raw: return "미기재%"

    # 1. 기초 정규화
    v = raw.replace(" ", "").replace('＜', '<').replace('＞', '>').replace('<=', '≤').replace('>=', '≥')
    
    # 🚨 [V17.3.0.5] 전역 키워드 스캔
    sym_less = "<" if re.search(r'(<|미\s*[만맊먄]|below|less)', v, re.I) else ("≤" if re.search(r'(≤|이\s*[하핚]|up\s*to)', v, re.I) else "")
    sym_more = ">" if re.search(r'(>|초\s*과|more|over)', v, re.I) else ("≥" if re.search(r'(≥|이\s*상|above|from)', v, re.I) else "")

    # 2. 특수 키워드
    if any(k in v.lower() for k in ["balance", "잔량", "rem"]): return "Rem.%"
    
    # 4. 수치 추출 및 부등호 결합
    nums = re.findall(r'(\d+\.?\d*|\.\d+)', v)
    
    if len(nums) >= 2:
        try:
            f1, f2 = float(nums[0]), float(nums[1])
            if f1 > f2: f1, f2 = f2, f1
            n1_s, n2_s = (int(f1) if f1.is_integer() else f1), (int(f2) if f2.is_integer() else f2)
            if sym_more == "≥" and sym_less == "≤": return f"{n1_s}~{n2_s}%"
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

test_val = "0.01이내"
result = _normalize_single_content(test_val)
print(f"Input: {test_val} -> Output: {result}")

test_val2 = "1.0% 이내"
result2 = _normalize_single_content(test_val2)
print(f"Input: {test_val2} -> Output: {result2}")
