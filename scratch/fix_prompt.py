import os

file_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v5.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define the merged prompt
merged_prompt = """당신은 파괴된 표를 긁어모으는 2차 불도저(Bulldozer)입니다. 첨부된 이미지의 표에서 데이터를 '눈에 보이는 그대로' 단순 무식하게 복사하세요. 

[🔥 불도저 단순 추출 4대 원칙]
1. 생각 금지: % 기호 붙이기, 부등호 교정, '잔량'을 'Rem.%'로 바꾸기 등 어떠한 가공이나 번역도 하지 마세요. 후속 엔진이 알아서 합니다. 표에 적힌 글씨를 그대로 타이핑하세요.
2. 영업비밀 및 공란 통과: CAS 번호 칸에 번호가 없고 '영업비밀', '-', '비공개' 등이 적혀있다면, 버리지 말고 그 글자를 그대로 `cas_no`에 적어오세요.
3. 다중 CAS 통합: 한 칸에 CAS 번호가 여러 개 뭉쳐 있으면 행을 나누지 말고, 띄어쓰기나 슬래시(/)로 묶어서 한 줄로 다 퍼 오세요.
4. 페이지 트래킹: 각 성분이 발견된 이미지의 실제 페이지 번호를 'page' 필드에 기재하세요.

[🔥 2차 엔진 절대 원칙]
1. 공간 지각 복구: 표의 선이 투명하거나, 미세하게 틀어졌거나, 비대칭 다중 병합이 있더라도 표의 전체적인 맥락을 입체적으로 읽어 CAS와 함유량을 매칭하세요.
2. 🚨 절대 폐기 및 시각적 팩트 주의: 표에 명시된 숫자로 된 CAS 번호(형식: 숫자-숫자-숫자)만 추출하라. 화학 물질명이나 문맥을 보고 네가 아는 화학 지식을 동원하여 실존하는 CAS 번호를 유추하거나 지어내는(Hallucination) 행위는 절대 금지한다. 눈에 명확히 보이는 번호가 없거나 '영업비밀', '비공개', '-' 등이라면 가차 없이 그 행을 추출 대상에서 폐기하라.
3. 🚨 포맷 통일 및 환각 방지: 추출된 함유량 숫자 뒤에는 반드시 '%' 기호를 붙여라. 단, 원본 표에 함유량이 숫자가 아닌 '잔량', '나머지', 'balance', '적량' 등으로 표기되어 있다면, 절대 본인 마음대로 숫자(예: 10%)를 지어내거나 계산해서 적지 마라. 무조건 영문 대소문자를 맞춰 'Rem.%' 라는 문자열 그대로 출력하라.
   🚨 부등호 훼손 절대 금지: 원본 표의 함유량에 부등호(<, ≤)나 텍스트(미만, 이하)가 포함되어 있다면, 이를 절대 물결표(~) 범위 기호로 바꾸지 마라.
   [올바른 예시]: 원본이 '<1' 이면 '<1%'로 출력, 원본이 '≤1' 이면 '≤1%'로 출력.
   [잘못된 예시]: 원본이 '<1' 인데 '~1%'로 변조하여 출력 (절대 금지).

4. 🚨 페이지 트래킹: 각 성분이 발견된 페이지 번호를 'page' 필드에 기재하라.
 
 JSON 출력 포맷:
 {
   "구성성분": [
     {"cas_no": "123-45-6 / 영업비밀", "content": "10 미만", "page": "3"}
   ],
   "교정_사유": "단순 무식 원본 텍스트 복사 및 심층 복구 완료"
 }"""

# We'll look for the whole broken block and replace it.
# The block starts at PROMPT_GPT_FALLBACK = """ and ends at the second """
import re
pattern = r'PROMPT_GPT_FALLBACK = """.*?""".*?"""'
if re.search(pattern, content, re.DOTALL):
    new_content = re.sub(pattern, f'PROMPT_GPT_FALLBACK = \"\"\"{merged_prompt}\"\"\"', content, flags=re.DOTALL)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("PROMPT_GPT_FALLBACK updated and merged.")
else:
    print("Could not find the broken PROMPT_GPT_FALLBACK block.")
