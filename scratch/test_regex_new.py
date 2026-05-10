import re

# [V17.4.0.5] 특수 대시 및 전각 부등호 대응 추가: –, — (En/Em Dash), ＜, ＞
cont_pattern = re.compile(r'(?<![a-zA-Z\d-])([<>＜＞≤≥~∼～\-\u2013\u2014]?\s?\b\d+(?:\.\d+)?\b(?:\s*(?:이상|미만|~|∼|～|\-\u2013\u2014|above|below|to|and|%)\s*)*[<>＜＞≤≥~∼～\-\u2013\u2014]?\s*\b\d*(?:\.\d+)?\b\s*%?(?:\s*(?:이상|미만|above|below|%)\s*)*)(?![a-zA-Z])', re.IGNORECASE)

test_text = "Concentration : ＞  85 ％"
matches = cont_pattern.findall(test_text)
print(f"Text: '{test_text}'")
print(f"Matches: {matches}")

test_text2 = "CAS number : 3567-66-6"
matches2 = cont_pattern.findall(test_text2)
print(f"Text: '{test_text2}'")
print(f"Matches: {matches2}")
