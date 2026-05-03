import msds_utils_v3

test_cases = [
    ("0.1~1미만", "0.1~<1%"),
    ("0.1~1", "0.1~1%"),
    ("1~5 미만", "1~<5%"),
    ("< 0.1", "<0.1%"),
    ("0.1 % 미만", "<0.1%")
]

for inp, exp in test_cases:
    actual = msds_utils_v3.format_content(inp)
    print(f"Input: {inp} -> Actual: {actual} (Expected: {exp})")
    assert actual == exp
