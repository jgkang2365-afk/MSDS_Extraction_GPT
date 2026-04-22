import sys
import os
import json
import re
import sqlite3
import time
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QLineEdit, QFileDialog, QTableWidget, 
    QTableWidgetItem, QHeaderView, QGroupBox, QGridLayout, 
    QScrollArea, QMessageBox, QComboBox, QProgressBar, QFrame,
    QSplitter, QTabWidget, QTextEdit, QStyledItemDelegate, QStyle,
    QStackedWidget, QToolButton, QSizePolicy
)
import fitz  # [NEW] PyMuPDF: 주님이 원하신 무지연 미리보기 엔진
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QRect, QPropertyAnimation, QEasingCurve, QUrl, QTimer
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette, QTextDocument, QCursor, QTextCursor, QImage, QPixmap
import pandas as pd # [NEW] 데이터 매칭용
from thefuzz import fuzz # [NEW] 데이터 매칭용
from html import escape
import subprocess # [NEW] Graphify 증분 인덱싱용
import graphify   # [NEW] 지능형 세만틱 엔진

import msds_core
import importlib # [HOT-RELOAD] 모듈 새로고침용
from msds_core import MSDSCore
import msds_engine_v5 as engine
import openpyxl  # [V6.994] 시트 목록 추출 및 사전 검증용

# [V7.0] 테이블 컬럼 인덱스 정의 (미리보기 브릿지용)
COL_IDX_FILENAME = 7
COL_IDX_HASH = 8
COL_IDX_FILEPATH = 9
COL_IDX_PAGE = 10

# [Part 1] 탐색기 스타일 자연스러운 정렬 (Natural Sort)
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

# [V9.0 우뇌 각성] Graphify 백그라운드 인덱싱 워커
class GraphifyIndexerThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)

    def __init__(self, pdf_path, extracted_data):
        super().__init__()
        self.pdf_path = pdf_path
        self.extracted_data = extracted_data

    def run(self):
        filename = os.path.basename(self.pdf_path)
        try:
            self.progress_signal.emit(f"🧠 지식 그래프 학습 중... ({filename})")
            import graphify
            # graphify 모듈의 증분 업데이트 함수 호출
            if hasattr(graphify, 'update_graph_incremental'):
                graphify.update_graph_incremental(file_path=self.pdf_path, context=self.extracted_data)
            self.finished_signal.emit(f"✅ 지식 그래프 업데이트 완료 ({filename})")
        except Exception as e:
            self.finished_signal.emit(f"❌ 지식 그래프 학습 실패 ({filename}): {e}")

# [Part 2] Seamless PDF Preview 패널 (바이너리 강제 로드 버전)
class PDFPreviewPanel(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter) 
        self.layout.setContentsMargins(0, 0, 0, 0) # 여백 제거 (시인성 극대화)
        self.layout.setSpacing(5)
        self.setWidget(self.container)
        self.setStyleSheet("background-color: #525659; border: none;")
        self.labels = [] 
        self.current_pdf_path = None
        self.setMinimumWidth(500) # 주님 요청: 최소 너비 500px 보장
        
        # [NEW] 실시간 고해상도 랜더링용 타이머 (성능과 화질 동시 잡기)
        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.apply_high_res_render)

    def resizeEvent(self, event):
        """[Responsive Zoom] 창 너비 변경 시 즉시 확대"""
        super().resizeEvent(event)
        self.update_label_sizes()
        self.render_timer.start(300) # 드래그 멈추면 0.3초 후 선명하게 다시 그리기

    def load_pdf(self, file_path):
        """[완전 해결] PNG 바이너리 변환 로드로 백지 현상 원천 차단"""
        for i in reversed(range(self.layout.count())):
            item = self.layout.itemAt(i)
            if item.widget(): item.widget().deleteLater()
        self.labels = []
        self.current_pdf_path = file_path
        
        if not file_path or not os.path.exists(file_path): return

        try:
            doc = fitz.open(file_path)
            for page in doc:
                ratio = page.rect.height / page.rect.width
                lbl = QLabel()
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet("background: white; border-bottom: 2px solid #222;")
                lbl.setScaledContents(True) 
                
                # [핵심] 포맷 mismatch 방지를 위해 PNG 데이터로 추출 후 로드
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                qimg = QImage.fromData(pix.tobytes("png")) # 이 방식이 가장 확실합니다
                
                lbl.setPixmap(QPixmap.fromImage(qimg))
                self.labels.append((lbl, ratio))
                self.layout.addWidget(lbl)
            doc.close()
            self.update_label_sizes()
            QApplication.processEvents()
            self.verticalScrollBar().setValue(0)
        except Exception as e:
            print(f"PDF Load Error: {e}")

    def navigate_to_page(self, page_num):
        """[V7.0] 특정 페이지로 스크롤 이동"""
        if 1 <= page_num <= len(self.labels):
            lbl, _ = self.labels[page_num - 1]
            # 해당 라벨의 위치로 스크롤바 이동
            self.verticalScrollBar().setValue(lbl.y())

    def apply_high_res_render(self):
        """[해결] 고해상도 렌더링 시에도 PNG 바이너리 방식 적용"""
        if not self.current_pdf_path or not self.labels: return
        target_width = self.viewport().width()

        try:
            doc = fitz.open(self.current_pdf_path)
            for i, (lbl, _) in enumerate(self.labels):
                if i >= len(doc): break
                page = doc[i]
                zoom = target_width / page.rect.width
                zoom = max(1.5, min(zoom, 3.5)) 
                
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                # PNG 바이너리 추출 로드
                img = QImage.fromData(pix.tobytes("png"))
                lbl.setPixmap(QPixmap.fromImage(img))
                lbl.repaint() # 화면 즉시 갱신 강제
            doc.close()
        except Exception as e:
            print(f"High-Res Render Error: {e}")

    def update_label_sizes(self):
        """창 너비에 맞춰 글자를 주먹만 하게 키움"""
        if not self.labels: return
        # 뷰포트 너비를 정확히 계산하여 '백지' 현상 차단
        target_width = max(500, self.viewport().width() - 2) 
        self.container.setFixedWidth(target_width)
        for lbl, ratio in self.labels:
            lbl.setFixedWidth(target_width)
            lbl.setFixedHeight(int(target_width * ratio))

class FileDropArea(QLabel):
    """[NEW] PDF 파일 및 폴더 드래그 앤 드롭 수신 영역 (헤더 통합형 슬림 디자인)"""
    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setText("[FILE] PDF 파일을 이곳에 드래그하여 추가 (폴더 드랍 가능)")
        self.setAcceptDrops(True)
        self.setFixedHeight(35) 
        self.setFixedWidth(420) # 너비 확장 (글자 잘림 방지)
        self.setStyleSheet("""
            QLabel {
                border: 1px dashed #0078d4;
                border-radius: 4px;
                background-color: #f3f9ff;
                color: #0078d4;
                font-weight: bold;
                font-size: 12px;
                margin-left: 20px;
                margin-right: 20px;
            }
            QLabel:hover {
                background-color: #e1f0ff;
                border-style: solid;
                color: #005a9e;
            }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        self.filesDropped.emit(files)

class MultiLineDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        if index.column() == 3: # CAS 원본 열
            editor = QTextEdit(parent)
            editor.setAcceptRichText(False)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() == 3:
            value = index.model().data(index, Qt.EditRole)
            editor.setPlainText(str(value))
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() == 3:
            model.setData(index, editor.toPlainText(), Qt.EditRole)
        else:
            super().setModelData(editor, model, index)

class HTMLDelegate(QStyledItemDelegate):
    """[Part 15-B] 고도화된 델리게이트. 배경과 텍스트 드로잉 분리 및 다중행 편집 지원"""
    
    # --- [V11.0] 다중 행 편집기(QTextEdit) 지원 로직 이식 ---
    def createEditor(self, parent, option, index):
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)
        editor.setStyleSheet("QTextEdit { padding: 3px; font-family: 'Malgun Gothic'; font-size: 9pt; }")
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        editor.setPlainText(str(value) if value is not None else "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText(), Qt.EditRole)
    # ---------------------------------------------------------

    def _get_doc(self, option, index):
        """[Part 15-C] HTML 문서를 생성하고 폰트 및 너비를 설정함."""
        text = index.data()
        if not text: return None
        
        parts = [p.strip() for p in re.split(r'[;\n]+', text) if p.strip()]
        html_parts = []
        for p in parts:
            p = p.strip()
            if not p: continue
            
            escaped_p = escape(p)
            
            if p.startswith("[특별]") or p.startswith("[허가]"):
                html_parts.append(f"<span style='color:#f56c6c;'>{escaped_p[:4]}</span>{escaped_p[4:]}")
            elif p.startswith("[특검]"):
                html_parts.append(f"<span style='color:#409eff;'>{escaped_p[:4]}</span>{escaped_p[4:]}")
            else:
                html_parts.append(escaped_p)
        
        # [수정점] 줄바꿈 시 ; 뒤에 HTML 개행 태그(<br>)를 강제 삽입하여 표시 화면도 완벽하게 줄바꿈
        final_html = f"<html><body style='font-family:Malgun Gothic; font-size:9pt;'>{';<br>'.join(html_parts)}</body></html>"
        
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setHtml(final_html)
        
        if option.widget:
            col_width = option.widget.columnWidth(index.column())
            target_width = max(50, col_width - 15)
        else:
            target_width = max(50, option.rect.width() - 15)
            
        doc.setTextWidth(target_width)
        return doc

    def paint(self, painter, option, index):
        try:
            self.initStyleOption(option, index)
            option.text = "" 
            style = option.widget.style() if option.widget else QApplication.style()
            style.drawControl(QStyle.CE_ItemViewItem, option, painter, option.widget)
            
            doc = self._get_doc(option, index)
            if not doc: return

            painter.save()
            v_offset = (option.rect.height() - doc.size().height()) / 2
            painter.translate(option.rect.left() + 5, option.rect.top() + v_offset)
            doc.drawContents(painter)
            painter.restore()
        except:
            super().paint(painter, option, index)

    def sizeHint(self, option, index):
        try:
            doc = self._get_doc(option, index)
            if not doc: return super().sizeHint(option, index)
            return QSize(int(doc.idealWidth()), int(doc.size().height()) + 10)
        except:
            return super().sizeHint(option, index)

# [Enterprise Style Constants]
PRIMARY_BLUE = "#0056b3"
SIDEBAR_BLUE = "#004494"
LIGHT_BLUE = "#e7f1ff"
WHITE = "#ffffff"
GRAY_BORDER = "#d1d1d1"
TEXT_MAIN = "#333333"
TEXT_SUB = "#666666"

LOG_INFO = "🟢"
LOG_WARN = "🟡"
LOG_ERROR = "🔴"

class SidebarButton(QPushButton):
    """익스플로러 스타일의 사이드바 버튼 (슬림 모드 지원)"""
    def __init__(self, text, icon_str, parent=None):
        super().__init__(parent)
        self.full_text = text
        self.icon_str = icon_str
        self.setText(text)
        self.setCheckable(True)
        self.setFixedHeight(50)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.update_style(False)

    def update_style(self, is_active):
        active_style = f"background-color: {WHITE}; color: {PRIMARY_BLUE}; border-left: 4px solid {WHITE};" if is_active else "background-color: transparent; color: white; border-left: 4px solid transparent;"
        self.setStyleSheet(f"""
            QPushButton {{
                {active_style}
                text-align: left;
                padding-left: 15px;
                font-weight: bold;
                font-size: 13px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.1);
            }}
        """)

    def set_slim(self, slim):
        if slim:
            self.setText(self.icon_str)
            self.setToolTip(self.full_text)
            self.setStyleSheet(self.styleSheet() + "padding-left: 0; text-align: center; font-size: 18px;")
        else:
            self.setText(self.full_text)
            self.setToolTip("")
            self.setStyleSheet(self.styleSheet() + "padding-left: 15px; text-align: left; font-size: 13px;")

class ExtractionWorker(QThread):
    """1단계: PDF에서 텍스트 기반 추출만 수행 (API 연동 없이)"""
    update_log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    result_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    cache_update_signal = pyqtSignal(str, dict) # [NEW] 캐시 업데이트 요청용

    def __init__(self, core, pdf_paths, cache=None):
        super().__init__()
        self.core = core
        self.pdf_paths = pdf_paths
        self.cache = cache or {}

    def run(self):
        total = len(self.pdf_paths)
        for i, path in enumerate(self.pdf_paths):
            try:
                fn = os.path.basename(path)
                if i > 0: self.update_log_signal.emit("") # [추가] 파일 간 가독성을 위한 빈 줄
                
                # [NEW] 캐시 체크 (SHA-256 해시 기준)
                f_hash = self.core.calculate_file_hash(path)
                if not f_hash:  # [V8.3] 해시 생성 보장 (Fallback)
                    f_hash = f"fallback_{i}_{fn}"
                
                if f_hash and getattr(self, 'cache', None) and f_hash in self.cache:
                    self.update_log_signal.emit(f"[*] [{fn}] 캐시된 결과가 발견되었습니다. (재추출 건너뜀)")
                    cached_data = self.cache[f_hash]
                    res_data = {
                        "filename": fn,
                        "f_hash": f_hash, # [NEW] 해시 포함
                        "product_name": cached_data.get("product_name", "미확인"),
                        "reliability": cached_data.get("reliability", "N/A"),
                        "신호등": cached_data.get("신호등", "⚪"),
                        "raw_content": cached_data.get("raw_content", ""),
                        "status": "캐시 데이터 로드됨"
                    }
                    self.result_signal.emit(res_data)
                    self.progress_signal.emit(int((i + 1) / total * 100))
                    continue

                self.update_log_signal.emit("="*20 + f" [{fn} 추출 시작] " + "="*20)
                # [V7-Final] 통합형 엔진으로 추출 수행 (정규식 개안 및 숲-나무 분석 적용)
                ext_res = engine.analyze_msds(path, log_func=self.update_log_signal.emit)
                
                extracted_data = {
                    "f_hash": f_hash,
                    "product_name": ext_res.get("제품명", "미확인"),
                    "reliability": ext_res.get("신뢰도", "N/A"),
                    "신호등": ext_res.get("신호등", "⚪"), 
                    "raw_content": ext_res.get("구성성분 및 함유량", ext_res.get("함유량", "")),
                    "full_path": path, # [V7.0] 절대 경로 저장
                    "page": ext_res.get("page", 1) # [V7.0] 페이지 정보 저장
                }
                
                # [NEW] 캐시에 저장 요청
                if f_hash:
                    self.cache_update_signal.emit(f_hash, extracted_data)

                res_data = extracted_data.copy()
                res_data["filename"] = fn
                res_data["status"] = "추출 완료"
                
                self.result_signal.emit(res_data)
                self.progress_signal.emit(int((i + 1) / total * 100))
            except Exception as e:
                self.update_log_signal.emit(f"[!] 오류 발생 ({os.path.basename(path)}): {e}")
                err_data = {
                    "filename": os.path.basename(path),
                    "product_name": "추출 오류",
                    "reliability": "[ERROR]",
                    "신호등": "🔴",
                    "raw_content": f"오류: {e}",
                    "status": "오류"
                }
                self.result_signal.emit(err_data)
                self.progress_signal.emit(int((i + 1) / total * 100))
            
            # [지능형 속도 조절] 파일 간 최소 1초의 간격을 두어 RPM 제한 회피
            time.sleep(1.0)
        
        self.finished_signal.emit()

class ValidationWorker(QThread):
    """2단계: 테이블의 CAS 데이터를 기반으로 KOSHA API 검증 수행"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    result_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()

    def __init__(self, parent_gui, core, table_data):
        super().__init__()
        self.parent_gui = parent_gui # [NEW] DB 접근 및 로그 출력을 위한 부모 참조
        self.core = core
        self.table_data = table_data # [[f_hash, fn, prod, cas_content], ...]

    def run(self):
        total = len(self.table_data)
        for i, data in enumerate(self.table_data):
            try:
                f_hash = data.get("f_hash")
                fn = data.get("filename")
                prod = data.get("prod")
                cas_content = data.get("cas_content")
                row_idx = data.get("row_idx") # Fallback용
                if i > 0: self.log_signal.emit("") # [추가] 파일 간 가독성을 위한 빈 줄
                
                # [Master 지시서] 🔵 파란색 신호등 기반 3-Way 하이브리드 로직 가동
                db_records = self.parent_gui.get_db_knowledge(prod)
                
                # Case 1: 지식이 딱 1개인 경우 (🟢 초록색 하이패스)
                if len(db_records) == 1:
                    rec = db_records[0]
                    res = {
                        "row_idx": row_idx, "f_hash": f_hash, "filename": fn, "status": "High-Pass",
                        "product_name": prod,
                        "validation": {
                            "cas_with_content": rec[0].split(";\n") if rec[0] else [],
                            "work_subjects": rec[1], 
                            "res_1st": rec[2].split(";\n") if rec[2] else [],
                            "res_2nd": rec[3].split(";\n") if rec[3] else []
                        }
                    }
                    self.result_signal.emit(res)
                    self.progress_signal.emit(int((i + 1) / total * 100))
                    continue

                # Case N: 지식이 2개 이상인 경우 (🔵 파란색 마킹 및 사후 검수 대상)
                elif len(db_records) >= 2:
                    rec = db_records[0] # 우선 최신 것 로드
                    res = {
                        "row_idx": row_idx, "f_hash": f_hash, "filename": fn, "status": "Review Required",
                        "product_name": prod, "db_records": db_records, # 전체 기록 전달
                        "validation": {
                            "cas_with_content": rec[0].split(";\n") if rec[0] else [],
                            "work_subjects": rec[1], 
                            "res_1st": rec[2].split(";\n") if rec[2] else [],
                            "res_2nd": rec[3].split(";\n") if rec[3] else []
                        }
                    }
                    self.result_signal.emit(res)
                    self.progress_signal.emit(int((i + 1) / total * 100))
                    continue

                # Case 0: DB에 지식이 없는 경우 (기존 API 엔진 가동)
                self.log_signal.emit(f"[*] [Case-0] DB 지식 0건: [{prod}] (API 엔진 가동)")
                self.log_signal.emit("="*20 + f" [{prod} API 검증 시작] " + "="*20)
                # [V8.8] 지능형 CAS 추출 및 함유량 보존 로직 (함유량% 보장)
                # [V8.8] 지능형 CAS 추출 및 함유량 보존 로직 (함유량% 보장)
                cas_to_content = {}
                for match in re.finditer(r"(\d{2,7}-\d{2}-\d)\s*(?:\(([^)]+)\))?", str(cas_content)):
                    cas = match.group(1)
                    content_val = match.group(2) if match.group(2) else ""
                    # [V8.8] 함유량 % 기호 강제 삽입 로직 (숫자가 있는데 %가 없으면 추가)
                    if content_val and "%" not in content_val:
                        # 숫자나 범위를 포함하고 있다면 % 추가
                        if re.search(r'\d', content_val):
                            content_val = f"{content_val}%"
                    cas_to_content[cas] = content_val
                
                # 2. 주님의 지시대로 순수 CAS 문자열만 발라내어 엔진에 전달
                pure_cas_list = list(cas_to_content.keys())
                pure_cas_str = "; ".join(pure_cas_list) if pure_cas_list else cas_content

                # [수정] 코어 호출 시 f_hash 파라미터 전달
                raw_val_res = self.core.validate_with_kosha(pure_cas_str, log_func=self.log_signal.emit, full=False, f_hash=f_hash)
                
                # [V7.0 추가] 캐시 적중 시 하위 파싱(components 루프 등) 전면 우회
                if raw_val_res.get("status") == "Cache-Hit":
                    manual = raw_val_res.get("manual_data", {})
                    val_res = {
                        "res_1st": manual.get("reg1", "").split(";\n") if manual.get("reg1") else [""],
                        "res_2nd": manual.get("reg2", "").split(";\n") if manual.get("reg2") else [""],
                        "work_subjects": manual.get("measure", ""),
                        "cas_with_content": manual.get("raw_content", "").split(";\n") if manual.get("raw_content") else []
                    }
                    res_data = {
                        "row_idx": row_idx,
                        "f_hash": f_hash,
                        "filename": fn,
                        "product_name": manual.get("product_name", prod),
                        "validation": val_res,
                        "status": "검증 완료 (캐시)"
                    }
                    self.result_signal.emit(res_data)
                    self.progress_signal.emit(int((i + 1) / total * 100))
                    continue # API 파싱 로직을 스킵하고 다음 파일로 즉시 이동
                
                # [V8.5] MSDS Core(components) -> GUI Format(res_1st, res_2nd) 브리지 변환기
                res_1st_list = []
                res_2nd_list = []
                res_work_subjects = []    # 1% 이상 측정대상
                res_work_non_subjects = [] # 1% 미만 측정 비대상
                
                for c in raw_val_res.get("components", []):
                    name = c.get("name", "Unknown")
                    cas = c.get("cas", "")
                    
                    # 엔진 전송 전 잘라냈던 함유량을 원본에서 복원
                    range_val = cas_to_content.get(cas, c.get("content", ""))
                    
                    # [V27.5 영문명/기호 완벽 보존 로직 복제]
                    if re.search(r'[가-힣]', name):
                        name_no_eng = re.sub(r'\s*\([^가-힣]*\)', '', name)
                        clean_name = name_no_eng.replace(" ", "").strip()
                    else:
                        clean_name = name.strip()
                        
                    # [최종 지침] MES 표준 명칭으로 치환 (결과 필드에서만)
                    mes_entry = self.parent_gui.mes_cas_map.get(cas, {})
                    mes_std_name = mes_entry.get("물질명", "")
                    if mes_std_name:
                        clean_name = str(mes_std_name)

                    osh = c.get("osh", {})
                    is_work = osh.get("is_measured", False)
                    is_spec = osh.get("is_special", False)
                    is_mgmt = osh.get("is_special_mgmt", False)
                    is_permit = osh.get("is_permit", False)

                    prefix = ""
                    if is_mgmt: prefix = "[특별]"
                    elif is_permit: prefix = "[허가]"
                    elif is_spec and not is_work: prefix = "[특검]"

                    c_str = f"({range_val})" if range_val else ""
                    
                    # [V9.1] 1차 결과: [접두사]물질명[CAS(함유량%)] 형식 엄수
                    res_1st_list.append(f"{prefix}{clean_name}[{cas}{c_str}]")
                    
                    # 2. 2차 결과: 작업환경측정 또는 특수건강진단 대상만 집계
                    if is_work or is_spec:
                        res_2nd_list.append(f"{prefix}{clean_name}{c_str}")
                        
                    # 3. 측정대상 (1% 기준 필터링 및 비대상 처리)
                    if is_work:
                        percentage = 0.0
                        nums = re.findall(r'[\d\.]+', range_val)
                        if nums:
                            try: percentage = max(float(n) for n in nums)
                            except: percentage = 0.0
                            if "<" in range_val and percentage <= 1.0: percentage = 0.5
                        else: percentage = 100.0 
                        
                        is_ge_1 = (percentage >= 1.0)
                        
                        if is_ge_1:
                            res_work_subjects.append(clean_name)
                        else:
                            # [V9.3] 주님 지령: <1% 성분은 반드시 측정 비대상[물질명(함유량%)] 형식으로 묶음
                            res_work_non_subjects.append(f"{clean_name}({range_val})")

                # 측정대상 포맷팅 결합
                subj_str = "; ".join(res_work_subjects)
                non_subj_str = f"측정 비대상[{'; '.join(res_work_non_subjects)}]" if res_work_non_subjects else ""
                final_work_str = "; ".join(filter(None, [subj_str, non_subj_str]))

                val_res = {
                    "res_1st": res_1st_list,
                    "res_2nd": res_2nd_list,
                    "work_subjects": final_work_str,
                    "cas_with_content": str(cas_content).split("; ") if cas_content else [] 
                }

                # [지시서] 용접(Welding) 상황 인식형 유해인자 보정 로직 발동
                is_welding = "용접" in prod
                has_iron = "7439-89-6" in cas_to_content
                
                if is_welding and has_iron:
                    # 1. 2차 결과(reg2) 강제 고착: API 결과와 무관하게 철 추가
                    iron_content = cas_to_content.get("7439-89-6", "")
                    iron_str = f"철({iron_content})"
                    if iron_str not in res_2nd_list:
                        res_2nd_list.append(iron_str)
                    
                    # 2. 측정대상(work_subjects) 최우선 기입: 용접흄; 산화철(분진, 흄)
                    # 기존 API 결과가 있으면 뒤에 세미콜론으로 연결
                    welding_hazard = "용접흄; 산화철(분진, 흄)"
                    if final_work_str:
                        final_work_str = f"{welding_hazard}; {final_work_str}"
                    else:
                        final_work_str = welding_hazard
                        
                    # val_res 갱신
                    val_res["res_2nd"] = res_2nd_list
                    val_res["work_subjects"] = final_work_str

                # [V8.3] 응답 보장: 결과가 비어있으면 명시적 메시지 삽입 (용접 보정 이후 최종 체크)
                if not val_res.get("res_1st"):
                    val_res["res_1st"] = [""]
                if not val_res.get("res_2nd"):
                    val_res["res_2nd"] = [""]
                
                res_data = {
                    "row_idx": row_idx,
                    "f_hash": f_hash, # [V8.0] 해시 정보 유지
                    "filename": fn,
                    "product_name": prod,
                    "validation": val_res,
                    "status": "검증 완료"
                }
                self.result_signal.emit(res_data)
                self.progress_signal.emit(int((i + 1) / total * 100))
            except Exception as e:
                self.log_signal.emit(f"[!] 오류 발생 ({fn}): {e}")
        
        self.finished_signal.emit()

class ModernMappingPanel(QGroupBox):
    """가로형(일반 목록) 전용 슬림 매핑 패널 (D, L, M, N, O 기본값)"""
    def __init__(self, title="데이터 열 매핑 설정 (가로형 전용)"):
        super().__init__(title)
        self.inputs = {}
        layout = QGridLayout()
        layout.setContentsMargins(15, 20, 15, 10)
        layout.setHorizontalSpacing(15)
        layout.setVerticalSpacing(10)

        # 사용자가 요청한 가로형 5대 핵심 열 + 바인딩 5개 필드
        fields = [
            ("제품명", "D"), ("파일명", "P"),
            ("2차 결과(규제)", "L"), ("1차 결과(전체)", "M"),
            ("측정대상1", "N"), ("측정대상2", ""), # 측정대상을 복수로 저장하기 위해 두 칸으로 분리
            ("CAS 원본", "O"),
            ("공정명", "B"), ("제조/사용", "C"),
            ("사용용도", "E"), ("월취급량", "S"), ("단위", "T")
        ]

        for i, (name, default) in enumerate(fields):
            # 측정대상2는 측정대상1 처리 시 같이 처리하므로 루프에서 건너뜀
            if name == "측정대상2": continue
            
            # 실제 표시되는 인덱스 계산을 위해 보정
            idx = sum(1 for f, _ in fields[:i] if f != "측정대상2") # 0, 1, 2...
            
            # 3개를 한 줄에 배치하여 좌측으로 밀집 (0, 1 / 2, 3 / 4, 5)
            row = idx // 3
            col_base = (idx % 3) * 2
            
            lbl = QLabel(name if name != "측정대상1" else "측정대상")
            lbl.setStyleSheet("font-weight: bold; color: #444; min-width: 85px;")
            layout.addWidget(lbl, row, col_base, Qt.AlignRight)
            
            if name == "측정대상1":
                # 수평 레이아웃으로 칸 두 개를 묶어서 그리드 한 칸에 배치
                h_box = QHBoxLayout()
                h_box.setContentsMargins(0, 0, 0, 0)
                h_box.setSpacing(5)
                
                edit1 = self._create_edit(default)
                edit2 = self._create_edit("")
                
                h_box.addWidget(edit1)
                h_box.addWidget(QLabel("&"))
                h_box.addWidget(edit2)
                h_box.addStretch()
                
                layout.addLayout(h_box, row, col_base + 1, Qt.AlignLeft)
                self.inputs["측정대상1"] = edit1
                self.inputs["측정대상2"] = edit2
            else:
                edit = self._create_edit(default)
                layout.addWidget(edit, row, col_base + 1, Qt.AlignLeft)
                self.inputs[name] = edit
        
        # 마지막 빈 열에 Stretch를 주어 위젯들이 좌측으로 밀집되도록 함
        layout.setColumnStretch(6, 1)
        # 하단 여백을 채워 위로 정렬되도록 함 (__init__의 마지막)
        layout.setRowStretch((len(fields) + 1) // 3 + 1, 1)
        self.setLayout(layout)

    def _create_edit(self, text):
        """[Helper] 표준화된 입력 필드 생성"""
        edit = QLineEdit(text)
        edit.setFixedWidth(50)
        edit.setFixedHeight(28)
        edit.setAlignment(Qt.AlignCenter)
        edit.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 2px;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
                background-color: #f0f7ff;
            }
        """)
        return edit

    def get_mapping(self):
        """현재 입력된 모든 매핑 정보를 딕셔너리로 반환"""
        return {k: v.text().strip() for k, v in self.inputs.items()}

    def set_mapping(self, data):
        """저장된 데이터를 바탕으로 매핑 입력창을 채움"""
        if not data: return
        for k, v in data.items():
            if k in self.inputs:
                self.inputs[k].setText(v)

class KnowledgeManager:
    """[Flawless] 1SMU 지능형 지식 관리 엔진 (Graphify 기반)"""
    def __init__(self, log_func=None):
        self.log = log_func or print
        self.graph_path = os.path.join(os.environ["USERPROFILE"], ".graphify", "knowledge", "graph.json")
        self.history_path = "matching_history.json"
        self.graph_data = self._load_graph()

    def _load_graph(self):
        if os.path.exists(self.graph_path):
            try:
                with open(self.graph_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: return {}
        return {}

    def get_semantic_score(self, source, target):
        """지식 그래프 및 매칭 히스토리를 통한 시멘틱 유사성(동의어/별칭) 검증"""
        source = source.strip().lower()
        target = target.strip().lower()
        if source == target: return 100

        # 1. 매칭 히스토리(학습 경험) 최우선 확인
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    temp_history = json.load(f)
                    # [지시서] 리스트 오염 방탄 로직: 데이터 타입 강제 변환
                    history = temp_history if isinstance(temp_history, dict) else {}
                    if source in history and history[source].get("matched_name", "").lower() == target:
                        return 99 # 학습된 매칭 경험 (최고 신뢰도)
            except: pass

        # 2. 지식 그래프 노드 내 Alias 매칭 확인
        if self.graph_data:
            nodes = self.graph_data.get("nodes", [])
            for node in nodes:
                metadata = node.get("metadata", {})
                aliases = [a.lower() for a in metadata.get("aliases", [])]
                name = node.get("name", "").lower()
                
                names_in_node = aliases + [name]
                if source in names_in_node and target in names_in_node:
                    return 98 # 시멘틱 링크 확인됨
                
        return 0

    def update_experience(self, pdf_name, excel_name, binding_data):
        """[Hot-Fix] 리스트([]) 생성 버그 차단 및 딕셔너리({}) 강제 전환"""
        history = {}
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    temp_data = json.load(f)
                    # 데이터 타입이 dict가 아닐 경우 즉시 빈 dict로 초기화하여 TypeError 방지
                    history = temp_data if isinstance(temp_data, dict) else {}
            except Exception:
                history = {}
        
        history[pdf_name] = {
            "matched_name": excel_name,
            "binding": binding_data,
            "timestamp": datetime.now().isoformat()
        }
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
            
        self.log(f"[*] 지능형 학습: '{pdf_name}' -> '{excel_name}' 매칭 경험 저장 완료.")
        
        # [핵심] Graphify 증분 인덱싱(Incremental Indexing) 호출
        try:
            subprocess.Popen(["graphify", "update", self.history_path], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.log("[*] Graphify 증분 인덱싱 백그라운드 실행 중...")
        except Exception as e:
            self.log(f"[!] 증분 인덱싱 실패: {e}")

class MatchingWorker(QThread):
    """
    엑셀의 '화학물질명'과 PDF 추출 결과의 '제품명'을 논리적으로 매칭함.
    thefuzz 라이브러리를 사용하여 유사도 점수 계산.
    """
    finished = pyqtSignal(list) # 매칭 결과 목록 [(pdf_idx, excel_idx, score, binding_data), ...]
    progress = pyqtSignal(int, str) # 현재 진행률, 메시지

    def __init__(self, excel_path, sheet_name, pdf_results, mapping=None):
        super().__init__()
        self.excel_path = excel_path
        self.sheet_name = sheet_name
        self.pdf_results = pdf_results # [{'제품명': '...', ...}, ...]
        self.mapping = mapping if mapping else {} # [NEW] 환경설정 매핑 정보 주입
        self.km = None 
        self.is_running = True

    @staticmethod
    def normalize_name(text):
        """[Hot-Fix] 제품명 정규화: 모델명 보존을 위해 괄호 내용 삭제 로직 전면 제거"""
        if not text: return ""
        text = str(text).strip().lower()
        
        # 1. 버전 및 특정 키워드만 정제 (괄호 안의 모델명은 보존)
        text = re.sub(r"v\d+(\.\d+)*", "", text)
        text = re.sub(r"rev\.\d+", "", text)
        text = text.replace("(최종)", "").replace("복사본", "").replace("copy", "")
        
        # 2. 특수문자 제거 시 모델명 식별자인 하이픈(-)은 보존
        text = re.sub(r"[^가-힣a-z0-9\-]", " ", text)
        return " ".join(text.split())

    def run(self):
        try:
            self.progress.emit(0, "엑셀 데이터 로드 중...")
            
            # [V9.7] 주님이 주입한 타입 무결성 검증 (숫자 인덱스여야 함)
            target_col_idx_raw = self.mapping.get("제품명", 4) # 기본값 D(4)
            if isinstance(target_col_idx_raw, int):
                target_col_idx = target_col_idx_raw - 1 # 0-based for pandas
            else:
                # 안전장치: 여전히 문자라면 여기서 마지막으로 변환 시도
                target_col_idx = SMUGUI.c2i(target_col_idx_raw) - 1

            if target_col_idx < 0:
                self.progress.emit(0, "오류: 잘못된 제품명 열 설정입니다.")
                self.finished.emit([])
                return

            target_col_letter = self.mapping.get("제품명_raw", "D") # 로깅용
            
            # [V9.6] 주님의 실무 양식 보장: 1~10행을 돌며 '제품명' 열에 데이터가 있는 행을 시작점(Header)으로 인지
            raw_xl = pd.read_excel(self.excel_path, sheet_name=self.sheet_name, engine='openpyxl', header=None, nrows=10)
            header_idx = 0
            for r_idx, row in raw_xl.iterrows():
                try:
                    cell_val = str(row[target_col_idx]).strip()
                    if cell_val and cell_val not in ["nan", "None"]:
                        header_idx = r_idx
                        break
                except: continue
            
            # 실제 데이터 로드
            df = pd.read_excel(self.excel_path, sheet_name=self.sheet_name, engine='openpyxl', header=header_idx)
            
            # [V10.1] 엑셀 열 확정 및 예외 처리 단일화 (구문 중복 제거)
            target_col_letter = self.mapping.get("제품명_raw", "D")
            try:
                target_col = df.columns[target_col_idx]
            except Exception as e:
                self.progress.emit(0, f"오류: 엑셀 열({target_col_letter})에서 데이터를 로드할 수 없습니다: {e}")
                self.finished.emit([])
                return

            self.progress.emit(10, "논리적 매칭 수행 중...")
            matches = []
            
            # [V9.6] 0% 매칭 검증 및 로그 추출용 표본 수집
            excel_names = [str(x).strip() for x in df[target_col]]
            norm_excel_names = [MatchingWorker.normalize_name(x) for x in excel_names]
            
            if len(norm_excel_names) > 0:
                samples = [x for x in excel_names[:5] if str(x).strip()]
                self.progress.emit(15, f"[*] 분석 대상 열('{target_col}') 표본: {', '.join(samples[:3])}...")
            
            total = len(self.pdf_results)

            for i, pdf_item in enumerate(self.pdf_results):
                if not self.is_running: break
                
                # [수정] '제품명' 대신 엔진 표준 키인 'product_name'을 엄격히 참조
                pdf_raw_name = str(pdf_item.get('product_name', '')).strip()
                pdf_norm_name = self.normalize_name(pdf_raw_name)
                
                if not pdf_norm_name:
                    matches.append({
                        'pdf_idx': i, 
                        'excel_idx': -1, 
                        'score': 0, 
                        'pdf_filename': pdf_item.get('filename', 'N/A'), 
                        'pdf_name': pdf_raw_name if pdf_raw_name else "추출 실패", # [V10.3] 공란 방지
                        'excel_name': "N/A", 
                        'binding_data': None
                    })
                    continue

                best_score = -1
                best_idx = -1
                
                for j, excel_raw_name in enumerate(excel_names):
                    excel_norm_name = norm_excel_names[j]
                    if not excel_norm_name: continue
                    
                    # 1. 정문화된 텍스트 완전 일치
                    if pdf_norm_name == excel_norm_name:
                        best_score = 100
                        best_idx = j
                        break
                    
                    # 2. 유사도 계산 (하이브리드 방식)
                    # A. Fuzzy Score (정문화 기반 비교로 노이즈 영향 최소화)
                    f_score = fuzz.token_sort_ratio(pdf_norm_name, excel_norm_name)
                    
                    # B. Semantic Score
                    s_score = 0
                    if hasattr(self, 'km') and self.km:
                        s_score = self.km.get_semantic_score(pdf_raw_name, excel_raw_name)
                    
                    # 지식 그래프 확인 시 가중치 부여
                    score = max(f_score, s_score)

                    if score > best_score:
                        best_score = score
                        best_idx = j
                
                # 바인딩 데이터 추출
                binding_data = None
                if best_idx != -1:
                    row = df.iloc[best_idx]
                    binding_data = {
                        "공정명": str(row.get("공정명", "")),
                        "제조/사용": str(row.get("제조/사용", "")),
                        "사용용도": str(row.get("사용용도", "")),
                        "월취급량": str(row.get("월취급량", "")),
                        "단위": str(row.get("단위", ""))
                    }

                matches.append({
                    'pdf_idx': i,
                    'excel_idx': best_idx,
                    'score': best_score,
                    'pdf_filename': pdf_item.get('filename', 'N/A'),
                    'pdf_name': pdf_raw_name if pdf_raw_name else "추출 실패", # [V10.3] 공란 방지
                    'excel_name': excel_names[best_idx] if best_idx != -1 else "N/A",
                    'binding_data': binding_data
                })
                
                self.progress.emit(10 + int((i + 1) / total * 80), f"매칭 중: {pdf_raw_name} ({i+1}/{total})")

            self.progress.emit(100, "논리적 매칭 분석 완료")
            
            # [V9.6] 전체 항목이 0% 매칭인 경우 경고 강화
            if total > 0 and all(m['score'] == 0 for m in matches):
                samples = [str(x) for x in excel_names[:5] if str(x).strip()]
                self.progress.emit(100, f"[!] 매칭률 0%: '{target_col}'열의 표본 {samples}을 확인하십시오. 열 지정이 정확한지 검토가 필요합니다.")
            
            self.finished.emit(matches)

        except Exception as e:
            self.progress.emit(0, f"매칭 엔진 오류: {str(e)}")
            self.finished.emit([])

    def stop(self):
        self.is_running = False

class SMUGUI(QMainWindow):
    @staticmethod
    def c2i(c):
        """[Utility] 엑셀 열 문자(A, B, C...)를 1-based 인덱스(1, 2, 3...)로 변환"""
        if not c: return 0
        c_str = str(c).strip().upper()
        if not c_str or not c_str.isalpha():
            try: return int(c_str) # 이미 숫자인 경우
            except: return 0
        idx = 0
        for x in c_str:
            idx = idx * 26 + (ord(x) - ord('A') + 1)
        return idx

    def __init__(self):
        super().__init__()
        self.core = msds_core.MSDSCore()
        self.pdf_paths = []
        self.results = []
        self.cache = {} 
        self.sidebar_slim = False
        self.need_review = []  # 검수 대기열 초기화
        self.active_graph_threads = [] # [V9.0] 활성 스레드 관리 리스트 추가
        self.init_db()         # 지능형 엔진 가동
        self.init_ui()
        
        # [V7.5] 동기화 무결성 확보를 위한 초기화 순서 재배치
        self._setup_tab_synchronization() # 1. 시그널 먼저 연결 (대기)
        self.km = KnowledgeManager(log_func=self.log) 
        self.load_config() # 2. 그 다음 설정 로드 (setText 발생 시 시그널 즉시 발동)
        self.load_mes_master() # [NEW] MES 마스터 데이터셋 구축
        self.showMaximized()

    def load_mes_master(self):
        """[Master 지시서] MES 마스터 데이터셋 구축 및 55개 헤더 변수화"""
        self.mes_master_list = [] # 순번 기반 전체 리스트 (누락 없음)
        self.mes_cas_map = {}     # CAS 번호 기반 조회 맵 (정규화용)
        
        mes_file = "유해인자_MES.txt"
        if not os.path.exists(mes_file):
            self.log(f"[!] {mes_file} 파일을 찾을 수 없습니다. 마스터 데이터셋을 생략합니다.")
            return

        try:
            # [V10.5] 순번으로 누락없이 전체 로드를 위해 pandas 활용
            df_mes = pd.read_csv(mes_file, sep='\t', encoding='cp949')
            
            # 주님 지시: CAS 번호가 없는 행도 모두 포함
            for idx, row in df_mes.iterrows():
                # 55개 헤더 전체를 딕셔너리로 변환하여 보관
                entry = row.to_dict()
                self.mes_master_list.append(entry)
                
                # CAS 번호가 있는 경우 정규화 조회 맵에 등록
                # 컬럼명이 깨질 수 있으므로 인덱스로 접근 시도 (CAS번호는 7번째 컬럼)
                cas_key = str(row.iloc[6]).strip() if len(row) > 6 else ""
                if cas_key and cas_key.lower() != 'nan' and re.match(r'^\d{2,7}-\d{2}-\d$', cas_key):
                    # 만약 중복 CAS가 있다면 최초 발견된 것(표준) 우선 사용
                    if cas_key not in self.mes_cas_map:
                        self.mes_cas_map[cas_key] = entry
            
            self.log(f"[*] MES 마스터 데이터셋 로드 완료: {len(self.mes_master_list)}행 (CAS 매핑: {len(self.mes_cas_map)}건)")
        except Exception as e:
            self.log(f"[!] MES 마스터 로드 실패: {e}")

    def _setup_sidebar(self):
        """프라이머리 블루 사이드바 구성 (슬림 모드 지원)"""
        self.sidebar_widget = QFrame()
        self.sidebar_widget.setFixedWidth(200)
        self.sidebar_widget.setStyleSheet(f"background-color: {SIDEBAR_BLUE}; border: none;")
        self.sidebar_layout = QVBoxLayout(self.sidebar_widget)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)

        # 사이드바 상단 토글 버튼
        self.btn_toggle_sidebar = QToolButton()
        self.btn_toggle_sidebar.setText("≡")
        self.btn_toggle_sidebar.setFixedSize(60, 50)
        self.btn_toggle_sidebar.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_toggle_sidebar.setStyleSheet("color: white; font-size: 20px; background: transparent; border: none;")
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        self.sidebar_layout.addWidget(self.btn_toggle_sidebar, 0, Qt.AlignLeft)

        self.sidebar_layout.addSpacing(20)

        # 메뉴 버튼 리스트
        self.menu_buttons = []
        menus = [
            ("추출 및 검증", "[DOC]", 0),
            ("논리적 매칭", "[LINK]", 1),
            ("환경 설정", "[SET]", 2),
            ("지식 DB 관리", "[DB]", 3)
        ]

        for text, icon, idx in menus:
            btn = SidebarButton(text, icon)
            btn.clicked.connect(lambda checked, i=idx, b=btn: self.switch_page(i, b))
            self.sidebar_layout.addWidget(btn)
            self.menu_buttons.append(btn)

        self.menu_buttons[0].setChecked(True)
        self.menu_buttons[0].update_style(True)

        self.sidebar_layout.addStretch()
        self.main_h_layout.addWidget(self.sidebar_widget)

    def toggle_sidebar(self):
        """[Premium] 사이드바 슬림 모드 <-> 풀 모드 전환 애니메이션"""
        self.sidebar_slim = not self.sidebar_slim
        target_width = 60 if self.sidebar_slim else 200
        
        # 너비 애니메이션 (최소/최대 너비 동시 제어로 레이아웃 밀기 효과 극대화)
        self.sidebar_anim = QPropertyAnimation(self.sidebar_widget, b"minimumWidth")
        self.sidebar_anim.setDuration(300) 
        self.sidebar_anim.setStartValue(self.sidebar_widget.width())
        self.sidebar_anim.setEndValue(target_width)
        self.sidebar_anim.setEasingCurve(QEasingCurve.OutQuint) 
        self.sidebar_anim.start()
        
        self.sidebar_max_anim = QPropertyAnimation(self.sidebar_widget, b"maximumWidth")
        self.sidebar_max_anim.setDuration(300)
        self.sidebar_max_anim.setStartValue(self.sidebar_widget.width())
        self.sidebar_max_anim.setEndValue(target_width)
        self.sidebar_max_anim.setEasingCurve(QEasingCurve.OutQuint)
        self.sidebar_max_anim.start()
        
        for btn in self.menu_buttons:
            btn.set_slim(self.sidebar_slim)
        
        self.btn_toggle_sidebar.setText("≡" if self.sidebar_slim else "◀")

    def switch_page(self, index, active_btn):
        """페이지 전환 및 버튼 스타일 업데이트 (V7.5 자동 갱신 추가)"""
        self.stacked_widget.setCurrentIndex(index)
        titles = ["PDF 추출 및 규제 검증", "화학물질 사용현황 매칭 매니저", "시스템 환경 설정", "지능형 지식 DB 관리자"]
        self.lbl_page_title.setText(titles[index] if index < len(titles) else "환경 설정")
        
        for btn in self.menu_buttons:
            btn.setChecked(btn == active_btn)
            btn.update_style(btn == active_btn)
            
        # [V7.5] 매칭 탭으로 전환 시, 시트 목록이 비어 있으면 강제 갱신 시도
        if index == 1: # 논리적 매칭 탭
            path = self.edit_usage_excel.text()
            if path and self.combo_usage_sheet.count() == 0:
                self._update_combo_sheets(path, self.combo_usage_sheet)
        elif index == 0: # 추출 및 검증 탭
            path = self.edit_excel.text()
            if path and self.combo_sheet.count() == 0:
                self._update_combo_sheets(path, self.combo_sheet)
        elif index == 3: # [NEW] 지식 DB 관리 탭
            self.load_db_to_table()

    def _setup_log_section(self):
        """하단 로그 창 및 토글 버튼 구성"""
        self.log_container = QWidget()
        self.log_v_layout = QVBoxLayout(self.log_container)
        self.log_v_layout.setContentsMargins(0, 0, 0, 0)
        self.log_v_layout.setSpacing(0)

        log_header = QFrame()
        log_header.setFixedHeight(30)
        log_header.setStyleSheet("background-color: #eee; border-top: 1px solid #ddd;")
        log_h_layout = QHBoxLayout(log_header)
        log_h_layout.setContentsMargins(10, 0, 10, 0)
        
        lbl_log = QLabel("시스템 분석 로그")
        lbl_log.setStyleSheet("font-size: 11px; font-weight: bold; color: #666;")
        log_h_layout.addWidget(lbl_log)
        log_h_layout.addStretch()

        self.btn_clear_log = QToolButton()
        self.btn_clear_log.setText("🧹 로그 초기화")
        self.btn_clear_log.setStyleSheet("font-size: 10px; border: 1px solid #ccc; background: white; padding: 2px 5px;")
        log_h_layout.addWidget(self.btn_clear_log)

        self.btn_toggle_log = QToolButton()
        self.btn_toggle_log.setText("▼ 로그 접기")
        self.btn_toggle_log.setStyleSheet("font-size: 10px; border: 1px solid #ccc; background: white; padding: 2px 5px;")
        self.btn_toggle_log.clicked.connect(self.toggle_log)
        log_h_layout.addWidget(self.btn_toggle_log)
        
        self.log_v_layout.addWidget(log_header)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #2b2b2b; color: #a9b7c6; font-family: 'Consolas'; border: none;")
        self.log_v_layout.addWidget(self.log_view)

        # [V10.8] 생성 순서 보정: log_view가 정의된 후 시그널 연결 (AttributeError 방지)
        self.btn_clear_log.clicked.connect(self.log_view.clear)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar { border: none; background: #eee; } QProgressBar::chunk { background-color: #0078d4; }")
        self.log_v_layout.addWidget(self.progress)
        
        self.main_splitter.addWidget(self.log_container)
        self.main_splitter.setSizes([600, 200])

    def toggle_log(self):
        """로그 창 숨기기/보이기 (애니메이션 없이 즉시 전환으로 반응성 확보)"""
        is_visible = self.log_view.isVisible()
        self.log_view.setVisible(not is_visible)
        self.progress.setVisible(not is_visible)
        self.btn_toggle_log.setText("▲ 로그 열기" if is_visible else "▼ 로그 접기")
        # 높이 제약 해제하여 QSplitter가 자동화하도록 위임

    def init_db(self):
        """[V10.0] SQLite 지능형 지식 저장소 초기화 및 복합 키 마이그레이션"""
        try:
            self.conn = sqlite3.connect("msds_knowledge.db", check_same_thread=False)
            self.db_cursor = self.conn.cursor()
            
            # 1. 신규 스키마 정의 (product_name + usage 복합 키)
            self.db_cursor.execute("""
                CREATE TABLE IF NOT EXISTS msds_info (
                    product_name TEXT,
                    usage TEXT DEFAULT '미지정',
                    cas_content TEXT,
                    work_subjects TEXT,
                    reg_1st TEXT,
                    reg_2nd TEXT,
                    last_updated DATETIME,
                    PRIMARY KEY (product_name, usage)
                )
            """)
            
            # 2. 하위 호환성 및 자동 마이그레이션 로직
            # 기존 테이블에 usage 컬럼이 없는 경우 (V9.x -> V10.0 업그레이드)
            self.db_cursor.execute("PRAGMA table_info(msds_info)")
            columns = [col[1] for col in self.db_cursor.fetchall()]
            
            if 'usage' not in columns:
                self.log("[*] DB 업그레이드 감지: 'usage' 필드를 추가하고 복합 키로 재구성합니다.")
                # 임시 테이블을 통한 PK 변경 마이그레이션
                self.db_cursor.execute("ALTER TABLE msds_info RENAME TO msds_info_old")
                self.db_cursor.execute("""
                    CREATE TABLE msds_info (
                        product_name TEXT,
                        usage TEXT DEFAULT '미지정',
                        cas_content TEXT,
                        work_subjects TEXT,
                        reg_1st TEXT,
                        reg_2nd TEXT,
                        last_updated DATETIME,
                        PRIMARY KEY (product_name, usage)
                    )
                """)
                self.db_cursor.execute("""
                    INSERT INTO msds_info (product_name, usage, cas_content, work_subjects, reg_1st, reg_2nd, last_updated)
                    SELECT product_name, '미지정', cas_content, work_subjects, reg_1st, reg_2nd, last_updated FROM msds_info_old
                """)
                self.db_cursor.execute("DROP TABLE msds_info_old")
                self.log("[*] DB 마이그레이션이 성공적으로 완료되었습니다.")
                
            self.conn.commit()
            print("[*] SQLite 지능형 지식 저장소(msds_knowledge.db) 커넥션 확보 완료.")
        except sqlite3.Error as e:
            print(f"[!] DB 초기화 실패: {e}")
            self.log(f"⚠️ 지식 저장소 연결 실패: {e}")

    def get_db_knowledge(self, product_name):
        """[V10.0] 제품명 100% 일치하는 모든 지식 기록 조회 (중복 처리용)"""
        try:
            # 복합 키 체계이므로 제품명으로 검색 시 1개 이상의 리스트가 반환될 수 있음
            self.db_cursor.execute("SELECT cas_content, work_subjects, reg_1st, reg_2nd, usage FROM msds_info WHERE product_name=?", (product_name,))
            return self.db_cursor.fetchall() # fetchone() 대신 fetchall()로 변경 (Case N 감지용)
        except: return []

    def save_db_knowledge(self, product_name, cas, subjects, reg1, reg2, usage="미지정"):
        """[V10.0] 전문가 지식 영구 고착화 (Usage 포함)"""
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 주님 지시: 1% Rule 적용 (함유량이 1% 미만인 성분은 규제 요약에서 제외)
            # reg1, reg2 데이터 내의 [...] 성분들을 필터링
            filtered_reg1, filtered_reg2 = self._apply_one_percent_filter(reg1, reg2)

            self.db_cursor.execute("""
                REPLACE INTO msds_info 
                (product_name, usage, cas_content, work_subjects, reg_1st, reg_2nd, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (product_name, usage, cas, subjects, filtered_reg1, filtered_reg2, now))
            self.conn.commit()
            return True
        except Exception as e:
            self.log(f"[!] DB 저장 실패: {e}")
            return False

    def _apply_one_percent_filter(self, reg1, reg2):
        """[V10.0] 규제 요약 정보에서 1% 미만 성분 강제 배제 (전문가 룰)"""
        def filter_content(text):
            if not text: return ""
            # 각 성분 단위 필터링 ('; '로 구분된 리스트)
            items = text.split("; ")
            filtered = []
            for item in items:
                # 함유량 추출 (예: [7439-89-6(0.5%)])
                match = re.search(r'\(([\d\.]+)\s*%\)', item)
                if match:
                    try:
                        val = float(match.group(1))
                        if val < 1.0: 
                            # self.log(f"[*] [1% Rule] 규제 제외: {item}") # 로그 과다 방지 위해 주석
                            continue
                    except: pass
                filtered.append(item)
            return "; ".join(filtered)

        return filter_content(reg1), filter_content(reg2)

    def log(self, message):
        """[Premium] 시스템 로그 출력 및 자동 스크롤 (GUI & 터미널 병행)"""
        if hasattr(self, 'log_view'):
            # GUI 로그 창이 준비된 경우에만 출력 (유니코드 완벽 지원)
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_view.append(f"[{timestamp}] {message}")
            self.log_view.ensureCursorVisible() # 자동 스크롤
            
        # [무결점] 터미널 출력 시 cp949 인코딩 오류 방지 (이모지 등 필터링)
        try:
            safe_msg = str(message).encode('cp949', errors='replace').decode('cp949')
            print(f"[*] {safe_msg}")
        except:
            # 최악의 경우 아스키 문자만 출력
            print(f"[*] {str(message).encode('ascii', errors='replace').decode('ascii')}")

    def _create_matching_page(self):
        """[Page 1] 논리적 매칭 레이아웃 및 컨트롤"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # 1. 상단 컨트롤 바 (엑셀 선택 및 시작)
        ctrl_group = QGroupBox("매칭 원본 데이터 (화학물질 사용현황)")
        ctrl_layout = QGridLayout()
        
        ctrl_layout.addWidget(QLabel("사용현황 엑셀:"), 0, 0)
        self.edit_usage_excel = QLineEdit()
        self.edit_usage_excel.setPlaceholderText("화학물질 사용현황 엑셀 파일을 선택하세요...")
        ctrl_layout.addWidget(self.edit_usage_excel, 0, 1)
        
        btn_usage_ex = QPushButton("파일 열기")
        btn_usage_ex.setFixedWidth(100)
        btn_usage_ex.setStyleSheet("background-color: #6c757d;")
        btn_usage_ex.clicked.connect(self.select_usage_excel)
        ctrl_layout.addWidget(btn_usage_ex, 0, 2)

        ctrl_layout.addWidget(QLabel("매칭 시트:"), 1, 0)
        self.combo_usage_sheet = QComboBox()
        ctrl_layout.addWidget(self.combo_usage_sheet, 1, 1, 1, 1)
        
        self.btn_run_matching = QPushButton("[RUN] 논리적 매칭 시작")
        self.btn_run_matching.setFixedHeight(40)
        self.btn_run_matching.setStyleSheet(f"background-color: {PRIMARY_BLUE}; font-size: 13px;")
        self.btn_run_matching.clicked.connect(self.run_logical_matching)
        ctrl_layout.addWidget(self.btn_run_matching, 1, 2)
        
        ctrl_group.setLayout(ctrl_layout)
        layout.addWidget(ctrl_group)

        # 2. 매칭 결과 테이블
        result_group = QGroupBox("매칭 분석 결과 및 데이터 바인딩 상태")
        result_layout = QVBoxLayout()
        
        self.match_table = QTableWidget(0, 8) # [V9.9] 컬럼 8개로 확장
        self.match_table.setHorizontalHeaderLabels([
            "신뢰도", "PDF 파일명", "PDF 제품명", "유사도(%)", "매칭된 엑셀 항목", "바인딩 데이터", "상태", "확정"
        ])
        header = self.match_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.match_table.setColumnWidth(0, 60)
        self.match_table.setColumnWidth(1, 150) # 파일명 칸
        self.match_table.setColumnWidth(2, 200) # 제품명 칸
        self.match_table.setColumnWidth(3, 80)
        self.match_table.setColumnWidth(4, 200)
        self.match_table.setColumnWidth(5, 300)
        self.match_table.setColumnWidth(7, 80)
        
        result_layout.addWidget(self.match_table)
        
        # [NEW] 수동 확정 버튼 추가
        btn_confirm = QPushButton("선택 항목 매칭 확정 (학습)")
        btn_confirm.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 8px;")
        btn_confirm.clicked.connect(self.confirm_manual_match)
        result_layout.addWidget(btn_confirm)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        # 3. 하단 안내 상자
        info_box = QFrame()
        info_box.setStyleSheet(f"background-color: {LIGHT_BLUE}; border-radius: 5px;")
        info_layout = QHBoxLayout(info_box)
        info_lbl = QLabel("💡 <b>매칭 가이드:</b> 90% 이상(🟢)은 자동 바인딩되며, 70%~89%(🟡)는 검토가 필요합니다. 70% 미만(🔴)은 수동 확인 권장.")
        info_lbl.setStyleSheet("color: #004085; font-size: 11px;")
        info_layout.addWidget(info_lbl)
        layout.addWidget(info_box)

        self.matching_results = [] # 매칭 결과 저장용
        return page

    def select_usage_excel(self):
        """사용현황 엑셀 파일 선택"""
        # [V7.1] 전역 확장자 필터 통합 (*.xlsx, *.xls, *.xlsm, *.xlsb)
        file_path, _ = QFileDialog.getOpenFileName(self, "사용현황 엑셀 선택", "", "Excel Files (*.xlsx *.xls *.xlsm *.xlsb)")
        if file_path:
            self.edit_usage_excel.setText(file_path)
            # 시트 목록 로드
            try:
                # [V7.1] openpyxl 엔진 강제로 매크로 시트 충돌 방지
                xl = pd.ExcelFile(file_path, engine='openpyxl')
                self.combo_usage_sheet.clear()
                self.combo_usage_sheet.addItems(xl.sheet_names)
                self.log(f"사용현황 엑셀 로드 완료: {os.path.basename(file_path)}")
            except Exception as e:
                self.log(f"엑셀 로드 실패: {e}")

    def run_logical_matching(self):
        """논리적 매칭 워커 실행"""
        if not self.results:
            QMessageBox.warning(self, "알림", "먼저 1단계 PDF 추출을 완료해야 합니다.")
            return
        
        excel_path = self.edit_usage_excel.text()
        sheet_name = self.combo_usage_sheet.currentText()
        
        if not excel_path or not sheet_name:
            QMessageBox.warning(self, "알림", "사용현황 엑셀 파일을 먼저 선택해 주세요.")
            return

        self.log("논리적 매칭 시작 (UI 데이터 동기화 포함)...")
        # [V10.7] 테이블 실시간 데이터 긁어오기 (사용자 수정본 반영)
        fresh_pdf_results = []
        for r in range(self.table.rowCount()):
            # 2번 열: 제품명, 7번 열: 파일명, 8번 열: 해시
            p_name = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else ""
            f_name = self.table.item(r, 7).text().strip() if self.table.item(r, 7) else "Unknown"
            f_hash = self.table.item(r, 8).text().strip() if self.table.item(r, 8) else ""
            
            # [방탄 로직] 순번이 없거나 999여도 제품명이 있다면 무조건 포함
            if p_name:
                fresh_pdf_results.append({
                    'product_name': p_name,
                    'filename': f_name,
                    'hash': f_hash,
                    'raw_content': self.table.item(r, 3).text().strip() if self.table.item(r, 3) else ""
                })

        if not fresh_pdf_results:
            QMessageBox.warning(self, "알림", "매칭할 유효한 제품 정보가 테이블에 없습니다.")
            return

        # [V9.7] 타입 무결성 패치: 생성 전 인덱스 변환 완료
        raw_mapping = self.mapping_panel.get_mapping()
        processed_mapping = {k: SMUGUI.c2i(v) for k, v in raw_mapping.items()}
        processed_mapping["제품명_raw"] = raw_mapping.get("제품명", "D") # 로그용 보존
        processed_mapping["측정대상1_idx"] = SMUGUI.c2i(raw_mapping.get("측정대상1", "N"))
        processed_mapping["측정대상2_idx"] = SMUGUI.c2i(raw_mapping.get("측정대상2", ""))
        
        # Fresh 데이터를 MatchingWorker에 주입
        self.match_worker = MatchingWorker(excel_path, sheet_name, fresh_pdf_results, mapping=processed_mapping)
        self.match_worker.km = self.km 
        self.match_worker.progress.connect(self.on_matching_progress)
        self.match_worker.finished.connect(self.on_matching_finished)
        self.match_worker.start()
        
        self.btn_run_matching.setEnabled(False)

    def on_matching_progress(self, val, msg):
        self.progress.setValue(val)
        self.log(msg)

    def on_matching_finished(self, matches):
        """[Hot-Fix] AttributeError: self.matching_worker -> self.match_worker 교정"""
        self.btn_run_matching.setEnabled(True)
        self.matching_results = matches
        self.match_table.setRowCount(0)
        
        for i, m in enumerate(matches):
            self.match_table.insertRow(i)
            
            score = m['score']
            status_icon = "🟢" if score >= 80 else "🟡" if score >= 70 else "🔴"
            
            # 1. 신뢰도 아이콘
            item_icon = QTableWidgetItem(status_icon)
            item_icon.setTextAlignment(Qt.AlignCenter)
            self.match_table.setItem(i, 0, item_icon)
            
            # 2. PDF 파일명 [V9.9 신규]
            self.match_table.setItem(i, 1, QTableWidgetItem(m.get('pdf_filename', 'N/A')))

            # 3. PDF 제품명
            self.match_table.setItem(i, 2, QTableWidgetItem(m['pdf_name']))
            
            # 4. 유사도
            self.match_table.setItem(i, 3, QTableWidgetItem(f"{score}%"))
            
            # 5. 엑셀 매칭명
            self.match_table.setItem(i, 4, QTableWidgetItem(m['excel_name']))
            
            # 6. 바인딩 데이터 (요약)
            b = m['binding_data']
            summary = "바인딩 없음"
            if b:
                summary = f"[{b['공정명']}] {b['사용용도']} ({b['월취급량']}{b['단위']})"
            self.match_table.setItem(i, 5, QTableWidgetItem(summary))
            
            # 7. 상태 텍스트
            status_txt = "자동 연결" if score >= 80 else "검토 필요" if score >= 70 else "수동 연결 필요"
            self.match_table.setItem(i, 6, QTableWidgetItem(status_txt))
            
            # 8. 확정 기능 안내
            confirm_item = QTableWidgetItem("선택 후 상단 확정 클릭")
            confirm_item.setTextAlignment(Qt.AlignCenter)
            confirm_item.setForeground(QColor("#6c757d"))
            self.match_table.setItem(i, 7, confirm_item)

        # [V9.0] 매칭 정보 영구 캐시 기록 (세션 재시작 후 즉시 복구용)
        for m in matches:
            if m['score'] >= 80:
                fn = m['pdf_name']
                # 8번 열(Hash)을 찾아 캐시 업데이트
                for r in range(self.table.rowCount()):
                    if self.table.item(r, 2) and self.table.item(r, 2).text() == fn:
                        f_hash = self.table.item(r, 8).text() if self.table.item(r, 8) else ""
                        if f_hash in self.cache:
                            self.cache[f_hash]["match_idx"] = m["excel_idx"]
                            # [수정] self.match_worker로 통일 (AttributeError 방지)
                            self.cache[f_hash]["match_excel"] = self.match_worker.excel_path
                            self.cache[f_hash]["match_sheet"] = self.match_worker.sheet_name
                            self.cache[f_hash]["match_name"] = m["excel_name"]
        self.save_cache()

        self.log(f"논리적 매칭 완료 (총 {len(matches)}건)")
        QMessageBox.information(self, "완료", f"매칭 분석이 완료되었습니다.\n성공한 매칭 정보는 영구 캐시에 저장되어 재시작 후에도 즉시 저장 가능합니다.")

    def confirm_manual_match(self):
        """[Intelligence] 선택된 항목의 매칭을 확정하고 지식 엔진에 학습시킴"""
        curr_row = self.match_table.currentRow()
        if curr_row < 0:
            QMessageBox.warning(self, "알림", "확정할 행을 먼저 선택해 주세요.")
            return
            
        if curr_row >= len(self.matching_results): return
        
        # [Hot-Fix] 리스트 스냅샷(matching_results) 대신 테이블의 현재 텍스트(Live UI) 직접 참조
        # 사용자가 테이블에서 매칭명을 수정한 후 확정할 수 있도록 보장
        pdf_name = self.match_table.item(curr_row, 2).text().strip() if self.match_table.item(curr_row, 2) else "Unknown"
        excel_name = self.match_table.item(curr_row, 4).text().strip() if self.match_table.item(curr_row, 4) else "N/A"
        
        # 바인딩 데이터는 런타임 캐시(matching_results)에서 가져오되 존재하지 않으면 N/A 처리
        match_data = self.matching_results[curr_row]
        binding = match_data.get('binding_data', {})
        usage_val = binding.get("사용용도", "미지정") if binding else "미지정"
        
        if excel_name == "N/A":
            QMessageBox.warning(self, "알림", "매칭된 엑셀 항목이 없는 경우 확정할 수 없습니다.")
            return

        reply = QMessageBox.question(self, "매칭 확정", 
                                   f"PDF 제품명: '{pdf_name}'\n매칭 항목: '{excel_name}'\n용도: '{usage_val}'\n\n이 매칭 결과를 확정하고 지능형 엔진에 학습시킬까요?",
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No: return
        
        # 1. 지식 엔진 학습 (매칭 히스토리 저장 및 증분 인덱싱 트리거)
        try:
            # [지시서] 다중 별칭 학습 (Multi-Alias Learning) 발동
            # 1-1. 전체 제품명 학습 (기존 KM)
            self.km.update_experience(pdf_name, excel_name, binding)
            
            # [Task 3] SQLite DB 지식 고착화 (Usage 필드 포함 및 1% 필터 자동 적용)
            # 메인 테이블에서 현재 UI에 표시된 최신 데이터(사용자 수정본) 긁어오기
            f_hash = ""
            db_data = {"cas": "", "measure": "", "reg1": "", "reg2": ""}
            
            for r in range(self.table.rowCount()):
                if self.table.item(r, 2) and self.table.item(r, 2).text().strip() == pdf_name:
                    f_hash = self.table.item(r, 8).text() if self.table.item(r, 8) else ""
                    db_data["cas"] = self.table.item(r, 3).text().strip() if self.table.item(r, 3) else ""
                    db_data["measure"] = self.table.item(r, 4).text().strip() if self.table.item(r, 4) else ""
                    db_data["reg2"] = self.table.item(r, 5).text().strip() if self.table.item(r, 5) else ""
                    db_data["reg1"] = self.table.item(r, 6).text().strip() if self.table.item(r, 6) else ""
                    break
            
            if f_hash:
                # [Task 4 추가] 저장 시점에도 용접 특례 강제 보정 (방탄 설계)
                if "용접" in pdf_name and "7439-89-6" in db_data["cas"]:
                    if "용접흄; 산화철" not in db_data["measure"]:
                        db_data["measure"] = f"용접흄; 산화철; {db_data['measure']}".strip("; ")
                        self.log(f"[*] [저장방탄] '{pdf_name}' 용접 특례 데이터로 보정하여 DB 기록합니다.")

                # 1-2. 핵심 식별자(제품명 전체) 저장 (Usage 포함)
                self.save_db_knowledge(pdf_name, db_data["cas"], db_data["measure"], db_data["reg1"], db_data["reg2"], usage=usage_val)
                
                # 1-3. 다중 학습 (모델명 추출 및 개별 저장)
                model_matches = re.findall(r"[A-Z0-9]+-[A-Z0-9]+|[A-Z]+[0-9]+[A-Z0-9]*", pdf_name)
                for model_id in model_matches:
                    if len(model_id) > 2 and model_id != pdf_name:
                        self.save_db_knowledge(model_id, db_data["cas"], db_data["measure"], db_data["reg1"], db_data["reg2"], usage=usage_val)
                        self.log(f"[*] 다중 별칭 학습 고착화: '{model_id}' (용도: {usage_val})")

            # 2. UI 시각적 피드백 업데이트
            # 신뢰도 아이콘 및 유사도 점수 강제 상향 표시
            self.match_table.setItem(curr_row, 0, QTableWidgetItem("🟢"))
            self.match_table.item(curr_row, 0).setTextAlignment(Qt.AlignCenter)
            # 유사도(3번) 및 상태(6번) 컬럼 업데이트
            self.match_table.setItem(curr_row, 3, QTableWidgetItem("99% (학습됨)"))
            self.match_table.setItem(curr_row, 6, QTableWidgetItem("학습 완료 (확정)"))
            
            # 행 색상 변경 (확정된 느낌 부여)
            confirm_color = QColor("#e1f7d5") # 연한 녹색
            for c in range(self.match_table.columnCount()):
                item = self.match_table.item(curr_row, c)
                if item: item.setBackground(confirm_color)
            
            # 3. 런타임 결과 업데이트 (90점 이상으로 간주하여 자동 저장 대상 포함)
            match_data['score'] = 99
            
            self.log(f"[*] 매칭 확정 및 전체 학습 완료: '{pdf_name}' -> '{excel_name}'")
            QMessageBox.information(self, "성공", "매칭 결과 및 핵심 모델명이 지능형 엔진에 성공적으로 반영되었습니다.")
        except Exception as e:
            self.log(f"[!] 매칭 확정 중 오류: {e}")
            QMessageBox.critical(self, "오류", f"매칭 확정 처리 중 오류가 발생했습니다: {e}")

    def init_ui(self):
        self.setWindowTitle("1SMU MSDS Intelligence - Enterprise Edition")
        self.resize(1300, 900)
        
        central = QWidget()
        self.setCentralWidget(central)
        self.main_h_layout = QHBoxLayout(central)
        self.main_h_layout.setContentsMargins(0, 0, 0, 0)
        self.main_h_layout.setSpacing(0)

        # 1. 사이드바
        self._setup_sidebar()

        # 2. 메인 컨텐츠 영역 (Stretch 1 부여하여 사이드바가 밀어내는 공간을 모두 점유)
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.main_h_layout.addLayout(self.content_layout, 1)

        self.page_header = QHBoxLayout()
        self.lbl_page_title = QLabel("PDF 추출 및 규제 검증")
        self.lbl_page_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.lbl_page_title.setStyleSheet(f"color: {PRIMARY_BLUE}; margin-bottom: 5px;")
        self.page_header.addWidget(self.lbl_page_title)
        self.page_header.addStretch()
        self.content_layout.addLayout(self.page_header)
        
        self.main_splitter = QSplitter(Qt.Vertical)
        self.content_layout.addWidget(self.main_splitter)

        self.stacked_widget = QStackedWidget()
        self.main_splitter.addWidget(self.stacked_widget)

        # 페이지 0: 기존 주 화면
        self.page_extraction = self._create_extraction_page()
        self.stacked_widget.addWidget(self.page_extraction)

        # 페이지 1: 논리 매칭 화면
        self.page_matching = self._create_matching_page()
        self.stacked_widget.addWidget(self.page_matching)

        self.page_settings = self._create_settings_page()
        self.stacked_widget.addWidget(self.page_settings)

        # 페이지 3: [NEW] 지식 DB 관리 화면
        self.page_db_mgmt = self._create_db_manager_page()
        self.stacked_widget.addWidget(self.page_db_mgmt)

        # 3. 로그 창
        self._setup_log_section()
        
        # [V7.1] 추출 탭과 매칭 탭 간의 설정 실시간 동기화 연결
        self._setup_tab_synchronization()

    def _create_settings_page(self):
        """[Page 2] 데이터 맵핑 및 보조 관리 도구를 모은 환경 설정 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # 1. 컬럼 맵핑 설정 영역
        map_group = QGroupBox("데이터 열 매핑 설정 (엑셀 컬럼 지정)")
        map_layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(400)
        self.mapping_panel = ModernMappingPanel()
        scroll.setWidget(self.mapping_panel)
        map_layout.addWidget(scroll)
        map_group.setLayout(map_layout)
        layout.addWidget(map_group)

        # 2. 파일 및 번호 관리 영역 (부가 기능)
        lower_layout = QHBoxLayout()
        
        file_mgmt_group = QGroupBox("파일 관리 및 번호 부여 (보조 도구)")
        file_mgmt_layout = QGridLayout()
        file_mgmt_layout.setContentsMargins(15, 15, 15, 15)
        
        file_mgmt_layout.addWidget(QLabel("시작 번호:"), 0, 0)
        self.edit_start_num = QLineEdit("1")
        self.edit_start_num.setFixedWidth(50)
        file_mgmt_layout.addWidget(self.edit_start_num, 0, 1)
        
        self.btn_batch_rename = QPushButton("파일명 일괄 변경")
        self.btn_batch_rename.setStyleSheet("background-color: #6c757d; min-height: 35px;")
        self.btn_batch_rename.clicked.connect(self.batch_rename_files)
        file_mgmt_layout.addWidget(self.btn_batch_rename, 1, 0, 1, 2)
        
        self.btn_excel_no = QPushButton("엑셀 A열 번호 부여")
        self.btn_excel_no.setStyleSheet("background-color: #e6a23c; min-height: 35px;")
        self.btn_excel_no.clicked.connect(self.assign_excel_numbers)
        file_mgmt_layout.addWidget(self.btn_excel_no, 2, 0, 1, 2)
        
        file_mgmt_group.setLayout(file_mgmt_layout)
        lower_layout.addWidget(file_mgmt_group)
        
        # 캐시 관리 등 추가 설정 버튼들 배치 가능
        info_group = QGroupBox("시스템 정보 및 캐시")
        info_layout = QVBoxLayout()
        info_layout.addWidget(QLabel("MSDS Intelligence v2.0 - Enterprise Edition"))
        info_layout.addWidget(QLabel(f"작동 모드: 지능형 바인딩 활성화"))
        btn_clear_cache = QPushButton("정밀 캐시(Hash) 초기화")
        btn_clear_cache.setStyleSheet("background-color: #f56c6c; color: white;")
        info_layout.addWidget(btn_clear_cache)
        info_group.setLayout(info_layout)
        lower_layout.addWidget(info_group)
        
        layout.addLayout(lower_layout)
        layout.addStretch()
        
        return page

    def _create_extraction_page(self):
        """[Page 0] 최적화된 추출 및 검증 메인 페이지 (테이블 확장형)"""
        page = QWidget()
        main_layout = QVBoxLayout(page)

        # A. 상단 액션 바 (파일 로드 및 엔진 제어)
        header = QHBoxLayout()
        self.drop_area = FileDropArea()
        self.drop_area.filesDropped.connect(self.on_files_dropped)
        header.addWidget(self.drop_area)

        self.lbl_file_count = QLabel("0개")
        self.lbl_file_count.setFixedWidth(50)
        self.lbl_file_count.setAlignment(Qt.AlignCenter)
        self.lbl_file_count.setStyleSheet("background-color: #f56c6c; color: white; border-radius: 10px; padding: 2px 5px; font-weight: bold; font-size: 11px;")
        header.addWidget(self.lbl_file_count)

        btn_load = QPushButton("파일 선택")
        btn_load.setFixedWidth(80); btn_load.setFixedHeight(35)
        btn_load.clicked.connect(self.load_pdfs)
        header.addWidget(btn_load)

        btn_reset = QPushButton("초기화")
        btn_reset.setFixedWidth(60); btn_reset.setFixedHeight(35)
        btn_reset.setStyleSheet("background-color: #6c757d;")
        btn_reset.clicked.connect(self.reset_all)
        header.addWidget(btn_reset)

        btn_reload = QPushButton("엔진 🔄")
        btn_reload.setFixedWidth(70); btn_reload.setFixedHeight(35)
        btn_reload.setStyleSheet("background-color: #67c23a;")
        btn_reload.clicked.connect(self.reload_engine)
        header.addWidget(btn_reload)

        header.addSpacing(20)
        self.btn_step1 = QPushButton("1단계 추출")
        self.btn_step1.setFixedHeight(35); self.btn_step1.setStyleSheet("font-weight: bold;")
        self.btn_step1.clicked.connect(self.run_extraction)
        header.addWidget(self.btn_step1)

        self.btn_step2 = QPushButton("2단계 검증")
        self.btn_step2.setFixedHeight(35); self.btn_step2.setStyleSheet("background-color: #f39c12; font-weight: bold;")
        self.btn_step2.clicked.connect(self.run_validation)
        header.addWidget(self.btn_step2)
        main_layout.addLayout(header)

        # B. 슬림 컨트롤 바 (엑셀 설정) - 가로형 배치로 공간 절약
        excel_bar = QHBoxLayout()
        excel_bar.addWidget(QLabel("저장 엑셀:"))
        self.edit_excel = QLineEdit()
        self.edit_excel.setPlaceholderText("결과를 저장할 엑셀 파일을 선택하세요...")
        excel_bar.addWidget(self.edit_excel)
        
        btn_ex = QPushButton("찾기")
        btn_ex.setFixedWidth(50); btn_ex.clicked.connect(self.select_excel)
        excel_bar.addWidget(btn_ex)

        excel_bar.addSpacing(15)
        excel_bar.addWidget(QLabel("시트:"))
        self.combo_sheet = QComboBox()
        self.combo_sheet.setMinimumWidth(100)
        excel_bar.addWidget(self.combo_sheet)

        excel_bar.addWidget(QLabel("행:"))
        self.edit_start_row = QLineEdit("3")
        self.edit_start_row.setFixedWidth(40); self.edit_start_row.setAlignment(Qt.AlignCenter)
        excel_bar.addWidget(self.edit_start_row)

        excel_bar.addSpacing(15)
        btn_save_h = QPushButton("📁 엑셀에 저장")
        btn_save_h.setFixedWidth(130); btn_save_h.setFixedHeight(35)
        btn_save_h.setStyleSheet("background-color: #28a745; font-weight: bold;")
        btn_save_h.clicked.connect(self.perform_standard_save)
        excel_bar.addWidget(btn_save_h)
        
        main_layout.addLayout(excel_bar)

        # C. 메인 컨텐츠 (Splitter 도입: 테이블 ↔ 미리보기)
        self.content_splitter = QSplitter(Qt.Horizontal)
        
        # [좌측] 테이블 영역 컨테이너
        self.left_container = QWidget()
        self.left_vbox = QVBoxLayout(self.left_container)
        self.left_vbox.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "순번", "No", "원본 제품명", "CAS 원본(수정)", 
            "측정대상", "2차 결과(규제)", "1차 결과(전체)", "파일명", "Hash", "Full Path", "Page"
        ])
        self.table.verticalHeader().setVisible(False)

        header_table = self.table.horizontalHeader()
        header_table.sectionResized.connect(self._safe_resize_rows)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 45)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 250)
        self.table.setColumnWidth(6, 300)
        # [V7.0] 관리용 열들은 모두 숨김 처리
        for hidden_col in [7, 8, 9, 10]:
            self.table.setColumnHidden(hidden_col, True)
        
        # [V8.6] HTML 델리게이트 복원 및 MultiLineDelegate 적용
        self.table.setItemDelegateForColumn(3, MultiLineDelegate(self))
        for col in [4, 5, 6]:
            self.table.setItemDelegateForColumn(col, HTMLDelegate(self))
            
        # [NEW] 우클릭 CAS 전용 복사 메뉴
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_cas_copy_menu)
        
        # [NEW] 행 선택 시 미리보기 연동
        self.table.itemSelectionChanged.connect(self.sync_pdf_preview)
        # [V7.0] 셀 클릭 시 즉각 미리보기 연동 (브릿지)
        self.table.cellClicked.connect(self.on_row_clicked)
        
        self.table.itemChanged.connect(self.on_table_item_changed)
        self.left_vbox.addWidget(self.table)
        
        self.content_splitter.addWidget(self.left_container)

        # [우측] 미리보기 패널 (신규)
        self.preview_pane = PDFPreviewPanel()
        self.content_splitter.addWidget(self.preview_pane)
        self.content_splitter.setSizes([1000, 650]) # 초기 너비 설정 (주님이 조절 가능)

        main_layout.addWidget(self.content_splitter)
        
        return page

    def on_row_clicked(self, row, column):
        """
        [V7.0 핵심 루틴] 테이블 행 클릭 시 즉각적으로 PDF 미리보기를 띄우는 브릿지
        """
        try:
            # 1. 숨겨진 열에서 해당 행의 원본 PDF 경로와 페이지 번호 확보
            target_pdf_path_item = self.table.item(row, COL_IDX_FILEPATH)
            target_page_item = self.table.item(row, COL_IDX_PAGE)
            
            if not target_pdf_path_item:
                return
                
            target_pdf_path = target_pdf_path_item.text()
            target_page_str = target_page_item.text() if target_page_item else "1"

            # 2. 예외 방어: 경로가 없거나 파일이 존재하지 않으면 무시
            if not target_pdf_path or not os.path.exists(target_pdf_path):
                return

            # 3. [Lazy Loading] 이미 로드된 PDF가 아니라면 새로 로드
            if self.preview_pane.current_pdf_path != target_pdf_path:
                self.preview_pane.load_pdf(target_pdf_path)

            # 4. [V6 좌표 유산 이식] 해당 물질이 있는 페이지로 즉시 자동 스크롤
            if target_page_str and target_page_str.isdigit():
                page_num = int(target_page_str)
                self.preview_pane.navigate_to_page(page_num)

        except Exception as e:
            # GUI 안정성을 위해 에러는 콘솔에만 출력
            print(f"Row Click Preview Error: {e}")

    def sync_pdf_preview(self):
        """[수정] 선택한 행의 제품명과 일치하는 정확한 PDF 경로 추적"""
        curr_row = self.table.currentRow()
        if curr_row < 0: return
        
        # 7번 열(파일명) 추출
        fn_item = self.table.item(curr_row, 7)
        if not fn_item: return
        fn = fn_item.text().strip()
        
        # 전체 경로 리스트에서 파일명 매칭
        path = next((p for p in self.pdf_paths if os.path.basename(p) == fn), None)
        
        if path:
            self.preview_pane.load_pdf(path) # 이제 엉뚱한 용접재 대신 럭키 락카가 뜹니다.

    def show_cas_copy_menu(self, pos):
        """[핵심] 우클릭 시 순수 CAS 번호만 추출하여 복사 기능"""
        index = self.table.indexAt(pos)
        if index.isValid() and index.column() == 3:
            menu = QMenu()
            cell_text = self.table.item(index.row(), 3).text()
            cas_list = re.findall(r'\d{2,7}-\d{2}-\d', cell_text)
            
            if cas_list:
                for cas in list(set(cas_list)):
                    action = menu.addAction(f"CAS {cas} 복사")
                    action.triggered.connect(lambda _, c=cas: QApplication.clipboard().setText(c))
                menu.addSeparator()
                action_all = menu.addAction("모든 CAS 복사 (세미콜론 구분)")
                action_all.triggered.connect(lambda: QApplication.clipboard().setText("; ".join(list(set(cas_list)))))
                
            menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _create_db_manager_page(self):
        """[Page 3] msds_knowledge.db의 지식을 시각적으로 관리하는 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # 1. 상단 컨트롤 영역 (검색 및 새로고침)
        ctrl_layout = QHBoxLayout()
        
        lbl_search = QLabel("물질명 검색:")
        lbl_search.setFixedWidth(70)
        ctrl_layout.addWidget(lbl_search)
        
        self.db_search_edit = QLineEdit()
        self.db_search_edit.setPlaceholderText("검색할 제품명 또는 모델명을 입력하세요 (실시간 필터)...")
        self.db_search_edit.textChanged.connect(self.search_db_knowledge)
        ctrl_layout.addWidget(self.db_search_edit)
        
        btn_refresh = QPushButton("DB 새로고침")
        btn_refresh.setFixedWidth(100)
        btn_refresh.setStyleSheet(f"background-color: {PRIMARY_BLUE};")
        btn_refresh.clicked.connect(self.load_db_to_table)
        ctrl_layout.addWidget(btn_refresh)
        
        layout.addLayout(ctrl_layout)

        # 2. 메인 DB 테이블 영역
        self.db_table = QTableWidget(0, 6)
        # 컬럼: 제품명, CAS 정보, 측정대상, 2차 결과, 1차 결과, 업데이트 일시
        self.db_table.setHorizontalHeaderLabels([
            "제품명(PK)", "CAS & 함유량", "측정대상", "2차 결과(규제)", "1차 결과(전체)", "학습 일시"
        ])
        
        # 스타일 설정 (HTMLDelegate 적용으로 규제 강조 유지)
        self.db_table.setItemDelegateForColumn(3, HTMLDelegate()) # 2차 결과
        self.db_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.db_table.setColumnWidth(0, 180) # 제품명
        self.db_table.setColumnWidth(1, 250) # CAS
        self.db_table.setColumnWidth(2, 120) # 측정대상
        self.db_table.setColumnWidth(3, 250) # 2차
        self.db_table.setColumnWidth(4, 300) # 1차
        self.db_table.setColumnWidth(5, 140) # 일시
        self.db_table.setSelectionBehavior(QTableWidget.SelectRows) # 행 단위 선택
        layout.addWidget(self.db_table)

        # 3. 하단 액션 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_delete = QPushButton("선택 항목 삭제 (DB 물리 제거)")
        btn_delete.setStyleSheet("background-color: #f56c6c; color: white; font-weight: bold; padding: 10px 20px;")
        btn_delete.clicked.connect(self.delete_db_entry)
        btn_layout.addWidget(btn_delete)
        
        layout.addLayout(btn_layout)
        
        return page

    def load_db_to_table(self):
        """msds_info 테이블의 모든 데이터를 UI 테이블에 로드"""
        try:
            self.db_cursor.execute("SELECT product_name, cas_content, work_subjects, reg_2nd, reg_1st, last_updated FROM msds_info ORDER BY last_updated DESC")
            data = self.db_cursor.fetchall()
            
            self.db_table.setRowCount(0)
            for row_idx, row_data in enumerate(data):
                self.db_table.insertRow(row_idx)
                for col_idx, val in enumerate(row_data):
                    item = QTableWidgetItem(str(val))
                    # 업데이트 일시 등은 읽기 전용 및 중앙 정렬
                    if col_idx in [2, 5]: 
                        item.setTextAlignment(Qt.AlignCenter)
                    item.setFlags(item.flags() ^ Qt.ItemIsEditable) # DB 탭은 관람/삭제 전용
                    self.db_table.setItem(row_idx, col_idx, item)
            
            self.log(f"[*] 지식 DB 데이터 {len(data)}건 로드 완료.")
        except Exception as e:
            self.log(f"[!] DB 로드 실패: {e}")

    def search_db_knowledge(self, text):
        """검색창 텍스트 변경 시 테이블 실시간 필터링"""
        search_term = text.lower().strip()
        for r in range(self.db_table.rowCount()):
            # '제품명' 컬럼(0번) 기준으로 필터링
            prod_item = self.db_table.item(r, 0)
            if prod_item:
                is_visible = search_term in prod_item.text().lower()
                self.db_table.setRowHidden(r, not is_visible)

    def delete_db_entry(self):
        """선택된 제품명을 DB에서 영구 삭제"""
        curr_row = self.db_table.currentRow()
        if curr_row < 0:
            QMessageBox.warning(self, "알림", "삭제할 항목을 먼저 선택해 주세요.")
            return
            
        prod_name = self.db_table.item(curr_row, 0).text()
        
        reply = QMessageBox.question(self, "데이터 삭제 확인", 
                                   f"제품명: '{prod_name}'\n\n이 지식을 DB에서 영구적으로 삭제하시겠습니까?\n삭제 후에는 하이패스 자동 로드가 불가능해집니다.",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                self.db_cursor.execute("DELETE FROM msds_info WHERE product_name=?", (prod_name,))
                self.conn.commit()
                self.db_table.removeRow(curr_row)
                self.log(f"[*] 지식 삭제 완료: {prod_name}")
                QMessageBox.information(self, "삭제 완료", f"'{prod_name}' 지식이 DB에서 물리적으로 제거되었습니다.")
            except Exception as e:
                self.log(f"[!] DB 삭제 실패: {e}")
                QMessageBox.critical(self, "오류", f"삭제 중 오류 발생: {e}")




    def closeEvent(self, event):
        """[V6.995] 프로그램 종료 시 자동 저장"""
        try:
            self.save_config()
        except: pass
        event.accept()

    def save_config(self):
        """[V6.995] 현재 설정을 config.json에 저장"""
        config = {
            "mapping": self.mapping_panel.get_mapping(),
            "excel_path": self.edit_excel.text().strip(),
            "sheet_name": self.combo_sheet.currentText(),
            "start_row": self.edit_start_row.text().strip(),
            "start_num": self.edit_start_num.text().strip(),
            "pdf_paths": self.pdf_paths if hasattr(self, 'pdf_paths') else []
        }
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            self.log("[*] 설정이 config.json에 자동 저장되었습니다.")
        except Exception as e:
            print(f"Config Save Error: {e}")

    def load_config(self):
        """[V6.995] config.json에서 설정을 읽어 UI 복구"""
        if not os.path.exists("config.json"): return
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
            
            # 1. 매핑 설정 복구
            if "mapping" in config:
                self.mapping_panel.set_mapping(config["mapping"])
            
            # 2. 기타 설정 복구
            if "excel_path" in config:
                self.edit_excel.setText(config["excel_path"])
                # 엑셀 경로가 있으면 시트 목록 로드 시도
                if config["excel_path"] and os.path.exists(config["excel_path"]):
                    self._update_sheet_list(config["excel_path"], config.get("sheet_name"))

            if "start_row" in config: self.edit_start_row.setText(config["start_row"])
            if "start_num" in config: self.edit_start_num.setText(config["start_num"])
            
            if "pdf_paths" in config:
                self.pdf_paths = config["pdf_paths"]
                if self.pdf_paths:
                    self.log(f"[*] 이전 세션에서 {len(self.pdf_paths)}개의 PDF 목록을 불러왔습니다.")
                    self.update_file_count_display()
                    
        except Exception as e:
            self.log(f"[!] 설정 복구 실패: {e}")

    def load_cache(self):
        """[NEW] smu_cache.json에서 영구 캐시 로드"""
        if not os.path.exists("smu_cache.json"): return
        try:
            with open("smu_cache.json", "r", encoding="utf-8") as f:
                self.cache = json.load(f)
            self.log(f"[*] {len(self.cache)}건의 분석 캐시를 불러왔습니다.")
        except: pass

    def save_cache(self):
        """[NEW] 현재 캐시를 smu_cache.json에 저장"""
        try:
            with open("smu_cache.json", "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=4)
        except: pass

    def update_cache(self, f_hash, data):
        """[NEW] 워커로부터 받은 새 분석 결과를 캐시에 저장"""
        self.cache[f_hash] = data
        self.save_cache()

    def on_table_item_changed(self, item):
        """[V7.3] 테이블 셀 수동 수정 시 캐시(JSON) 실시간 업데이트 (Gold Shield)"""
        if not self.table.signalsBlocked():
            row = item.row()
            col = item.column()
            
            # 감시 범위 확대: 제품명(2), CAS(3), 측정대상(4), 2차(5), 1차(6)
            if col in [2, 3, 4, 5, 6]:
                hash_item = self.table.item(row, 8) 
                if hash_item:
                    f_hash = hash_item.text().strip()
                    if f_hash in self.cache:
                        new_text = item.text().strip()
                        # manual_data 구조 확보
                        if "manual_data" not in self.cache[f_hash]:
                            self.cache[f_hash]["manual_data"] = {}
                        
                        # 각 컬럼별 키 매핑
                        col_map = {2: "product_name", 3: "raw_content", 4: "measure", 5: "reg2", 6: "reg1"}
                        key = col_map.get(col)
                        
                        if key:
                            # 1. 캐시 영구 저장
                            if "manual_data" not in self.cache[f_hash]:
                                self.cache[f_hash]["manual_data"] = {}
                            self.cache[f_hash]["manual_data"][key] = new_text
                            self.save_cache()
                            
                            # 2. self.results 메모리 실시간 동기화 (Hot-Sync)
                            for res in self.results:
                                if res.get('hash') == f_hash:
                                    res[key] = new_text
                                    break
                            
                            # 3. [Task 5 추가] 만약 제품명이 수정되었다면 다른 연관 정보들도 즉시 동기화 유지
                            # (주님이 수동으로 고친 결과가 시스템 내부 변수에 즉시 각인됨)
                            self.log(f"[*] 실시간 동기화 완료: {key} -> {new_text[:20]}...")

    def _update_sheet_list(self, path, select_name=None):
        """[V6.995] 설정 복구 시 시트 목록 자동 갱신 헬퍼"""
        try:
            self.combo_sheet.clear()
            wb = openpyxl.load_workbook(path, read_only=True)
            sheets = wb.sheetnames
            self.combo_sheet.addItems(sheets)
            if select_name and select_name in sheets:
                self.combo_sheet.setCurrentText(select_name)
            wb.close()
        except:
            self.combo_sheet.addItem("Sheet1")

    def reset_all(self):
        """[NEW] 모든 데이터 초기화 (파일 목록, 테이블, 로그, 진행바)"""
        # 작업 중인 경우 확인
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, "확인", "현재 작업이 진행 중입니다. 작업을 중단하고 모든 데이터를 초기화할까요?", 
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No: return
            self.worker.terminate()
            self.worker.wait()
            self.log("[!] 작업이 사용자 요청으로 중단되었습니다.")

        # 최종 확인 (작업 중이 아닐 때만 별도 호출됨)
        else:
            reply = QMessageBox.question(self, "전체 초기화", "모든 파일 목록과 추출 결과, 로그를 초기화하시겠습니까?", 
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No: return

        # 데이터 초기화
        self.pdf_paths = []
        self.results = []
        self.table.setRowCount(0)
        self.log_view.clear()
        self.progress.setValue(0)
        self.update_file_count_display()
        self.log("✅ 모든 데이터가 초기화되었습니다.")

    def reload_engine(self):
        """[HOT-RELOAD] 엔진 모듈을 다시 로드하며 캐시 파일도 삭제(초기화)"""
        try:
            # [NEW] 캐시 파일 삭제
            if os.path.exists("smu_cache.json"):
                os.remove("smu_cache.json")
                self.cache = {}
                self.log("[!] 엔진 새로고침에 따라 분석 캐시가 삭제되었습니다.")

            import msds_engine_v5
            importlib.reload(msds_engine_v5)
            importlib.reload(msds_core)
            self.core = msds_core.MSDSCore()
            self.log("✅ 엔진 및 코어 모듈이 성공적으로 재로드되었습니다.")
            QMessageBox.information(self, "성공", "수정된 엔진이 GUI에 반영되었습니다.")
        except Exception as e:
            self.log(f"❌ 엔진 재로드 실패: {e}")
            QMessageBox.critical(self, "실패", f"엔진 재로드 중 오류 발생:\n{e}")

    def stop_worker(self):
        """현재 실행 중인 워커 스레드 중단"""
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, "확인", "진행 중인 모든 작업을 중단하시겠습니까?", 
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.worker.terminate()
                self.worker.wait() # 스레드가 종료될 때까지 대기
                self.log("[!] 사용자에 의해 작업이 강제 중단되었습니다.")
                self.progress.setValue(0)
                QMessageBox.warning(self, "중단", "작업이 중단되었습니다.")
        else:
            QMessageBox.information(self, "안내", "현재 실행 중인 작업이 없습니다.")

    def load_pdfs(self):
        """[Part 6] PDF 파일 선택 다이얼로그"""
        files, _ = QFileDialog.getOpenFileNames(self, "분석할 MSDS PDF 선택", "", "PDF Files (*.pdf)")
        if files:
            # [NEW] 중복 파일 제외 로직
            new_files = []
            for f in files:
                if f in self.pdf_paths:
                    self.log(f"[경고] {os.path.basename(f)} 파일은 이미 목록에 있습니다. (추가 제외됨)")
                    continue
                new_files.append(f)
            
            if new_files:
                self.pdf_paths.extend(new_files)
                self.update_file_count_display()
                self.log(f"[*] {len(new_files)}개의 PDF 파일이 추가되었습니다.")

    def on_files_dropped(self, paths):
        """[NEW] 드래그 앤 드롭된 파일/폴더 처리"""
        all_pdfs = []
        for p in paths:
            if os.path.isfile(p):
                if p.lower().endswith(".pdf"):
                    all_pdfs.append(p)
            elif os.path.isdir(p):
                # 폴더 내 모든 PDF 재귀 검색
                for root, _, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith(".pdf"):
                            all_pdfs.append(os.path.join(root, f))
        
        if all_pdfs:
            # 중복 제거 및 누적 추가
            if not hasattr(self, 'pdf_paths'): self.pdf_paths = []
            current_set = set(self.pdf_paths)
            new_count = 0
            for f in all_pdfs:
                if f not in current_set:
                    self.pdf_paths.append(f)
                    current_set.add(f)
                    new_count += 1
            
            self.update_file_count_display()
            self.log(f"[*] 드래그 앤 드롭으로 {new_count}개의 PDF 파일이 추가되었습니다. (총 {len(self.pdf_paths)}개)")

    def update_file_count_display(self):
        """[NEW] 첨부된 파일 수를 UI에 업데이트"""
        count = len(self.pdf_paths) if hasattr(self, 'pdf_paths') else 0
        self.lbl_file_count.setText(f"{count}개")
        # 0개면 회색, 1개 이상이면 빨간색 배지
        if count > 0:
            self.lbl_file_count.setStyleSheet("background-color: #f56c6c; color: white; border-radius: 10px; padding: 2px 5px; font-weight: bold; font-size: 11px; margin-left: -15px;")
        else:
            self.lbl_file_count.setStyleSheet("background-color: #909399; color: white; border-radius: 10px; padding: 2px 5px; font-weight: bold; font-size: 11px; margin-left: -15px;")

    def batch_rename_files(self):
        """[NEW] PDF 파일명 일괄 변경 (기존 번호 제거 후 새 번호 부여)"""
        if not hasattr(self, 'pdf_paths') or not self.pdf_paths:
            QMessageBox.warning(self, "경고", "먼저 PDF 파일을 추가해 주세요.")
            return

        try:
            start_num = int(self.edit_start_num.text().strip())
        except ValueError:
            QMessageBox.warning(self, "경고", "시작 번호는 숫자만 입력 가능합니다.")
            return

        reply = QMessageBox.question(self, "확인", 
                                     f"총 {len(self.pdf_paths)}개 파일의 이름을 변경할까요?\n"
                                     f"(기존 번호 접두사가 있으면 제거하고 {start_num:03d}_ 형식으로 새로 부여합니다.)",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No: return

        new_paths = []
        errors = []
        # 파일명 기준 정렬하여 순차 번호 부여
        self.pdf_paths.sort()
        
        for idx, old_path in enumerate(self.pdf_paths):
            dir_name = os.path.dirname(old_path)
            base_name = os.path.basename(old_path)
            
            # 기존 번호 접두사 제거 (예: 001_, 12-, 3. 등)
            clean_name = re.sub(r"^\d+[_ \-\.]*", "", base_name)
            
            new_name = f"{start_num + idx:03d}_{clean_name}"
            new_path = os.path.join(dir_name, new_name)
            
            if old_path == new_path:
                new_paths.append(old_path)
                continue
                
            try:
                os.rename(old_path, new_path)
                new_paths.append(new_path)
            except Exception as e:
                errors.append(f"{base_name}: {e}")
                new_paths.append(old_path)

        self.pdf_paths = new_paths
        
        if errors:
            err_msg = "\n".join(errors[:10])
            if len(errors) > 10: err_msg += "\n..."
            QMessageBox.critical(self, "변경 실패 안내", 
                                 f"일부 파일명을 변경하지 못했습니다. 해당 파일을 다른 프로그램에서 사용 중인지 확인하고 닫은 뒤 다시 시도해 주세요.\n\n[실패 내역]\n{err_msg}")
        else:
            self.log(f"[*] {len(new_paths)}개 파일명 일괄 변경 완료 (시작 번호: {start_num})")
            QMessageBox.information(self, "성공", "파일명 변경이 완료되었습니다.")

    def is_file_locked(self, path):
        """[V6.994] 대상 파일이 이미 다른 프로그램에서 열려 있는지 확인"""
        if not os.path.exists(path): return False
        try:
            # 쓰기 모드로 열어보고 실패하면 잠긴 것으로 간주
            with open(path, 'a'):
                pass
            return False
        except IOError:
            return True

    def assign_excel_numbers(self):
        """[NEW] 엑셀 A열에 001, 002... 형식으로 번호 자동 부여"""
        excel_path = self.edit_excel.text().strip()
        if not excel_path or not os.path.exists(excel_path):
            QMessageBox.warning(self, "경고", "먼저 유효한 엑셀 파일을 선택해 주세요.")
            return

        # [V6.994] 파일 잠금 체크
        if self.is_file_locked(excel_path):
            QMessageBox.critical(self, "파일 열림", f"대상 엑셀 파일({os.path.basename(excel_path)})이 이미 열려 있습니다.\n파일을 닫은 후 다시 시도해 주세요.")
            return

        try:
            start_no = int(self.edit_start_num.text().strip())
            start_row = int(self.edit_start_row.text().strip())
        except ValueError:
            QMessageBox.warning(self, "경고", "시작 번호와 시작 행은 숫자여야 합니다.")
            return

        count = len(getattr(self, 'pdf_paths', []))
        if count == 0:
            QMessageBox.warning(self, "경고", "분석할 PDF 파일이 로드되지 않았습니다.")
            return

        import pythoncom
        try:
            import win32com.client
        except ImportError:
            QMessageBox.critical(self, "오류", "win32com 라이브러리가 필요합니다. (pip install pywin32)")
            return

        pythoncom.CoInitialize()
        excel = None
        try:
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            wb = excel.Workbooks.Open(os.path.abspath(excel_path))
            ws = wb.Sheets(self.combo_sheet.currentText())

            # 1. 기존 값 체크 (중복 및 데이터 존재 확인)
            conflicts = []
            for i in range(count):
                cell_val = ws.Cells(start_row + i, 1).Value
                if cell_val is not None and str(cell_val).strip() != "":
                    conflicts.append(f"{start_row + i}행: '{cell_val}'")
            
            if conflicts:
                msg = f"선택한 범위({start_row}행부터 {count}개) 중 이미 값이 존재하는 셀이 있습니다:\n\n"
                msg += "\n".join(conflicts[:10])
                if len(conflicts) > 10: msg += f"\n...외 {len(conflicts)-10}건"
                msg += "\n\n기존 값을 무시하고 번호를 새로 부여할까요?"
                reply = QMessageBox.question(self, "데이터 존재 알림", msg, QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    wb.Close(False)
                    return

            # 2. 번호 부여 (A열)
            for i in range(count):
                val = start_no + i
                # 문자열 포맷팅 ('001 형식으로 입력하여 엑셀이 숫자로 자동 변환하는 것 방지)
                ws.Cells(start_row + i, 1).Value = f"'{val:03d}" 
            
            wb.Save()
            self.log(f"[*] 엑셀 A열 {start_row}행부터 {count}개의 번호를 부여했습니다. (시작: {start_no:03d})")
            QMessageBox.information(self, "성공", "엑셀 번호 부여가 완료되었습니다.")
            
        except Exception as e:
            self.log(f"❌ 엑셀 작업 오류: {e}")
            QMessageBox.critical(self, "오류", f"엑셀 작업 중 오류 발생:\n{e}")
        finally:
            if excel:
                try: 
                    excel.Visible = True
                    excel.UserControl = True
                except: pass
            pythoncom.CoUninitialize()

    def select_excel(self):
        """[V6.994] 엑셀 선택 시 시트 목록 자동 로드"""
        # [V7.1] 전역 확장자 필터 통합 (*.xlsx, *.xls, *.xlsm, *.xlsb)
        path, _ = QFileDialog.getOpenFileName(self, "대상 엑셀 파일 선택", "", "Excel Files (*.xlsx *.xls *.xlsm *.xlsb)")
        if path:
            self.edit_excel.setText(path)
            self.combo_sheet.clear()
            try:
                # [Part 3-A] openpyxl을 사용하여 실제 시트 목록 추출
                wb = openpyxl.load_workbook(path, read_only=True, keep_vba=True)
                sheets = wb.sheetnames
                if sheets:
                    self.combo_sheet.addItems(sheets)
                    self.log(f"[*] 엑셀 시트 {len(sheets)}개를 성공적으로 로드했습니다.")
                else:
                    self.combo_sheet.addItem("Sheet1")
                wb.close()
            except Exception as e:
                self.log(f"⚠️ 시트 목록 로드 실패: {e}")
                self.combo_sheet.addItem("Sheet1")

    def _setup_tab_synchronization(self):
        """[V7.7] 탭 간 파일 경로 및 시트 선택 값 실시간 상호 동기화 (완성형)"""
        # 1. 경로 동기화 시그널
        self.edit_excel.textChanged.connect(self._sync_to_matching_tab)
        self.edit_usage_excel.textChanged.connect(self._sync_to_extraction_tab)
        
        # 2. 시트 선택값 동기화 시그널 (추가)
        self.combo_sheet.currentTextChanged.connect(self._sync_sheet_to_matching)
        self.combo_usage_sheet.currentTextChanged.connect(self._sync_sheet_to_extraction)

    def _sync_to_matching_tab(self, text):
        """저장 탭 -> 매칭 탭 경로 동기화 (V7.7)"""
        if not text: return
        path = text.strip()
        if self.edit_usage_excel.text().strip() != path:
            self.edit_usage_excel.blockSignals(True)
            self.edit_usage_excel.setText(path)
            self.edit_usage_excel.blockSignals(False)
            self._update_combo_sheets(path, self.combo_usage_sheet)
            self.log(f"[*] 매칭 탭으로 경로 동기화 완료")

    def _sync_to_extraction_tab(self, text):
        """매칭 탭 -> 저장 탭 경로 동기화 (V7.7)"""
        if not text: return
        path = text.strip()
        if self.edit_excel.text().strip() != path:
            self.edit_excel.blockSignals(True)
            self.edit_excel.setText(path)
            self.edit_excel.blockSignals(False)
            self._update_combo_sheets(path, self.combo_sheet)
            self.log(f"[*] 추출 탭으로 경로 동기화 완료")

    def _sync_sheet_to_matching(self, sheet_name):
        """저장 탭 시트 변경 -> 매칭 탭 시트 동기화"""
        if not sheet_name: return
        if self.combo_usage_sheet.currentText() != sheet_name:
            self.combo_usage_sheet.blockSignals(True)
            idx = self.combo_usage_sheet.findText(sheet_name)
            if idx >= 0:
                self.combo_usage_sheet.setCurrentIndex(idx)
                self.log(f"[*] 매칭 시트 동기화: {sheet_name}")
            self.combo_usage_sheet.blockSignals(False)

    def _sync_sheet_to_extraction(self, sheet_name):
        """매칭 탭 시트 변경 -> 저장 탭 시트 동기화"""
        if not sheet_name: return
        if self.combo_sheet.currentText() != sheet_name:
            self.combo_sheet.blockSignals(True)
            idx = self.combo_sheet.findText(sheet_name)
            if idx >= 0:
                self.combo_sheet.setCurrentIndex(idx)
                self.log(f"[*] 추출 시트 동기화: {sheet_name}")
            self.combo_sheet.blockSignals(False)

    def _update_combo_sheets(self, path, combo_widget):
        """[V7.7] 범용 시트 목록 갱신 및 선택값 지능형 유지"""
        if not path or not os.path.exists(path):
            return
            
        try:
            # 현재 선택된 시트명 기억
            original_sheet = combo_widget.currentText()
            
            wb = openpyxl.load_workbook(path, read_only=True, keep_vba=True)
            sheets = wb.sheetnames
            wb.close()
            
            # 목록 갱신
            combo_widget.blockSignals(True)
            combo_widget.clear()
            if sheets:
                combo_widget.addItems(sheets)
                # 이전에 선택했던 시트가 새 목록에도 있다면 다시 선택
                idx = combo_widget.findText(original_sheet)
                if idx >= 0: combo_widget.setCurrentIndex(idx)
            else:
                combo_widget.addItem("Sheet1")
            combo_widget.blockSignals(False)

            # 상대방 콤보박스와 지능형 지배권 동기화
            other_combo = self.combo_usage_sheet if combo_widget == self.combo_sheet else self.combo_sheet
            if other_combo.currentText() != combo_widget.currentText():
                idx = other_combo.findText(combo_widget.currentText())
                if idx >= 0:
                    other_combo.blockSignals(True)
                    other_combo.setCurrentIndex(idx)
                    other_combo.blockSignals(False)
                    
        except Exception:
            # 실패 시 pandas fallback (생략 가능하나 무결성 위해 유지)
            try:
                xl = pd.ExcelFile(path, engine='openpyxl')
                sheets = xl.sheet_names
                combo_widget.clear()
                combo_widget.addItems(sheets)
            except: pass

    def run_extraction(self):
        if not hasattr(self, 'pdf_paths') or not self.pdf_paths:
            QMessageBox.warning(self, "경고", "먼저 분석할 PDF 파일을 선택하세요.")
            return

        self.results = []
        # [Part 1] 탐색기 스타일 자연스러운 정렬 (Natural Sort) 적용
        if hasattr(self, 'pdf_paths') and self.pdf_paths:
            self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

        self.table.blockSignals(True) # [NEW] 대량 작업 전 시그널 차단
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.worker = ExtractionWorker(self.core, self.pdf_paths, cache=self.cache)
        self.worker.update_log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.result_signal.connect(self.add_result_to_table)
        self.worker.cache_update_signal.connect(self.update_cache) # [NEW] 캐시 업데이트 연동
        self.worker.finished_signal.connect(lambda: QMessageBox.information(self, "완료", "1단계 PDF 추출이 완료되었습니다. 수정 후 2단계를 진행하세요."))
        self.worker.start()

    def run_validation(self):
        rowCount = self.table.rowCount()
        if rowCount == 0:
            QMessageBox.warning(self, "경고", "검증할 데이터가 없습니다. 먼저 1단계를 진행하세요.")
            return

        self.table.blockSignals(True) # [NEW] 시그널 일시 차단

        # 테이블에서 현재 CAS/함유량 데이터 읽기
        table_data = []
        for r in range(rowCount):
            # [V7.9] 파일 해시(8번 열)를 고유 키로 추출
            f_hash = self.table.item(r, 8).text() if self.table.item(r, 8) else ""
            fn = self.table.item(r, 7).text() if self.table.item(r, 7) else ""
            prod = self.table.item(r, 2).text()
            cas_content = self.table.item(r, 3).text()
            table_data.append({"row_idx": r, "f_hash": f_hash, "filename": fn, "prod": prod, "cas_content": cas_content})

        self.progress.setValue(0)
        self.worker = ValidationWorker(self, self.core, table_data) # [Task 2] self(GUI) 전달 추가
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.result_signal.connect(self.on_validation_result) 
        self.worker.finished_signal.connect(self.on_validation_finished)
        self.worker.start()

    def on_validation_result(self, res_data):
        """[V10.2] 하이브리드 검증 결과 처리 (신호등 🔵 마킹 및 검수 큐잉 포함)"""
        target_hash = res_data.get("f_hash")
        v = res_data.get("validation", {})
        fn = res_data.get("filename", "unknown")
        status = res_data.get("status", "High-Pass")
        
        # [DEBUG] 데이터 도달 여부 확인
        self.log(f"[*] API 응답 수집됨: {fn} (상태: {status})")
        
        # 현재 테이블에서 해시가 일치하는 행 검색 (핀포인트 바인딩)
        found_row = -1
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 8)
            if item and item.text().strip() == target_hash:
                found_row = r
                break
        
        # [V8.3] 이중 바인딩 (Fallback 연동)
        if found_row == -1 and "row_idx" in res_data:
            fallback_idx = res_data["row_idx"]
            if 0 <= fallback_idx < self.table.rowCount():
                found_row = fallback_idx

        if found_row != -1:
            # [Task 4] Case N (중복 검수 대상)인 경우 대기열에 추가
            if status == "Review Required":
                self.need_review.append({
                    "row": found_row,
                    "product_name": res_data.get("product_name"),
                    "records": res_data.get("db_records", [])
                })
                self.log(f"    - [🔵검수대기] {found_row}행을 검수 대기열에 등록합니다.")

            self.update_validation_row(
                found_row, 
                v.get("cas_with_content", []), 
                v.get("res_1st", []), 
                v.get("res_2nd", []),
                v.get("work_subjects", ""),
                status=status # [NEW] 상태값 전달
            )

    def on_validation_finished(self):
        """[V10.2] 검증 완료 시 처리 및 사후 검수 엔진 트리거"""
        self.table.blockSignals(False)
        self.log(f"[*] 검증 작업 종료. (검수 필요 항목: {len(self.need_review)}건)")
        
        if self.need_review:
            # [Task 4] 순차적 팝업 검수 엔진 가동
            self.process_review_queue()
        else:
            QMessageBox.information(self, "완료", "2단계 API 검증이 완료되었습니다.")

    def closeEvent(self, event):
        # [안전장치] 백그라운드 학습 중 종료 방지
        if hasattr(self, 'active_graph_threads') and self.active_graph_threads:
            active_count = len(self.active_graph_threads)
            reply = QMessageBox.warning(self, '종료 경고', 
                f"현재 {active_count}개의 지식 그래프 업데이트가 백그라운드에서 진행 중입니다.\n"
                "강제 종료 시 우뇌 DB(지식망)가 손상될 수 있습니다. 정말 종료하시겠습니까?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            
            if reply == QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()
                return
        event.accept()

    def process_review_queue(self):
        """[Master 지시서] 사후 정밀 검수 엔진 (Post-Batch Review)"""
        if not self.need_review:
            # self.log("[*] 모든 검수 대상이 처리되었습니다.")
            return

        item = self.need_review.pop(0)
        row = item['row']
        prod = item['product_name']
        records = item['records'] # DB에서 가져온 과거 기록 리스트

        # 다이얼로그 구성을 위한 리스트 가공 (용객 + 학습일시)
        choices = []
        for r in records:
            # records 구조: (cas, subjects, reg1, reg2, usage, last_updated)
            # last_updated가 없을 수도 있으니 안전하게 접근
            last_date = r[5] if len(r) > 5 else "N/A"
            usage = r[4] if r[4] else "용도 미기재"
            choices.append(f"[{usage}] / (학습: {last_date})")

        from PyQt5.QtWidgets import QInputDialog
        choice, ok = QInputDialog.getItem(
            self, f"사후 정밀 검수 - {row+1}행", 
            f"제품명: {prod}\n과거 사용 기록 중 올바른 용도를 선택하세요:",
            choices, 0, False
        )

        if ok and choice:
            idx = choices.index(choice)
            selected = records[idx]
            
            # 선택된 데이터로 테이블 업데이트 및 신호등 🟢 교체
            self.update_validation_row(
                row,
                selected[0].split(";\n") if selected[0] else [], # cas
                selected[2].split(";\n") if selected[2] else [], # reg1
                selected[3].split(";\n") if selected[3] else [], # reg2
                selected[1], # subjects
                status="Confirmed",
                db_records=records
            )
            self.log(f"[*] [검수확정] {row+1}행 '{prod}' -> '{choice}' 적용 완료.")
            
            # [Master 지시서] 매칭 확정 시 엑셀 용도를 DB에 즉시 기록 (지능형 엔진 강화)
            # (이 로직은 저장 시점에 동작하게 하거나 여기서 즉시 km.save_knowledge 호출 가능)
        else:
            self.log(f"[!] {row+1}행 '{prod}' 검수가 건너뛰어졌습니다. (파란색 🔵 유지)")

        # 다음 검수 항목 처리 (GUI 프리징 방지)
        if self.need_review:
            QTimer.singleShot(200, self.process_review_queue)

    def _safe_resize_rows(self):
        """[Part 18] 재귀 호출 방지를 포함한 안전한 행 높이 조절"""
        try:
            if not hasattr(self, "_resizing_rows") or not self._resizing_rows:
                self._resizing_rows = True
                self.table.resizeRowsToContents()
                self._resizing_rows = False
        except:
            self._resizing_rows = False

    def _clean_comp_name(self, name):
        """[Part 21] 성분명 정제: 한글명(영문명) -> 한글명(띄어쓰기 제거) 로직"""
        if not name: return ""
        name = str(name).strip()
        
        # 1. 한글명(영문명) 패턴에서 영문명 제거
        match = re.match(r'^([가-힣\s\d\w\-\,\.\/]+)\s*[\(\[].*?[\)\]]', name)
        if match:
            korean_part = match.group(1).strip()
            if any(ord('가') <= ord(char) <= ord('힣') for char in korean_part):
                return korean_part.replace(" ", "")
        
        # 2. 한글 패턴이 명확한 경우 전체 공백 제거
        if any(ord('가') <= ord(char) <= ord('힣') for char in name):
            name = re.sub(r'\s*[\(\[].*?[\)\]]', '', name).strip()
            return name.replace(" ", "")
            
        return name

    def _format_content(self, range_val):
        """[Part 22] 함유량 포맷: 숫자 뒤에 % 강제 부여"""
        if not range_val: return ""
        if "%" in str(range_val): return str(range_val)
        
        val = str(range_val).strip()
        if "~" in val:
            parts = val.split("~")
            return f"{parts[0]}~{parts[1]}%"
        return f"{val}%"

    def add_result_to_table(self, data):
        """1단계 결과를 테이블에 추가 (V7.3 캐시 쉴드 적용)"""
        try:
            self.results.append(data)
            self.table.blockSignals(True) # [V7.3] 캐시 오염 차단
            self.table.setSortingEnabled(False)
            
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # 1. 순번 (신호등 이모지 + 숫자 통합)
            traffic_val = data.get("신호등", "🔴")
            if not traffic_val or traffic_val == "N/A":
                raw_rel = data.get("reliability", "")
                if "[AUTO-PASS]" in raw_rel: traffic_val = "🟢"
                elif "[AI-FIXED]" in raw_rel: traffic_val = "🟡"
                else: traffic_val = "🔴"
            
            traffic_emoji = traffic_val[0] if traffic_val else "🔴"
            
            # [V6.96] 시각적 강조 로직: 녹색(🟢)은 생략, 황색(🟡)/적색(🔴)만 강조
            bg_color = None
            if traffic_emoji == "🔴":
                bg_color = QColor("#ffebeb") # 연한 빨강
            elif traffic_emoji == "🟡":
                bg_color = QColor("#fff9db") # 연한 노랑
            
            # [수정] 행 번호보다는 데이터의 순수 순번을 위해 row+1 사용 (정렬 후에도 고유하도록)
            combined_idx = f"{traffic_emoji} {row + 1}"
            
            item_seq = QTableWidgetItem(combined_idx)
            item_seq.setTextAlignment(Qt.AlignCenter)
            if bg_color: item_seq.setBackground(bg_color)
            self.table.setItem(row, 0, item_seq)

            # 2. No (파일명 앞 숫자 추출)
            fn = data.get("filename", "")
            match_no = re.match(r"^(\d+)", fn)
            no_val = match_no.group(1) if match_no else "999" # 번호 없으면 뒤로
            item_no = QTableWidgetItem(no_val)
            item_no.setTextAlignment(Qt.AlignCenter)
            if bg_color: item_no.setBackground(bg_color)
            self.table.setItem(row, 1, item_no)

            # [방탄] 제품명 NoneType 및 에러 방어 로직
            raw_prod = data.get("product_name")
            if not raw_prod or str(raw_prod).lower() == "none":
                raw_prod = f"미추출({data.get('filename')})"
                
            item_prod = QTableWidgetItem(str(raw_prod))
            if bg_color: item_prod.setBackground(bg_color)
            self.table.setItem(row, 2, item_prod)

            # [최종 확정] CAS 원본 열은 PDF 추출 원문과 함유량을 100% 순수 유지 (표준명 병기 폐기)
            raw = str(data.get("raw_content", ""))
            clean_cas_parts = [p.strip() for p in str(raw).split(";") if p.strip()]
            
            item_cas = QTableWidgetItem(";\n".join(clean_cas_parts)) # 공백 제거
            if bg_color: item_cas.setBackground(bg_color)
            self.table.setItem(row, 3, item_cas)

            # 5-7. 공란 (2단계용)
            for c_idx in range(4, 7):
                item_blank = QTableWidgetItem("")
                if bg_color: item_blank.setBackground(bg_color)
                self.table.setItem(row, c_idx, item_blank)
            
            # 8. 파일명 (숨김)
            item_fn = QTableWidgetItem(fn)
            if bg_color: item_fn.setBackground(bg_color)
            self.table.setItem(row, COL_IDX_FILENAME, item_fn)

            # 9. 해시 (숨김) - [NEW] 캐시 업데이트용
            f_hash = data.get("f_hash", "")
            item_hash = QTableWidgetItem(f_hash)
            self.table.setItem(row, COL_IDX_HASH, item_hash)

            # 10. [V7.0] Full Path (숨김 - 미리보기 브릿지용)
            item_path = QTableWidgetItem(data.get("full_path", ""))
            self.table.setItem(row, COL_IDX_FILEPATH, item_path)

            # 11. [V7.0] Page (숨김 - 미리보기 브릿지용)
            item_page = QTableWidgetItem(str(data.get("page", 1)))
            self.table.setItem(row, COL_IDX_PAGE, item_page)

            # [핵심] No(1번 열) 기준으로 오름차순 정렬 활성
            self.table.setSortingEnabled(True)
            self.table.sortItems(1, Qt.AscendingOrder)
            
            # 행 높이 재조정
            self._safe_resize_rows()
            
            self._safe_resize_rows()
            self.table.blockSignals(False) # [NEW] 시그널 재개

            # [V9.0 우뇌 가동] UI 업데이트 직후 백그라운드 학습 트리거
            pdf_path = data.get("full_path", "")
            if pdf_path:
                graph_thread = GraphifyIndexerThread(pdf_path, data)
                graph_thread.progress_signal.connect(lambda msg: self.statusBar().showMessage(msg))
                graph_thread.finished_signal.connect(lambda msg: self.statusBar().showMessage(msg, 5000))
                graph_thread.finished_signal.connect(lambda _: self.active_graph_threads.remove(graph_thread) if graph_thread in self.active_graph_threads else None)
                
                self.active_graph_threads.append(graph_thread)
                graph_thread.start()
        except Exception as e:
            self.table.blockSignals(False)
            self.log(f"[에러] 테이블 추가 실패: {e}")

    def update_validation_row(self, row, cas_with_content, res_1st_list, res_2nd_list, work_subjects="", status="High-Pass", db_records=None):
        """2단계 검증 결과를 테이블에 업데이트 (V10.2 파란색 신호등 🔵 제어 추가)"""
        try:
            # Hash를 가져와 캐시 조회
            f_hash = self.table.item(row, 8).text() if self.table.item(row, 8) else ""
            manual = self.cache.get(f_hash, {}).get("manual_data", {})
            
            self.table.blockSignals(True)
            
            # [Master 지시서] 신호등 이모지 및 배경색 제어
            traffic_col = 0
            curr_traffic_text = self.table.item(row, traffic_col).text() if self.table.item(row, traffic_col) else ""
            pure_idx = re.sub(r'^[🔴🟡🟢🔵]\s*', '', curr_traffic_text)
            
            emoji = "🟢"
            bg_color = None

            if status == "Review Required":
                emoji = "🔵"
                bg_color = QColor("#e7f1ff") # 연한 파란색
                # [NEW] 사후 검수를 위해 대기열에 추가
                fn = self.table.item(row, 7).text() if self.table.item(row, 7) else ""
                prod = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
                if not any(item['row'] == row for item in self.need_review):
                    self.need_review.append({
                        "row": row, "product_name": prod, "records": db_records, "filename": fn
                    })
                    self.log(f"    - [Visual] {row}행 파란색(🔵) 마킹 및 검수 대기열 등록.")
            elif status == "Confirmed":
                emoji = "🟢"
                bg_color = QColor("#e1f7d5") # 연한 초록색 (확격 표시)
            
            # 신호등 업데이트
            item_seq = QTableWidgetItem(f"{emoji} {pure_idx}")
            item_seq.setTextAlignment(Qt.AlignCenter)
            if bg_color: item_seq.setBackground(bg_color)
            self.table.setItem(row, traffic_col, item_seq)

            # 1% 필터 배제 규칙 강화 (정규표현식으로 함유량 파싱)
            def is_above_one_percent(text):
                m = re.search(r'\((\d+\.?\d*)\s*%\)', text)
                if m:
                    return float(m.group(1)) >= 1.0
                return True # 함유량 미기재 시 일단 포함

            final_res1 = [r for r in res_1st_list if is_above_one_percent(r)]
            final_res2 = [r for r in res_2nd_list if is_above_one_percent(r)]

            # 1. 제품명
            existing_prod = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
            item_prod = QTableWidgetItem(manual.get("product_name", existing_prod))
            if bg_color: item_prod.setBackground(bg_color)
            self.table.setItem(row, 2, item_prod)

            # 2. CAS (추출된 것이나 수동 수정본)
            api_cas = ";\n".join(cas_with_content) if cas_with_content else "" # 공백 제거
            old_cas = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
            item_cas = QTableWidgetItem(manual.get("raw_content", api_cas if api_cas else old_cas))
            if bg_color: item_cas.setBackground(bg_color)
            self.table.setItem(row, 3, item_cas)

            # 3. 측정대상 (1% 필터링 반영)
            final_measure = manual.get("measure", work_subjects)
            item_measure = QTableWidgetItem(final_measure)
            if bg_color: item_measure.setBackground(bg_color)
            self.table.setItem(row, 4, item_measure)

            # 4. 2차 결과 (1% 필터링 반영)
            final_reg2_str = manual.get("reg2", ";\n".join(final_res2)) # 공백 제거
            item_reg2 = QTableWidgetItem(final_reg2_str)
            if bg_color: item_reg2.setBackground(bg_color)
            self.table.setItem(row, 5, item_reg2)

            # 5. 1차 결과 (1% 필터링 반영)
            final_reg1_str = manual.get("reg1", ";\n".join(final_res1)) # 공백 제거
            item_reg1 = QTableWidgetItem(final_reg1_str)
            if bg_color: item_reg1.setBackground(bg_color)
            self.table.setItem(row, 6, item_reg1)
            
            # 기타 열 배경색 맞춤
            for c_idx in [1, 7]:
                item = self.table.item(row, c_idx)
                if item and bg_color: item.setBackground(bg_color)

            self.table.blockSignals(False)
            self._safe_resize_rows()
        except Exception as e:
            self.table.blockSignals(False)
            self.log(f"[!] 행 업데이트 실패: {e}")
            self._safe_resize_rows()
            
        except Exception as e:
            self.log(f"[에러] 테이블 업데이트 실패: {row}행, {e}")
        finally:
            # [V8.3] 무조건 UI 시그널 락 해제
            self.table.blockSignals(False)


    def perform_standard_save(self):
        """[V6.998] 가로형 저장 고도화: 사용자가 지정한 시작 행/열에 데이터 입력"""
        if not self.results:
            QMessageBox.warning(self, "경고", "저장할 결과 데이터가 없습니다.")
            return
            
        excel_path = self.edit_excel.text().strip()
        sheet_name = self.combo_sheet.currentText()
        if not excel_path or not os.path.exists(excel_path):
            QMessageBox.warning(self, "경고", "올바른 엑셀 경로를 지정해 주세요.")
            return

        if self.is_file_locked(excel_path):
            QMessageBox.critical(self, "파일 열림", f"대상 엑셀 파일({os.path.basename(excel_path)})이 이미 열려 있습니다.\n파일을 닫은 후 다시 시도해 주세요.")
            return

        self.log(f"[*] 가로형 저장 시작... (대상: {os.path.basename(excel_path)})")
        
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        excel = None
        try:
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            
            wb = excel.Workbooks.Open(os.path.abspath(excel_path))
            ws = wb.Sheets(sheet_name)
            
            # [V9.7] 중앙화된 c2i 정적 메서드 활용 (타입 무결성)
            mapping = {k: SMUGUI.c2i(v.text().strip()) for k, v in self.mapping_panel.inputs.items()}
            
            try:
                st_row = int(self.edit_start_row.text())
            except:
                st_row = 3

            # [NEW] 기존 데이터 존재 여부 사전 체크 (덮어쓰기 방지)
            conflicts = []
            max_check_count = len(self.results)
            self.log(f"[*] 기존 데이터 존재 여부 검사 중... (범위: {st_row}행부터 {max_check_count}개 행)")
            
            for idx in range(max_check_count):
                check_row = st_row + idx
                for key, col in mapping.items():
                    if col <= 0: continue
                    cell_val = ws.Cells(check_row, col).Value
                    if cell_val is not None and str(cell_val).strip() != "":
                        conflicts.append(f"{check_row}행 ({key})")
                        break # 행당 하나만 기록
                if len(conflicts) >= 5: break # 예시 5개면 충분

            if conflicts:
                msg = f"엑셀의 지정한 범위({st_row}행부터 {max_check_count}개 행) 내에 이미 데이터가 존재합니다.\n\n"
                msg += "[발견된 샘플]\n" + "\n".join(conflicts) + ("\n..." if len(conflicts) >= 5 else "")
                msg += "\n\n기존 데이터를 무시하고 강제로 덮어쓰시겠습니까?"
                
                reply = QMessageBox.question(self, "데이터 중복 알림", msg, 
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.No:
                    self.log("[!] 사용자의 취소로 저장을 중단했습니다. 엑셀을 확인해 주세요.")
                    wb.Close(False)
                    return

            # 테이블 데이터 매핑용 캐시 (V9.2 해시 데이터 포함)
            table_dict = {}
            for r in range(self.table.rowCount()):
                fn_item = self.table.item(r, 7)
                if fn_item:
                    fn = fn_item.text()
                    table_dict[fn] = {
                        "no": self.table.item(r, 1).text().strip(),      # No (1번 열)
                        "product_name": self.table.item(r, 2).text().strip(), # 제품명 (2번 열)
                        "cas_sum": self.table.item(r, 3).text(),
                        "measure": self.table.item(r, 4).text(),
                        "reg2": self.table.item(r, 5).text(),
                        "reg1": self.table.item(r, 6).text(),
                        "hash": self.table.item(r, 8).text() if self.table.item(r, 8) else ""
                    }

            # [V9.6] 저장 전 매칭 결과가 없다면 즉시 백그라운드 자동 매칭 (환경설정 연동)
            if not hasattr(self, 'matching_results') or not self.matching_results:
                self.log("[*] 매칭 결과가 감지되지 않아 지능형 자동 매칭을 긴급 가동합니다...")
                try:
                    # [V10.2] 타입 무결성 확보 및 로깅 변수 복구
                    raw_mapping = self.mapping_panel.get_mapping()
                    target_col_letter = str(raw_mapping.get("제품명", "D"))
                    mapping = {k: SMUGUI.c2i(v) for k, v in raw_mapping.items()}
                    
                    target_col_idx = mapping.get("제품명", 4) - 1 # 0-based for pandas
                    
                    # 헤더 탐색 (MatchingWorker와 동일 로직)
                    raw_h = pd.read_excel(excel_path, sheet_name=sheet_name, engine='openpyxl', header=None, nrows=10)
                    h_pos = 0
                    for r_idx, row in raw_h.iterrows():
                        try:
                            if str(row[target_col_idx]).strip() not in ["nan", "None", ""]:
                                h_pos = r_idx; break
                        except: continue
                    
                    df_m = pd.read_excel(excel_path, sheet_name=sheet_name, engine='openpyxl', header=h_pos)
                    target_col = df_m.columns[target_col_idx]
                    
                    ex_names = [str(x).strip() for x in df_m[target_col]]
                    n_ex_names = [MatchingWorker.normalize_name(x) for x in ex_names]
                    from thefuzz import process, fuzz
                    self.matching_results = []
                    for res_item in self.results:
                        p_n = res_item.get("product_name", "")
                        b_m = process.extractOne(MatchingWorker.normalize_name(p_n), n_ex_names, scorer=fuzz.token_sort_ratio)
                        if b_m and b_m[1] >= 80:
                            actual_idx = n_ex_names.index(b_m[0])
                            self.matching_results.append({
                                "pdf_name": p_n, "excel_name": ex_names[actual_idx], 
                                "excel_idx": actual_idx, "score": b_m[1], "binding_data": None
                            })
                    self.log(f"[*] 자동 매칭 데이터 {len(self.matching_results)}건 생성 성공 (설정열: {target_col_letter}).")
                except Exception as e: self.log(f"[!] 자동 매칭 실패: {e}")

            # [NEW] ID 매칭을 위한 A열 사전 스캔 (지능형 매칭 도입)
            scan_limit = max(ws.UsedRange.Rows.Count + st_row + 50, 500)
            self.log(f"[*] 엑셀 ID 매칭 준비 중 (범위: {st_row}~{scan_limit}행)...")
            
            # A열(1번 열) 데이터를 한 번에 가져와서 속도 최적화
            a_values = ws.Range(ws.Cells(st_row, 1), ws.Cells(scan_limit, 1)).Value
            a_map = {}
            if a_values:
                for r_idx, val_tuple in enumerate(a_values):
                    actual_row = st_row + r_idx
                    val = val_tuple[0]
                    if val is not None:
                        try:
                            # 숫자 형태인 경우 '001' 형식으로 보정하여 매칭률 향상
                            clean_id = str(int(float(val))).zfill(3)
                            a_map[clean_id] = actual_row
                        except:
                            a_map[str(val).strip()] = actual_row

            # [NEW] 논리적 매칭 결과 사전 가공 (90% 이상 자동 바인딩 및 인덱스 맵 생성)
            usage_map = {}
            index_map = {} # PDF 제품명 -> excel_idx
            if hasattr(self, 'matching_results') and self.matching_results:
                for m in self.matching_results:
                    p_name = m['pdf_name']
                    if m['score'] >= 80 and m['binding_data']:
                        usage_map[p_name] = m['binding_data']
                    if 'excel_idx' in m and m['excel_idx'] != -1:
                        index_map[p_name] = m['excel_idx']

            matched_count = 0
            # [V6.999] 가로형 저장 고도화: ID 매칭을 통한 정밀 기입 + 데이터 바인딩 병합
            for idx, item in enumerate(self.results):
                fn = item["filename"]
                
                if fn in table_dict:
                    td = table_dict[fn]
                    prod_name = td["product_name"] # 테이블에서 수정된 제품명
                    
                    # [V9.0] 999 무시 및 지능형 매칭 최우선 (캐시 복원 포함)
                    # 우선순위 1: 런타임 매칭 결과
                    idx_val = index_map.get(item.get("product_name", ""), index_map.get(prod_name))
                    
                    # 우선순위 1-1: 영구 캐시에서 복원 (재시작 대응)
                    if idx_val is None:
                        f_hash = table_dict[fn].get("hash", "")
                        c_data = self.cache.get(f_hash, {})
                        if c_data.get("match_idx") is not None:
                            # 현재 선택된 엑셀/시트와 일치하는지 검증 (필수)
                            if c_data.get("match_excel") == excel_path and c_data.get("match_sheet") == sheet_name:
                                idx_val = c_data["match_idx"]
                                self.log(f"[*] 캐시에서 지능형 매칭 정보 복원: {fn} -> {idx_val}행")

                    tr = None
                    strategy = "N/A"
                    
                    if idx_val is not None:
                        tr = st_row + idx_val
                        strategy = "지능형 매칭 (캐시 복원/999 무시)"
                        
                        # [V9.0 Drift Protection] 행 밀림 방지 '이중 검증' 로직
                        try:
                            # 엑셀의 해당 행 제품명 실제 조회
                            # target_col 인덱스 찾기
                            t_col_idx = 1
                            for col_i in range(1, 10):
                                val = ws.Cells(st_row - 1, col_i).Value
                                if any(kw in str(val) for kw in ["화학물질명", "제품명", "물질명", "성분명"]):
                                    t_col_idx = col_i
                                    break
                            
                            actual_name = str(ws.Cells(tr, t_col_idx).Value).strip()
                            # 단순 비교 (공백 제거 후) - Drawing from central Static Method
                            if MatchingWorker.normalize_name(actual_name) != MatchingWorker.normalize_name(prod_name):
                                self.log(f"[!] [행밀림탐지] {tr}행 제품명 불일치('{actual_name}' vs '{prod_name}'). 보정 시작...")
                                # 인접 100행 스캔
                                search_range = range(max(st_row, tr - 100), tr + 100)
                                for s_idx in search_range:
                                    s_val = str(ws.Cells(s_idx, t_col_idx).Value).strip()
                                    if MatchingWorker.normalize_name(s_val) == MatchingWorker.normalize_name(prod_name):
                                        tr = s_idx
                                        self.log(f"[*] [행보정성공] {tr}행에서 일치하는 제품명 발견.")
                                        break
                        except Exception as e:
                            self.log(f"[주의] 행 보정 중 오류: {e}")
                    
                    # 우선순위 2: 엑셀 A열 번호 매칭 (Fallback)
                    if not tr:
                        num_key = td["no"].zfill(3) if td["no"].isdigit() else td["no"]
                        tr = a_map.get(num_key)
                        if tr:
                            strategy = "A열 ID 매칭 (보조)"
                    
                    if not tr:
                        self.log(f"[!] [매칭실패] 매칭 인덱스 및 A열 ID 정보가 없습니다 (파일: {fn}). 건너뜀.")
                        continue
                    
                    curr_row = tr
                    self.log(f"[*] [저장타겟] {fn} -> {curr_row}행 ({strategy})")

                    # [NEW] 바인딩 데이터 조회 (90% 이상 확신도)
                    # PDF 원본 제품명 또는 테이블 수정 제품명 둘 다 체크 지원
                    binding = usage_map.get(item.get("product_name", ""), usage_map.get(prod_name))

                    for key, col in mapping.items():
                        if col <= 0: continue
                        
                        val = ""
                        if key == "파일명": val = fn
                        elif key == "제품명": val = prod_name
                        elif key == "CAS 원본": val = td["cas_sum"].replace("\n", " ").replace("  ", " ").strip()
                        elif key == "2차 결과(규제)": val = td["reg2"].replace("\n", " ").replace("  ", " ").strip()
                        elif key == "1차 결과(전체)": val = td["reg1"].replace("\n", " ").replace("  ", " ").strip()
                        # [주님 지시] 측정대상을 복수(둘 다) 열에 저장
                        elif key in ["측정대상1", "측정대상2"]: 
                            val = td["measure"].replace("\n", " ").replace("  ", " ").strip()
                        
                        # [NEW] 바인딩 필드 처리
                        elif binding:
                            if key == "공정명": val = binding.get("공정명", "")
                            elif key == "제조/사용": val = binding.get("제조/사용", "")
                            elif key == "사용용도": val = binding.get("사용용도", "")
                            elif key == "월취급량": val = binding.get("월취급량", "")
                            elif key == "단위": val = binding.get("단위", "")
                        
                        if val:
                            ws.Cells(curr_row, col).Value = val
                    matched_count += 1
            
            wb.Save()
            excel.Visible = True
            excel.Interactive = True
            self.log(f"[완료] {matched_count}건 가로형 저장 성공 (시작 행: {st_row})")
            QMessageBox.information(self, "완료", f"가로형 엑셀 저장이 완료되었습니다.\n({matched_count}건 저장됨)")

        except Exception as e:
            if excel: excel.Visible = True
            self.log(f"[오류] 저장 실패: {str(e)}")
            QMessageBox.critical(self, "오류", str(e))
        finally:
            pythoncom.CoUninitialize()


def global_exception_handler(exctype, value, tb):
    """[Part 20] 전역 예외 처리기: 모든 스레드/슬롯의 크래시를 팝업으로 표시"""
    import traceback
    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    print(f"CRITICAL SYSTEM ERROR:\n{err_msg}")
    # 파일로도 기록
    with open("crash_log.txt", "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now()}]\n{err_msg}\n")
    
    # GUI 상에서 에러 메시지 표시 시도
    try:
        QMessageBox.critical(None, "시스템 오류 발생", f"프로그램이 예상치 못한 오류로 종료됩니다.\n\n{value}")
    except:
        pass
    sys.exit(1)

if __name__ == "__main__":
    # 시스템 예외 가로채기 설정
    sys.excepthook = global_exception_handler
    
    app = QApplication(sys.argv)
    window = SMUGUI()
    window.show()
    sys.exit(app.exec_())
