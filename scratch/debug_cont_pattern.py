import re

# msds_engine_v5의 cont_pattern (V17.4.0.9)
cont_pattern = re.compile(r'(?<![a-zA-Z\d-])([<>≤≥\uff1c\uff1e~∼～\-\u2013\u2014]?\s*\b\d+(?:\.\d+)?\b(?:\s*(?:이상|미만|~|∼|～|\-\u2013\u2014|above|below|to|and|%)\s*)*[<>≤≥\uff1c\uff1e~∼～\-\u2013\u2014]?\s*\b\d*(?:\.\d+)?\b\s*%?(?:\s*(?:이상|미만|above|below|%)\s*)*)(?![a-zA-Z])', re.IGNORECASE)

if __name__ == "__main__":
    test_texts = [
        "40~<50%",
        "1~ < 10 %",
        "0.1 ~ <1%",
        "Concentration: 40~<50%",
        "Range 0.1- < 1.0%"
    ]
    
    print(f"{'Input':<25} | {'Matches'}")
    print("-" * 50)
    for txt in test_texts:
        matches = cont_pattern.findall(txt)
        print(f"{txt:<25} | {matches}")
