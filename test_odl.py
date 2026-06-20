# -*- coding: utf-8 -*-
import os
import sys
import traceback
import fitz
import tempfile
import shutil

def main():
    # 윈도우 인코딩 노이즈 방어
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

    try:
        from opendataloader.pdf import PDFParser
        parser = PDFParser()
        pdf_path = os.path.join("TEST_File", "010_포름알데하이드_시그마.pdf")
        
        print(f"[*] 대상 PDF 존재 여부: {os.path.exists(pdf_path)}")
        
        # 1. 임시 디렉토리 생성
        tmp_dir = tempfile.mkdtemp()
        tmp_pdf_path = os.path.join(tmp_dir, "input.pdf")
        
        print("[*] fitz로 PDF를 열고 클리닝 저장 시도...")
        doc = fitz.open(pdf_path)
        doc.save(tmp_pdf_path, garbage=4, deflate=True, clean=True)
        doc.close()
        print(f"[+] 클리닝 임시 PDF 크기: {os.path.getsize(tmp_pdf_path)} bytes")
        
        # 2. opendataloader_pdf 직접 호출 테스트 (원래 패키지 내부 코드 흐름 에뮬레이션)
        import subprocess
        print("[*] opendataloader_pdf CLI 직접 구동 시도...")
        cmd = [sys.executable, "-m", "opendataloader_pdf", "input.pdf", "--format", "json", "--output-dir", ".", "--quiet"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp_dir)
        
        print(f"[*] Return Code: {result.returncode}")
        if result.returncode != 0:
            print(f"[-] CLI 실행 실패:")
            print(f"Stdout: {result.stdout}")
            print(f"Stderr: {result.stderr}")
        else:
            print("[+] CLI 실행 성공!")
            # JSON 파일 리스트 조회
            from pathlib import Path
            json_files = list(Path(tmp_dir).glob("*.json"))
            print(f"[+] 생성된 JSON 파일들: {json_files}")
            if json_files:
                import json
                with open(json_files[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"[+] JSON 데이터 정상 로드 완료. (keys: {list(data.keys())})")
                
        # 정리
        shutil.rmtree(tmp_dir, ignore_errors=True)
        
    except Exception as e:
        print("[-] 예외 발생:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
