import os
import json
import base64
import requests
import fitz
from dotenv import load_dotenv

load_dotenv(override=True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

pdf_path = r"C:\Users\USER\Documents\★ 강종구-측정계획 및 견적서\TEST_농업기술센터-스마트농업과-농기계임대센터(동)\012_엔진오일(5w-30).pdf"
doc = fitz.open(pdf_path)

pages = []
for i in range(len(doc)):
    text = doc[i].get_text("text")
    if "3. 구성성분" in text or "SECTION 3" in text or "3 : COMPOSITION" in text:
        pages.append(i)
        break

if not pages:
    print("Page not found")
else:
    print(f"Pages found: {pages}")
    
    img_data = []
    for p in pages:
        pix = doc[p].get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
        img_data.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))

    prompt = """
당신은 2차 심층 복구 요원(Recovery Agent)입니다. 1차 엔진이 이 표의 공간적 구조를 파악하지 못해 당신에게 넘어왔습니다. 첨부된 이미지를 보고 데이터를 추출하세요.

[🔥 2차 엔진 절대 원칙]
1. 공간 지각 복구: 표의 선이 투명하거나, 미세하게 틀어졌거나, 비대칭 다중 병합이 있더라도 표의 전체적인 맥락을 입체적으로 읽어 CAS와 함유량을 매칭하세요.
2. 🚨 유연한 식별 원칙 (1차와 다름): CAS 번호 칸에 다른 식별번호(예: /KE-12345)가 섞여 있더라도, 어떻게든 유효한 CAS 번호(형식: 숫자-숫자-숫자)를 찾아내서 살려내세요. 단, 정말로 '영업비밀', '비공개' 등의 문구만 있어서 CAS를 찾을 수 없는 경우에만 폐기하세요.
3. 🚨 포맷 통일 및 환각 방지: 추출된 함유량 숫자 뒤에는 반드시 '%' 기호를 붙여라. 단, 원본 표에 함유량이 숫자가 아닌 '잔량', '나머지', 'balance', '적량' 등으로 표기되어 있다면, 절대 본인 마음대로 숫자(예: 10%)를 지어내거나 계산해서 적지 마라. 무조건 영문 대소문자를 맞춰 'Rem.%' 라는 문자열 그대로 출력하라.

JSON 출력 포맷:
{
  "구성성분": [
    {"cas_no": "123-45-6", "content": "10~20%"}
  ],
  "교정_사유": "추출 근거 요약"
}
"""
    content_list = [{"type": "text", "text": prompt}]
    for img in img_data:
        content_list.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img}"}
        })
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": content_list}],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    print(response.status_code)
    try:
        print(response.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print("Error:", e)
        print(response.text)
