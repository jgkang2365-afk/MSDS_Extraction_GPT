import os
import json
import hashlib
import glob
import re

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cache_file = os.path.join(base_dir, "msds_cache_registry.json")
test_file_dir = os.path.join(base_dir, "TEST_File")

# 타겟 ID 목록 (이 ID들의 캐시를 소각하여 실시간 분석을 강제함)
target_ids = ["025", "028", "033", "048", "049"]

# 각 파일의 SHA-256 해시를 구하여 키 탐색
def calculate_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

pdf_files = glob.glob(os.path.join(test_file_dir, "*.pdf")) + glob.glob(os.path.join(test_file_dir, "*.PDF"))
pdf_files = list(set(pdf_files))

target_hashes = []
for p in pdf_files:
    fn = os.path.basename(p)
    m = re.match(r'^(\d+)', fn)
    if m and m.group(1) in target_ids:
        f_hash = calculate_sha256(p)
        target_hashes.append((m.group(1), fn, f_hash))
        print(f"[*] Target file found: ID {m.group(1)} | {fn} | Hash {f_hash}")

# msds_cache_registry.json 로드 후 삭제
if os.path.exists(cache_file):
    with open(cache_file, "r", encoding="utf-8") as f:
        cache_data = json.load(f)
        
    original_len = len(cache_data)
    removed_count = 0
    for tid, fn, f_hash in target_hashes:
        if f_hash in cache_data:
            del cache_data[f_hash]
            removed_count += 1
            print(f"[*] Cache removed: {fn} (Hash: {f_hash})")
            
    print(f"[*] Total {original_len} entries, {removed_count} entries removed. Remaining: {len(cache_data)}")
    
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
else:
    print("❌ 캐시 파일이 존재하지 않습니다!")
