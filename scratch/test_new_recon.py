import os
import base64
import json
import fitz
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

api_key = os.getenv("MSDS_GOOGLE_API_KEY_1") or os.getenv("MSDS_GOOGLE_API_KEY")
pdf_path = r'c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\TEST_File\015_Bentone Gel ISD V _ MSDS (KO).pdf'

def call_gemini(image_list, prompt, model="gemini-1.5-flash-latest"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    parts = [{"text": prompt}]
    for img_data in image_list:
        parts.append({"inlineData": {"mimeType": "image/png", "data": img_data}})
    
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
    }
    
    response = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload)
    if response.status_code == 200:
        res_json = response.json()
        return res_json.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
    else:
        return f"Error: {response.status_code}, {response.text}"

doc = fitz.open(pdf_path)
recon_images = []
for i in range(min(5, len(doc))):
    pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.8, 0.8))
    recon_images.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))

# Old prompt
old_prompt = "이 이미지들 중 '2. 구성성분' 또는 '3. 구성성분' 표가 있는 페이지 번호(0부터 시작)를 찾아라. JSON응답: {\"page_index\": 숫자}"

# New prompt
new_prompt = """각 이미지를 분석하여 '3. 구성성분의 명칭 및 함유량' (Composition / Information on Ingredients) 섹션이 시작되는 페이지 번호를 찾아라.
이 섹션은 보통 화학물질명, CAS 번호, 중량퍼센트(%)가 포함된 표 형식이다. 
반드시 0부터 시작하는 인덱스(첫 번째 이미지가 0)로 응답하라.
결과는 반드시 JSON 형식으로 {"page_index": 숫자} 로만 응답하라."""

print(f"Testing with gemini-1.5-flash-latest...")
print(f"Old Prompt Result:")
res_old = call_gemini(recon_images, old_prompt, model="gemini-1.5-flash-latest")
print(res_old)

print(f"\nNew Prompt Result:")
res_new = call_gemini(recon_images, new_prompt, model="gemini-1.5-flash-latest")
print(res_new)

doc.close()
