import re

# msds_engine_v5.py의 핵심 로직 시뮬레이션
def minimal_clean(content):
    if not content: return ""
    return str(content).replace(" ", "")

def prove_extraction_logic():
    # 1. AI가 이미지를 보고 추출해온 가상의 raw 데이터 (사용자가 보내준 이미지 기준)
    ai_raw_components = [
        {"name": "고도로 수소화 처리된 중파라핀 증류액", "cas_no": "64742-54-7", "content": ">97%"},
        {"name": "Phosphorodithioic acid", "cas_no": "68649-42-3", "content": "<2%"},
        {"name": "Alkyl phenol", "cas_no": "123-45-6", "content": "<0.6%"} # 규격에 맞는 CAS 가정
    ]

    print("=== [v15.0.1 테이블 조립 로직 증명] ===")
    
    comp_parts = []
    for comp in ai_raw_components:
        # (1) CAS 정규화
        cas = str(comp.get("cas_no", "")).strip()
        if re.match(r'^0+\d+-\d{2}-\d$', cas): 
            cas = re.sub(r'^0+', '', cas)
        
        # (2) 함유량 정제 (정의 누락되었던 그 변수!)
        substance_content = minimal_clean(comp.get("content", ""))
        if not substance_content: continue

        # (3) 물질명(name) 부활 로직
        name = str(comp.get("name", "")).strip()
        
        # (4) 최종 문자열 조립
        if name:
            formatted = f"{name} {cas}({substance_content})"
        else:
            formatted = f"{cas}({substance_content})"
        
        comp_parts.append(formatted)
        print(f"ㄴ 개별 성분 조립: {formatted}")

    # (5) 최종 결과물 (이 값이 GUI 테이블의 '함유량' 칸에 들어감)
    final_output = "; ".join(comp_parts)
    print("\n[최종 테이블 출력 값]")
    print(f"Result: {final_output}")

if __name__ == "__main__":
    prove_extraction_logic()
