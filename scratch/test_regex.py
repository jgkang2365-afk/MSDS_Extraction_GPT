import re

# 개선 정규식 V2 (알파벳 접두사/접미사 가드레일 장착)
new_pattern = re.compile(
    r'(\b\d+(?:\.\d+)?\s*(?:이상|이하|미만|초과)?\s*[-~∼～](?![a-zA-Z])\s*)'
    r'([^0-9~∼～]*?[a-zA-Z가-힣][^0-9~∼～]*?)'
    r'((?<![a-zA-Z-])\b\d+(?:\.\d+)?\b\s*%?\s*(?:미만|이하|이상|초과)?)'
)

text = "Methacrylic acid-2-ethylhexyl ac Methacrylic acid-2-e [CAS_ANCHOR] 1 이상 ~ rylate-styrene polymer thylhexyl acrylate-s 10 % 미만 tyrene polymer"

print("--- 개선 정규식 V2 결과 ---")
match_new = new_pattern.search(text)
if match_new:
    print("매칭 성공:", match_new.group(0))
    print("대체 결과:", new_pattern.sub(r'\1\3 \2', text))
else:
    print("매칭 실패")
