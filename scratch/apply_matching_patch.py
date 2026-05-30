import os
import re
import unicodedata

file_path = "smu_gui.py"
if not os.path.exists(file_path):
    print("Error: smu_gui.py not found")
    exit(1)

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 줄바꿈 정규화
norm_content = content.replace("\r\n", "\n")

# 1. get_mapped_factor 주입
# normalize_name 함수 정의를 찾아서 주입
pattern_norm = r"(def normalize_name\(name\):.*?return re\.sub\(r'\\s\+', '', name\)\.lower\(\))"
match_norm = re.search(pattern_norm, norm_content, re.DOTALL)

if not match_norm:
    print("Error: def normalize_name not found in smu_gui.py!")
    exit(1)

normalize_name_block = match_norm.group(1)
replacement_norm = normalize_name_block + """

        def get_mapped_factor(cas, name):
            clean_name = normalize_name(name)
            # 1. 특정 CAS / 명칭 매핑
            if cas == "1317-65-3" or "limestone" in clean_name:
                return ["기타광물성분진"]
            elif cas == "471-34-1" or "탄산" in clean_name:
                return ["기타광물성분진"]
            elif cas == "1317-80-2" or "금홍석" in clean_name:
                return ["이산화티타늄", "기타광물성분진"]
            elif cas == "14807-96-6" or "소우프스톤" in clean_name:
                return ["활석(석면불포함)", "활석", "소우프스톤"]
            
            # 2. 마스터 DB 조회
            std_names = []
            if cas:
                for entry in self.mes_master_list:
                    m_cas = str(entry.get("CAS No.", "")).strip()
                    m_name = str(entry.get("측정대상 물질명", "")).strip()
                    if m_cas == cas and m_name:
                        std_names.append(m_name)
            if not std_names:
                std_names = [name]
            return list(set(std_names))"""

norm_content = norm_content.replace(normalize_name_block, replacement_norm, 1)
print("Success: get_mapped_factor function injected.")

# 2. 매칭 및 조립 루프 정규식 교체
# i_items = split_i_val(i_val) 로 시작해서 new_j_val += j_item 로 끝나는 가장 첫 번째 블록 매칭
# J열 조립의 j_item 대입 부분(new_j_val += j_item)을 타겟으로 함
pattern_matching = r"(i_items\s*=\s*split_i_val\(i_val\).*?new_j_val\s*\+=\s*j_item)"
match_matching = re.search(pattern_matching, norm_content, re.DOTALL)

if not match_matching:
    print("Error: Target matching block not found via regex!")
    exit(1)

matching_block_to_replace = match_matching.group(1)

replacement_matching_block = """i_items = split_i_val(i_val)
                j_items = [x.strip() for x in j_val.split(";") if x.strip()]
                
                # 1. I열 원본 성분들을 순회하며 오타 교정을 먼저 수행하고 clean_i_items 구축
                clean_i_items = []
                for i_item in i_items:
                    parsed_i = parse_substance_item(i_item)
                    if not parsed_i:
                        continue
                    i_sub = parsed_i["pure_name"]
                    category = parsed_i["category"]
                    sub_prefix = parsed_i["sub_prefix"]
                    
                    if not i_sub:
                        self.clean_log(f"⚠️ [건너뜀] {r}행: 알맹이 이름이 없는 고아 항목 '{i_item}' 감지되어 제외 조치합니다.")
                        continue
                        
                    # 🚨 [V24.3.4.0] 영구 교정 기억 장치(사전) 조회 및 자동 대체
                    i_sub_norm = normalize_name(i_sub)
                    if i_sub_norm in correction_rules:
                        corrected_val = correction_rules[i_sub_norm]
                        if corrected_val != i_sub:
                            self.clean_log(f"[*] {r}행: 캐시된 오타 교정 규칙 적용 '{i_sub}' -> '{corrected_val}'")
                            i_sub = corrected_val
                            i_sub_norm = normalize_name(i_sub)
                            
                    # [V24.3.5.0] 지능형 부모-자식 자동 교정 규칙 적용
                    cas = name_to_cas.get(i_sub, "")
                    if cas:
                        siblings = cas_to_names.get(cas, [])
                        # 🚨 [V24.3.5.2] 활석/소우프스톤 계열(CAS 14807-96-6)은 자동 교정에서 강제 제외
                        if cas == "14807-96-6":
                            pass
                        elif len(siblings) > 1:
                            # 동일 CAS를 가진 형제들 중 가장 짧은 명칭을 부모명으로 판단
                            sorted_siblings = sorted(siblings, key=len)
                            parent_name = sorted_siblings[0]
                            if i_sub == parent_name:
                                # 부모명이 자식명 텍스트 내에 포함되는 실질 상세 자식명만 필터링하여 이명(예: 소우프스톤 등)과의 간섭 차단
                                children = [s for s in siblings if s != parent_name and parent_name in s]
                                if len(children) == 1:
                                    target_child = children[0]
                                    self.clean_log(f"[*] {r}행: 부모 물질명 '{i_sub}' ➔ 자식 표준명 '{target_child}' 자동 교정 적용 (유일 자식)")
                                    i_sub = target_child
                                    i_sub_norm = normalize_name(i_sub)
 
                    # 마스터 DB 표준 풀네임 집합 대조
                    # 🚨 [V24.3.5.2] 활석/소우프스톤 계열(CAS 14807-96-6) 중 대표 부모명("활석")인 경우에만 수동 팝업 강제 호출
                    is_talc_parent = (cas == "14807-96-6" and i_sub == "활석")
                    if i_sub_norm in valid_substances_clean and not is_talc_parent:
                        # 1단계: 사용자 기재 신뢰 (Zero-Popup Pass)
                        pass
                    else:
                        # 마스터 DB에 정확히 일치하지 않거나, 예외 강제 팝업 케이스
                        cas = name_to_cas.get(i_sub, "")
                        candidates = []
                        is_multi_regulation = False
                        
                        if cas:
                            siblings = cas_to_names.get(cas, [])
                            # 🚨 [V24.3.5.2] 활석/소우프스톤 계열은 대표 부모명인 '활석'을 제외하고 팝업 후보 구성
                            if cas == "14807-96-6":
                                candidates = [s for s in siblings if s != "활석"]
                                is_multi_regulation = True
                            # 2단계: 동일 CAS 형제들의 TWA 규제 조건 상이 여부 분석
                            elif len(siblings) > 1:
                                twa_sets = set()
                                for sib in siblings:
                                    info = substance_info_map.get(sib, {})
                                    twa_sets.add((
                                        info.get("특별관리", ""),
                                        info.get("허가대상", ""),
                                        info.get("특검", ""),
                                        info.get("측정", ""),
                                        substance_sort_map.get(sib, "ZZZZZZ")
                                    ))
                                if len(twa_sets) > 1:
                                    candidates = siblings
                                    is_multi_regulation = True
                                else:
                                    # 규제 조건이 동일하다면 대표 성상명으로 자동 매핑
                                    i_sub = siblings[0]
                                    i_sub_norm = normalize_name(i_sub)
                            else:
                                candidates = siblings
                                
                        # CAS 번호가 없거나, 성상 분기가 불필요하며, 여전히 마스터 DB에 없는 오타인 경우
                        if not candidates:
                            # 3단계: 유사도 임계치 cutoff=0.8로 상향하여 오타 후보 구축
                            candidates = list(difflib.get_close_matches(i_sub, list(valid_substances), n=3, cutoff=0.8))
                            for vname in valid_substances:
                                if vname not in candidates and (i_sub in vname or vname in i_sub):
                                    if len(vname) - len(i_sub) in [-2, -1, 0, 1, 2]:
                                        candidates.append(vname)
                                        
                        # 교정 대화상자 호출
                        if candidates and not all_skip:
                            if all_apply:
                                proposed = candidates[0]
                                self.clean_log(f"[교정] {r}행: '{i_sub}' -> '{proposed}' (자동 적용)")
                                i_sub = proposed
                                i_sub_norm = normalize_name(i_sub)
                            else:
                                title = "동일 CAS 다중 규제 물질 선택" if is_multi_regulation else "물질명 오타 교정 제안"
                                dlg = SubstanceCorrectionDialog(r, i_sub, candidates, parent=self)
                                dlg.setWindowTitle(title)
                                dlg.exec_()
                                
                                if dlg.result_action in (SubstanceCorrectionDialog.RESULT_APPLY, SubstanceCorrectionDialog.RESULT_ALL_APPLY):
                                    self.clean_log(f"[교정] {r}행: '{i_sub}' -> '{dlg.corrected_name}' (적용)")
                                    
                                    # 영구 교정 기억 사전에 매핑 정보 등록
                                    i_item_raw_norm = normalize_name(i_sub)
                                    correction_rules[i_item_raw_norm] = dlg.corrected_name
                                    self.save_cache() # 캐시 파일 영구 저장
                                    
                                    i_sub = dlg.corrected_name
                                    i_sub_norm = normalize_name(i_sub)
                                    
                                    if dlg.result_action == SubstanceCorrectionDialog.RESULT_ALL_APPLY:
                                        all_apply = True
                                elif dlg.result_action == SubstanceCorrectionDialog.RESULT_ALL_SKIP:
                                    all_skip = True
                                    self.clean_log(f"[교정] {r}행: '{i_sub}' (이후 모두 건너뛰기 활성화)")
                                else:
                                    self.clean_log(f"[교정] {r}행: '{i_sub}' (건너뜀)")
                                    
                    # 마스터 데이터셋을 바탕으로 수식어 자동 복원 및 우선순위 매핑
                    info = substance_info_map.get(i_sub)
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
                        
                    sort_code = substance_sort_map.get(i_sub) or "ZZZZZZ"
                    
                    # 🚨 [V24.3.5.6] 보관 카테고리인데 월취급량(G열)이 0이 아니면 비즈니스 룰 위반 오류(적색 마킹)
                    is_red = False
                    if category == "보관" and not is_g_zero:
                        is_red = True
                        self.clean_log(f"⚠️ {r}행: '보관' 성분 '{i_sub}'이 존재하나 G열(월취급량: '{g_raw}')이 '0'이 아닙니다.")
                        
                    clean_i_items.append({
                        "category": category,
                        "sub_prefix": sub_prefix,
                        "pure_name": i_sub,
                        "sort_code": sort_code,
                        "is_red": is_red
                    })
                    
                # 2. I열 중복 제거 적용
                unique_i_list = []
                seen_i_keys = set()
                for item in clean_i_items:
                    key = (item["category"], item["sub_prefix"], item["pure_name"])
                    if key not in seen_i_keys:
                        seen_i_keys.add(key)
                        unique_i_list.append(item)
                        
                # 3. J열 성분 분석 및 지능형 N:1 매칭
                j_parser_pat = re.compile(r"^(?:(\\[특별\\]|\\\[특검\\]|\\\[허가\\]))?(.*?)(?:\\(([^)]*)\\))?$")
                j_matched_data = []
                
                for j_item in j_items:
                    match = j_parser_pat.match(j_item)
                    if not match:
                        j_matched_data.append({
                            "j_item": j_item,
                            "category": "측정대상",
                            "sort_code": "ZZZZZZ",
                            "is_red": True
                        })
                        continue
                        
                    j_prefix = match.group(1) or ""
                    j_pure_name = match.group(2) or ""
                    j_concentration = match.group(3) or ""
                    
                    j_pure_clean = extract_pure_substance_name(j_pure_name)
                    j_cas = name_to_cas.get(j_pure_clean, "")
                    
                    # 지능형 매핑 후보 도출
                    j_mapped_factors = get_mapped_factor(j_cas, j_pure_clean)
                    
                    matched_i_item = None
                    for i_item in unique_i_list:
                        i_pure_clean = extract_pure_substance_name(i_item["pure_name"])
                        i_cas = name_to_cas.get(i_pure_clean, "")
                        
                        # A. 지능형 매핑 표준명 대조
                        is_match = False
                        for factor in j_mapped_factors:
                            if normalize_name(factor) == normalize_name(i_item["pure_name"]):
                                is_match = True
                                break
                        # B. CAS 번호 대조
                        if not is_match and j_cas and i_cas and j_cas == i_cas:
                            is_match = True
                        # C. 텍스트 포함 대조
                        if not is_match:
                            i_norm = normalize_name(i_item["pure_name"])
                            j_norm = normalize_name(j_pure_clean)
                            if i_norm and j_norm and (i_norm in j_norm or j_norm in i_norm):
                                is_match = True
                                
                        if is_match:
                            matched_i_item = i_item
                            break
                            
                    if matched_i_item:
                        # 보관 카테고리인데 G열 0 아님 오류 재확인
                        is_red = False
                        if matched_i_item["category"] == "보관" and not is_g_zero:
                            is_red = True
                            matched_i_item["is_red"] = True
                            self.clean_log(f"⚠️ {r}행: '보관' 성분 '{matched_i_item['pure_name']}'이 존재하나 G열(월취급량: '{g_raw}')이 '0'이 아닙니다.")
                            
                        j_matched_data.append({
                            "j_item": j_item,
                            "category": matched_i_item["category"],
                            "sort_code": matched_i_item["sort_code"],
                            "is_red": is_red
                        })
                    else:
                        # 매칭 실패한 경우 ➔ 마스터 DB 규제 대상(측정/특검)인지 확인
                        is_regulation = False
                        reg_info = substance_info_map.get(j_pure_clean)
                        if reg_info:
                            is_measure = str(reg_info.get("측정") or "").strip() == "○"
                            is_exam = str(reg_info.get("특검") or "").strip() == "○"
                            if is_measure or is_exam:
                                is_regulation = True
                                
                        if is_regulation:
                            self.clean_log(f"⚠️ {r}행: 규제 대상 성분 '{j_pure_name}'에 상응하는 비고(I열) 매칭 물질이 누락되어 [누락]으로 표시합니다.")
                            
                            # unique_i_list에 [누락] 임시 추가
                            nu_exists = False
                            for item in unique_i_list:
                                if (item["category"], item["sub_prefix"], item["pure_name"]) == ("측정대상", "", "[누락]"):
                                    nu_exists = True
                                    break
                            if not nu_exists:
                                unique_i_list.append({
                                    "category": "측정대상",
                                    "sub_prefix": "",
                                    "pure_name": "[누락]",
                                    "sort_code": "ZZZZZZ",
                                    "is_red": True
                                })
                                
                            j_matched_data.append({
                                "j_item": j_item,
                                "category": "측정대상",
                                "sort_code": "ZZZZZZ",
                                "is_red": True
                            })
                        else:
                            # 단순 일반 성분인 경우 ➔ [누락] 없이 J열에만 보존
                            j_matched_data.append({
                                "j_item": j_item,
                                "category": "측정대상",
                                "sort_code": "ZZZZZZ",
                                "is_red": False
                            })
                            
                # 4. 정렬
                j_matched_data.sort(key=lambda x: x["sort_code"])
                unique_i_list.sort(key=lambda x: x["sort_code"])
                
                # 5. I열 조립 및 마킹 좌표 계산
                new_i_val = ""
                red_marks_i = []
                blue_marks_i = []
                first_i = True
                
                group_definitions = [
                    ("측정대상", "; ", ""),
                    ("측정 비대상", "; ", "측정 비대상["),
                    ("단시간 및 임시작업", "; ", "단시간 및 임시작업["),
                    ("허용소비량 미만", "; ", "허용소비량 미만["),
                    ("보관", "; ", "보관[")
                ]
                
                for cat_name, sep, wrapper in group_definitions:
                    cat_items = [x for x in unique_i_list if x["category"] == cat_name]
                    if not cat_items:
                        continue
                        
                    if not first_i:
                        new_i_val += "; "
                    first_i = False
                    
                    if wrapper:
                        new_i_val += wrapper
                        
                    for idx, item in enumerate(cat_items):
                        if idx > 0:
                            new_i_val += sep
                            
                        sub_prefix = item["sub_prefix"]
                        pure_sub_name = item["pure_name"]
                        
                        if sub_prefix:
                            start_pos = len(new_i_val) + 1
                            blue_marks_i.append((start_pos, len(sub_prefix)))
                            new_i_val += sub_prefix
                            
                        if pure_sub_name:
                            pure_sub_norm = normalize_name(pure_sub_name)
                            is_i_red = False
                            if pure_sub_name == "[누락]":
                                is_i_red = True
                            elif pure_sub_norm not in valid_substances_clean and pure_sub_norm not in api_valid_substances:
                                is_i_red = True
                            if item.get("is_red", False):
                                is_i_red = True
                                
                            if is_i_red:
                                start_pos = len(new_i_val) + 1
                                red_marks_i.append((start_pos, len(pure_sub_name)))
                            new_i_val += pure_sub_name
                            
                    if wrapper:
                        new_i_val += "]"
                        
                # 6. J열 조립 및 마킹 좌표 계산
                new_j_val = ""
                red_marks_j = []
                blue_marks_j = []
                first_j = True
                
                for idx, item in enumerate(j_matched_data):
                    j_item = item["j_item"]
                    if not j_item:
                        continue
                        
                    if not first_j:
                        new_j_val += "; "
                    first_j = False
                    
                    match = j_parser_pat.match(j_item)
                    if match:
                        sub_prefix = match.group(1) or ""
                        pure_sub_name = match.group(2) or ""
                        concentration = match.group(3) or ""
                        
                        if sub_prefix:
                            start_pos = len(new_j_val) + 1
                            blue_marks_j.append((start_pos, len(sub_prefix)))
                            new_j_val += sub_prefix
                            
                        if pure_sub_name:
                            pure_sub_norm = normalize_name(pure_sub_name)
                            is_sub_red = False
                            if item.get("is_red", False):
                                is_sub_red = True
                            elif pure_sub_norm not in valid_substances_clean and pure_sub_norm not in api_valid_substances:
                                is_sub_red = True
                            if match.group(3) is None or not concentration.strip():
                                is_sub_red = True
                                
                            if is_sub_red:
                                start_pos = len(new_j_val) + 1
                                red_marks_j.append((start_pos, len(pure_sub_name)))
                            new_j_val += pure_sub_name
                            
                        if match.group(3) is not None:
                            paren_content = f"({concentration})"
                            is_conc_red = ("%" not in concentration or not concentration.strip())
                            start_pos = len(new_j_val) + 1
                            if is_conc_red:
                                red_marks_j.append((start_pos, len(paren_content)))
                            new_j_val += paren_content
                    else:
                        start_pos = len(new_j_val) + 1
                        red_marks_j.append((start_pos, len(j_item)))
                        new_j_val += j_item"""

norm_content = norm_content.replace(matching_block_to_replace, replacement_matching_block, 1)
print("Success: Matching block replaced.")

# 줄바꿈 복원 및 저장
final_content = norm_content.replace("\n", "\r\n")
with open(file_path, "w", encoding="utf-8") as f:
    f.write(final_content)

print("Patch applied successfully!")
