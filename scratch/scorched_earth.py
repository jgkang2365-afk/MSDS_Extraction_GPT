import os

def scorched_earth_restore():
    with open('msds_engine_v5_utf8.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        # 비-ASCII 문자가 있으면 그 줄은 버림 (단, 핵심 로직이 깨지지 않도록 주의)
        if any(ord(c) > 127 for c in line):
            # 주석이 아닌데 한글이 포함된 경우 (주로 프롬프트)
            # 일단은 다 버리고 나중에 프롬프트만 따로 채움
            continue
        new_lines.append(line)
    
    # 기본 엔진 구조 저장
    with open('msds_engine_v5.py', 'w', encoding='ascii') as f:
        f.writelines(new_lines)
    
    print("Scorched earth restoration completed. ASCII only.")

if __name__ == "__main__":
    scorched_earth_restore()
