import sys
import os
import time
import json
import re
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QLineEdit, QFileDialog, QTableWidget, 
    QTableWidgetItem, QHeaderView, QGroupBox, QGridLayout, 
    QScrollArea, QMessageBox, QComboBox, QProgressBar, QFrame,
    QSplitter, QTabWidget, QTextEdit, QStyledItemDelegate, QStyle,
    QStackedWidget, QToolButton, QSizePolicy, QMenu
)
import fitz  # [NEW] PyMuPDF: 주님이 원하신 무지연 미리보기 엔진
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QRect, QPropertyAnimation, QEasingCurve, QUrl, QTimer
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette, QTextDocument, QCursor, QTextCursor, QImage, QPixmap
from html import escape

import msds_core
import importlib # [HOT-RELOAD] 모듈 새로고침용
from msds_core import MSDSCore
import msds_engine_v5 as engine
import openpyxl  # [V6.994] 시트 목록 추출 및 사전 검증용
import pandas as pd # [V10.5] 마스터 DB 로드용

# [V7.0] 테이블 컬럼 인덱스 정의 (미리보기 브릿지용)
COL_IDX_FILENAME = 7
COL_IDX_HASH = 8
COL_IDX_FILEPATH = 9
COL_IDX_PAGE = 10

# [Part 1] 탐색기 스타일 자연스러운 정렬 (Natural Sort)
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]


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
        
        # [수정] 강제 개행(<br>)을 제거하고 세미콜론과 공백(; )으로 연결하여 가로 흐름 최적화 (수직 팽창 방지)
        final_html = f"<html><body style='font-family:Malgun Gothic; font-size:9pt;'>{'; '.join(html_parts)}</body></html>"
        
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
    finished_signal = pyqtSignal(dict)
    cache_update_signal = pyqtSignal(str, dict) # [NEW] 캐시 업데이트 요청용

    def __init__(self, core, pdf_paths, cache=None):
        super().__init__()
        self.core = core
        self.pdf_paths = pdf_paths
        self.cache = cache or {}
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        stats = {"regex": 0, "flash": 0, "bulldozer": 0}
        total = len(self.pdf_paths)
        for i, path in enumerate(self.pdf_paths):
            if not self.is_running: break
            try:
                fn = os.path.basename(path)
                if i > 0: self.update_log_signal.emit("<span style='color:#5DADE2;'><b>" + "━"*70 + "</b></span>") 
                
                # [NEW] 캐시 체크 (SHA-256 해시 기준)
                f_hash = self.core.calculate_file_hash(path)
                if not f_hash:  # [V8.3] 해시 생성 보장 (Fallback)
                    f_hash = f"fallback_{i}_{fn}"
                
                if f_hash and getattr(self, 'cache', None) and f_hash in self.cache:
                    cached_data = self.cache[f_hash]
                    manual = cached_data.get("manual_data", {})
                    
                    # [V11.7 핵심 로직] 수동 데이터가 없고(not manual), 과거에 AI가 실패했던 경우에만 재시도!
                    if not manual and (cached_data.get("product_name") == "제품명 확인 필요" or "오류" in cached_data.get("status", "")):
                        self.update_log_signal.emit(f"[*] [{fn}] 불완전한 추출 결과(AI 뻗음 등) 감지: API 재호출을 시도합니다.")
                        # continue 안 함 -> AI 엔진 재가동
                    else:
                        self.update_log_signal.emit(f"[*] [{fn}] 캐시된 결과가 발견되었습니다. (재추출 건너뜀)")
                        
                        # [V11.6 로직 유지] manual_data 금고 확인 및 최우선 덮어쓰기
                        final_product = manual.get("product_name", cached_data.get("product_name", "미확인"))
                        final_content = manual.get("raw_content", cached_data.get("raw_content", ""))

                        res_data = {
                            "filename": fn,
                            "f_hash": f_hash, 
                            "product_name": final_product, 
                            "reliability": cached_data.get("reliability", "N/A"),
                            "신호등": cached_data.get("신호등", "⚪"),
                            "raw_content": final_content, 
                            "status": "수동 수정됨" if manual else "캐시 로드됨"
                        }
                        self.result_signal.emit(res_data)
                        self.progress_signal.emit(int((i + 1) / total * 100))
                        stats["regex"] += 1
                        continue

                self.update_log_signal.emit("="*20 + f" [{fn} 추출 시작] " + "="*20)
                # [V7-Final] 통합형 엔진으로 추출 수행 (정규식 개안 및 숲-나무 분석 적용)
                ext_res = engine.analyze_msds(path, log_func=self.update_log_signal.emit)
                
                extracted_data = {
                    "f_hash": f_hash,
                    "product_name": ext_res.get("제품명", "미확인"),
                    "reliability": ext_res.get("신뢰도", "N/A"),
                    "신호등": ext_res.get("신호등", "⚪"), 
                    "raw_content": ext_res.get("구성성분", ext_res.get("구성성분 및 함유량", "")),
                    # 🚨 [V15.3 파이프 연결] 엔진이 강제로 쏴주는 '측정대상' 수신!
                    "measure_target": ext_res.get("측정대상", ""), 
                    "full_path": path, 
                    "page": ext_res.get("page", 1), 
                    "used_engine": ext_res.get("used_engine", "regex")
                }
                
                # [NEW] 캐시에 저장 요청
                if f_hash:
                    self.cache_update_signal.emit(f_hash, extracted_data)

                res_data = extracted_data.copy()
                res_data["filename"] = fn
                res_data["status"] = "추출 완료"
                
                # 통계 집계
                engine_type = res_data.get("used_engine", "regex")
                if engine_type in stats:
                    stats[engine_type] += 1
                else:
                    stats["regex"] += 1

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
        
        self.finished_signal.emit(stats)

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
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        total = len(self.table_data)
        for i, data in enumerate(self.table_data):
            if not self.is_running: break
            try:
                f_hash = data.get("f_hash")
                fn = data.get("filename")
                prod = data.get("prod")
                cas_content = data.get("cas_content")
                row_idx = data.get("row_idx") # Fallback용
                if i > 0: self.log_signal.emit("<span style='color:#5DADE2;'><b>" + "━"*70 + "</b></span>")
                
                # [V11.4 신규] 사용자가 테이블의 CAS를 직접 수정한 경우 (캐시에 manual_data 내 raw_content 존재) 감지
                is_manual_cas = False
                if f_hash and self.parent_gui.cache.get(f_hash, {}).get("manual_data", {}).get("raw_content"):
                    is_manual_cas = True

                # Case 0: DB 지식 로직 제거 (항상 API 엔진 가동)
                self.log_signal.emit(f"[*] API 엔진 가동: [{prod}]")
                self.log_signal.emit("="*20 + f" [{prod} API 검증 시작] " + "="*20)
                # [V8.8] 지능형 CAS 추출 및 함유량 보존 로직 (함유량% 보장)
                # [V8.8] 지능형 CAS 추출 및 함유량 보존 로직 (함유량% 보장)
                cas_to_content = {}
                preserved_non_cas = [] # [버그 수정] KOSHA에 안 갈 '영업비밀' 등 보존소
                
                for item in str(cas_content).split(";"):
                    item = item.strip()
                    if not item: continue
                    
                    match = re.search(r'(\d{2,7}-\d{2}-\d)', item)
                    if match:
                        cas = match.group(1)
                        # 함유량 괄호 안의 내용만 추출
                        content_match = re.search(r'\(([^)]+)\)', item)
                        content_val = content_match.group(1) if content_match else ""
                        
                        if content_val and "%" not in content_val and re.search(r'\d', content_val):
                            content_val = f"{content_val}%"
                        cas_to_content[cas] = content_val
                    else:
                        # CAS 번호 규격이 아닌 것(예: 영업비밀(10%))은 그대로 킵해둠
                        preserved_non_cas.append(item)
                
                pure_cas_list = list(cas_to_content.keys())
                pure_cas_str = "; ".join(pure_cas_list) if pure_cas_list else cas_content

                # [V11.4 핵심] 수동 수정 시 KOSHA API 캐시(Cache-Hit)도 강제 우회
                f_hash_for_api = None if is_manual_cas else f_hash
                if is_manual_cas:
                    self.log_signal.emit(f"[*] CAS 수동 수정 감지: 과거 지식을 무시하고 KOSHA API를 재호출합니다.")

                # [수정] 코어 호출 시 조건부 f_hash 파라미터 전달
                raw_val_res = self.core.validate_with_kosha(pure_cas_str, log_func=self.log_signal.emit, full=False, f_hash=f_hash_for_api)
                
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
                        
                    # [V11.3 최종 지침] KOSHA API 결과도 엔진(V5)의 표준명칭과 100% 동기화
                    mes_std_name = engine.MES_MASTER_MAP.get(cas, "")
                    
                    if mes_std_name:
                        clean_name = str(mes_std_name)
                        # 마스터 DB 노이즈 제거 (분진/흄 등은 철저히 보존)
                        clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()
                    else:
                        # 엔진 맵에 없을 경우에만 GUI 로컬 맵에서 2차 방어망 가동
                        mes_entry = self.parent_gui.mes_cas_map.get(cas, {})
                        fallback_name = mes_entry.get("물질명") or mes_entry.get("상용명")
                        if fallback_name and str(fallback_name).lower() != 'nan':
                            clean_name = str(fallback_name)
                            clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()

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

                # [버그 수정] KOSHA 검색에서 제외되었던 영업비밀 등을 1차 결과(전체)에 다시 합류시킴
                if preserved_non_cas:
                    res_1st_list.extend(preserved_non_cas)

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
                is_welding = ("용접" in prod) or ("welding" in prod.lower())
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
            ("순번/No", "A"), ("제품명", "D"), ("파일명", "P"),
            ("2차 결과(규제)", "L"), ("1차 결과(전체)", "N"),
            ("측정대상1", "M"), ("측정대상2", ""), # 측정대상을 복수로 저장하기 위해 두 칸으로 분리
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
        self.init_ui()
        
        # [V7.5] 동기화 무결성 확보를 위한 초기화 순서 재배치
        self.load_cache() # 1. 캐시 먼저 로드
        self.load_config() # 2. 그 다음 설정 로드 (setText 발생 시 시그널 즉시 발동)
        self.load_mes_master() # [NEW] MES 마스터 데이터셋 구축
        self.showMaximized()
        
        # [NEW] 세션 복구: 이전 파일 목록을 테이블에 복원
        self.restore_table_from_session()

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
            ("환경 설정", "[SET]", 1)
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

    def switch_page(self, idx, btn):
        """[Premium] 페이지 전환 및 사이드바 버튼 상태 업데이트"""
        self.stacked_widget.setCurrentIndex(idx)
        for b in self.menu_buttons:
            b.setChecked(False)
            b.update_style(False)
        btn.setChecked(True)
        btn.update_style(True)

        # [V7.5] 탭으로 전환 시, 시트 목록이 비어 있으면 강제 갱신 시도
        if idx == 0: # 추출 및 검증 탭
            path = self.edit_excel.text()
            if path and self.combo_sheet.count() == 0:
                self._update_sheet_list(path)

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


        self.main_splitter = QSplitter(Qt.Vertical)
        self.content_layout.addWidget(self.main_splitter)

        self.stacked_widget = QStackedWidget()
        self.main_splitter.addWidget(self.stacked_widget)

        # 페이지 0: 기존 주 화면
        self.page_extraction = self._create_extraction_page()
        self.stacked_widget.addWidget(self.page_extraction)

        self.page_settings = self._create_settings_page()
        self.stacked_widget.addWidget(self.page_settings)

        # 3. 로그 창
        self._setup_log_section()
        

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

        btn_load = QPushButton("폴더/파일 선택")
        btn_load.setFixedWidth(110); btn_load.setFixedHeight(35)
        
        menu_load = QMenu(self)
        action_file = menu_load.addAction("📄 파일 선택")
        action_folder = menu_load.addAction("📁 폴더 선택")
        action_file.triggered.connect(self.load_pdfs)
        action_folder.triggered.connect(self.load_pdf_folder)
        btn_load.setMenu(menu_load)
        
        header.addWidget(btn_load)

        btn_reset = QPushButton("초기화")
        btn_reset.setFixedWidth(60); btn_reset.setFixedHeight(35)
        btn_reset.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold;")
        btn_reset.clicked.connect(self.reset_all)
        header.addWidget(btn_reset)

        btn_reload = QPushButton("엔진 🔄")
        btn_reload.setFixedWidth(70); btn_reload.setFixedHeight(35)
        btn_reload.setStyleSheet("background-color: #67c23a; color: white; font-weight: bold;")
        btn_reload.clicked.connect(self.reload_engine)
        header.addWidget(btn_reload)

        header.addSpacing(20)
        self.btn_step1 = QPushButton("1단계 추출")
        self.btn_step1.setFixedHeight(35); self.btn_step1.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold;")
        self.btn_step1.setToolTip("목록에 있는 PDF 파일들에서 MSDS 데이터를 AI로 자동 추출합니다.")
        self.btn_step1.clicked.connect(self.run_extraction)
        header.addWidget(self.btn_step1)

        self.btn_step2 = QPushButton("2단계 검증")
        self.btn_step2.setFixedHeight(35); self.btn_step2.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
        self.btn_step2.setToolTip("추출된 데이터를 바탕으로 공단 DB 및 마스터 DB와 대조하여 규제 여부를 검증합니다.")
        self.btn_step2.clicked.connect(self.run_validation)
        header.addWidget(self.btn_step2)

        self.btn_stop = QPushButton("실행 중지")
        self.btn_stop.setFixedHeight(35); self.btn_stop.setStyleSheet("QPushButton { background-color: #d93025; color: white; font-weight: bold; } QPushButton:disabled { background-color: #eaa9a9; color: #ffffff; }")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_process)
        header.addWidget(self.btn_stop)

        header.addStretch() # 버튼들을 왼쪽으로 밀고 우측에 여백 확보

        # [NEW] UX/UI 온보딩: 도움말 버튼 추가 (기존 빈 줄 낭비 방지를 위해 이 줄로 편입)
        self.btn_help = QToolButton()
        self.btn_help.setText(" ? ")
        self.btn_help.setToolTip("핵심 사용법 가이드를 확인합니다.")
        self.btn_help.setStyleSheet(f"""
            QToolButton {{
                background-color: {PRIMARY_BLUE};
                color: white;
                border-radius: 12px;
                font-weight: bold;
                font-size: 14px;
                padding: 2px;
            }}
            QToolButton:hover {{
                background-color: #004d80;
            }}
        """)
        self.btn_help.setFixedSize(25, 25)
        self.btn_help.clicked.connect(self.show_help_dialog)
        header.addWidget(self.btn_help)

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
        btn_save_h.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        btn_save_h.setToolTip("현재 화면에 표시된 데이터를 엑셀(Excel) 파일로 저장합니다.")
        btn_save_h.clicked.connect(self.perform_standard_save)
        excel_bar.addWidget(btn_save_h)
        
        self.btn_open_ex = QPushButton("📂 엑셀 열기")
        self.btn_open_ex.setFixedWidth(110); self.btn_open_ex.setFixedHeight(35)
        self.btn_open_ex.setStyleSheet("background-color: #17a2b8; color: white; font-weight: bold;")
        self.btn_open_ex.clicked.connect(self.open_saved_excel)
        excel_bar.addWidget(self.btn_open_ex)
        
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
        self.table.horizontalHeaderItem(3).setToolTip("CAS 번호를 클릭하면 KOSHA 화학물질정보 페이지로 이동합니다.")
        self.table.verticalHeader().setVisible(False)

        header_table = self.table.horizontalHeader()
        header_table.sectionResized.connect(self._safe_resize_rows)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 45)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 220)
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
        
        # [NEW] 빈 화면 워터마크 (Empty State Label)
        self.lbl_watermark = QLabel("① 여기에 PDF 파일을 끌어다 놓으세요  →  ② [추출 시작] 버튼을 누르세요", self.table)
        self.lbl_watermark.setAlignment(Qt.AlignCenter)
        self.lbl_watermark.setStyleSheet("color: #b0b0b0; font-size: 16px; font-weight: bold; background: transparent;")
        # 테이블 중앙에 위치시키기 위해 레이아웃 트릭 사용
        watermark_layout = QVBoxLayout(self.table)
        watermark_layout.addWidget(self.lbl_watermark)
        self.lbl_watermark.show() # 초기 상태는 노출

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
        [V7.0 & V11.0 통합] 테이블 행 클릭 시 미리보기 연동 (1페이지 강제 고정)
        """
        try:
            target_pdf_path_item = self.table.item(row, COL_IDX_FILEPATH)
            if not target_pdf_path_item: return
                
            target_pdf_path = target_pdf_path_item.text()

            if not target_pdf_path or not os.path.exists(target_pdf_path): return

            # PDF 로드
            if self.preview_pane.current_pdf_path != target_pdf_path:
                self.preview_pane.load_pdf(target_pdf_path)
                # [최종 단순화] 새로운 PDF를 로드할 때만 스크롤을 맨 위로 고정
                self.preview_pane.verticalScrollBar().setValue(0)

        except Exception as e:
            print(f"Row Click Error: {e}")

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

    def restore_table_from_session(self):
        """[NEW] 저장된 pdf_paths와 cache를 이용해 테이블 UI 복구"""
        if not hasattr(self, 'pdf_paths') or not self.pdf_paths:
            return
            
        self.log("[*] 테이블 데이터를 복구 중입니다...")
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        
        for path in self.pdf_paths:
            if not os.path.exists(path):
                continue
                
            fn = os.path.basename(path)
            f_hash = self.core.calculate_file_hash(path)
            
            # 캐시가 있으면 캐시 데이터 사용, 없으면 기본 정보만 사용
            if f_hash and f_hash in self.cache:
                data = self.cache[f_hash].copy()
                data["filename"] = fn
                data["full_path"] = path
                data["f_hash"] = f_hash
                self.add_result_to_table(data)
                
                # 검증 결과도 있으면 반영
                if "manual_data" in data or "reliability" in data:
                    row = self.table.rowCount() - 1
                    # add_result_to_table이 정렬을 할 수 있으므로 행을 다시 찾아야 함
                    for r in range(self.table.rowCount()):
                        if self.table.item(r, 8) and self.table.item(r, 8).text() == f_hash:
                            row = r
                            break
                    
                    # 수동 데이터나 검증 결과가 있으면 update_validation_row 호출
                    v_data = data.get("manual_data", {})
                    self.update_validation_row(
                        row,
                        v_data.get("raw_content", data.get("raw_content", "")).split("; "),
                        v_data.get("reg1", "").split(";\n"),
                        v_data.get("reg2", "").split(";\n"),
                        v_data.get("measure", ""),
                        status=data.get("status", "캐시 로드됨")
                    )
            else:
                # 캐시 없는 파일은 기본 행만 추가
                data = {
                    "filename": fn,
                    "f_hash": f_hash,
                    "product_name": "미분석",
                    "reliability": "[NEW]",
                    "신호등": "⚪",
                    "raw_content": "",
                    "full_path": path,
                    "status": "대기 중"
                }
                self.add_result_to_table(data)
                
        self.table.blockSignals(False)
        self.update_file_count_display()
        self.log("✅ 세션 복구가 완료되었습니다.")

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
                            
                            # [V11.4 캐시 정화] CAS(raw_content)가 수정되면, 기존 규제 결과 캐시를 모두 삭제
                            if key == "raw_content":
                                for old_k in ["measure", "reg2", "reg1"]:
                                    if old_k in self.cache[f_hash]["manual_data"]:
                                        del self.cache[f_hash]["manual_data"][old_k]
                                        
                            self.cache[f_hash]["manual_data"][key] = new_text
                            self.save_cache()
                            
                            # 2. self.results 메모리 실시간 동기화 (Hot-Sync)
                            for res in self.results:
                                if res.get('f_hash') == f_hash:
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
                f = os.path.normpath(f).replace('\\', '/')
                if f in self.pdf_paths:
                    self.log(f"[경고] {os.path.basename(f)} 파일은 이미 목록에 있습니다. (추가 제외됨)")
                    continue
                new_files.append(f)
            
            if new_files:
                self.pdf_paths.extend(new_files)
                self.update_file_count_display()
                self.log(f"[*] {len(new_files)}개의 PDF 파일이 추가되었습니다.")

    def load_pdf_folder(self):
        """[NEW] 폴더 선택 및 하위 PDF 일괄 추가"""
        folder = QFileDialog.getExistingDirectory(self, "분석할 MSDS 폴더 선택")
        if folder:
            all_pdfs = []
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(".pdf"):
                        all_pdfs.append(os.path.normpath(os.path.join(root, f)).replace('\\', '/'))
            
            if not all_pdfs:
                self.log("[!] 선택한 폴더에 추가할 PDF 파일이 없습니다.")
                return
                
            new_files = []
            for f in all_pdfs:
                if f in self.pdf_paths:
                    continue
                new_files.append(f)
            
            if new_files:
                self.pdf_paths.extend(new_files)
                self.update_file_count_display()
                self.log(f"[*] 폴더에서 {len(new_files)}개의 PDF 파일이 일괄 추가되었습니다. (중복 제외)")
            else:
                self.log("[경고] 해당 폴더 내의 모든 PDF가 이미 목록에 포함되어 있습니다.")

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

        # [NEW] 워터마크 상태 연동
        if hasattr(self, 'lbl_watermark'):
            if count > 0 or (hasattr(self, 'table') and self.table.rowCount() > 0):
                self.lbl_watermark.hide()
            else:
                self.lbl_watermark.show()

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
            excel = win32com.client.DispatchEx("Excel.Application")
            try: excel.Visible = False
            except AttributeError: pass
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

            # 2. 번호 부여 (매핑된 열 사용)
            mapping = self.mapping_panel.get_mapping()
            col_letter = mapping.get("순번/No", "A")
            col_idx = SMUGUI.c2i(col_letter)
            if col_idx < 1: col_idx = 1 # Fallback to A

            for i in range(count):
                val = start_no + i
                # 문자열 포맷팅 ('001 형식으로 입력하여 엑셀이 숫자로 자동 변환하는 것 방지)
                ws.Cells(start_row + i, col_idx).Value = f"'{val:03d}" 
            
            wb.Save()
            self.log(f"[*] 엑셀 A열 {start_row}행부터 {count}개의 번호를 부여했습니다. (시작: {start_no:03d})")
            QMessageBox.information(self, "성공", "엑셀 번호 부여가 완료되었습니다.")
            
        except Exception as e:
            self.log(f"❌ 엑셀 작업 오류: {e}")
            QMessageBox.critical(self, "오류", f"엑셀 작업 중 오류 발생:\n{e}")
        finally:
            if excel:
                try: excel.Visible = True
                except AttributeError: pass
                try: excel.UserControl = True
                except AttributeError: pass
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
        self.btn_stop.setEnabled(True)
        self.btn_step1.setEnabled(False)
        self.btn_step2.setEnabled(False)
        self.worker = ExtractionWorker(self.core, self.pdf_paths, cache=self.cache)
        self.worker.update_log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.result_signal.connect(self.add_result_to_table)
        self.worker.cache_update_signal.connect(self.update_cache) # [NEW] 캐시 업데이트 연동
        self.worker.finished_signal.connect(self.on_extraction_finished)
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
        self.btn_stop.setEnabled(True)
        self.btn_step1.setEnabled(False)
        self.btn_step2.setEnabled(False)
        self.worker = ValidationWorker(self, self.core, table_data) # [Task 2] self(GUI) 전달 추가
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.result_signal.connect(self.on_validation_result) 
        self.worker.finished_signal.connect(self.on_validation_finished)
        self.worker.start()

    def on_extraction_finished(self, stats):
        """1단계 PDF 추출 완료 요약 보고 (V12.8 통계 대시보드)"""
        self.table.blockSignals(False)
        self.btn_stop.setEnabled(False)
        self.btn_step1.setEnabled(True)
        self.btn_step2.setEnabled(True)
        self.log("[*] 1단계 PDF 추출 작업이 완료되었습니다.")
        
        summary = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "   📊 MSDS 추출 가동 현황 보고\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ 총 처리 파일: {sum(stats.values())}건\n\n"
            f"🔹 REGEX (정규식/캐시): {stats.get('regex', 0)}건\n"
            f"🔸 FLASH (Gemini 2.5): {stats.get('flash', 0)}건\n"
            f"🚀 BULLDOZER (Fallback): {stats.get('bulldozer', 0)}건\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "추출된 데이터를 확인/수정한 후 [2단계 검증]을 진행하세요."
        )
        QMessageBox.information(self, "추출 완료 리포트", summary)

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

            self.update_validation_row(
                found_row, 
                v.get("cas_with_content", []), 
                v.get("res_1st", []), 
                v.get("res_2nd", []),
                v.get("work_subjects", ""),
                status=status # [NEW] 상태값 전달
            )

    def on_validation_finished(self):
        """2단계 API 검증 완료 처리"""
        self.table.blockSignals(False)
        self.btn_stop.setEnabled(False)
        self.btn_step1.setEnabled(True)
        self.btn_step2.setEnabled(True)
        self.log("[*] 2단계 API 검증 작업이 완료되었습니다.")
        QMessageBox.information(self, "완료", "2단계 API 검증이 완료되었습니다.")

    def stop_process(self):
        """[NEW] 현재 진행 중인 작업을 중지"""
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log("🛑 사용자에 의해 중지 신호가 전달되었습니다. 잠시만 기다려 주세요...")
            # 강제 종료보다는 안전하게 루프가 끝날 때까지 대기하도록 유도
            self.btn_stop.setEnabled(False)

    def open_saved_excel(self):
        """[NEW] 저장된 엑셀 파일을 즉시 열기"""
        path = self.edit_excel.text().strip()
        if path and os.path.exists(path):
            try:
                os.startfile(path)
                self.log(f"[*] 엑셀 파일 열기: {os.path.basename(path)}")
            except Exception as e:
                self.log(f"[!] 파일 열기 실패: {e}")
        else:
            QMessageBox.warning(self, "파일 없음", "지정된 엑셀 파일을 찾을 수 없거나 경로가 비어 있습니다.")

    def closeEvent(self, event):
        """[V6.995 통합] 프로그램 종료 시 안전 점검 및 설정 저장"""
        # 1. 백그라운드 작업 체크
        if hasattr(self, 'active_graph_threads') and self.active_graph_threads:
            active_count = len(self.active_graph_threads)
            reply = QMessageBox.warning(self, '종료 경고', 
                f"현재 {active_count}개의 지식 그래프 업데이트가 백그라운드에서 진행 중입니다.\n"
                "강제 종료 시 우뇌 DB(지식망)가 손상될 수 있습니다. 정말 종료하시겠습니까?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            
            if reply == QMessageBox.No:
                event.ignore()
                return

        # 2. 작업 중 체크
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, "종료 확인", "현재 분석 작업이 진행 중입니다. 중단하고 종료할까요?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
            self.worker.terminate()
            self.worker.wait()

        # 3. 설정 및 캐시 저장
        try:
            self.save_config()
            self.save_cache()
            self.log("[*] 모든 설정과 캐시가 안전하게 저장되었습니다.")
        except: pass
        
        event.accept()

    def show_help_dialog(self):
        """[Page UX] 핵심 사용법 1분 가이드 팝업"""
        help_text = (
            "<h2>💡 AI 화학물질 브레인 사용 가이드</h2>"
            "<ol>"
            "<li><b>파일 넣기:</b> 바탕화면의 MSDS PDF를 표 안으로 드래그 앤 드롭하세요.</li>"
            "<li><b>추출 하기:</b> [추출 시작]을 누르면 AI가 성분을 분석합니다.</li>"
            "<li><b>교차 검증:</b> 파란색 CAS 번호를 클릭하면 <b>안전보건공단(KOSHA)</b> 창이 열려 즉시 확인 가능합니다.</li>"
            "<li><b>마스터 DB 연동:</b> 마스터에 없는 물질은 [미등록]으로 표시됩니다.</li>"
            "</ol>"
        )
        QMessageBox.information(self, "사용 설명서", help_text)


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

    # [V15.5.4] GUI-side character substitution logic (assassin) removed to preserve data integrity.
    # Raw data from the engine is now displayed As-is.

    def add_result_to_table(self, data):
        """1단계 결과를 테이블에 추가 (V7.3 캐시 쉴드 적용)"""
        # [NEW] 워터마크 즉시 숨김
        if hasattr(self, 'lbl_watermark'):
            self.lbl_watermark.hide()
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
            
            item_cas = QTableWidgetItem(";\n".join(clean_cas_parts))
            if bg_color: item_cas.setBackground(bg_color)
            self.table.setItem(row, 3, item_cas)

            # 5. [수정] 공란이었던 측정대상(4번 열)에 엔진이 강제로 보낸 데이터가 있다면 삽입!
            measure_val = data.get("measure_target", "")
            item_measure = QTableWidgetItem(str(measure_val))
            if bg_color: item_measure.setBackground(bg_color)
            self.table.setItem(row, 4, item_measure)

            # 6-7. 2차/1차 결과 열(5, 6번 열)만 2단계를 위해 공란으로 비워둠
            for c_idx in range(5, 7):
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
            self.table.blockSignals(False) # [NEW] 시그널 재개
        except Exception as e:
            self.table.blockSignals(False)
            self.log(f"[에러] 테이블 추가 실패: {e}")

    def update_validation_row(self, row, cas_with_content, res_1st_list, res_2nd_list, work_subjects="", status="High-Pass"):
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

            if "검증 완료" in status:
                emoji = "🟢"
                bg_color = QColor("#e1f7d5") # 연한 초록색 (확격 표시)
            
            # 신호등 업데이트
            item_seq = QTableWidgetItem(f"{emoji} {pure_idx}")
            item_seq.setTextAlignment(Qt.AlignCenter)
            if bg_color: item_seq.setBackground(bg_color)
            self.table.setItem(row, traffic_col, item_seq)

            # [V12.6] 1% 필터 배제 규칙 제거 (필터 없이 그대로 통과)
            final_res1 = res_1st_list
            final_res2 = res_2nd_list

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
            self.log(f"[에러] 테이블 업데이트 실패: {row}행, {e}")
            self._safe_resize_rows()
        finally:
            # [V8.3] 무조건 UI 시그널 락 해제
            self.table.blockSignals(False)


    def perform_standard_save(self):
        """[Standard] GUI 테이블의 데이터를 직접 참조하여 엑셀에 저장 (단순화된 파이프라인)"""
        if not hasattr(self, 'results') or not self.results:
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

        self.log(f"[*] 엑셀 저장 시작... (대상: {os.path.basename(excel_path)})")
        
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        excel = None
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            
            wb = excel.Workbooks.Open(os.path.abspath(excel_path))
            ws = wb.Sheets(sheet_name)
            
            # [V9.7] 중앙화된 c2i 정적 메서드 활용 (타입 무결성)
            raw_mapping = self.mapping_panel.get_mapping()
            mapping = {k: SMUGUI.c2i(v) for k, v in raw_mapping.items()}
            
            try:
                st_row = int(self.edit_start_row.text())
            except:
                st_row = 3

            # 테이블 데이터 스냅샷 생성 (파일명 기준)
            table_dict = {}
            for r in range(self.table.rowCount()):
                fn_item = self.table.item(r, 7) # 파일명 (7번 열)
                if fn_item:
                    fn = fn_item.text().strip()
                    table_dict[fn] = {
                        "no": self.table.item(r, 1).text().strip() if self.table.item(r, 1) else "",
                        "product_name": self.table.item(r, 2).text().strip() if self.table.item(r, 2) else "",
                        "cas_sum": self.table.item(r, 3).text().strip() if self.table.item(r, 3) else "",
                        "measure": self.table.item(r, 4).text().strip() if self.table.item(r, 4) else "",
                        "reg2": self.table.item(r, 5).text().strip() if self.table.item(r, 5) else "",
                        "reg1": self.table.item(r, 6).text().strip() if self.table.item(r, 6) else ""
                    }

            # 데이터 기입 (순차적 저장)
            saved_count = 0
            for row_idx in range(self.table.rowCount()):
                fn_item = self.table.item(row_idx, 7) # 파일명 (7번 열)
                if not fn_item: continue
                fn = fn_item.text().strip()
                
                if fn not in table_dict:
                    continue
                
                td = table_dict[fn]
                curr_row = st_row + saved_count # 시각적 순서대로 연속된 행에 기록
                
                # [V12.7] 매핑된 모든 컬럼에 데이터 기입 (유연한 확장)
                for key, c_idx in mapping.items():
                    if not c_idx or c_idx < 1: continue
                    
                    val = None
                    if key == "제품명": val = td.get("product_name")
                    elif key == "파일명": val = fn
                    elif key == "CAS 원본": val = td.get("cas_sum")
                    elif key == "측정대상1" or key == "측정대상2": val = td.get("measure")
                    elif key == "2차 결과(규제)": val = td.get("reg2")
                    elif key == "1차 결과(전체)": val = td.get("reg1")
                    elif key == "순번/No": val = td.get("no")
                    
                    if val is not None:
                        ws.Cells(curr_row, c_idx).Value = val

                saved_count += 1

            wb.Save()
            wb.Close()
            excel.Quit()
            self.log(f"[*] 저장 완료: 총 {saved_count}건의 데이터가 엑셀({sheet_name})에 반영되었습니다.")
            QMessageBox.information(self, "저장 완료", f"총 {saved_count}건의 데이터가 성공적으로 저장되었습니다.")
            
        except Exception as e:
            self.log(f"[!] 저장 중 오류 발생: {e}")
            if excel:
                try: excel.Quit()
                except: pass
            QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다: {e}")
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
