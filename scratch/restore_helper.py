# -*- coding: utf-8 -*-
import subprocess

def main():
    # git show HEAD:smu_gui.py 명령을 실행하여 바이트 단위로 출력을 가져옴
    result = subprocess.run(["git", "show", "HEAD:smu_gui.py"], capture_output=True, check=True)
    
    # UTF-8로 디코딩
    content = result.stdout.decode('utf-8', errors='ignore')
    lines = content.splitlines()
    
    # _create_settings_page 함수의 시작과 끝 추출
    start_idx = -1
    for idx, line in enumerate(lines):
        if "def _create_settings_page(self):" in line:
            start_idx = idx
            break
            
    if start_idx == -1:
        print("오류: _create_settings_page를 찾을 수 없습니다.")
        return
        
    print(f"_create_settings_page 발견: {start_idx + 1}번째 라인")
    
    # 다음 함수 정의가 나올 때까지 추출
    extracted_lines = []
    for line in lines[start_idx:]:
        extracted_lines.append(line)
        # 다음 함수의 시작 부분을 탐색 (들여쓰기 없는 def)
        if len(extracted_lines) > 1 and line.startswith("    def ") and not line.startswith("    def _create_settings_page"):
            # 이전 라인까지가 이 함수의 끝임
            extracted_lines.pop()
            break
            
    extracted_content = "\n".join(extracted_lines)
    
    # 추출 결과를 UTF-8 파일로 저장
    with open("scratch/extracted_settings_page.py", "w", encoding="utf-8") as f:
        f.write(extracted_content)
        
    print("성공: scratch/extracted_settings_page.py 파일에 저장되었습니다.")

if __name__ == "__main__":
    main()
