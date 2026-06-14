# -*- coding: utf-8 -*-
import json
import os
import sys

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def main():
    json_path = "msds_index.json"
    if not os.path.exists(json_path):
        print("오류: msds_index.json이 없습니다.")
        return
        
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    print(f"총 데이터 개수: {len(data)}")
    
    # 이산화티타늄 검색
    target_name = "이산화티타늄"
    target_cas = "13463-67-7"
    
    found_by_name = []
    found_by_cas = []
    
    for idx, entry in enumerate(data):
        name = entry.get("측정대상 물질명", "")
        cas = entry.get("CAS No.", "")
        
        if target_name in name:
            found_by_name.append(entry)
        if target_cas in cas:
            found_by_cas.append(entry)
            
    print(f"\n'{target_name}' 이름 검색 결과 ({len(found_by_name)}건):")
    for item in found_by_name[:5]:
        print(item)
        
    print(f"\n'{target_cas}' CAS 검색 결과 ({len(found_by_cas)}건):")
    for item in found_by_cas[:5]:
        print(item)

if __name__ == "__main__":
    main()
