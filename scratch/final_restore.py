import os
import re

file_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v5.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Restore PROMPT_GEMINI_FLASH and clean up the leaked area
gemini_flash_def = """PROMPT_GEMINI_FLASH = \"\"\"
당신은 1차 고속 시각 추출기(Sniper)입니다. 첨부된 MSDS 표 이미지만 보고 데이터를 추출하세요.

[🔥 1차 엔진 5대 절대 원칙]
1. 🚨 엄격한 수평(Y-axis) 1:1 매칭: 표에 선이 없거나 칸이 넓어 성분명, CAS 번호, 함유량이 어긋나 있더라도, 반드시 같은 행(Row)의 문맥을 추적하여 1:1로 매칭하라. 한 물질의 CAS가 2줄로 쪼개져 있다면 병합하라.
2. 🚨 환각 금지(가장 중요): 표에 '함유량'이나 '%'가 명시된 컬럼이 없을 경우, 절대 옆에 있는 '분자량'이나 '녹는점' 같은 무관한 숫자를 함유량으로 둔갑시켜 추출하지 마라.
3. 🚨 결측치 처리: CAS 칸이 비어있거나 '영업비밀', '비공개' 등이면 가차 없이 폐기하라. 반대로 CAS는 있는데 함유량 칸이 비어있거나 '-' 처리되어 있다면 함유량을 '미기재%'로 출력하라. 단, '잔량', 'balance' 등으로 명시된 경우만 'Rem.%'로 출력하라.
4. 🚨 1% 부등호 조작 금지: 원본에 '0.1-1' 이라 적혀 있으면 '0.1~1%'로 출력하라. 임의로 '<1%'처럼 부등호를 지어내는 환각을 절대 금지한다.
5. 포맷 통일: 함유량 숫자 뒤에는 반드시 '%'를 붙여라.

JSON 출력 포맷:
{
  "구성성분": [
    {"cas_no": "123-45-6", "content": "10~20%"}
  ],
  "교정_사유": "시각 추출 완료"
}
\"\"\"
"""

# The leaked area starts around SYSTEM_PROMPT_TEXT = load_system_prompt()
# and ends before PROMPT_GPT_FALLBACK = """
leak_pattern = re.compile(r'SYSTEM_PROMPT_TEXT = load_system_prompt\(\)\n\n.*?PROMPT_GPT_FALLBACK =', re.DOTALL)
if leak_pattern.search(content):
    content = leak_pattern.sub(f'SYSTEM_PROMPT_TEXT = load_system_prompt()\n\n{gemini_flash_def}\n# 🚜 [2차 복구 요원용 프롬프트] GPT-4o-mini 전용\nPROMPT_GPT_FALLBACK =', content)

# 2. Fix PROMPT_GPT_FALLBACK (Bulldozer version)
bulldozer_prompt = """당신은 파괴된 표를 긁어모으는 2차 불도저(Bulldozer)입니다. 첨부된 이미지의 표에서 데이터를 '눈에 보이는 그대로' 단순 무식하게 복사하세요. 

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

prompt_pattern = re.compile(r'PROMPT_GPT_FALLBACK = """.*?"""', re.DOTALL)
if prompt_pattern.search(content):
    content = prompt_pattern.sub(f'PROMPT_GPT_FALLBACK = \"\"\"{bulldozer_prompt}\"\"\"', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Engine file fully restored and cleaned.")
