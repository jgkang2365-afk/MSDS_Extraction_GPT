import json
import math
import pandas as pd

# 1. 엑셀 파일 로드
input_file = "msds_index_edit.xlsx"
df = pd.read_excel(input_file)

# 2. JSON 객체 리스트 생성
json_data = []

for idx, row in df.iterrows():
    item = {}
    for col in df.columns:
        if col == "원래순서":
            # 원래순서 컬럼은 JSON 파일 저장 시 제외
            continue
            
        val = row[col]
        
        # 빈 값(NaN 등) 처리
        if pd.isna(val):
            if col == "별칭":
                item[col] = []
            elif col == "형태학적_필터":
                item[col] = None
            else:
                item[col] = ""
            continue
            
        # 별칭 및 형태학적_필터 특수 복원 처리
        if col == "별칭":
            try:
                if isinstance(val, str) and val.strip() == "":
                    item[col] = []
                else:
                    item[col] = json.loads(str(val))
            except Exception:
                item[col] = []
        elif col == "형태학적_필터":
            try:
                if isinstance(val, str) and val.strip() == "":
                    item[col] = None
                else:
                    item[col] = json.loads(str(val))
            except Exception:
                item[col] = None
        else:
            # 수치형 데이터 정밀 복원 (실수 중 정수 형태 보정)
            if isinstance(val, float):
                if val.is_integer():
                    item[col] = int(val)
                elif math.isnan(val):
                    item[col] = ""
                else:
                    item[col] = val
            elif isinstance(val, int):
                item[col] = val
            else:
                item[col] = str(val)
                
    json_data.append(item)

# 3. JSON 파일 저장
output_file = "msds_index.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(json_data, f, ensure_ascii=False, indent=4)

print(f"성공적으로 {output_file}이 갱신되었습니다.")
