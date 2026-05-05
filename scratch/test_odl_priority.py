
import re

def _clean_content_odl(text):
    return text.strip()

def _normalize_single_content(text):
    # Dummy version for testing
    return text.strip()

def test_logic(cells):
    strong_content, weak_content = None, None
    
    # Simulate the loop in parse_row_robust_v2
    for c in reversed(cells):
        c = c.strip()
        if not c: continue
        
        # Skip CAS logic for now as it's not the focus
        if re.match(r'^\d+-\d+-\d+$', c):
            continue

        norm_c = _normalize_single_content(c)
        if norm_c != "미기재%":
            is_percent = '%' in c
            is_symbol = any(k in c for k in ['~', '∼', '～', '<', '>', '≤', '≥', 'Rem', '잔량', 'balance', '미만', '이하', '초과', '이상'])
            is_range = '-' in c or '–' in c or '—' in c

            if is_percent:
                strong_content = _clean_content_odl(norm_c)
            elif not strong_content and is_symbol:
                strong_content = _clean_content_odl(norm_c)
            elif not strong_content and is_range and '(' not in c:
                strong_content = _clean_content_odl(norm_c)
            else:
                try:
                    clean_weak = float(re.sub(r'[^\d.]', '', norm_c))
                    if clean_weak <= 100 and not weak_content: 
                        weak_content = _clean_content_odl(norm_c)
                except: pass
                
    return strong_content or weak_content or "미기재%"

# Case 1: TCI style with ENCS hijacking
# Name | Weight | MW | ENCS | ISHL | CAS
case1 = ["4-Aminoantipyrine", "99.0", "203.24", "(9)-62", "N/A", "83-07-8"]
print(f"Case 1 (TCI/ENCS): {test_logic(case1)}") # Expected: 99.0

# Case 2: Wako style with inequality
case2 = ["3-Methyl-1-phenyl-5-pyrazolone", "=<100", "174.20", "(5)-287", "N/A", "89-25-8"]
print(f"Case 2 (Wako/Inequality): {test_logic(case2)}") # Expected: =<100

# Case 3: Parenthesized concentration (regression check)
case3 = ["Substance", "(>99%)", "100-20-5"]
print(f"Case 3 (Parenthesized %): {test_logic(case3)}") # Expected: (>99%)

# Case 4: Normal range with %
case4 = ["Mixture", "1-5%", "7732-18-5"]
print(f"Case 4 (Range %): {test_logic(case4)}") # Expected: 1-5%
