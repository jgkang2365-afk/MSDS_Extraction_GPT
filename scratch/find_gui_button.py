# -*- coding: utf-8 -*-
# 한국어 주석 필수 준수

import os
import glob

def search_subprocess_in_workspace():
    base_dir = r"c:\Users\USER\Desktop\안티그래티비\MSDS_EXtaction_V3(v24+GUI통합)"
    py_files = glob.glob(os.path.join(base_dir, "*.py"))
    
    print(f"[*] 총 {len(py_files)}개의 파일에서 프로세스 생성 패턴 조사")
    keywords = ["subprocess", "Popen", "os.system", "sys.executable", "msds_engine_v5", "python"]
    
    for file_path in py_files:
        filename = os.path.basename(file_path)
        if filename in ["find_gui_button.py", "test_paddle_table.py"]:
            continue
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except:
            try:
                with open(file_path, "r", encoding="cp949") as f:
                    lines = f.readlines()
            except:
                continue
                
        for idx, line in enumerate(lines, 1):
            line_lower = line.lower()
            # "python"은 너무 흔하므로, "python "이나 "python.exe"나 "python"이 subprocess 등과 같이 쓰이는 패턴을 체크하거나 단순 매칭
            # msds_engine_v5 호출이나 subprocess가 핵심입니다.
            if any(k in line_lower for k in ["subprocess", "popen", "qprocess", "sys.executable", "os.system"]):
                try:
                    print(f"[{filename}:{idx}] {line.strip()}")
                except:
                    print(f"[{filename}:{idx}] (safe) {line.strip().encode('ascii', errors='replace').decode('ascii')}")
            # 또한 msds_engine_v5.py를 문자열로 언급하는 곳 체크
            elif "msds_engine_v5" in line_lower and ("run" in line_lower or "exec" in line_lower or "call" in line_lower or "sys" in line_lower or "cmd" in line_lower):
                try:
                    print(f"[{filename}:{idx}] {line.strip()}")
                except:
                    print(f"[{filename}:{idx}] (safe) {line.strip().encode('ascii', errors='replace').decode('ascii')}")

if __name__ == "__main__":
    search_subprocess_in_workspace()
