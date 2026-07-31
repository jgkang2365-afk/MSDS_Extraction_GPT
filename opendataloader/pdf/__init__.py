import os
import sys
import json
import subprocess
import tempfile
import shutil
from pathlib import Path

class PDFParser:
    """
    OpenDataLoader CLI를 위한 Python 브릿지 클래스.
    JSON 결과를 msds_engine_v5.py가 기대하는 객체 구조로 변환합니다.
    """
    def __init__(self):
        # Java 환경 확인 및 CLI 기본 설정
        pass

    def parse(self, pdf_path, cancel_check=None):
        # 1. 임시 디렉토리 생성
        tmp_dir = tempfile.mkdtemp()
        try:
            # 한글 경로 문제 및 손상된 PDF 구조 방어를 위해 fitz로 열어 클리닝 임시 PDF로 저장
            import fitz
            tmp_pdf_path = os.path.join(tmp_dir, "input.pdf")
            doc = fitz.open(pdf_path)
            doc.save(tmp_pdf_path, garbage=4, deflate=True, clean=True)
            doc.close()
            
            # 2. OpenDataLoader CLI 호출 (json 포맷) - 가상환경의 파이썬 인터프리터를 직접 매핑
            cmd = [sys.executable, "-m", "opendataloader_pdf", "input.pdf", "--format", "json", "--output-dir", ".", "--quiet"]
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=tmp_dir,
            )
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    if cancel_check and cancel_check():
                        process.terminate()
                        try:
                            process.communicate(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
                        raise InterruptedError("사용자 중지 요청")
            
            if process.returncode != 0:
                print(f"⚠️ [ODL Bridge] CLI 실행 실패 (Return Code: {process.returncode})")
                if stderr:
                    print(f"   └─ 상세 정보: {stderr.strip()}")
                return None

            # 3. 생성된 JSON 파일 찾기
            json_files = list(Path(tmp_dir).glob("*.json"))
            if not json_files:
                return None
            
            with open(json_files[0], "r", encoding="utf-8") as f:
                data = json.load(f)

            # 4. ODL JSON 구조를 msds_engine_v5 호환 구조로 변환
            return Document(data)
        except Exception as e:
            print(f"❌ [ODL Bridge] 처리 중 예외 발생: {str(e)}")
            return None
        finally:
            # 임시 디렉토리 정리
            shutil.rmtree(tmp_dir, ignore_errors=True)

class Document:
    def __init__(self, data):
        self.pages = []
        # ODL JSON은 'kids'에 페이지 단위 정보가 아닌 전체 요소가 섞여 있을 수 있음
        # 하지만 'number of pages' 정보와 각 요소의 'page number'가 있음
        num_pages = data.get("number of pages", 1)
        
        # 페이지별로 elements를 분류하여 저장
        page_map = {i+1: [] for i in range(num_pages)}
        
        def collect_elements(kids):
            for kid in kids:
                p_num = kid.get("page number", 1)
                etype = kid.get("type", "").upper()
                
                if etype == "TABLE":
                    page_map[p_num].append(TableElement(kid))
                elif etype in ["PARAGRAPH", "HEADING", "TEXT"]:
                    page_map[p_num].append(TextElement(kid))
                
                # 재귀적으로 kids 탐색 (문서 구조가 고도로 중첩된 경우 대비)
                if "kids" in kid and etype not in ["TABLE", "TABLE ROW", "TABLE CELL"]:
                    collect_elements(kid["kids"])

        collect_elements(data.get("kids", []))
        
        for i in range(1, num_pages + 1):
            self.pages.append(Page(page_map[i]))

class Page:
    def __init__(self, elements):
        self.elements = elements

class TextElement:
    def __init__(self, data):
        self.type = "TEXT"
        # ODL의 content 필드를 text로 매핑
        self.text = data.get("content", "").strip()
        # [보완] '제 품 명' 처럼 공백이 섞인 경우를 위해 엔진의 키워드 매칭을 돕도록 처리하거나
        # 엔진(msds_engine_v5)의 코드를 수정하는 대신 여기서 최대한 원본 텍스트를 깨끗하게 전달합니다.
        if "kids" in data:
            texts = []
            def _collect(ks):
                for k in ks:
                    if "content" in k: texts.append(k["content"])
                    if "kids" in k: _collect(k["kids"])
            _collect(data["kids"])
            if texts: self.text = " ".join(texts).strip()

class TableElement:
    def __init__(self, data):
        self.type = "TABLE"
        # [V24.4.5.5] 기하학적 분석을 위해 바운딩 박스 보존
        self.bbox = data.get("bounding box", None)
        self.rows = [Row(r) for r in data.get("rows", [])]

class Row:
    def __init__(self, data):
        self.cells = [Cell(c) for c in data.get("cells", [])]

class Cell:
    def __init__(self, data):
        # 셀 내부의 텍스트들을 모두 합침
        texts = []
        def _extract_text(kids):
            for k in kids:
                if "content" in k: texts.append(k["content"])
                if "kids" in k: _extract_text(k["kids"])
        
        if "kids" in data:
            _extract_text(data["kids"])
        
        self.text = " ".join(texts).strip()
        # [V24.4.5.5] 기하학적 분석을 위해 바운딩 박스 보존
        self.bbox = data.get("bounding box", None)
