import hashlib
import re

def get_hash(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()
    func_match = re.search(r"def extract_from_text_regex\(.*?\):(.*?)def extract_section3_images", code, re.DOTALL)
    if func_match:
        core_logic = func_match.group(1).strip()
        current_hash = hashlib.sha256(core_logic.encode("utf-8")).hexdigest()[:16]
        return current_hash
    return None

hash_v6 = get_hash(r"c:\Users\USER\Desktop\안티그래비티\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v6.py")
hash_clean = get_hash(r"c:\Users\USER\Desktop\안티그래비티\MSDS_EXtaction_V3(v24+GUI통합)\MSDS_Extraction_Clean\msds_engine_v6.py")

print(f"msds_engine_v6.py Hash: {hash_v6}")
print(f"Clean msds_engine_v6.py Hash: {hash_clean}")
