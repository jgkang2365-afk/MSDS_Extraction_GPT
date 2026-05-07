import os
import sys
import fitz
import re

# 부모 디렉토리를 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 인코딩 설정
import io
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

pdf_path = "013_아이생각수성내부프로 (M-BASE)_GHS국문.pdf"

def search_cas_context(cas):
    doc = fitz.open(pdf_path)
    print(f"\n--- [CAS {cas} 주변 텍스트 탐색] ---")
    for i in range(len(doc)):
        text = doc[i].get_text("text")
        if cas in text:
            print(f"\n[Page {i}]")
            # CAS 번호 주변 100자씩 출력
            idx = text.find(cas)
            start = max(0, idx - 100)
            end = min(len(text), idx + 200)
            print(f"... {text[start:end]} ...")
    doc.close()

# 주요 CAS 번호로 탐색
search_cas_context("7732-18-5") # 물
search_cas_context("14807-96-6") # 활석
