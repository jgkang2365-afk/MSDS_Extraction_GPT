import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('golden/msds_golden_v1.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    scanned_files = [c['file'] for c in data['cases'] if c.get('document_type') == 'scanned']
    print(f"총 개수: {len(scanned_files)}")
    print(f"리스트: {scanned_files}")
