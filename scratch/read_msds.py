import sys

def read_file_range(filepath, start_line, end_line):
    try:
        with open(filepath, 'r', encoding='utf-8-sig', errors='replace') as f:
            lines = f.readlines()
            return lines[start_line-1:end_line]
    except Exception as e:
        return [f"Error: {str(e)}"]

if __name__ == "__main__":
    path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\msds_engine_v5.py"
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
        content = f.read()
    
    # Save to a clean file for analysis
    output_path = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)\scratch\clean_engine.py"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"File dumped to {output_path}")
