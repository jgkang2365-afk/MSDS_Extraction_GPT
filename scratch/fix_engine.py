import re

file_path = 'msds_engine_v5.py'
with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# 1. Version Update
content = content.replace('VERSION = "17.3.1.24" # 광대역 윈도우 스캔 및 노이즈 세척 (고분자 성분 함량 복구)', 
                          'VERSION = "17.3.2.0" # 광대역 윈도우 스캔 및 [CAS-함량] 정밀 매칭 (성분명 추출 제외)')

# 2. Fix corrupted final_quality_control
# Use regex to find the corrupted block and replace it
corrupted_pattern = re.compile(r'for v_cas in valid_text_cas:\s+# 1글자만 틀린 경우 \(AI 오def extract_from_text_regex\(text\):.*?return found 방어\] 3단계 퍼지 쉴드 붕괴\. 환각 CAS 영구 폐기: {cas}\"\)', re.DOTALL)
replacement_logic = """for v_cas in valid_text_cas:
                    # 1글자만 틀린 경우 (AI 오타 방어)
                    diff_count = sum(1 for a, b in zip(cas, v_cas) if a != b) if len(cas) == len(v_cas) else 99
                    if diff_count <= 1:
                        cas = v_cas
                        break
                else:
                    if log_func: log_func(f" 🔴 [Fuzzy 방어] 3단계 퍼지 쉴드 붕괴. 환각 CAS 영구 폐기: {cas}")
                    has_invalid = True
                    continue """

content = corrupted_pattern.sub(replacement_logic, content)

# 3. Replace the old extract_from_text_regex
old_regex_func = """def extract_from_text_regex(text):
    \"\"\"[V17.3.1.20] 안정적인 라인 기반 로직으로 원복 (함량 로직 임의 수정 금지)\"\"\"
    found = []
    cas_pattern = re.compile(r'(?<![\\d-])(\\d{2,7}-\\d{2}-\\d)(?![\\d-])')
    lines = [l.strip() for l in text.split('\\n') if l.strip()]
    for line in lines:
        matches = list(cas_pattern.finditer(line))
        if not matches: continue
        for i, match in enumerate(matches):
            cas = match.group(1)
            # [V17.3.1.22] 텍스트 레이어 추출 시에도 Grounding(문서 원본) 대조 허용
            if not verify_cas_number(cas, grounding_text=text): continue
            start_pos = match.end()
            end_pos = matches[i+1].start() if i+1 < len(matches) else len(line)
            search_area = line[start_pos:end_pos]
            content = "미기재%"
            m_cont = re.search(r'([<>≤≥~∼～-]?\\s?\\d+(?:\\.\\d+)?(?:\\s*[:~∼～-]\\s*[<>≤≥~∼～-]?\\s?\\d+(?:\\.\\d+)?)?\\s*%?)', search_area)
            if m_cont:
                content = _normalize_single_content(m_cont.group(1))
            name_start = matches[i-1].end() if i > 0 else 0
            name_area = line[name_start:match.start()]
            name_parts = re.split(r'\\s{2,}', name_area.strip())
            name = name_parts[-1].strip() if name_parts else "성분명 미탐지"
            found.append({"name": name, "cas_no": cas, "content": content})
    return found"""

new_regex_func = """def extract_from_text_regex(text):
    \"\"\"[V17.3.2.0] CAS 기준 광대역 윈도우 스캔 (함량 정밀 매칭 및 성분명 무시)\"\"\"
    found = []
    # 1. 노이즈 제거 및 정규화 (맊/핚 대응 포함)
    clean_text = text.replace('̻', '').replace('̸', '').replace('맊', '만').replace('핚', '한')
    cas_pattern = re.compile(r'(?<![\\d-])(\\d{2,7}-\\d{2}-\\d)(?![\\d-])')
    
    all_matches = list(cas_pattern.finditer(clean_text))
    if not all_matches: return []
    
    for i, match in enumerate(all_matches):
        cas = match.group(1)
        if not verify_cas_number(cas, grounding_text=clean_text): continue
        
        # 2. 탐색 범위 설정 (앞뒤 300자, 단 다른 CAS 번호를 침범하지 않음)
        win_start = all_matches[i-1].end() if i > 0 else max(0, match.start() - 300)
        win_end = all_matches[i+1].start() if i+1 < len(all_matches) else min(len(clean_text), match.end() + 300)
        
        # 3. 우선순위 탐색: 뒤쪽(표준) -> 앞쪽(역전 표)
        after_cas = clean_text[match.end():win_end]
        before_cas = clean_text[win_start:match.start()]
        
        content = "미기재%"
        # 함량 정규식 (부등호 및 범위 포함, OCR 노이즈 대응)
        cont_regex = r'([<>≤≥~∼～-]?\\s?\\d+(?:\\.\\d+)?(?:\\s*[:~∼～-]\\s*[<>≤≥~∼～-]?\\s?\\d+(?:\\.\\d+)?)?\\s*%?)'
        
        m_after = re.search(cont_regex, after_cas)
        if m_after:
            content = _normalize_single_content(m_after.group(1))
        else:
            # 뒤에 없으면 앞쪽을 뒤짐 (가장 가까운 수치를 찾기 위해 뒤에서부터 매칭)
            m_before_all = list(re.finditer(cont_regex, before_cas))
            if m_before_all:
                content = _normalize_single_content(m_before_all[-1].group(1))
        
        # [DNA] 성분명은 PDF에서 읽지 않고 CAS 기반 자동 매핑 대상으로 처리
        name = "CAS 기반 자동 매핑"
        
        found.append({"name": name, "cas_no": cas, "content": content, "engine": "Regex-Window"})
    return found"""

# Since I can't guarantee exact string match for the whole function due to whitespace, 
# I'll use a more flexible search or just replace known markers.
if old_regex_func in content:
    content = content.replace(old_regex_func, new_regex_func)
else:
    print("Warning: Could not find old_regex_func exactly. Using fallback replacement.")
    # Fallback: search for the docstring
    content = re.sub(r'def extract_from_text_regex\(text\):\s+\"\"\"\[V17\.3\.1\.20\].*?return found', new_regex_func, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Successfully fixed msds_engine_v5.py")
