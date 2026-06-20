# -*- coding: utf-8 -*-
import os
import sys
import fitz
import tempfile
import json
import subprocess
import shutil

def main():
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

    pdf_path = os.path.join("TEST_File", "010_포름알데하이드_시그마.pdf")
    if not os.path.exists(pdf_path):
        print(f"[-] 파일을 찾을 수 없습니다: {pdf_path}")
        return

    tmp_dir = tempfile.mkdtemp()
    tmp_pdf_path = os.path.join(tmp_dir, "input.pdf")

    try:
        # PDF 클리닝 및 복사
        doc = fitz.open(pdf_path)
        doc.save(tmp_pdf_path, garbage=4, deflate=True, clean=True)
        doc.close()

        # ODL CLI 실행
        cmd = [sys.executable, "-m", "opendataloader_pdf", "input.pdf", "--format", "json", "--output-dir", ".", "--quiet"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp_dir)

        if result.returncode != 0:
            print("[-] ODL 실행 실패")
            print("Stderr:", result.stderr)
            return

        from pathlib import Path
        json_files = list(Path(tmp_dir).glob("*.json"))
        if not json_files:
            print("[-] JSON 파일이 생성되지 않았습니다.")
            return

        with open(json_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)

        # JSON 결과를 보존하기 위해 작업 디렉토리에 복사 저장
        out_path = os.path.join("scratch", "010_formaldehyde_odl.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[+] JSON 데이터 임시 저장 완료: {out_path}")

    except Exception as e:
        print(f"[-] 에외 발생: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
