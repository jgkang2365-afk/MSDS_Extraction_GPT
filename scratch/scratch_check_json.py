import json
import unicodedata

with open("msds_index.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total entries: {len(data)}")

# 자소분리 세척기
def clean(text):
    if not text: return ""
    return unicodedata.normalize("NFKC", text).strip()

targets = ["소우프스톤", "활석", "활석(석면불포함)", "기타광물성분진", "Limestone", "탄산 칼슘", "탄산칼슘", "금홍석", "이산화티타늄"]
target_cleans = [clean(t) for t in targets]

found = {}
for entry in data:
    for k, v in entry.items():
        if isinstance(v, str):
            v_c = clean(v)
            for t, tc in zip(targets, target_cleans):
                if tc in v_c:
                    if t not in found: found[t] = []
                    found[t].append(entry)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    item_c = clean(item)
                    for t, tc in zip(targets, target_cleans):
                        if tc in item_c:
                            if t not in found: found[t] = []
                            found[t].append(entry)

for t in targets:
    entries = found.get(t, [])
    print(f"Target '{t}': found {len(entries)} entries")
    if entries:
        print(f"  First match: name={entries[0].get('측정대상 물질명')}, CAS={entries[0].get('CAS No.')}, code={entries[0].get('정렬코드')}, aliases={entries[0].get('별칭')}")
