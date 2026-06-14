import os
import requests
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(override=True)

api_key = os.getenv("MSDS_GOOGLE_API_KEY_1")
print(f"[*] Sniper-1 Loaded Key: {api_key[:10]}...{api_key[-5:] if api_key else ''}")

if not api_key:
    print("[-] MSDS_GOOGLE_API_KEY_1 does not exist.")
    exit(1)

# 제미나이 2.5 플래시 API 호출 테스트
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
payload = {
    "contents": [{"parts": [{"text": "Hello, who are you? Please reply in one short sentence."}]}]
}
headers = {'Content-Type': 'application/json'}

print("[*] Calling Gemini 2.5 Flash...")
try:
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    print(f"[*] Response HTTP Status: {response.status_code}")
    if response.status_code == 200:
        res_json = response.json()
        text = res_json.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        print(f"[+] Success! Response: {text}")
    else:
        print(f"[-] Failed! Server Error Message:")
        # 인코딩 에러 방지를 위해 ascii 호환 문자열로 출력 처리
        print(response.text.encode('ascii', errors='replace').decode('ascii'))
except Exception as e:
    print(f"[-] Error occurred: {e}")
