# -*- coding: utf-8 -*-
"""[NEW] 화학물질 정리 및 교정 개선 로직 단위 테스트 (풀네임 버전)"""
import re

# msds_index.json에 있는 예시 데이터 모킹
valid_substances = {
    "산화철",
    "산화철(분진, 흄)",
    "톨루엔",
    "벤젠",
    "크실렌",
    "알루미늄(금속분진)",
    "알루미늄(흄)"
}

substance_sort_map = {
    "산화철": "3M-20-001",
    "산화철(분진, 흄)": "3M-20-002",
    "벤젠": "3M-01-010",
    "톨루엔": "3M-01-020",
    "크실렌": "3M-01-030",
    "알루미늄(금속분진)": "3M-05-010",
    "알루미늄(흄)": "3M-05-020"
}

substance_info_map = {
    "산화철": {"특별관리": "", "허가대상": "", "특검": "", "측정": ""},
    "산화철(분진, 흄)": {"특별관리": "", "허가대상": "", "특검": "", "측정": ""},
    "벤젠": {"특별관리": "○", "허가대상": "", "특검": "", "측정": ""},
    "톨루엔": {"특별관리": "", "허가대상": "", "특검": "", "측정": ""},
    "크실렌": {"특별관리": "", "허가대상": "", "특검": "", "측정": ""},
    "알루미늄(금속분진)": {"특별관리": "", "허가대상": "", "특검": "", "측정": ""},
    "알루미늄(흄)": {"특별관리": "", "허가대상": "", "특검": "", "측정": ""}
}

def normalize_name(name):
    if not name:
        return ""
    return re.sub(r'\s+', '', name).lower()

valid_substances_clean = {normalize_name(name) for name in valid_substances}

# 모의 캐시 사전
cache = {
    "correction_rules": {}
}

def parse_substance_item(item):
    item = item.strip()
    if not item:
        return None
    
    category = "측정대상"
    for prefix in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
        if item.startswith(prefix):
            category = prefix
            item = item[len(prefix):].strip()
            break
            
    if item.startswith("[") and item.endswith("]"):
        item = item[1:-1].strip()
        
    sub_prefix = ""
    for sub in ["[특별]", "[허가]", "[특검]"]:
        if item.startswith(sub):
            sub_prefix = sub
            item = item[len(sub):].strip()
            break
            
    # 🚨 [V24.3.4.0] 괄호 분리 삭제. 풀네임 보존
    pure_name = item.replace("[", "").replace("]", "").strip()
    
    return {
        "category": category,
        "sub_prefix": sub_prefix,
        "pure_name": pure_name,
        "suffix": ""
    }

def split_i_val(i_val):
    if not i_val:
        return []
    chars = list(i_val)
    in_paren = 0
    in_bracket = 0
    for i, ch in enumerate(chars):
        if ch == '(': in_paren += 1
        elif ch == ')': in_paren -= 1
        elif ch == '[': in_bracket += 1
        elif ch == ']': in_bracket -= 1
        elif ch == ';' and (in_paren > 0 or in_bracket > 0):
            chars[i] = '\u0001'
    
    protected_val = "".join(chars)
    raw_splits = []
    for part in re.split(r';', protected_val):
        part = part.strip()
        if not part:
            continue
        raw_splits.append(part.replace('\u0001', ';'))
        
    final_items = []
    for part in raw_splits:
        matched_prefix = None
        for prefix in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
            if part.startswith(prefix):
                matched_prefix = prefix
                break
                
        if matched_prefix:
            inner_content = part[len(matched_prefix):].strip()
            if inner_content.startswith("[") and inner_content.endswith("]"):
                inner_content = inner_content[1:-1].strip()
            elif inner_content.startswith("(") and inner_content.endswith(")"):
                inner_content = inner_content[1:-1].strip()
            
            sub_parts = re.split(r';', inner_content)
            for sub_p in sub_parts:
                sub_p = sub_p.strip()
                if sub_p:
                    final_items.append(f"{matched_prefix}[{sub_p}]")
        else:
            final_items.append(part)
    return final_items

def run_test_case(i_val, j_val, mock_user_correction=None):
    print(f"\n--- 테스트 입력 ---")
    print(f"I열: {i_val}")
    print(f"J열: {j_val}")
    
    i_items = split_i_val(i_val)
    j_items = [x.strip() for x in j_val.split(";") if x.strip()]
    
    def extract_pure_substance_name(item):
        m_br = re.search(r'\[(.*?)\]', item)
        text = m_br.group(1).strip() if m_br else item.strip()
        text = re.sub(r'^\[.*?\]', '', text).strip()
        text = re.sub(r'\(.*?\)', '', text).strip()
        for prefix in ["측정 비대상", "단시간 및 임시작업", "보관", "허용소비량 미만"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        text = text.replace("[", "").replace("]", "").strip()
        return text

    used_j_indices = set()
    paired_data = []
    
    for i_item in i_items:
        parsed_i = parse_substance_item(i_item)
        i_pure = parsed_i["pure_name"] if parsed_i else extract_pure_substance_name(i_item)
        matched_j_item = None
        matched_idx = -1
        
        for idx, j_item in enumerate(j_items):
            if idx in used_j_indices:
                continue
            j_pure = extract_pure_substance_name(j_item)
            if i_pure == j_pure:
                matched_j_item = j_item
                matched_idx = idx
                break
                
        if matched_j_item is None:
            for idx, j_item in enumerate(j_items):
                if idx in used_j_indices:
                    continue
                j_pure = extract_pure_substance_name(j_item)
                if i_pure and j_pure and (i_pure in j_pure or j_pure in i_pure):
                    matched_j_item = j_item
                    matched_idx = idx
                    break
                    
        if matched_j_item is not None:
            used_j_indices.add(matched_idx)
        else:
            matched_j_item = ""
            
        paired_data.append((i_item, matched_j_item))
        
    for idx, j_item in enumerate(j_items):
        if idx not in used_j_indices:
            paired_data.append(("", j_item))
            
    row_data = []
    correction_rules = cache["correction_rules"]

    for i_item, j_item in paired_data:
        if not i_item:
            row_data.append({
                "i_item_final": "",
                "j_item": j_item,
                "category": "측정대상",
                "sort_code": "ZZZZZZ",
                "is_red": True
            })
            continue
            
        parsed_i = parse_substance_item(i_item)
        if not parsed_i:
            continue
        i_sub = parsed_i["pure_name"]
        category = parsed_i["category"]
        
        if not i_sub:
            print(f"  [배제] 고아 항목 무시됨: '{i_item}'")
            continue
            
        # 🚨 [V24.3.4.0] 영구 기억 조회
        i_sub_norm = normalize_name(i_sub)
        if i_sub_norm in correction_rules:
            corrected_val = correction_rules[i_sub_norm]
            if corrected_val != i_sub:
                print(f"  [자동 교정] 캐시 규칙 적용: '{i_sub}' -> '{corrected_val}'")
                i_sub = corrected_val
                i_sub_norm = normalize_name(i_sub)
                
        # 마스터 DB 대조
        if i_sub_norm in valid_substances_clean:
            # 1단계: 사용자 기재 신뢰 (Zero-Popup)
            pass
        else:
            # 교정이 필요한 경우 (오타)
            # 모의 교정값 적용
            if mock_user_correction and i_sub in mock_user_correction:
                corrected_name = mock_user_correction[i_sub]
                print(f"  [교정 실행] 사용자 직접 교정: '{i_sub}' -> '{corrected_name}'")
                # 영구 캐시에 규칙 저장
                correction_rules[i_sub_norm] = corrected_name
                i_sub = corrected_name
                i_sub_norm = normalize_name(i_sub)
            else:
                print(f"  [경고] '{i_sub}' 은 마스터 DB에 없으며 모의 교정 값도 지정되지 않았습니다.")
                
        info = substance_info_map.get(i_sub)
        sub_prefix = ""
        if info:
            is_special = str(info.get("특별관리") or "").strip() == "○"
            is_permit = str(info.get("허가대상") or "").strip() == "○"
            is_exam = str(info.get("특검") or "").strip() == "○"
            is_measure = str(info.get("측정") or "").strip() == "○"
            
            if is_special:
                sub_prefix = "[특별]"
            elif is_permit:
                sub_prefix = "[허가]"
            elif is_exam and not is_measure:
                sub_prefix = "[특검]"
        else:
            sub_prefix = parsed_i["sub_prefix"]
            
        i_item_final = f"{sub_prefix}{i_sub}"
        sort_code = substance_sort_map.get(i_sub)
        
        is_red = False
        if i_sub_norm not in valid_substances_clean:
            sort_code = "ZZZZZZ"
            is_red = True
            
        row_data.append({
            "i_item_final": i_item_final,
            "j_item": j_item,
            "category": category,
            "sort_code": sort_code,
            "is_red": is_red
        })
        
    row_data.sort(key=lambda x: x["sort_code"])
    
    group_i_results = []
    group_j_results = []
    group_definitions = [
        ("측정대상", "; ", ""),
        ("측정 비대상", "; ", "측정 비대상["),
        ("단시간 및 임시작업", "; ", "단시간 및 임시작업["),
        ("허용소비량 미만", "; ", "허용소비량 미만["),
        ("보관", "; ", "보관[")
    ]
    
    for cat_name, sep, wrapper in group_definitions:
        cat_items = [x for x in row_data if x["category"] == cat_name]
        if not cat_items:
            continue
        
        inner_i_texts = [x["i_item_final"] for x in cat_items if x["i_item_final"]]
        if inner_i_texts:
            if wrapper:
                group_i_results.append(f"{wrapper}{sep.join(inner_i_texts)}]")
            else:
                group_i_results.append(sep.join(inner_i_texts))
                
        inner_j_texts = [x["j_item"] for x in cat_items if x["j_item"]]
        if inner_j_texts:
            group_j_results.append(sep.join(inner_j_texts))
            
    new_i_val = "; ".join(group_i_results)
    new_j_val = "; ".join(group_j_results)
    
    print(f"--- 테스트 결과 ---")
    print(f"새 I열: {new_i_val}")
    print(f"새 J열: {new_j_val}")
    
    reds = [x["i_item_final"] for x in row_data if x["is_red"]]
    if reds:
        print(f"[Error] 오류 마킹 대상 성분: {reds}")
    else:
        print("[OK] 모든 성분이 마스터 DB 검증을 통과했습니다.")

if __name__ == "__main__":
    # 시나리오 1: 표준 명칭 입력 시 팝업 없이 100% 통과 검증 (Zero-Popup Pass)
    # 산화철(분진, 흄) 이 마스터 DB에 있으므로 바로 성공해야 함
    run_test_case("산화철(분진, 흄)", "산화철(분진, 흄)(10~20%)")
    
    # 시나리오 2: 오타 물질 교정 및 캐시 영구 저장 테스트
    # "알루미늄ㅁ(금속분진)" -> 첫 번째 교정 창 호출 모의를 통해 "알루미늄(금속분진)"으로 교정
    mock_corrections = {
        "알루미늄ㅁ(금속분진)": "알루미늄(금속분진)"
    }
    run_test_case("알루미늄ㅁ(금속분진)", "알루미늄(금속분진)(5~10%)", mock_corrections)
    
    # 시나리오 2-B: 캐시 기억 작동 확인 테스트
    # 위에서 교정한 이력에 의해 두 번째 호출 시 팝업(mock_user_correction) 없이 자동으로 "알루미늄(금속분진)"으로 교정되는지 확인
    run_test_case("알루미늄ㅁ(금속분진)", "알루미늄(금속분진)(5~10%)")
    
    # 시나리오 3: 괄호 내 오타 발생 시 풀네임 매칭 및 교정 기억 테스트
    # "산화철(분진, 흄ㅁ)" -> "산화철(분진, 흄)"으로 풀네임 교정
    mock_corrections_2 = {
        "산화철(분진, 흄ㅁ)": "산화철(분진, 흄)"
    }
    run_test_case("산화철(분진, 흄ㅁ)", "산화철(분진, 흄)(5~10%)", mock_corrections_2)
    # 캐시 적용 검증
    run_test_case("산화철(분진, 흄ㅁ)", "산화철(분진, 흄)(5~10%)")

    # 시나리오 4: I열/J열 정렬 동기화 최종 검증
    run_test_case(
        "톨루엔; 측정 비대상[[특별]벤젠]; 단시간 및 임시작업[크실렌]",
        "크실렌(2~4%); 벤젠(0.1~0.7%); 톨루엔(1~10%)"
    )
