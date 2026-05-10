import msds_engine_v5 as engine
import re

# 1. Shikimic Acid Case (Range with symbols)
text1 = ">=95 - <= 100 %"
matches1 = engine.cont_pattern.findall(text1)
print(f"Match for '{text1}': {matches1}")
if matches1:
    norm1 = engine._normalize_single_content(matches1[0])
    print(f"Normalized: {norm1}")

# 2. Parenthesis Guard Test - Valid context
text2 = "(CAS [CAS_ANCHOR], 100%)"
# We need to simulate the loop in extract_from_text_regex
def test_guard(clean_text):
    results = []
    for m in engine.cont_pattern.finditer(clean_text):
        val = m.group(1).strip()
        start = m.start()
        prefix = clean_text[:start]
        if prefix.count('(') > prefix.count(')'):
            last_open = prefix.rfind('(')
            context_window = clean_text[max(0, last_open-30):start]
            if "[CAS_ANCHOR]" not in context_window:
                continue
        results.append(val)
    return results

print(f"Guard test for '{text2}': {test_guard(text2)}")

# 3. Parenthesis Guard Test - Invalid context (Noise)
text3 = "Butane (Butadiene 0%) [CAS_ANCHOR] 11~14%"
print(f"Guard test for '{text3}': {test_guard(text3)}")
