import re

def verify_cas_number(cas_string):
    if not cas_string: return False
    clean_cas = re.sub(r'[^0-9-]', '', cas_string).strip()
    parts = clean_cas.split('-')
    if len(parts) != 3: return False
    try:
        check_digit = int(parts[2])
        digits = parts[0] + parts[1]
        total = sum(int(digit) * i for i, digit in enumerate(reversed(digits), 1))
        return (total % 10) == check_digit
    except: return False

test_cas = "26638-08-8"
print(f"CAS {test_cas} 유효성: {verify_cas_number(test_cas)}")
