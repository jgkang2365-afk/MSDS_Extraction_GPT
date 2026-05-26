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
    QStackedWidget, QToolButton, QSizePolicy, QMenu, QDialog,
    QButtonGroup, QRadioButton, QAbstractItemView
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


# [Part 1.5] 세부 성상 선택 팝업 다이얼로그 (1:N 매칭 제어용)
class SubstanceSelectDialog(QDialog):
    def __init__(self, title, name, cas, content, candidates, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.selected_code = None
        self.selected_entry = None
        self.candidates = candidates
        
        # 메인 레이아웃 구성
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # 상세 안내 정보 라벨
        info_text = f"성분명: {name}\nCAS 번호: {cas}\n함유량: {content if content else '미기재%'}\n\n아래의 상세 성상 목록 중 수집 대상 물질을 선택해 주세요:"
        lbl_info = QLabel(info_text)
        lbl_info.setStyleSheet("font-family: 'Malgun Gothic'; font-size: 10pt; font-weight: bold; color: #222222; line-height: 140%;")
        layout.addWidget(lbl_info)
        
        # 후보 목록 그룹박스
        group_box = QGroupBox("매칭 후보 물질 목록")
        group_box.setStyleSheet("QGroupBox { font-family: 'Malgun Gothic'; font-weight: bold; color: #555; }")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(10, 15, 10, 10)
        group_layout.setSpacing(8)
        
        self.group = QButtonGroup(self)
        self.radio_buttons = []
        
        for idx, cand in enumerate(candidates):
            m_name = cand.get("측정대상 물질명") or ""
            twa = cand.get("노출기준(TWA)", "") or "-"
            stel = cand.get("노출기준(STEL)", "") or "-"
            display_text = f"{m_name} [TWA: {twa} / STEL: {stel}]"
            
            radio = QRadioButton(display_text)
            radio.setStyleSheet("QRadioButton { font-family: 'Malgun Gothic'; font-size: 9.5pt; padding: 2px; } QRadioButton::indicator { width: 16px; height: 16px; }")
            if idx == 0:
                radio.setChecked(True)
            group_layout.addWidget(radio)
            self.group.addButton(radio, idx)
            self.radio_buttons.append((radio, cand.get("정렬코드"), cand))
            
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        
        # 확인 / 취소 버튼 박스
        btn_layout = QHBoxLayout()
        btn_apply = QPushButton("적용")
        btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8;
                color: white;
                font-family: 'Malgun Gothic';
                font-size: 9.5pt;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #1557b0;
            }
        """)
        btn_apply.clicked.connect(self.accept)
        
        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #f1f3f4;
                color: #3c4043;
                font-family: 'Malgun Gothic';
                font-size: 9.5pt;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #e8eaed;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_apply)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        self.setMinimumWidth(450)
        
    def get_selected_data(self):
        idx = self.group.checkedId()
        if idx != -1:
            return self.radio_buttons[idx][1], self.radio_buttons[idx][2]
        return None, None


# [Part 1.6] 물질명 오타 교정 다이얼로그 (사용자 직접 편집 가능)
class SubstanceCorrectionDialog(QDialog):
    """표준 마스터에 없는 물질명이 감지될 때 표시되는 교정 다이얼로그.
    사용자가 추천안을 선택하거나 직접 입력하여 교정할 수 있음."""
    
    # 반환 코드 상수 정의
    RESULT_APPLY = 1       # 교정 적용
    RESULT_SKIP = 2        # 건너뛰기
    RESULT_ALL_APPLY = 3   # 이후 모두 교정
    RESULT_ALL_SKIP = 4    # 이후 모두 건너뛰기
    
    def __init__(self, row_num, detected_name, suggestions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("물질명 오타 교정 제안")
        self.setModal(True)
        self.result_action = self.RESULT_SKIP
        self.corrected_name = detected_name
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # 안내 라벨
        lbl_info = QLabel(f"[행 {row_num}] 표준 마스터 리스트에 없는 물질명이 감지되었습니다.")
        lbl_info.setStyleSheet("font-family: 'Malgun Gothic'; font-size: 10pt; font-weight: bold; color: #d32f2f;")
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)
        
        # 감지된 명칭 표시
        lbl_detected = QLabel(f"감지된 명칭: <span style='color: #1a73e8; font-weight: bold;'>{detected_name}</span>")
        lbl_detected.setStyleSheet("font-family: 'Malgun Gothic'; font-size: 10pt; color: #222222;")
        layout.addWidget(lbl_detected)
        
        # 교정 입력 필드 (사용자가 직접 편집 가능)
        lbl_edit = QLabel("교정할 물질명 (직접 수정 가능):")
        lbl_edit.setStyleSheet("font-family: 'Malgun Gothic'; font-size: 9.5pt; color: #555;")
        layout.addWidget(lbl_edit)
        
        self.edit_name = QLineEdit()
        self.edit_name.setText(suggestions[0] if suggestions else detected_name)
        self.edit_name.setStyleSheet("""
            QLineEdit {
                font-family: 'Malgun Gothic'; font-size: 10pt;
                padding: 6px 10px; border: 2px solid #1a73e8;
                border-radius: 4px; background-color: #fff;
            }
            QLineEdit:focus { border-color: #0d47a1; }
        """)
        layout.addWidget(self.edit_name)
        
        # 추천 교정안 목록 (클릭 시 edit_name에 자동 반영)
        if suggestions:
            lbl_suggest = QLabel("추천 교정안 (클릭하면 위 입력란에 반영):")
            lbl_suggest.setStyleSheet("font-family: 'Malgun Gothic'; font-size: 9pt; color: #777;")
            layout.addWidget(lbl_suggest)
            
            for sug in suggestions:
                btn_sug = QPushButton(f"  → {sug}")
                btn_sug.setCursor(QCursor(Qt.PointingHandCursor))
                btn_sug.setStyleSheet("""
                    QPushButton {
                        text-align: left; font-family: 'Malgun Gothic'; font-size: 9.5pt;
                        color: #1a73e8; background: transparent; border: 1px solid #e0e0e0;
                        border-radius: 3px; padding: 4px 8px;
                    }
                    QPushButton:hover { background-color: #e8f0fe; border-color: #1a73e8; }
                """)
                btn_sug.clicked.connect(lambda checked, s=sug: self.edit_name.setText(s))
                btn_sug.installEventFilter(self)
                btn_sug.setProperty("sug_name", sug)
                layout.addWidget(btn_sug)
        
        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #e0e0e0;")
        layout.addWidget(line)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        btn_apply = QPushButton("교정 적용")
        btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: white;
                font-family: 'Malgun Gothic'; font-size: 9.5pt; font-weight: bold;
                border-radius: 4px; padding: 6px 16px;
            }
            QPushButton:hover { background-color: #1557b0; }
        """)
        btn_apply.clicked.connect(self._on_apply)
        
        btn_skip = QPushButton("건너뛰기")
        btn_skip.setStyleSheet("""
            QPushButton {
                background-color: #f1f3f4; color: #3c4043;
                font-family: 'Malgun Gothic'; font-size: 9.5pt;
                border-radius: 4px; padding: 6px 16px;
            }
            QPushButton:hover { background-color: #e8eaed; }
        """)
        btn_skip.clicked.connect(self._on_skip)
        
        btn_all_apply = QPushButton("이후 모두 교정")
        btn_all_apply.setStyleSheet("""
            QPushButton {
                background-color: #e8f5e9; color: #2e7d32;
                font-family: 'Malgun Gothic'; font-size: 9pt;
                border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background-color: #c8e6c9; }
        """)
        btn_all_apply.clicked.connect(self._on_all_apply)
        
        btn_all_skip = QPushButton("이후 모두 건너뛰기")
        btn_all_skip.setStyleSheet("""
            QPushButton {
                background-color: #fff3e0; color: #e65100;
                font-family: 'Malgun Gothic'; font-size: 9pt;
                border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background-color: #ffe0b2; }
        """)
        btn_all_skip.clicked.connect(self._on_all_skip)
        
        btn_layout.addWidget(btn_apply)
        btn_layout.addWidget(btn_skip)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_all_apply)
        btn_layout.addWidget(btn_all_skip)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        self.setMinimumWidth(500)
    
    def _on_apply(self):
        self.corrected_name = self.edit_name.text().strip()
        self.result_action = self.RESULT_APPLY
        self.accept()
    
    def _on_skip(self):
        self.result_action = self.RESULT_SKIP
        self.accept()
    
    def _on_all_apply(self):
        self.corrected_name = self.edit_name.text().strip()
        self.result_action = self.RESULT_ALL_APPLY
        self.accept()
    
    def _on_all_skip(self):
        self.result_action = self.RESULT_ALL_SKIP
        self.accept()
    
    def eventFilter(self, obj, event):
        """추천 버튼 더블클릭 시 즉시 교정 적용"""
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.MouseButtonDblClick and isinstance(obj, QPushButton):
            sug_name = obj.property("sug_name")
            if sug_name:
                self.edit_name.setText(sug_name)
                self._on_apply()
                return True
        return super().eventFilter(obj, event)


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
        # [V17.3.2.11] 동일 파일 중복 로드 방지 (스크롤 튐 현상 해결)
        if self.current_pdf_path == file_path:
            return

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
        if index.column() in [3, 4, 5, 6]: # [V17.3.1.1] CAS, 측정대상, 1/2차 결과 모두 멀티라인 편집 지원
            editor = QTextEdit(parent)
            editor.setAcceptRichText(False)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() in [3, 4, 5, 6]:
            value = index.model().data(index, Qt.EditRole)
            editor.setPlainText(str(value))
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() in [3, 4, 5, 6]:
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
        
        # [V17.3.1.1] 주님 지침 반영: 가로 흐름 대신 수직 개행(;<br>)을 사용하여 성분별 가독성 극대화
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
                
                # [V17.2.9.9] 캐시 체크 로직 강화: 파일 해시 + 엔진 버전 동기화 확인
                if f_hash and getattr(self, 'cache', None) and f_hash in self.cache:
                    cached_data = self.cache[f_hash]
                    manual = cached_data.get("manual_data", {})
                    cached_version = cached_data.get("engine_version", "unknown")
                    
                    # [핵심] 버전이 다르거나, 수동 데이터가 없는데 AI 결과가 불완전한 경우 재추출
                    use_cache = True
                    if cached_version != engine.VERSION:
                        self.update_log_signal.emit(f"[*] [{fn}] 엔진 버전 변경 감지 ({cached_version} -> {engine.VERSION}): 재추출을 수행합니다.")
                        use_cache = False
                    elif not manual and (cached_data.get("product_name") == "제품명 확인 필요" or "오류" in cached_data.get("status", "")):
                        self.update_log_signal.emit(f"[*] [{fn}] 불완전한 추출 결과 감지: API 재호출을 시도합니다.")
                        use_cache = False
                    # 🚨 [V17.3.3.3] 사용자 요청(공란) 감지: 제품명이나 CAS 원본이 비어있으면 강제 재추출
                    elif manual.get("product_name") == "" or manual.get("raw_content") == "":
                        self.update_log_signal.emit(f"[*] [{fn}] 사용자 요청(공란) 감지: 강제 재추출을 수행합니다.")
                        use_cache = False
                    
                    if use_cache:
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
                    "used_engine": ext_res.get("used_engine", "regex"),
                    "engine_version": engine.VERSION # [V17.2.9.9] 버전 낙인 찍기
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
                    
                    # [버그 수정] 캐시된 성분 목록 로드 및 함유량 강제 복원
                    cached_comps = self.parent_gui.cache.get(f_hash, {}).get("components", [])
                    if cached_comps:
                        for c in cached_comps:
                            cas = c.get("cas", "")
                            if cas in cas_to_content:
                                c["content"] = cas_to_content[cas]
                                
                    # [버그 수정] 복원된 성분 정보를 기반으로 1차/2차 규제 및 측정대상을 실시간으로 완벽 재구성
                    if cached_comps:
                        new_res1, new_res2, new_work = self.parent_gui.regenerate_validation_results(cached_comps)
                        val_res = {
                            "res_1st": new_res1,
                            "res_2nd": new_res2,
                            "work_subjects": new_work,
                            "cas_with_content": str(cas_content).split("; ") if cas_content else []
                        }
                    else:
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
                        "components": cached_comps,
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
                    c["content"] = range_val
                    
                    # [V27.5 영문명/기호 완벽 보존 로직 복제]
                    # [V15.8.18 수정] 과도한 명칭 훼손 방지 (글로벌 명칭 및 모델명, 공백 보존)
                    if re.search(r'[가-힣]', name):
                        # 괄호 안의 영문을 지우되, (주), (사) 같은 회사명이나 필수 기호는 보존
                        name_no_eng = re.sub(r'\s*\([A-Za-z\s\d,]+\)$', '', name)
                        clean_name = name_no_eng.strip() # replace(" ", "") 절대 금지! 공백 보존!
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
                        fallback_name = mes_entry.get("측정대상 물질명")
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

                    # [V17.3.2.18] 함량 누락 시 '미기재%' 표시 형식 통합
                    if not range_val or str(range_val).strip() == "":
                        range_val = "미기재%"
                    c_str = f"({range_val})"
                    
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
                            res_work_subjects.append(f"{clean_name}({range_val})")
                        else:
                            res_work_non_subjects.append(f"{clean_name}({range_val})")

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
                    "components": raw_val_res.get("components", []),
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
        """저장된 데이터를 바탕으로 매핑 입력창을 채움 (안전 폴백 포함)"""
        default_map = {
            "순번/No": "A", "제품명": "D", "파일명": "P",
            "2차 결과(규제)": "L", "1차 결과(전체)": "N",
            "측정대상1": "M", "측정대상2": "",
            "CAS 원본": "O",
            "공정명": "B", "제조/사용": "C",
            "사용용도": "E", "월취급량": "S", "단위": "T"
        }
        if not data:
            data = default_map
        for k, default_v in default_map.items():
            if k in self.inputs:
                v = data.get(k, "")
                if v is None or str(v).strip() == "":
                    v = default_v
                self.inputs[k].setText(v)


class MeasurePlanMappingPanel(QGroupBox):
    # 측정계획 수립 전용 동적 열 매핑 패널
    def __init__(self, title="측정계획 수립용 열 매핑 설정"):
        super().__init__(title)
        self.inputs = {}
        layout = QGridLayout()
        layout.setContentsMargins(15, 20, 15, 10)
        layout.setHorizontalSpacing(15)
        layout.setVerticalSpacing(10)

        # 측정계획 수립에 필요한 핵심 열들 (내부 키값, UI 표시명, 기본값)
        fields = [
            ("공정명 열", "공정명 열 (측정대상 과/공정)", "B"),
            ("화학물질명 열", "화학물질명 열 (측정대상 유해인자)", "C"),
            ("일련번호 수 열", "근로자수 열 (일련번호 수)", "D"),
            ("번호코드 열(F)", "번호코드 열 (근로자명)", "F"),
            ("번호코드 열(G)", "번호코드 열 (장비번호)", "G"),
            ("노출기준 L값 열", "측정매체(실무용) 열", "I"),
            ("노출기준 E값 열", "유량 열", "J"),
            ("분석방법 열", "분석방법 열 (분석방법)", "K"),
            ("병합 대상 열", "병합 대상 열", "D, E, F, G, M"),
            ("현황 공정명 열", "현황 공정명 열 (제조/사용)", "C"),
            ("현황 화학물질명 열", "현황 화학물질명 열 (비고)", "I")
        ]

        for idx, (key, display_name, default) in enumerate(fields):
            row = idx // 3
            col_base = (idx % 3) * 2
            
            lbl = QLabel(display_name)
            lbl.setStyleSheet("font-weight: bold; color: #444; min-width: 100px;")
            layout.addWidget(lbl, row, col_base, Qt.AlignRight)
            
            edit = QLineEdit(default)
            # 병합 대상 열의 경우 쉼표 구분 목록이므로 너비를 넓게 잡음
            if key == "병합 대상 열":
                edit.setFixedWidth(120)
            else:
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
            layout.addWidget(edit, row, col_base + 1, Qt.AlignLeft)
            self.inputs[key] = edit
            
        layout.setColumnStretch(6, 1)
        layout.setRowStretch((len(fields) + 2) // 3, 1)
        self.setLayout(layout)

    def get_mapping(self):
        return {k: v.text().strip() for k, v in self.inputs.items()}

    def set_mapping(self, data):
        # 데이터 유실 방지를 위한 기본값 폴백 매핑
        default_map = {
            "공정명 열": "B",
            "화학물질명 열": "C",
            "일련번호 수 열": "D",
            "번호코드 열(F)": "F",
            "번호코드 열(G)": "G",
            "노출기준 L값 열": "I",
            "노출기준 E값 열": "J",
            "분석방법 열": "K",
            "병합 대상 열": "D, E, F, G, M",
            "현황 공정명 열": "C",
            "현황 화학물질명 열": "I"
        }
        if not data:
            data = default_map
        for k, default_v in default_map.items():
            if k in self.inputs:
                v = data.get(k, "")
                if v is None or str(v).strip() == "":
                    v = default_v
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
        self.last_selected_row = -1 # [NEW] 동일 행 내 열 이동 시 미리보기 초기화 방지용
        self.init_ui()
        
        # [V7.5] 동기화 무결성 확보를 위한 초기화 순서 재배치
        self.load_cache() # 1. 캐시 먼저 로드
        self.load_config() # 2. 그 다음 설정 로드 (setText 발생 시 시그널 즉시 발동)
        self.load_mes_master() # [NEW] MES 마스터 데이터셋 구축
        self.showMaximized()
        
        # [NEW] 세션 복구: 이전 파일 목록을 테이블에 복원
        self.restore_table_from_session()

    def load_mes_master(self):
        """[Master 지시서] msds_index.json을 마스터 데이터셋으로 구축"""
        self.mes_master_list = [] # 전체 리스트
        self.mes_cas_map = {}     # CAS 번호 기반 조회 맵
        
        mes_file = "msds_index.json"
        if not os.path.exists(mes_file):
            self.log(f"[!] {mes_file} 파일을 찾을 수 없습니다. 마스터 데이터셋을 생략합니다.")
            return

        try:
            with open(mes_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.mes_master_list = data
            
            for entry in data:
                # msds_index.json에서 "CAS No." 필드를 가져옴
                cas_key = str(entry.get("CAS No.", "")).strip()
                if cas_key and cas_key.lower() != 'nan' and re.match(r'^\d{2,7}-\d{2}-\d$', cas_key):
                    # 중복 CAS가 있다면 최초 발견된 표준 우선 사용
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
            ("화학물질 정리", "[CLEAN]", 1),
            ("측정계획 수립", "[PLAN]", 3),
            ("환경 설정", "[SET]", 2)
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
        elif idx == 1: # 화학물질 정리 탭
            self._update_substance_clean_info()
        elif idx == 3: # 측정계획 수립 탭
            self._update_measure_plan_info()

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
        log_header.setStyleSheet("background-color: #eee; border: none;")
        log_h_layout = QHBoxLayout(log_header)
        log_h_layout.setContentsMargins(10, 0, 10, 0)
        
        lbl_log = QLabel("작업 모니터링 로그")
        lbl_log.setStyleSheet("font-size: 11px; font-weight: bold; color: #666;")
        log_h_layout.addWidget(lbl_log)
        
        # [NEW] 진행 상황 텍스트 표시 라벨
        self.lbl_extraction_progress = QLabel("")
        self.lbl_extraction_progress.setStyleSheet("font-size: 11px; font-weight: bold; color: #0078d4; margin-left: 15px;")
        log_h_layout.addWidget(self.lbl_extraction_progress)
        
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
        """[V17.4.0.2] 지능형 시스템 로그 출력: 사용자가 검토 중일 땐 스크롤 고정"""
        if hasattr(self, 'log_view'):
            # 1. 현재 스크롤바 상태 확인 (최하단 여부)
            v_bar = self.log_view.verticalScrollBar()
            is_at_bottom = v_bar.value() >= v_bar.maximum() - 10 # 약간의 마진 허용
            
            # 2. 로그 추가
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_view.append(f"[{timestamp}] {message}")
            
            # 3. 조건부 자동 스크롤: 최하단에 있었을 때만 화면을 내림
            if is_at_bottom:
                self.log_view.ensureCursorVisible()
            
        # [무결점] 터미널 출력 시 cp949 인코딩 오류 방지 (이모지 필터링 및 텍스트 태그 변환)
        try:
            # 터미널용 텍스트 변환 맵
            tag_map = {
                "🚀": "[START]", "✅": "[OK]", "❌": "[FAIL]", 
                "⚠️": "[WARN]", "🎯": "[TARGET]", "🔍": "[SEARCH]",
                "🟢": "[PASS]", "🟡": "[CHECK]", "🔴": "[ERROR]", "🔵": "[INFO]"
            }
            terminal_msg = str(message)
            for emoji, tag in tag_map.items():
                terminal_msg = terminal_msg.replace(emoji, tag)
            
            safe_msg = terminal_msg.encode('cp949', errors='replace').decode('cp949')
            print(f"[*] {safe_msg}")
        except:
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
        # [V15.8.15] 로그창과 테이블 경계 시인성 강화를 위한 프리미엄 블루 디바이더 이식
        self.main_splitter.setStyleSheet(f"""
            QSplitter::handle:vertical {{
                height: 3px;
                background-color: {PRIMARY_BLUE};
            }}
            QSplitter::handle:vertical:hover {{
                background-color: #0078d4;
            }}
        """)
        self.content_layout.addWidget(self.main_splitter)

        self.stacked_widget = QStackedWidget()
        self.main_splitter.addWidget(self.stacked_widget)

        # 페이지 0: 기존 주 화면
        self.page_extraction = self._create_extraction_page()
        self.stacked_widget.addWidget(self.page_extraction)

        # 페이지 1: 화학물질 정리
        self.page_substance_clean = self._create_substance_clean_page()
        self.stacked_widget.addWidget(self.page_substance_clean)

        # 페이지 2: 환경 설정
        self.page_settings = self._create_settings_page()
        self.stacked_widget.addWidget(self.page_settings)

        # 페이지 3: 측정계획 수립
        self.page_measure_plan = self._create_measure_plan_page()
        self.stacked_widget.addWidget(self.page_measure_plan)

        # 3. 로그 창
        self._setup_log_section()

    def _create_settings_page(self):
        """[페이지 2] 데이터 맵핑 및 보조 관리 도구를 모은 환경 설정 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # 1. 컬럼 매핑 설정 영역
        map_group = QGroupBox("데이터 열 매핑 설정 (엑셀 컬럼 지정)")
        map_layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(400)
        
        # 내부 컨테이너 위젯과 레이아웃 생성
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(0, 0, 0, 0)
        scroll_content_layout.setSpacing(15)
        
        # 가로형 수집용 매핑 패널 추가
        self.mapping_panel = ModernMappingPanel()
        scroll_content_layout.addWidget(self.mapping_panel)
        
        # 측정계획 수립용 매핑 패널 추가
        self.measure_mapping_panel = MeasurePlanMappingPanel()
        scroll_content_layout.addWidget(self.measure_mapping_panel)
        
        # 자동 백업 설정 그룹박스 추가
        backup_group = QGroupBox("측정계획 자동 백업 설정")
        backup_layout = QGridLayout()
        backup_layout.setContentsMargins(15, 15, 15, 15)
        backup_layout.setSpacing(10)
        
        backup_layout.addWidget(QLabel("백업 저장 경로:"), 0, 0)
        self.edit_backup_path = QLineEdit("")
        self.edit_backup_path.setPlaceholderText("백업 파일이 저장될 폴더 경로를 지정해 주세요. (미지정 시 백업 생략)")
        backup_layout.addWidget(self.edit_backup_path, 0, 1)
        
        btn_browse_backup = QPushButton("찾아보기")
        btn_browse_backup.setFixedWidth(80)
        btn_browse_backup.clicked.connect(self.browse_backup_path)
        backup_layout.addWidget(btn_browse_backup, 0, 2)
        
        backup_group.setLayout(backup_layout)
        scroll_content_layout.addWidget(backup_group)
        
        scroll_content_layout.addStretch()
        scroll.setWidget(scroll_content)
        
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

    def _create_substance_clean_page(self):
        """[페이지 1] 화학물질 정리 및 교정 제어 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # 1. 헤더 카드 (기업 스타일)
        header_card = QFrame()
        header_card.setStyleSheet(f"background-color: {LIGHT_BLUE}; border-radius: 8px; border: 1px solid {GRAY_BORDER};")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        title_label = QLabel("화학물질 정리 및 교정 도구")
        title_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {PRIMARY_BLUE};")
        desc_label = QLabel("엑셀 파일의 I열(비고)과 J열(MSDS) 내 기재된 화학물질들을 표준 마스터 정렬코드로 정렬하고,\n오타 등의 물질명을 대화식으로 자동 교정합니다. (미매칭 단어는 적색 표시)")
        desc_label.setStyleSheet(f"font-size: 12px; color: {TEXT_SUB}; line-height: 15px;")
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(desc_label)
        layout.addWidget(header_card)
        
        # 2. 정보 표시 카드
        info_group = QGroupBox("현재 연동 정보")
        info_layout = QGridLayout()
        
        lbl_file_title = QLabel("연동 대상 엑셀 파일:")
        lbl_file_title.setStyleSheet("font-weight: bold;")
        self.lbl_clean_excel_path = QLabel("선택된 파일 없음")
        self.lbl_clean_excel_path.setWordWrap(True)
        
        lbl_sheet_title = QLabel("연동 대상 시트명:")
        lbl_sheet_title.setStyleSheet("font-weight: bold;")
        self.combo_clean_sheet = QComboBox()
        self.combo_clean_sheet.setMinimumWidth(150)
        
        info_layout.addWidget(lbl_file_title, 0, 0)
        info_layout.addWidget(self.lbl_clean_excel_path, 0, 1)
        info_layout.addWidget(lbl_sheet_title, 1, 0)
        info_layout.addWidget(self.combo_clean_sheet, 1, 1)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # 3. 제어 영역
        control_layout = QHBoxLayout()
        self.btn_run_clean = QPushButton(" 정리 및 교정 실행")
        self.btn_run_clean.setFixedHeight(40)
        self.btn_run_clean.setStyleSheet(f"background-color: {PRIMARY_BLUE}; color: white; font-weight: bold; font-size: 13px; border-radius: 4px;")
        self.btn_run_clean.clicked.connect(self.clean_substances_excel)
        
        self.btn_open_excel = QPushButton(" 엑셀 파일 열기")
        self.btn_open_excel.setFixedHeight(40)
        self.btn_open_excel.setStyleSheet(f"background-color: #5cb85c; color: white; font-weight: bold; font-size: 13px; border-radius: 4px;")
        self.btn_open_excel.clicked.connect(self.open_current_excel)
        
        control_layout.addWidget(self.btn_run_clean)
        control_layout.addWidget(self.btn_open_excel)
        layout.addLayout(control_layout)
        
        # 4. 화학물질 마스터 DB 조회 및 관계 필터 영역
        search_group = QGroupBox("화학물질 마스터 DB 조회 및 관계 필터")
        search_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        search_layout = QVBoxLayout()
        
        # 검색 컨트롤 레이아웃
        filter_layout = QHBoxLayout()
        lbl_keyword = QLabel("조회 물질명/CAS:")
        lbl_keyword.setStyleSheet("font-weight: bold;")
        self.edit_search_keyword = QLineEdit()
        self.edit_search_keyword.setPlaceholderText("검색할 물질명 또는 CAS 번호를 입력하세요 (예: 바륨, 7440-39-3)")
        self.edit_search_keyword.setStyleSheet("""
            QLineEdit {
                font-family: 'Malgun Gothic'; font-size: 10pt;
                padding: 4px 8px; border: 1px solid #ccc;
                border-radius: 4px; background-color: #fff;
            }
        """)
        self.edit_search_keyword.returnPressed.connect(self.search_substance_db)
        
        self.btn_search_substance = QPushButton("조회")
        self.btn_search_substance.setStyleSheet(f"background-color: {PRIMARY_BLUE}; color: white; font-weight: bold; padding: 4px 12px; border-radius: 4px;")
        self.btn_search_substance.clicked.connect(self.search_substance_db)
        
        filter_layout.addWidget(lbl_keyword)
        filter_layout.addWidget(self.edit_search_keyword)
        filter_layout.addWidget(self.btn_search_substance)
        search_layout.addLayout(filter_layout)
        
        # 결과 표시 테이블
        self.tbl_search_results = QTableWidget()
        self.tbl_search_results.setColumnCount(6)
        self.tbl_search_results.setHorizontalHeaderLabels(["정렬코드", "측정대상 물질명", "CAS No.", "노출기준(TWA)", "관계 유형", "상세 성상 정보"])
        self.tbl_search_results.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_search_results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_search_results.setStyleSheet("""
            QTableWidget {
                font-family: 'Malgun Gothic'; font-size: 9.5pt;
                gridline-color: #e0e0e0; background-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #f5f5f5; font-weight: bold;
                border: 1px solid #e0e0e0; padding: 4px;
            }
        """)
        search_layout.addWidget(self.tbl_search_results)
        
        search_group.setLayout(search_layout)
        layout.addWidget(search_group)
        
        return page

    def _create_measure_plan_page(self):
        """[페이지 3] 측정계획 수립 핵심 기능 제어 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # 1. 헤더 카드 (기업 스타일)
        header_card = QFrame()
        header_card.setStyleSheet(f"background-color: {LIGHT_BLUE}; border-radius: 8px; border: 1px solid {GRAY_BORDER};")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        title_label = QLabel("측정계획 수립 및 제어 도구")
        title_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {PRIMARY_BLUE};")
        desc_label = QLabel("측정계획(양식) 시트의 공정명과 물질명을 기반으로 매체를 업데이트하고,\n"
                            "셀 병합 및 번호 자동 부여 워크플로우를 실행하여 최종 양식을 완성합니다.")
        desc_label.setStyleSheet(f"font-size: 12px; color: {TEXT_SUB}; line-height: 15px;")
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(desc_label)
        layout.addWidget(header_card)
        
        # 2. 정보 표시 카드
        info_group = QGroupBox("현재 연동 정보")
        info_layout = QGridLayout()
        
        lbl_file_title = QLabel("연동 대상 엑셀 파일:")
        lbl_file_title.setStyleSheet("font-weight: bold;")
        self.lbl_measure_excel_path = QLabel("선택된 파일 없음")
        self.lbl_measure_excel_path.setWordWrap(True)
        
        lbl_sheet_title = QLabel("연동 대상 시트명:")
        lbl_sheet_title.setStyleSheet("font-weight: bold;")
        self.combo_measure_sheet = QComboBox()
        self.combo_measure_sheet.setMinimumWidth(150)
        
        info_layout.addWidget(lbl_file_title, 0, 0)
        info_layout.addWidget(self.lbl_measure_excel_path, 0, 1)
        info_layout.addWidget(lbl_sheet_title, 1, 0)
        info_layout.addWidget(self.combo_measure_sheet, 1, 1)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # 3. 제어 영역 (5대 핵심 버튼)
        control_layout = QHBoxLayout()
        
        self.btn_measure_import = QPushButton(" 현황 데이터 반영")
        self.btn_measure_import.setFixedHeight(40)
        self.btn_measure_import.setStyleSheet("background-color: #17a2b8; color: white; font-weight: bold; font-size: 13px; border-radius: 4px;")
        self.btn_measure_import.clicked.connect(self.measure_plan_import_slot)
        
        self.btn_measure_update = QPushButton(" 매체 업데이트")
        self.btn_measure_update.setFixedHeight(40)
        self.btn_measure_update.setStyleSheet(f"background-color: {PRIMARY_BLUE}; color: white; font-weight: bold; font-size: 13px; border-radius: 4px;")
        self.btn_measure_update.clicked.connect(self.measure_plan_update_slot)
        
        self.btn_measure_workflow = QPushButton(" 워크플로우 실행")
        self.btn_measure_workflow.setFixedHeight(40)
        self.btn_measure_workflow.setStyleSheet("background-color: #e6a23c; color: white; font-weight: bold; font-size: 13px; border-radius: 4px;")
        self.btn_measure_workflow.clicked.connect(self.measure_plan_workflow_slot)
        
        self.btn_measure_reset = QPushButton(" 초기화")
        self.btn_measure_reset.setFixedHeight(40)
        self.btn_measure_reset.setStyleSheet("background-color: #f56c6c; color: white; font-weight: bold; font-size: 13px; border-radius: 4px;")
        self.btn_measure_reset.clicked.connect(self.measure_plan_reset_slot)
        
        self.btn_measure_survey = QPushButton(" 예비조사 데이터 취합")
        self.btn_measure_survey.setFixedHeight(40)
        self.btn_measure_survey.setStyleSheet("background-color: #67c23a; color: white; font-weight: bold; font-size: 13px; border-radius: 4px;")
        self.btn_measure_survey.clicked.connect(self.measure_plan_survey_slot)
        
        control_layout.addWidget(self.btn_measure_import)
        control_layout.addWidget(self.btn_measure_update)
        control_layout.addWidget(self.btn_measure_workflow)
        control_layout.addWidget(self.btn_measure_reset)
        control_layout.addWidget(self.btn_measure_survey)
        layout.addLayout(control_layout)
        
        # 4. 모니터링 로그 기록 영역
        log_group = QGroupBox("측정계획 수립 로그")
        log_layout = QVBoxLayout()
        self.txt_measure_log = QTextEdit()
        self.txt_measure_log.setReadOnly(True)
        self.txt_measure_log.setStyleSheet("background-color: #222222; color: #00FF00; font-family: 'Consolas'; font-size: 11px;")
        
        # 헬퍼 함수 2: 미분류 유해인자 그룹화 및 중복 제거 (대괄호/접두사 제거 및 비정상 괄호 자동 세척, 중복 제거 보강)
        def format_grouped_chems(chem_list_str, active_chems=None):
            if active_chems is None:
                active_chems = set()
            if not chem_list_str or chem_list_str.strip() == "":
                return "-"
                
            # 물질명 정제 헬퍼 함수
            def clean_chem_name(name):
                if not name:
                    return ""
                # 1. 특별, 특검, 허가 수식어 대괄호 제거
                name = re.sub(r'\[특별\]|\[특검\]|\[허가\]', '', name).strip()
                # 2. 겉에 씌워진 불완전 대괄호 제거
                name = name.replace("[", "").replace("]", "").strip()
                # 3. 소괄호 짝 밸런싱 세척
                open_p = name.count("(")
                close_p = name.count(")")
                if open_p > close_p:
                    name += ")" * (open_p - close_p)
                elif close_p > open_p:
                    name = "(" * (close_p - open_p) + name
                return name.strip()

            protected = process_special_patterns(chem_list_str)
            items = [x.strip() for x in protected.split(";") if x.strip()]
            
            groups = {}
            for item in items:
                item = item.replace('\u0001', ';').strip()
                if not item:
                    continue
                matched_prefix = None
                for prefix in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
                    if item.startswith(prefix):
                        matched_prefix = prefix
                        break
                        
                if matched_prefix:
                    inner = item[len(matched_prefix):].strip()
                    if inner.startswith("[") and inner.endswith("]"):
                        inner = inner[1:-1].strip()
                    elif inner.startswith("(") and inner.endswith(")"):
                        inner = inner[1:-1].strip()
                        
                    sub_parts = [x.strip() for x in inner.split(";") if x.strip()]
                    if matched_prefix not in groups:
                        groups[matched_prefix] = []
                    for sp in sub_parts:
                        cleaned_sp = clean_chem_name(sp)
                        # 활성 측정대상 물질명과 중복되면 제외 목록에서 누락
                        if cleaned_sp in active_chems:
                            continue
                        if cleaned_sp and cleaned_sp not in groups[matched_prefix]:
                            groups[matched_prefix].append(cleaned_sp)
                else:
                    cleaned_item = clean_chem_name(item)
                    if cleaned_item in active_chems:
                        continue
                    if cleaned_item:
                        if "기타" not in groups:
                            groups["기타"] = []
                        if cleaned_item not in groups["기타"]:
                            groups["기타"].append(cleaned_item)
        
        log_layout.addWidget(self.txt_measure_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        return page

    def _update_measure_plan_info(self):
        """환경 설정에서 연동된 엑셀 파일 및 시트명 갱신"""
        path = self.edit_excel.text().strip()
        
        if path:
            self.lbl_measure_excel_path.setText(path)
            if self.combo_measure_sheet.count() == 0:
                self._update_sheet_list(path)
        else:
            self.lbl_measure_excel_path.setText("환경 설정에서 결과를 저장할 엑셀 파일을 선택하세요.")

    def browse_backup_path(self):
        """자동 백업 경로 찾아보기 다이얼로그"""
        folder = QFileDialog.getExistingDirectory(self, "백업 파일 저장 폴더 선택")
        if folder:
            self.edit_backup_path.setText(os.path.normpath(folder).replace('\\', '/'))
            self.save_config()

    def measure_plan_log(self, text):
        """측정계획 수립 진행 로그 출력"""
        self.txt_measure_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")
        self.txt_measure_log.moveCursor(QTextCursor.End)
        QApplication.processEvents()

    def run_backup_engine(self, file_path):
        """작업 시작 전 지정 폴더에 안전 백업본 생성"""
        backup_dir = self.edit_backup_path.text().strip()
        if not backup_dir or not os.path.exists(backup_dir):
            self.measure_plan_log("⚠️ 자동 백업 경로가 미지정되었거나 유효하지 않아 백업을 생략합니다.")
            return True
            
        if not os.path.exists(file_path):
            return True
            
        try:
            import shutil
            fn = os.path.basename(file_path)
            base, ext = os.path.splitext(fn)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_fn = f"{base}_백업_{timestamp}{ext}"
            backup_path = os.path.join(backup_dir, backup_fn)
            
            shutil.copy2(file_path, backup_path)
            self.measure_plan_log(f"✅ 백업본이 안전하게 저장되었습니다: {backup_fn}")
            return True
        except Exception as e:
            self.measure_plan_log(f"🔴 백업 생성 중 오류 발생: {e}")
            reply = QMessageBox.question(self, "백업 오류", 
                                         f"백업본을 만들지 못했습니다. 작업을 백업 없이 계속 진행할까요?\n사유: {e}",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            return reply == QMessageBox.Yes

    def measure_plan_import_slot(self):
        """[핵심 0] 화학물질 현황(화학물질입력_양식) 시트 데이터를 측정계획 시트에 최초 반영"""
        excel_path = self.edit_excel.text().strip()
        src_sheet_name = self.combo_clean_sheet.currentText().strip()
        
        if not excel_path or not os.path.exists(excel_path):
            QMessageBox.warning(self, "경고", "올바른 엑셀 경로를 지정해 주세요.")
            return
            
        if not src_sheet_name:
            src_sheet_name = "화학물질입력_양식"
            
        dest_sheet_name = self.combo_measure_sheet.currentText().strip() or "측정계획(양식)"
        
        # 1. 자동 백업 실행
        if not self.run_backup_engine(excel_path):
            self.measure_plan_log("🛑 사용자가 백업 실패 후 작업을 취소하였습니다.")
            return
            
        self.txt_measure_log.clear()
        self.measure_plan_log("🟢 화학물질 현황 최초 반영 작업 시작...")
        
        # 2. 마스터 데이터셋 구축 확인
        if not hasattr(self, 'mes_master_list') or not self.mes_master_list:
            self.measure_plan_log("[*] msds_index.json 마스터 데이터를 로드합니다...")
            self.load_mes_master()
            
        if not self.mes_master_list:
            QMessageBox.critical(self, "오류", "msds_index.json을 로드할 수 없어 작업을 진행할 수 없습니다.")
            return
            
        # 3. 마스터 데이터셋 구조화
        dictMethod = {}
        dictOrder = {}
        dictLValue = {}
        dictEValue = {}
        
        for idx, entry in enumerate(self.mes_master_list):
            chemName = str(entry.get("측정대상 물질명", "")).strip()
            if chemName:
                if chemName not in dictMethod:
                    dictMethod[chemName] = str(entry.get("분석방법", "")).strip()
                    dictOrder[chemName] = idx
                    # dictLValue는 측정매체(실무용)로 들어가며, dictEValue는 적정유속(유량)으로 들어감 (VBA 원래 로직 복구)
                    l_val = str(entry.get("매체(실무용)", "")).strip() or str(entry.get("매체", "")).strip()
                    dictLValue[chemName] = l_val
                    dictEValue[chemName] = str(entry.get("적정유속(L/min)", "")).strip()
                    
        # 4. 분석방법 우선순위 리스트 정의
        priorityList = [
            "누적소음계", "중량분석법", "중량분석법(호)", "중량분석법(흡)", "FTIR법(다)",
            "위상차현미경법", "중량분석법(단)", "ICP법(다)", "ICP법(다)호", "IC법(단)-금",
            "ICP법(단)흡", "ICP법(단)", "GC법(다)", "GC법(다)2", "GC법(다)3", "GC법(다)4",
            "GC법(다)5", "GC법(다)6", "GC법(다)7", "GC법(다)8", "GC법(단)", "HPLC법(다)",
            "HPLC법(다)2", "HPLC법(다)3", "HPLC법(다)4", "HPLC법(단)",
            "IC법(다)-산알", "IC법(다)2-산알", "UV법(다)", "IC법(단)-산알",
            "UV법(단)", "GC법(NPD)(단)", "IC법(다)3-가스", "IC법(단)-가스", "VIS(다)", "추출법",
            "GC법(단)-C", "HPLC법(단)-C", "ICP법(다)-C", "UV법(단)-C",
            "직독식", "WBGT"
        ]
        
        # 헬퍼 함수 1: 스페셜 패턴 처리 (괄호 안의 세미콜론 임시 치환)
        def process_special_patterns(text):
            if not text:
                return ""
            chars = list(text)
            in_paren = 0
            in_bracket = 0
            for i, ch in enumerate(chars):
                if ch == '(': in_paren += 1
                elif ch == ')': in_paren -= 1
                elif ch == '[': in_bracket += 1
                elif ch == ']': in_bracket -= 1
                elif ch == ';' and (in_paren > 0 or in_bracket > 0):
                    chars[i] = '\u0001'
            return "".join(chars)
            
        # 헬퍼 함수 2: 미분류 유해인자 그룹화 및 중복 제거 (대괄호/접두사 제거 및 비정상 괄호 자동 세척, 중복 제거 보강)
        def format_grouped_chems(chem_list_str, active_chems=None):
            if active_chems is None:
                active_chems = set()
            if not chem_list_str or chem_list_str.strip() == "":
                return "-"
                
            # 물질명 정제 헬퍼 함수
            def clean_chem_name(name):
                if not name:
                    return ""
                # 1. 특별, 특검, 허가 수식어 대괄호 제거
                name = re.sub(r'\[특별\]|\[특검\]|\[허가\]', '', name).strip()
                # 2. 겉에 씌워진 불완전 대괄호 제거
                name = name.replace("[", "").replace("]", "").strip()
                # 3. 소괄호 짝 밸런싱 세척
                open_p = name.count("(")
                close_p = name.count(")")
                if open_p > close_p:
                    name += ")" * (open_p - close_p)
                elif close_p > open_p:
                    name = "(" * (close_p - open_p) + name
                return name.strip()

            protected = process_special_patterns(chem_list_str)
            items = [x.strip() for x in protected.split(";") if x.strip()]
            
            groups = {}
            for item in items:
                item = item.replace('\u0001', ';').strip()
                if not item:
                    continue
                matched_prefix = None
                for prefix in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
                    if item.startswith(prefix):
                        matched_prefix = prefix
                        break
                        
                if matched_prefix:
                    inner = item[len(matched_prefix):].strip()
                    if inner.startswith("[") and inner.endswith("]"):
                        inner = inner[1:-1].strip()
                    elif inner.startswith("(") and inner.endswith(")"):
                        inner = inner[1:-1].strip()
                        
                    sub_parts = [x.strip() for x in inner.split(";") if x.strip()]
                    if matched_prefix not in groups:
                        groups[matched_prefix] = []
                    for sp in sub_parts:
                        cleaned_sp = clean_chem_name(sp)
                        # 활성 측정대상 물질명과 중복되면 제외 목록에서 누락
                        if cleaned_sp in active_chems:
                            continue
                        if cleaned_sp and cleaned_sp not in groups[matched_prefix]:
                            groups[matched_prefix].append(cleaned_sp)
                else:
                    cleaned_item = clean_chem_name(item)
                    if cleaned_item in active_chems:
                        continue
                    if cleaned_item:
                        if "기타" not in groups:
                            groups["기타"] = []
                        if cleaned_item not in groups["기타"]:
                            groups["기타"].append(cleaned_item)
                        
            # [V24.3.5.7] 제외사유별 수집된 물질들을 마스터 DB 정렬 키 기준으로 정렬
            def get_chem_sort_key(c):
                name_clean = re.sub(r'\[.*?\]|\(.*?\)', '', c).strip()
                if name_clean in dictOrder:
                    return dictOrder[name_clean]
                for m_name, idx in dictOrder.items():
                    if m_name in name_clean or name_clean in m_name:
                        return idx
                return 999999
                
            result_parts = []
            if "기타" in groups and groups["기타"]:
                groups["기타"].sort(key=get_chem_sort_key)
                result_parts.append("; ".join(groups["기타"]))
            for cat in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
                if cat in groups and groups[cat]:
                    groups[cat].sort(key=get_chem_sort_key)
                    result_parts.append(f"▷ {cat} - {'; '.join(groups[cat])}")
                    
            return "\n".join(result_parts)
            
        import win32com.client
        import pythoncom
        
        pythoncom.CoInitialize()
        excel = None
        wb = None
        try:
            self.measure_plan_log("[*] Excel 인스턴스 획득 중...")
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except:
                excel = win32com.client.Dispatch("Excel.Application")
                excel.Visible = True
                
            abs_excel_path = os.path.abspath(excel_path)
            excel_filename = os.path.basename(excel_path)
            
            # 이미 열려있는 통합문서 검색
            for w in excel.Workbooks:
                try:
                    if w.FullName.lower() == abs_excel_path.lower() or w.Name.lower() == excel_filename.lower():
                        wb = w
                        break
                except:
                    continue
                    
            if wb is None:
                self.measure_plan_log(f"[*] 엑셀 파일 오픈: {excel_filename}")
                wb = excel.Workbooks.Open(abs_excel_path)
                excel.Visible = True
                
            # 시트 확인
            try:
                wsInput = wb.Worksheets(src_sheet_name)
            except Exception as sheet_err:
                self.measure_plan_log(f"🔴 현황 시트 '{src_sheet_name}'를 찾을 수 없습니다: {sheet_err}")
                QMessageBox.critical(self, "시트 없음", f"화학물질 현황 시트 '{src_sheet_name}'가 존재하지 않습니다.\n설정을 확인해 주세요.")
                return
                
            try:
                wsOutput = wb.Worksheets(dest_sheet_name)
            except Exception as sheet_err:
                # 없으면 신규 생성
                wsOutput = wb.Worksheets.Add(Before=None, After=wb.Worksheets(wb.Worksheets.Count))
                wsOutput.Name = dest_sheet_name
                self.measure_plan_log(f"📂 '{dest_sheet_name}' 시트가 존재하지 않아 신규 생성하였습니다.")
                
            # 매핑 열 정보 획득
            map_data = self.measure_mapping_panel.get_mapping()
            col_process = map_data.get("공정명 열", "B")
            col_chem = map_data.get("화학물질명 열", "C")
            col_l = map_data.get("노출기준 L값 열", "I")
            col_e = map_data.get("노출기준 E값 열", "J")
            col_method = map_data.get("분석방법 열", "K")
            
            col_src_process = map_data.get("현황 공정명 열", "C")
            col_src_chem = map_data.get("현황 화학물질명 열", "I")
            
            idx_process = SMUGUI.c2i(col_process)
            idx_chem = SMUGUI.c2i(col_chem)
            idx_l = SMUGUI.c2i(col_l)
            idx_e = SMUGUI.c2i(col_e)
            idx_method = SMUGUI.c2i(col_method)
            
            idx_src_process = SMUGUI.c2i(col_src_process)
            idx_src_chem = SMUGUI.c2i(col_src_chem)
            
            # 입력 데이터의 마지막 행 감지 (idx_src_chem 기준)
            last_src_row = wsInput.Cells(wsInput.Rows.Count, idx_src_chem).End(-4162).Row # xlUp
            if last_src_row < 3:
                last_src_row = 3
                
            self.measure_plan_log(f"[*] 현황 데이터 범위: {src_sheet_name} 시트 3행 ~ {last_src_row}행")
            
            # 5. 입력 데이터를 읽어서 메모리에서 공정별 데이터 구성
            master_dict = {}
            missing_dict = {}
            has_missing = False
            
            for r in range(3, last_src_row + 1):
                processName = str(wsInput.Cells(r, idx_src_process).Value or "").strip()
                chemList = str(wsInput.Cells(r, idx_src_chem).Value or "").strip()
                
                if processName != "" and chemList != "":
                    # 특별관리물질 패턴 전처리 (VBA 정규식 로직 포팅)
                    chemList_clean = re.sub(r'특별관리물질(?:\[([^\]]+)\]|\(([^()]+)\))', r'\1\2', chemList)
                    
                    protected_chemList = process_special_patterns(chemList_clean)
                    arrChems = [x.strip() for x in protected_chemList.split(";") if x.strip()]
                    
                    for item in arrChems:
                        chemName = item.replace('\u0001', ';').strip()
                        if chemName:
                            # 예외 항목(단시간, 보관, 허용소비량 미만)은 무조건 분석방법 없음으로 수집
                            is_exception = ("단시간 및 임시작업" in chemName) or ("보관" in chemName) or ("허용소비량 미만" in chemName)
                            
                            if not is_exception and chemName in dictMethod and dictMethod[chemName] != "":
                                method = dictMethod[chemName]
                                if processName not in master_dict:
                                    master_dict[processName] = {}
                                if method not in master_dict[processName]:
                                    master_dict[processName][method] = {}
                                master_dict[processName][method][chemName] = 1
                            else:
                                if processName not in missing_dict:
                                    missing_dict[processName] = {}
                                missing_dict[processName][chemName] = 1
                                has_missing = True
                                
            # 6. 기존 측정계획 시트 데이터 영역 삭제
            clearRowB = wsOutput.Cells(wsOutput.Rows.Count, idx_process).End(-4162).Row
            if clearRowB < 4: clearRowB = 4
            
            clearRowI = wsOutput.Cells(wsOutput.Rows.Count, idx_l).End(-4162).Row
            if clearRowI < 4: clearRowI = 4
            
            # 🚨 [V24.3.5.8] 병합 셀로 인한 삭제 에러 방지를 위해 기존 범위 병합 전체 해제
            max_clear_row = max(clearRowB, clearRowI)
            if max_clear_row >= 4:
                wsOutput.Range(wsOutput.Cells(4, idx_process), wsOutput.Cells(max_clear_row, 12)).UnMerge()
            
            # 공정명, 화학물질명 삭제
            wsOutput.Range(wsOutput.Cells(4, idx_process), wsOutput.Cells(clearRowB, idx_chem)).ClearContents()
            # L값, E값, 분석방법 삭제
            wsOutput.Range(wsOutput.Cells(4, idx_l), wsOutput.Cells(clearRowI, idx_method)).ClearContents()
            
            # 글꼴 색상 초기화 (검정색으로)
            fontRow = max(clearRowB, clearRowI)
            if fontRow < 4: fontRow = 4
            wsOutput.Range(wsOutput.Cells(4, idx_process), wsOutput.Cells(fontRow, idx_method)).Font.Color = 0
            
            # 7. 메모리에 수집된 데이터를 정렬하여 순차적으로 기입
            output_row = 4
            
            for pKey in master_dict.keys():
                processName = pKey
                method_dict = master_dict[pKey]
                
                arrMethods = list(method_dict.keys())
                def get_method_priority(m):
                    if m in priorityList:
                        return priorityList.index(m)
                    return 9999
                arrMethods.sort(key=get_method_priority)
                
                for method in arrMethods:
                    chem_dict = method_dict[method]
                    arrSortedChems = list(chem_dict.keys())
                    def get_chem_order(c):
                        if c in dictOrder:
                            return dictOrder[c]
                        return 999999
                    arrSortedChems.sort(key=get_chem_order)
                    
                    firstChem = arrSortedChems[0]
                    
                    if "(단)" in method:
                        for c_item in arrSortedChems:
                            wsOutput.Cells(output_row, idx_process).Value = processName
                            wsOutput.Cells(output_row, idx_chem).Value = c_item
                            wsOutput.Cells(output_row, idx_l).Value = dictLValue.get(c_item, "-") if c_item in dictLValue else "-"
                            wsOutput.Cells(output_row, idx_e).Value = dictEValue.get(c_item, "-") if c_item in dictEValue else "-"
                            wsOutput.Cells(output_row, idx_method).Value = method
                            output_row += 1
                    else:
                        wsOutput.Cells(output_row, idx_process).Value = processName
                        wsOutput.Cells(output_row, idx_chem).Value = "; ".join(arrSortedChems)
                        wsOutput.Cells(output_row, idx_l).Value = dictLValue.get(firstChem, "-") if firstChem in dictLValue else "-"
                        wsOutput.Cells(output_row, idx_e).Value = dictEValue.get(firstChem, "-") if firstChem in dictEValue else "-"
                        
                        if len(arrSortedChems) == 1 and "(다)" in method:
                            wsOutput.Cells(output_row, idx_method).Value = method.replace("(다)", "(단)")
                        else:
                            wsOutput.Cells(output_row, idx_method).Value = method
                        output_row += 1
                        
            # 8. [V24.3.5.9] 누락 및 미대상(물리적인자, 분진, 비대상 등) 항목 기입 (적색 및 카테고리별 행분할 기입, 셀맞춤/줄바꿈 해제)
            if has_missing:
                output_row += 2 # 2칸 아래에서 표시되도록 빈 행 2개 건너뜀
                for pKey in missing_dict.keys():
                    processName = pKey
                    m_chems = list(missing_dict[pKey].keys())
                    
                    # 활성 측정대상 물질 수집 (교차 중복 방지)
                    active_chems = set()
                    if processName in master_dict:
                        for method in master_dict[processName]:
                            for chem in master_dict[processName][method]:
                                active_chems.add(chem)
                    
                    # 그룹화 및 중복 제거
                    formatted_chems_str = format_grouped_chems("; ".join(m_chems), active_chems)
                    parts = [x.strip() for x in formatted_chems_str.split("\n") if x.strip()]
                    
                    for part in parts:
                        # B열 공정명 기입 (모든 행에 실제 값을 기입하여 조건부 서식 연동 보장)
                        wsOutput.Cells(output_row, idx_process).Value = processName
                        
                        # C열 화학물질명 기입 및 서식 설정 (좌측 정렬, 가로 병합 제거, 셀맞춤 해제, 줄바꿈 해제)
                        c_cell = wsOutput.Cells(output_row, idx_chem)
                        c_cell.Value = part
                        c_cell.HorizontalAlignment = -4131 # xlLeft = -4131
                        c_cell.VerticalAlignment = -4108 # xlCenter = -4108
                        c_cell.ShrinkToFit = False         # 🚨 셀 맞춤 해제
                        c_cell.WrapText = False            # 🚨 줄 바꿈 해제 (우측 오버플로우 허용)
                        
                        # D열부터 L열까지는 빈 값 처리
                        for col_idx in range(idx_chem + 1, 13):
                            wsOutput.Cells(output_row, col_idx).Value = ""
                            
                        # B열부터 L열까지 전체 적색 글자 서식 지정
                        wsOutput.Range(wsOutput.Cells(output_row, idx_process), wsOutput.Cells(output_row, 12)).Font.Color = 255
                        
                        # 행높이 기본 30 설정
                        wsOutput.Rows(output_row).RowHeight = 30
                        
                        output_row += 1
                    
            # 9. 실시간 수식 갱신
            try:
                excel.Calculate()
            except:
                pass
                
            wb.Save()
            self.measure_plan_log("🟢 화학물질 현황 시트 최초 반영 완료!")
            QMessageBox.information(self, "완료", "화학물질 현황 데이터 반영이 정상적으로 완료되었습니다!")
            
        except Exception as e:
            self.measure_plan_log(f"🔴 오류 발생: {e}")
            QMessageBox.critical(self, "오류", f"작업 중 예기치 못한 오류가 발생했습니다:\n{e}")
        finally:
            pythoncom.CoUninitialize()

    def measure_plan_update_slot(self):
        """[핵심 1] 측정계획 매체 업데이트 실행"""
        excel_path = self.edit_excel.text().strip()
        sheet_name = self.combo_measure_sheet.currentText().strip() or "측정계획(양식)"
        
        if not excel_path or not os.path.exists(excel_path):
            QMessageBox.warning(self, "경고", "올바른 엑셀 경로를 지정해 주세요.")
            return
            
        if not sheet_name:
            sheet_name = "측정계획(양식)"
            
        # 1. 자동 백업 실행
        if not self.run_backup_engine(excel_path):
            self.measure_plan_log("🛑 사용자가 백업 실패 후 작업을 취소하였습니다.")
            return
            
        self.txt_measure_log.clear()
        self.measure_plan_log("🟢 매체 업데이트 및 재정렬 작업 시작...")
        
        # 2. 마스터 데이터셋 구축 확인
        if not hasattr(self, 'mes_master_list') or not self.mes_master_list:
            self.measure_plan_log("[*] msds_index.json 마스터 데이터를 로드합니다...")
            self.load_mes_master()
            
        if not self.mes_master_list:
            QMessageBox.critical(self, "오류", "msds_index.json을 로드할 수 없어 작업을 진행할 수 없습니다.")
            return
            
        # 3. 마스터 데이터셋 구조화
        dictMethod = {}
        dictOrder = {}
        dictLValue = {}
        dictEValue = {}
        
        for idx, entry in enumerate(self.mes_master_list):
            chemName = str(entry.get("측정대상 물질명", "")).strip()
            if chemName:
                if chemName not in dictMethod:
                    dictMethod[chemName] = str(entry.get("분석방법", "")).strip()
                    dictOrder[chemName] = idx
                    # dictLValue는 측정매체(실무용)로 들어가며, dictEValue는 적정유속(유량)으로 들어감 (VBA 원래 로직 복구)
                    l_val = str(entry.get("매체(실무용)", "")).strip() or str(entry.get("매체", "")).strip()
                    dictLValue[chemName] = l_val
                    dictEValue[chemName] = str(entry.get("적정유속(L/min)", "")).strip()
                    
        # 4. 분석방법 우선순위 리스트 정의
        priorityList = [
            "누적소음계", "중량분석법", "중량분석법(호)", "중량분석법(흡)", "FTIR법(다)",
            "위상차현미경법", "중량분석법(단)", "ICP법(다)", "ICP법(다)호", "IC법(단)-금",
            "ICP법(단)흡", "ICP법(단)", "GC법(다)", "GC법(다)2", "GC법(다)3", "GC법(다)4",
            "GC법(다)5", "GC법(다)6", "GC법(다)7", "GC법(다)8", "GC법(단)", "HPLC법(다)",
            "HPLC법(다)2", "HPLC법(다)3", "HPLC법(다)4", "HPLC법(단)",
            "IC법(다)-산알", "IC법(다)2-산알", "UV법(다)", "IC법(단)-산알",
            "UV법(단)", "GC법(NPD)(단)", "IC법(다)3-가스", "IC법(단)-가스", "VIS(다)", "추출법",
            "GC법(단)-C", "HPLC법(단)-C", "ICP법(다)-C", "UV법(단)-C",
            "직독식", "WBGT"
        ]
        
        # 헬퍼 함수 1: 스페셜 패턴 처리 (괄호 안의 세미콜론 임시 치환)
        def process_special_patterns(text):
            if not text:
                return ""
            chars = list(text)
            in_paren = 0
            in_bracket = 0
            for i, ch in enumerate(chars):
                if ch == '(': in_paren += 1
                elif ch == ')': in_paren -= 1
                elif ch == '[': in_bracket += 1
                elif ch == ']': in_bracket -= 1
                elif ch == ';' and (in_paren > 0 or in_bracket > 0):
                    chars[i] = '\u0001'
            return "".join(chars)
            
        # 헬퍼 함수 2: 미분류 유해인자 그룹화 및 중복 제거
        def format_grouped_chems(chem_list_str):
            if not chem_list_str or chem_list_str.strip() == "":
                return "-"
            protected = process_special_patterns(chem_list_str)
            items = [x.strip() for x in protected.split(";") if x.strip()]
            
            groups = {}
            for item in items:
                item = item.replace('\u0001', ';').strip()
                if not item:
                    continue
                matched_prefix = None
                for prefix in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
                    if item.startswith(prefix):
                        matched_prefix = prefix
                        break
                        
                if matched_prefix:
                    inner = item[len(matched_prefix):].strip()
                    if inner.startswith("[") and inner.endswith("]"):
                        inner = inner[1:-1].strip()
                    elif inner.startswith("(") and inner.endswith(")"):
                        inner = inner[1:-1].strip()
                        
                    sub_parts = [x.strip() for x in inner.split(";") if x.strip()]
                    if matched_prefix not in groups:
                        groups[matched_prefix] = []
                    for sp in sub_parts:
                        if sp not in groups[matched_prefix] and (not active_chems or sp not in active_chems):
                            groups[matched_prefix].append(sp)
                else:
                    if "기타" not in groups:
                        groups["기타"] = []
                    if item not in groups["기타"]:
                        groups["기타"].append(item)
                        
            # [V24.3.5.7] 제외사유별 수집된 물질들을 마스터 DB 정렬 키 기준으로 정렬
            def get_chem_sort_key(c):
                name_clean = re.sub(r'\[.*?\]|\(.*?\)', '', c).strip()
                if name_clean in dictOrder:
                    return dictOrder[name_clean]
                for m_name, idx in dictOrder.items():
                    if m_name in name_clean or name_clean in m_name:
                        return idx
                return 999999
                
            result_parts = []
            if "기타" in groups and groups["기타"]:
                groups["기타"].sort(key=get_chem_sort_key)
                result_parts.append("; ".join(groups["기타"]))
            for cat in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
                if cat in groups and groups[cat]:
                    groups[cat].sort(key=get_chem_sort_key)
                    result_parts.append(f"▷ {cat} - {'; '.join(groups[cat])}")
                    
            return "\n".join(result_parts)
            
        import win32com.client
        import pythoncom
        
        pythoncom.CoInitialize()
        excel = None
        wb = None
        try:
            self.measure_plan_log("[*] Excel 인스턴스 획득 중...")
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except:
                excel = win32com.client.Dispatch("Excel.Application")
                excel.Visible = True
                
            abs_excel_path = os.path.abspath(excel_path)
            excel_filename = os.path.basename(excel_path)
            
            # 이미 열려있는 통합문서 검색
            for w in excel.Workbooks:
                try:
                    if w.FullName.lower() == abs_excel_path.lower() or w.Name.lower() == excel_filename.lower():
                        wb = w
                        break
                except:
                    continue
                    
            if wb is None:
                self.measure_plan_log(f"[*] 엑셀 파일 오픈: {excel_filename}")
                wb = excel.Workbooks.Open(abs_excel_path)
                excel.Visible = True
                
            ws = wb.Worksheets(sheet_name)
            
            # 매핑 열 정보 획득
            map_data = self.measure_mapping_panel.get_mapping()
            col_process = map_data.get("공정명 열", "B")
            col_chem = map_data.get("화학물질명 열", "C")
            col_l = map_data.get("노출기준 L값 열", "I")
            col_e = map_data.get("노출기준 E값 열", "J")
            col_method = map_data.get("분석방법 열", "K")
            
            idx_process = SMUGUI.c2i(col_process)
            idx_chem = SMUGUI.c2i(col_chem)
            idx_l = SMUGUI.c2i(col_l)
            idx_e = SMUGUI.c2i(col_e)
            idx_method = SMUGUI.c2i(col_method)
            
            # 🚨 [V24.3.5.9] 엑셀 데이터의 마지막 행 감지 (제외대상 텍스트까지 감지하기 위해 idx_chem 기준으로 변경)
            last_row = ws.Cells(ws.Rows.Count, idx_chem).End(-4162).Row # xlUp
            if last_row < 4:
                last_row = 4
                
            # 공정명이 비어 있고 화학물질명이 있는 행 체크 (제외대상 ▷ 행은 B열 글씨가 가려져 있어 Value가 공백처럼 보일 수 있으므로 ▷ 로 시작하면 통과)
            for r in range(4, last_row + 1):
                c_val = str(ws.Cells(r, idx_chem).Value or "").strip()
                p_val = str(ws.Cells(r, idx_process).Value or "").strip()
                if c_val != "" and p_val == "" and not c_val.startswith("▷"):
                    self.measure_plan_log(f"⚠️ 공정명({col_process}열)이 비어 있는 행이 감지되었습니다. (행 번호: {r})")
                    QMessageBox.warning(self, "입력 오류", 
                                        f"공정명({col_process}열)이 비어 있는 행이 있습니다. 확인 후 다시 실행해주세요.\n"
                                        f"문제가 있는 행 번호: {r}")
                    return
                    
            # 5. 기존 데이터를 읽어서 메모리에서 공정별 데이터 재구성 (Self-Reading)
            master_dict = {}
            noMethodList = [] # 분석방법 없음 물질 수집용 (로컬 정의를 위로 이동)
            for r in range(4, last_row + 1):
                processName = str(ws.Cells(r, idx_process).Value or "").strip()
                chemList = str(ws.Cells(r, idx_chem).Value or "").strip()
                
                # 🚨 [V24.3.5.9] ▷ 제외대상 행 발견 시, 카테고리와 물질 리스트를 파싱하여 noMethodList에 보존 수집
                if chemList.startswith("▷") or chemList.startswith("▷"):
                    match = re.match(r'^▷\s*([^-]+)\s*-\s*(.*)$', chemList)
                    if match:
                        cat_name = match.group(1).strip()
                        chems_part = match.group(2).strip()
                        # 포맷팅 변환: 카테고리[물질들] 구조로 format_grouped_chems에 전달
                        reconstructed = f"{cat_name}[{chems_part}]"
                        noMethodList.append({
                            "process": processName,
                            "chems": reconstructed,
                            "method": "분석방법 없음"
                        })
                    else:
                        noMethodList.append({
                            "process": processName,
                            "chems": chemList,
                            "method": "분석방법 없음"
                        })
                    continue
                
                if processName != "" and chemList != "":
                    protected_chemList = process_special_patterns(chemList)
                    arrChems = [x.strip() for x in protected_chemList.split(";") if x.strip()]
                    
                    for item in arrChems:
                        chemName = item.replace('\u0001', ';').strip()
                        if chemName:
                            # 분석방법 및 매체/노출기준 조회
                            if chemName in dictMethod and dictMethod[chemName] != "":
                                method = dictMethod[chemName]
                            else:
                                method = "분석방법 없음"
                                
                            if processName not in master_dict:
                                master_dict[processName] = {}
                            if method not in master_dict[processName]:
                                master_dict[processName][method] = {}
                            master_dict[processName][method][chemName] = 1
                            
            # 6. 기존 시트 데이터 영역 삭제
            # 6-1. B열 기준 마지막 행 계산
            clearRowB = ws.Cells(ws.Rows.Count, idx_process).End(-4162).Row
            if clearRowB < 4: clearRowB = 4
            
            clearRowI = ws.Cells(ws.Rows.Count, idx_l).End(-4162).Row
            if clearRowI < 4: clearRowI = 4
            
            # 🚨 [V24.3.5.8] 병합 셀로 인한 삭제 에러 방지를 위해 기존 범위 병합 전체 해제
            max_clear_row = max(clearRowB, clearRowI)
            if max_clear_row >= 4:
                ws.Range(ws.Cells(4, idx_process), ws.Cells(max_clear_row, 12)).UnMerge()
            
            # 공정명, 화학물질명 삭제
            ws.Range(ws.Cells(4, idx_process), ws.Cells(clearRowB, idx_chem)).ClearContents()
            # L값, E값, 분석방법 삭제
            ws.Range(ws.Cells(4, idx_l), ws.Cells(clearRowI, idx_method)).ClearContents()
            
            # 글꼴 색상 초기화 (검정색으로)
            fontRow = max(clearRowB, clearRowI)
            if fontRow < 4: fontRow = 4
            ws.Range(ws.Cells(4, idx_process), ws.Cells(fontRow, idx_method)).Font.Color = 0
            
            # 7. 메모리에 재구성된 데이터를 정렬하여 순차적으로 기입 (noMethodList는 상단에서 정의됨)
            output_row = 4
            
            for pKey in master_dict.keys():
                processName = pKey
                method_dict = master_dict[pKey]
                
                # 분석방법을 우선순위 리스트 기준으로 정렬
                arrMethods = list(method_dict.keys())
                def get_method_priority(m):
                    if m in priorityList:
                        return priorityList.index(m)
                    return 9999
                arrMethods.sort(key=get_method_priority)
                
                for method in arrMethods:
                    chem_dict = method_dict[method]
                    # 화학물질을 마스터 DB 인덱스 기준으로 정렬
                    arrSortedChems = list(chem_dict.keys())
                    def get_chem_order(c):
                        if c in dictOrder:
                            return dictOrder[c]
                        return 999999
                    arrSortedChems.sort(key=get_chem_order)
                    
                    firstChem = arrSortedChems[0]
                    
                    if method == "분석방법 없음":
                        # 🚨 [V24.3.5.9] 제외 대상을 그룹화하여 1행으로 기입하기 위해 이전 방식 복구
                        noMethodList.append({
                            "process": processName,
                            "chems": format_grouped_chems("; ".join(arrSortedChems)),
                            "l_val": dictLValue.get(firstChem, "-") if firstChem in dictLValue else "-",
                            "e_val": dictEValue.get(firstChem, "-") if firstChem in dictEValue else "-",
                            "method": method
                        })
                    elif "(단)" in method:
                        # (단) 성분은 각 물질당 1행씩 쪼개어 기입
                        for c_item in arrSortedChems:
                            ws.Cells(output_row, idx_process).Value = processName
                            ws.Cells(output_row, idx_chem).Value = c_item
                            ws.Cells(output_row, idx_l).Value = dictLValue.get(c_item, "-") if c_item in dictLValue else "-"
                            ws.Cells(output_row, idx_e).Value = dictEValue.get(c_item, "-") if c_item in dictEValue else "-"
                            ws.Cells(output_row, idx_method).Value = method
                            output_row += 1
                    else:
                        # (다) 성분은 동일 공정/동일 분석방법을 세미콜론으로 묶어서 기입
                        ws.Cells(output_row, idx_process).Value = processName
                        ws.Cells(output_row, idx_chem).Value = "; ".join(arrSortedChems)
                        ws.Cells(output_row, idx_l).Value = dictLValue.get(firstChem, "-") if firstChem in dictLValue else "-"
                        ws.Cells(output_row, idx_e).Value = dictEValue.get(firstChem, "-") if firstChem in dictEValue else "-"
                        
                        # 다성분 분석인데 물질이 단 1개만 존재하는 경우 (다) ➔ (단) 자동 치환
                        if len(arrSortedChems) == 1 and "(다)" in method:
                            ws.Cells(output_row, idx_method).Value = method.replace("(다)", "(단)")
                        else:
                            ws.Cells(output_row, idx_method).Value = method
                        output_row += 1
                        
            # 8. [V24.3.5.9] 분석방법 없음 항목들은 C열의 최종 기입 행에서 2칸 아래(2행의 빈 줄을 띄우고)부터 적색으로 기입 (공정별로 통합 및 중복 제거 후 카테고리별 행분할 기입)
            if noMethodList:
                output_row += 2 # 2칸 아래에서 표시되도록 빈 행 2개 건너뜀
                
                # 공정명별로 수집된 제외대상 데이터 그룹화
                grouped_no_methods = {}
                for noItem in noMethodList:
                    p = noItem["process"]
                    c = noItem["chems"]
                    if p not in grouped_no_methods:
                        grouped_no_methods[p] = []
                    grouped_no_methods[p].append(c)
                
                for processName, chem_list in grouped_no_methods.items():
                    # 해당 공정에 활성화된 측정대상 물질들 모으기 (교차 중복 방지)
                    active_chems = set()
                    if processName in master_dict:
                        for method in master_dict[processName]:
                            for chem in master_dict[processName][method]:
                                active_chems.add(chem)
                    
                    # 수집된 제외 텍스트들을 조인하여 정제 및 중복 제거
                    full_chem_str = "; ".join(chem_list)
                    formatted_chems_str = format_grouped_chems(full_chem_str, active_chems)
                    
                    parts = [x.strip() for x in formatted_chems_str.split("\n") if x.strip()]
                    
                    for part in parts:
                        # B열 공정명 기입 (모든 행에 실제 값을 기입하여 조건부 서식 연동 보장)
                        ws.Cells(output_row, idx_process).Value = processName
                        
                        # C열 화학물질명 기입 및 서식 설정 (좌측 정렬, 가로 병합 제거, 셀맞춤 해제, 줄바꿈 해제)
                        c_cell = ws.Cells(output_row, idx_chem)
                        c_cell.Value = part
                        c_cell.HorizontalAlignment = -4131 # xlLeft = -4131
                        c_cell.VerticalAlignment = -4108 # xlCenter = -4108
                        c_cell.ShrinkToFit = False         # 🚨 셀 맞춤 해제
                        c_cell.WrapText = False            # 🚨 줄 바꿈 해제 (우측 오버플로우 허용)
                        
                        # D열부터 L열까지는 빈 값 처리
                        for col_idx in range(idx_chem + 1, 13):
                            ws.Cells(output_row, col_idx).Value = ""
                        
                        # 적색 글씨 적용 (RGB 255, 0, 0)
                        ws.Range(ws.Cells(output_row, idx_process), ws.Cells(output_row, 12)).Font.Color = 255
                        
                        # 행높이 기본 30 설정
                        ws.Rows(output_row).RowHeight = 30
                        
                        output_row += 1
                    
            # 9. 엑셀 수식 실시간 반영을 위해 재계산 강제 호출 (Calculate)
            try:
                excel.Calculate()
            except Exception as calc_err:
                self.measure_plan_log(f"⚠️ 수식 재계산 실패: {calc_err}")
                
            wb.Save()
            self.measure_plan_log("🟢 매체 업데이트 및 재정렬 완료!")
            QMessageBox.information(self, "완료", "매체 재정렬 및 업데이트가 정상적으로 완료되었습니다!")
            
        except Exception as e:
            self.measure_plan_log(f"🔴 오류 발생: {e}")
            QMessageBox.critical(self, "오류", f"작업 중 예기치 못한 오류가 발생했습니다:\n{e}")
            pythoncom.CoUninitialize()

    def measure_plan_workflow_slot(self):
        """[핵심 2] 측정계획 워크플로우 실행 (셀 병합, 번호 부여, 줄높이, 테두리 설정)"""
        excel_path = self.edit_excel.text().strip()
        sheet_name = self.combo_measure_sheet.currentText().strip() or "측정계획(양식)"
        
        if not excel_path or not os.path.exists(excel_path):
            QMessageBox.warning(self, "경고", "올바른 엑셀 경로를 지정해 주세요.")
            return
            
        if not sheet_name:
            sheet_name = "측정계획(양식)"
            
        reply = QMessageBox.question(self, "측정계획 워크플로우", 
                                     "병합을 진행하고 근로자 수를 입력하시겠습니까?\n"
                                     "(이미 병합했다면 '아니오'를 눌러 번호 부여 단계로 이동하세요)",
                                     QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
        
        if reply == QMessageBox.Cancel:
            return
            
        # 백업 실행
        if not self.run_backup_engine(excel_path):
            self.measure_plan_log("🛑 사용자가 백업 실패 후 작업을 취소하였습니다.")
            return
            
        import win32com.client
        import pythoncom
        
        pythoncom.CoInitialize()
        excel = None
        wb = None
        
        try:
            self.measure_plan_log("[*] Excel 인스턴스 획득 중...")
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except:
                excel = win32com.client.Dispatch("Excel.Application")
                excel.Visible = True
                
            abs_excel_path = os.path.abspath(excel_path)
            excel_filename = os.path.basename(excel_path)
            
            for w in excel.Workbooks:
                try:
                    if w.FullName.lower() == abs_excel_path.lower() or w.Name.lower() == excel_filename.lower():
                        wb = w
                        break
                except:
                    continue
                    
            if wb is None:
                wb = excel.Workbooks.Open(abs_excel_path)
                excel.Visible = True
                
            ws = wb.Worksheets(sheet_name)
            
            # 매핑 열 정보 획득
            map_data = self.measure_mapping_panel.get_mapping()
            col_process = map_data.get("공정명 열", "B")
            col_chem = map_data.get("화학물질명 열", "C")
            col_worker = map_data.get("일련번호 수 열", "E")
            col_code_f = map_data.get("번호코드 열(F)", "F")
            col_code_g = map_data.get("번호코드 열(G)", "G")
            col_merge_str = map_data.get("병합 대상 열", "D, E, F, G, M")
            
            idx_process = SMUGUI.c2i(col_process)
            idx_chem = SMUGUI.c2i(col_chem)
            idx_worker = SMUGUI.c2i(col_worker)
            idx_code_f = SMUGUI.c2i(col_code_f)
            idx_code_g = SMUGUI.c2i(col_code_g)
            target_cols = [x.strip() for x in col_merge_str.split(",") if x.strip()]
            
            # Excel 상수
            xlUp = -4162
            xlCenter = -4108
            xlLeft = -4131
            xlNone = -4142
            xlContinuous = 1
            xlThin = 2
            
            last_row = ws.Cells(ws.Rows.Count, idx_chem).End(xlUp).Row
            if last_row < 4:
                last_row = 4
                
            if reply == QMessageBox.Yes:
                # ----------------------------------------------------
                # 1단계: B열(공정명) 기준 지정된 대상 열 셀 병합 처리
                # ----------------------------------------------------
                self.measure_plan_log("🟢 1단계: 공정명 기준 셀 병합을 시작합니다...")
                excel.ScreenUpdating = False
                excel.DisplayAlerts = False
                
                currentRow = 4
                while currentRow <= last_row:
                    currentValue = ws.Cells(currentRow, idx_process).Value
                    if currentValue is None:
                        currentValue = ""
                    currentValue = str(currentValue).strip()
                    
                    endRow = currentRow
                    while endRow + 1 <= last_row:
                        nextValue = ws.Cells(endRow + 1, idx_process).Value
                        if nextValue is None:
                            nextValue = ""
                        nextValue = str(nextValue).strip()
                        
                        if nextValue == currentValue and nextValue != "":
                            endRow += 1
                        else:
                            break
                            
                    if endRow >= currentRow:
                        for col_letter in target_cols:
                            idx_col = SMUGUI.c2i(col_letter)
                            if idx_col < 1: continue
                            
                            cell_range = ws.Range(ws.Cells(currentRow, idx_col), ws.Cells(endRow, idx_col))
                            if cell_range.MergeCells:
                                cell_range.UnMerge()
                            cell_range.Merge()
                            cell_range.HorizontalAlignment = xlCenter
                            cell_range.VerticalAlignment = xlCenter
                            
                    currentRow = endRow + 1
                    
                excel.DisplayAlerts = True
                excel.ScreenUpdating = True
                wb.Save()
                
                self.measure_plan_log("🟢 1단계 병합 완료! 근로자 수와 측정 건수를 기입한 후 다시 워크플로우를 가동하여 번호를 부여해주세요.")
                QMessageBox.information(self, "완료", "1단계 셀 병합 처리가 완료되었습니다.\n근로자 수(E열 등)와 측정 횟수(H열 등)를 입력한 뒤 다시 실행해 주세요.")
                
            elif reply == QMessageBox.No:
                # ----------------------------------------------------
                # 3단계: E열(근로자수) 기준 번호 코드 부여 및 행높이 조절
                # ----------------------------------------------------
                self.measure_plan_log("🟢 3단계: 번호 자동 부여 및 행높이 균등 분배를 시작합니다...")
                excel.ScreenUpdating = False
                
                counter = 1
                currentRow = 4
                
                while currentRow <= last_row:
                    groupStartRow = currentRow
                    currentGroup = ws.Cells(currentRow, idx_process).Value
                    if currentGroup is None:
                        currentGroup = ""
                    currentGroup = str(currentGroup).strip()
                    
                    while currentRow + 1 <= last_row:
                        nextGroup = ws.Cells(currentRow + 1, idx_process).Value
                        if nextGroup is None:
                            nextGroup = ""
                        nextGroup = str(nextGroup).strip()
                        
                        if nextGroup == currentGroup:
                            currentRow += 1
                        else:
                            break
                            
                    groupEndRow = currentRow
                    rowCount = groupEndRow - groupStartRow + 1
                    
                    # skipGroup 판단: H열(8번 열) 값이 전부 "횟수조정"이거나 "0"인 경우 번호 미부여
                    skipGroup = True
                    for r in range(groupStartRow, groupEndRow + 1):
                        hVal = str(ws.Cells(r, 8).Value or "").strip()
                        if hVal != "횟수조정" and hVal != "0" and hVal != "":
                            skipGroup = False
                            break
                            
                    if not skipGroup:
                        # E열(일련번호 수 열)의 병합 첫 셀 값 가져옴
                        val = ws.Cells(groupStartRow, idx_worker).MergeArea.Cells(1, 1).Value
                        try:
                            val_num = int(float(val))
                        except:
                            val_num = 0
                            
                        if val_num > 0:
                            # 번호 텍스트 생성
                            text_out = "\n"
                            for r in range(1, val_num + 1):
                                text_out += f" {counter})\n\n"
                                counter += 1
                            text_out = text_out[:-1] # 마지막 줄바꿈 제거
                            
                            # 번호코드 열(F, G) 처리
                            for idx_col in [idx_code_f, idx_code_g]:
                                if idx_col < 1: continue
                                cell_range = ws.Range(ws.Cells(groupStartRow, idx_col), ws.Cells(groupEndRow, idx_col))
                                cell_range.UnMerge()
                                cell_range.Merge()
                                cell_range.Value = text_out
                                cell_range.WrapText = True
                                cell_range.HorizontalAlignment = xlLeft
                                cell_range.VerticalAlignment = xlCenter
                                
                            # 행 높이 계산 (줄당 25pt 기준)
                            totalHeight = 25 * (2 * val_num + 1)
                            
                            # C열 화학물질명 1차 AutoFit 후 높이 총합 측정
                            cHeightSum = 0
                            for i in range(groupStartRow, groupEndRow + 1):
                                try:
                                    ws.Rows(i).AutoFit()
                                    cHeightSum += ws.Rows(i).RowHeight
                                except:
                                    pass
                                    
                            if cHeightSum > totalHeight:
                                totalHeight = cHeightSum
                                
                            # 최소 높이 한계 보장
                            if totalHeight < (25 * rowCount):
                                totalHeight = 25 * rowCount
                                
                            eachRowHeight = totalHeight / rowCount
                            if eachRowHeight > 409:
                                eachRowHeight = 409
                                
                            for i in range(groupStartRow, groupEndRow + 1):
                                ws.Rows(i).RowHeight = eachRowHeight
                        else:
                            # E열 값이 유효하지 않은 경우 공란 처리
                            skipGroup = True
                            
                    if skipGroup:
                        for idx_col in [idx_code_f, idx_code_g]:
                            if idx_col < 1: continue
                            cell_range = ws.Range(ws.Cells(groupStartRow, idx_col), ws.Cells(groupEndRow, idx_col))
                            cell_range.UnMerge()
                            cell_range.Merge()
                            cell_range.Value = ""
                            cell_range.WrapText = False
                            
                        for i in range(groupStartRow, groupEndRow + 1):
                            if ws.Rows(i).RowHeight < 25:
                                ws.Rows(i).RowHeight = 25
                                
                    currentRow += 1
                    
                # ----------------------------------------------------
                # 테두리 설정 (SetConditionalBorders 로직 통합)
                # ----------------------------------------------------
                self.measure_plan_log("[*] 테두리 정밀 포맷팅을 수행합니다...")
                
                # C4부터 공백이 나오는 실제 마지막 행 재측정
                lastRowBorder = 4
                for r in range(4, ws.Rows.Count + 1):
                    val_c = ws.Cells(r, idx_chem).Value
                    if val_c is None or str(val_c).strip() == "":
                        lastRowBorder = r - 1
                        break
                if lastRowBorder < 4: lastRowBorder = 4
                
                # A4:L{lastRowBorder} 전체 영역 기본 테두리 실선
                whole_range = ws.Range(ws.Cells(4, 1), ws.Cells(lastRowBorder, 12))
                whole_range.Borders.LineStyle = xlContinuous
                whole_range.Borders.Color = 0
                whole_range.Borders.Weight = xlThin
                
                # B열 공정 그룹별 가로 테두리 제거 및 외곽 유지
                currentRow = 4
                while currentRow <= lastRowBorder:
                    currentVal = ws.Cells(currentRow, idx_process).Value
                    if currentVal is None: currentVal = ""
                    currentVal = str(currentVal).strip()
                    
                    if currentVal == "":
                        currentRow += 1
                        continue
                        
                    startR = currentRow
                    while currentRow + 1 <= lastRowBorder:
                        nextVal = ws.Cells(currentRow + 1, idx_process).Value
                        if nextVal is None: nextVal = ""
                        nextVal = str(nextVal).strip()
                        
                        if nextVal == currentVal:
                            currentRow += 1
                        else:
                            break
                            
                    endR = currentRow
                    group_rng = ws.Range(ws.Cells(startR, idx_process), ws.Cells(endR, idx_process))
                    
                    # 안쪽 가로 테두리 제거 (B열 전용)
                    group_rng.Borders(12).LineStyle = xlNone # xlInsideHorizontal = 12
                    
                    # 첫행 위쪽, 마지막행 아래쪽, 좌우 테두리는 실선 유지
                    group_rng.Cells(1, 1).Borders(8).LineStyle = xlContinuous # xlEdgeTop = 8
                    group_rng.Cells(group_rng.Rows.Count, 1).Borders(9).LineStyle = xlContinuous # xlEdgeBottom = 9
                    
                    if group_rng.Rows.Count > 2:
                        for row_offset in range(1, group_rng.Rows.Count - 1):
                            group_rng.Cells(row_offset + 1, 1).Borders(8).LineStyle = xlNone
                            group_rng.Cells(row_offset + 1, 1).Borders(9).LineStyle = xlNone
                    elif group_rng.Rows.Count == 2:
                        group_rng.Cells(2, 1).Borders(8).LineStyle = xlNone
                        
                    group_rng.Borders(7).LineStyle = xlContinuous # xlEdgeLeft = 7
                    group_rng.Borders(10).LineStyle = xlContinuous # xlEdgeRight = 10
                    
                    currentRow += 1
                    
                # A열 및 C~L열 내부/외곽 테두리 전체 강제 유지
                for a_col in [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]:
                    col_rng = ws.Range(ws.Cells(4, a_col), ws.Cells(lastRowBorder, a_col))
                    col_rng.Borders.LineStyle = xlContinuous
                    col_rng.Borders.Color = 0
                    col_rng.Borders.Weight = xlThin
                    
                excel.ScreenUpdating = True
                wb.Save()
                
                self.measure_plan_log("🟢 3단계 번호 자동 부여 및 정밀 테두리 세팅 완료!")
                QMessageBox.information(self, "완료", "3단계 번호 부여 및 레이아웃 포맷팅이 완료되었습니다!")
                
        except Exception as e:
            self.measure_plan_log(f"🔴 오류 발생: {e}")
            QMessageBox.critical(self, "오류", f"작업 중 예기치 못한 오류가 발생했습니다:\n{e}")
        finally:
            pythoncom.CoUninitialize()

    def measure_plan_reset_slot(self):
        """[핵심 3] 측정계획 폼 초기화 실행"""
        excel_path = self.edit_excel.text().strip()
        sheet_name = self.combo_measure_sheet.currentText().strip() or "측정계획(양식)"
        
        if not excel_path or not os.path.exists(excel_path):
            QMessageBox.warning(self, "경고", "올바른 엑셀 경로를 지정해 주세요.")
            return
            
        if not sheet_name:
            sheet_name = "측정계획(양식)"
            
        reply = QMessageBox.question(self, "초기화 경고", 
                                     "현재 시트(A4:L295)의 데이터와 병합 서식을 모두 지우고 기본값으로 초기화합니다.\n"
                                     "정말 진행하시겠습니까?", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return
            
        if not self.run_backup_engine(excel_path):
            return
            
        import win32com.client
        import pythoncom
        
        pythoncom.CoInitialize()
        excel = None
        wb = None
        
        try:
            self.measure_plan_log("[*] Excel 인스턴스 획득 중...")
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except:
                excel = win32com.client.Dispatch("Excel.Application")
                excel.Visible = True
                
            abs_excel_path = os.path.abspath(excel_path)
            excel_filename = os.path.basename(excel_path)
            
            for w in excel.Workbooks:
                try:
                    if w.FullName.lower() == abs_excel_path.lower() or w.Name.lower() == excel_filename.lower():
                        wb = w
                        break
                except:
                    continue
                    
            if wb is None:
                wb = excel.Workbooks.Open(abs_excel_path)
                excel.Visible = True
                
            ws = wb.Worksheets(sheet_name)
            
            # Excel 상수
            xlNone = -4142
            xlCenter = -4108
            
            self.measure_plan_log("🟢 시트 초기화를 수행 중입니다...")
            
            # 1. 대상 범위 A4:L295 설정
            targetRange = ws.Range("A4:L295")
            
            # 2. 값 삭제 및 병합 해제
            targetRange.ClearContents()
            targetRange.UnMerge()
            
            # 3. 글꼴 기본 설정 (굴림, 16pt, 검정)
            targetRange.Font.Name = "굴림"
            targetRange.Font.Size = 16
            targetRange.Font.Color = 0
            
            # 4. 채우기 제거 및 맞춤(가운데, ShrinkToFit)
            targetRange.Interior.Pattern = xlNone
            targetRange.HorizontalAlignment = xlCenter
            targetRange.VerticalAlignment = xlCenter
            targetRange.ShrinkToFit = True
            
            # 5. A열 '@', C~L열 'General' 표시형식 복구
            ws.Range("A4:A295").NumberFormat = "@"
            ws.Range("C4:L295").NumberFormat = "General"
            
            # 6. 테두리 전체 제거
            targetRange.Borders.LineStyle = xlNone
            
            # 7. 행높이 30으로 일괄 설정
            for i in range(4, 296):
                ws.Rows(i).RowHeight = 30
                
            wb.Save()
            self.measure_plan_log("🟢 측정계획 시트 초기화 완료!")
            QMessageBox.information(self, "완료", "시트가 성공적으로 초기화되었습니다.")
            
        except Exception as e:
            self.measure_plan_log(f"🔴 오류 발생: {e}")
            QMessageBox.critical(self, "오류", f"초기화 중 오류가 발생했습니다:\n{e}")
        finally:
            pythoncom.CoUninitialize()

    def measure_plan_survey_slot(self):
        """[핵심 4] 예비조사 참고 데이터 취합 실행"""
        excel_path = self.edit_excel.text().strip()
        sheet_name = self.combo_measure_sheet.currentText().strip() or "측정계획(양식)"
        
        if not excel_path or not os.path.exists(excel_path):
            QMessageBox.warning(self, "경고", "올바른 엑셀 경로를 지정해 주세요.")
            return
            
        if not sheet_name:
            sheet_name = "측정계획(양식)"
            
        # 백업 실행
        if not self.run_backup_engine(excel_path):
            return
            
        import win32com.client
        import pythoncom
        
        pythoncom.CoInitialize()
        excel = None
        wb = None
        
        try:
            self.measure_plan_log("[*] Excel 인스턴스 획득 중...")
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except:
                excel = win32com.client.Dispatch("Excel.Application")
                excel.Visible = True
                
            abs_excel_path = os.path.abspath(excel_path)
            excel_filename = os.path.basename(excel_path)
            
            for w in excel.Workbooks:
                try:
                    if w.FullName.lower() == abs_excel_path.lower() or w.Name.lower() == excel_filename.lower():
                        wb = w
                        break
                except:
                    continue
                    
            if wb is None:
                wb = excel.Workbooks.Open(abs_excel_path)
                excel.Visible = True
                
            wsPlan = wb.Worksheets(sheet_name)
            
            # 예비조사_참고 시트 조회 및 없으면 신규 생성
            wsRef = None
            for s in wb.Worksheets:
                if s.Name == "예비조사_참고":
                    wsRef = s
                    break
                    
            if wsRef is None:
                # 마지막 시트 뒤에 추가
                wsRef = wb.Worksheets.Add(Before=None, After=wb.Worksheets(wb.Worksheets.Count))
                wsRef.Name = "예비조사_참고"
                self.measure_plan_log("📂 '예비조사_참고' 시트가 존재하지 않아 신규 생성하였습니다.")
                
            # 기존 데이터 삭제 (A3:B마지막행)
            lastRefRow = wsRef.Cells(wsRef.Rows.Count, 1).End(-4162).Row # xlUp
            if lastRefRow >= 3:
                wsRef.Range(wsRef.Cells(3, 1), wsRef.Cells(lastRefRow, 2)).ClearContents()
                
            # 매핑 열 정보 획득
            map_data = self.measure_mapping_panel.get_mapping()
            col_process = map_data.get("공정명 열", "B")
            col_chem = map_data.get("화학물질명 열", "C")
            idx_process = SMUGUI.c2i(col_process)
            idx_chem = SMUGUI.c2i(col_chem)
            
            # 측정계획 시트 데이터 취합
            lastPlanRow = wsPlan.Cells(wsPlan.Rows.Count, idx_chem).End(-4162).Row
            if lastPlanRow < 4:
                lastPlanRow = 4
                
            self.measure_plan_log("🟢 예비조사 데이터 수집 중...")
            
            data_dict = {}
            for i in range(4, lastPlanRow + 1):
                processName = str(wsPlan.Cells(i, idx_process).Value or "").strip()
                factors = str(wsPlan.Cells(i, idx_chem).Value or "").strip()
                
                if not factors:
                    break
                if not processName:
                    continue
                    
                # 쉼표 구분자로 통일
                factors_clean = factors.replace("; ", ", ").strip()
                
                if processName not in data_dict:
                    data_dict[processName] = []
                
                # 물질 쪼개기 및 중복 제거 수집
                factor_arr = [x.strip() for x in factors_clean.split(", ") if x.strip()]
                for f in factor_arr:
                    if f and f not in data_dict[processName]:
                        data_dict[processName].append(f)
                        
            # 결과 기입 (A3부터 시작)
            outputRow = 3
            for key, val_list in data_dict.items():
                wsRef.Cells(outputRow, 1).Value = key
                wsRef.Cells(outputRow, 2).Value = ", ".join(val_list)
                wsRef.Cells(outputRow, 2).WrapText = True
                
                # 행 높이 AutoFit 및 최소 높이 25 보장
                wsRef.Rows(outputRow).AutoFit()
                if wsRef.Rows(outputRow).RowHeight < 25:
                    wsRef.Rows(outputRow).RowHeight = 25
                outputRow += 1
                
            # 컬럼 자동 조정
            wsRef.Columns("A:B").AutoFit()
            
            wb.Save()
            self.measure_plan_log("🟢 예비조사 데이터 취합 완료!")
            QMessageBox.information(self, "완료", "예비조사 참고자료 데이터 취합이 성공적으로 완료되었습니다!")
            
        except Exception as e:
            self.measure_plan_log(f"🔴 오류 발생: {e}")
            QMessageBox.critical(self, "오류", f"데이터 취합 중 오류가 발생했습니다:\n{e}")
        finally:
            pythoncom.CoUninitialize()

    def _update_substance_clean_info(self):
        """환경 설정에서 연동된 엑셀 파일 및 시트명 갱신"""
        path = self.edit_excel.text().strip()
        
        if path:
            self.lbl_clean_excel_path.setText(path)
            if self.combo_clean_sheet.count() == 0:
                self._update_sheet_list(path)
        else:
            self.lbl_clean_excel_path.setText("환경 설정에서 결과를 저장할 엑셀 파일을 선택하세요.")

    def open_current_excel(self):
        """현재 설정된 엑셀 파일을 열린 상태로 실행"""
        path = self.edit_excel.text().strip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "경고", "올바른 엑셀 경로를 지정해 주세요.")
            return
            
        try:
            import win32com.client
            excel = None
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except:
                excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = True
            
            # 이미 열려있는 통합문서 확인
            wb_opened = False
            abs_path = os.path.abspath(path)
            for wb in excel.Workbooks:
                try:
                    if wb.FullName.lower() == abs_path.lower():
                        wb_opened = True
                        break
                except:
                    continue
            if not wb_opened:
                excel.Workbooks.Open(abs_path)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"엑셀 파일을 여는 중 오류가 발생했습니다: {e}")

    def search_substance_db(self):
        """[V24.3.5.0] 화학물질 마스터 DB 조회 및 관계 필터 메서드"""
        keyword = self.edit_search_keyword.text().strip()
        if not keyword:
            self.tbl_search_results.setRowCount(0)
            return

        # 마스터 데이터셋 로딩 확인
        if not hasattr(self, 'mes_master_list') or not self.mes_master_list:
            self.load_mes_master()

        if not self.mes_master_list:
            QMessageBox.critical(self, "오류", "msds_index.json 마스터 데이터를 로드할 수 없습니다.")
            return

        # 검색 대상 필터링
        results = []
        for entry in self.mes_master_list:
            name = entry.get("측정대상 물질명", "") or ""
            cas = entry.get("CAS No.", "") or ""
            if keyword.lower() in name.lower() or keyword.lower() in cas.lower():
                results.append(entry)

        # 동일 CAS 번호별 관계 분석용 임시 매핑 구축
        # 전체 DB를 돌며 CAS 번호별 모든 형제 목록 수집
        cas_siblings = {}
        for entry in self.mes_master_list:
            c = str(entry.get("CAS No.", "")).strip()
            n = str(entry.get("측정대상 물질명", "")).strip()
            if c and c.lower() != 'nan' and n:
                if c not in cas_siblings:
                    cas_siblings[c] = set()
                cas_siblings[c].add(n)

        self.tbl_search_results.setRowCount(len(results))
        for row_idx, entry in enumerate(results):
            code = entry.get("정렬코드", "") or ""
            name = entry.get("측정대상 물질명", "") or ""
            cas = entry.get("CAS No.", "") or ""
            twa = entry.get("노출기준(TWA)", "") or ""
            spec = entry.get("비고", "") or ""

            # 관계 유형 분석
            rel_type = "단일 (대표명)"
            cas_strip = cas.strip()
            if cas_strip in cas_siblings:
                siblings = list(cas_siblings[cas_strip])
                if len(siblings) > 1:
                    # 이름 길이 비교: 가장 짧은 것을 부모(대표명)로 판정, 나머지는 자식(상세명)
                    sorted_siblings = sorted(siblings, key=len)
                    parent_name = sorted_siblings[0]
                    if name == parent_name:
                        rel_type = "부모 (대표명)"
                    elif parent_name in name:
                        rel_type = "자식 (상세명)"
                    else:
                        rel_type = "이명 (동의어)"

            self.tbl_search_results.setItem(row_idx, 0, QTableWidgetItem(str(code)))
            self.tbl_search_results.setItem(row_idx, 1, QTableWidgetItem(str(name)))
            self.tbl_search_results.setItem(row_idx, 2, QTableWidgetItem(str(cas)))
            self.tbl_search_results.setItem(row_idx, 3, QTableWidgetItem(str(twa)))
            self.tbl_search_results.setItem(row_idx, 4, QTableWidgetItem(rel_type))
            self.tbl_search_results.setItem(row_idx, 5, QTableWidgetItem(str(spec)))

    def clean_log(self, text):
        """한글 진행 로그 출력 및 화면 강제 갱신"""
        self.log_view.append(f"[{datetime.now().strftime('%H:%M:%S')}] [정리] {text}")
        self.log_view.moveCursor(QTextCursor.End)
        QApplication.processEvents()

    def clean_substances_excel(self):
        """이미 열려있는 엑셀을 직접 제어하여 물질명을 정렬하고 오타를 교정"""
        excel_path = self.edit_excel.text().strip()
        sheet_name = self.combo_clean_sheet.currentText().strip() or "Sheet1"
        
        if not excel_path or not os.path.exists(excel_path):
            QMessageBox.warning(self, "경고", "올바른 엑셀 경로를 지정해 주세요.")
            return
            
        # 마스터 데이터셋 로딩 확인
        if not hasattr(self, 'mes_master_list') or not self.mes_master_list:
            self.clean_log("[*] msds_index.json 마스터 데이터를 로드합니다...")
            self.load_mes_master()
            
        if not self.mes_master_list:
            QMessageBox.critical(self, "오류", "msds_index.json을 로드할 수 없어 작업을 진행할 수 없습니다.")
            return

        self.log_view.clear()
        self.clean_log("🟢 화학물질 정렬 및 교정 작업 시작...")
        
        import win32com.client
        import pythoncom
        import difflib
        
        # 마스터 데이터 셋업
        def normalize_name(name):
            if not name:
                return ""
            return re.sub(r'\s+', '', name).lower()

        # [수정 후 대체 코드] 마스터DB의 측정대상 물질명과 별칭을 모두 검증 집합에 등록
        valid_substances = set()
        for entry in self.mes_master_list:
            name = entry.get("측정대상 물질명", "").strip()
            if name:
                valid_substances.add(name)
            
            # 마스터DB의 별칭(리스트 형식)을 검증 대상에 포함
            aliases = entry.get("별칭")
            if isinstance(aliases, list):
                for alias in aliases:
                    alias_clean = str(alias).strip()
                    if alias_clean:
                        valid_substances.add(alias_clean)

        valid_substances_clean = {normalize_name(name) for name in valid_substances}

        def extract_pure_substance_name(item):
            if not item:
                return ""
            # 1. 소괄호 내용(함유량 등) 제거
            text = re.sub(r'\(.*?\)', '', item).strip()
            
            # 2. 메인 카테고리 접두사 제거
            for prefix in ["측정 비대상", "단시간 및 임시작업", "보관", "허용소비량 미만"]:
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
                    
            # 3. 서브 수식어([특별], [특검], [허가]) 제거 (대괄호와 함께 매칭하여 세척)
            text = re.sub(r'\[특별\]|\[특검\]|\[허가\]', '', text).strip()
            
            # 4. 남아있는 모든 대괄호 제거
            text = text.replace("[", "").replace("]", "").strip()
            return text

        def get_core_chemical_name(name):
            if not name:
                return ""
            core = name
            suffixes = [
                "및 그 가용성 화합물",
                "및 그 화합물",
                "및 화합물",
                " 및 그 가용성 화합물",
                " 및 그 화합물",
                " 및 화합물",
                "(석면불포함)",
                "석면불포함",
                " 계열",
                "계열",
                " 유기화합물",
                " 무기화합물"
            ]
            for suf in sorted(suffixes, key=len, reverse=True):
                if suf in core:
                    core = core.replace(suf, "")
            return core.strip()

        def split_i_val(i_val):
            if not i_val:
                return []
            
            # 소괄호() 및 대괄호[] 안의 세미콜론(;)을 임시 치환하여 괄호 안 쪼개짐 방지
            chars = list(i_val)
            in_paren = 0
            in_bracket = 0
            for i, ch in enumerate(chars):
                if ch == '(': in_paren += 1
                elif ch == ')': in_paren -= 1
                elif ch == '[': in_bracket += 1
                elif ch == ']': in_bracket -= 1
                elif ch == ';' and (in_paren > 0 or in_bracket > 0):
                    chars[i] = '\u0001'
            
            protected_val = "".join(chars)
            
            # 세미콜론 기준으로만 분리 (화학식 내부의 쉼표 보존을 위해 쉼표 분리 로직은 완전 제거)
            raw_splits = []
            for part in re.split(r';', protected_val):
                part = part.strip()
                if not part:
                    continue
                raw_splits.append(part.replace('\u0001', ';'))
                
            final_items = []
            for part in raw_splits:
                matched_prefix = None
                for prefix in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
                    if part.startswith(prefix):
                        matched_prefix = prefix
                        break
                        
                if matched_prefix:
                    # 대괄호/소괄호 내부의 알맹이 내용 추출
                    inner_content = part[len(matched_prefix):].strip()
                    if inner_content.startswith("[") and inner_content.endswith("]"):
                        inner_content = inner_content[1:-1].strip()
                    elif inner_content.startswith("(") and inner_content.endswith(")"):
                        inner_content = inner_content[1:-1].strip()
                    
                    # 대괄호 내부도 세미콜론 기준으로만 분리
                    sub_parts = re.split(r';', inner_content)
                    for sub_p in sub_parts:
                        sub_p = sub_p.strip()
                        if sub_p:
                            final_items.append(f"{matched_prefix}[{sub_p}]")
                else:
                    final_items.append(part)
            return final_items

        def parse_substance_item(item):
            item = item.strip()
            if not item:
                return None
            
            # 메인 카테고리 접두사 분리
            category = "측정대상"
            for prefix in ["측정 비대상", "단시간 및 임시작업", "허용소비량 미만", "보관"]:
                if item.startswith(prefix):
                    category = prefix
                    item = item[len(prefix):].strip()
                    break
                    
            # 겉껍데기 대괄호 탈착
            if item.startswith("[") and item.endswith("]"):
                item = item[1:-1].strip()
                
            # 서브 접두사 분리 (특별, 허가, 특검 수식어)
            sub_prefix = ""
            for sub in ["[특별]", "[허가]", "[특검]"]:
                if item.startswith(sub):
                    sub_prefix = sub
                    item = item[len(sub):].strip()
                    break
                    
            # 🚨 [V24.3.4.0] 괄호 분리 로직 완전 제거. 풀네임 자체를 보존
            pure_name = item.replace("[", "").replace("]", "").strip()
            
            return {
                "category": category,
                "sub_prefix": sub_prefix,
                "pure_name": pure_name,
                "suffix": ""
            }
        substance_sort_map = {}
        substance_info_map = {}
        for entry in self.mes_master_list:
            name = entry.get("측정대상 물질명", "").strip()
            code = entry.get("정렬코드", "").strip()
            if name:
                if name not in substance_sort_map:
                    substance_sort_map[name] = code
                # 특별, 허가, 특검, 측정 정보 취합
                if name not in substance_info_map:
                    substance_info_map[name] = {
                        "특별관리": entry.get("특별관리") or "",
                        "허가대상": entry.get("허가대상") or "",
                        "특검": entry.get("특검") or "",
                        "측정": entry.get("측정") or ""
                    }
                else:
                    # 중복 물질의 경우 특별이나 허가 등이 하나라도 있으면 우대 적용
                    existing = substance_info_map[name]
                    if entry.get("특별관리") == "○": existing["특별관리"] = "○"
                    if entry.get("허가대상") == "○": existing["허가대상"] = "○"
                    if entry.get("특검") == "○": existing["특검"] = "○"
                    if entry.get("측정") == "○": existing["측정"] = "○"

        # CAS 번호 기반 역방향 맵 구축 (동일 CAS 형제 물질 탐색용)
        cas_to_names = {}  # CAS번호 -> [물질명1, 물질명2, ...]
        name_to_cas = {}   # 물질명 -> CAS번호
        for entry in self.mes_master_list:
            name = entry.get("측정대상 물질명", "").strip()
            cas = entry.get("CAS No.", "").strip()
            if name and cas:
                name_to_cas[name] = cas
                if cas not in cas_to_names:
                    cas_to_names[cas] = []
                if name not in cas_to_names[cas]:
                    cas_to_names[cas].append(name)

        pythoncom.CoInitialize()
        excel = None
        wb = None
        try:
            self.clean_log("[*] Excel 인스턴스 획득 중...")
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except:
                excel = win32com.client.Dispatch("Excel.Application")
                excel.Visible = True
                
            abs_excel_path = os.path.abspath(excel_path)
            excel_filename = os.path.basename(excel_path)
            
            # 이미 열려있는 파일인지 체크
            for w in excel.Workbooks:
                try:
                    if w.FullName.lower() == abs_excel_path.lower() or w.Name.lower() == excel_filename.lower():
                        wb = w
                        break
                except:
                    continue
                    
            if wb is None:
                self.clean_log(f"[*] 엑셀 파일 오픈: {excel_filename}")
                wb = excel.Workbooks.Open(abs_excel_path)
                excel.Visible = True
                
            ws = wb.Worksheets(sheet_name)
            
            try:
                st_row = int(self.edit_start_row.text())
            except:
                st_row = 3
                
            # 데이터 행 감지
            max_row = ws.UsedRange.Rows.Count + ws.UsedRange.Row - 1
            if max_row < st_row:
                self.clean_log("[!] 처리할 데이터가 존재하지 않습니다.")
                return
                
            self.clean_log(f"[*] 처리 대상 범위: {st_row}행 ~ {max_row}행")
            
            # 캐시의 correction_rules 사전 확보 (없으면 생성)
            if not hasattr(self, 'cache') or self.cache is None:
                self.cache = {}
            if "correction_rules" not in self.cache:
                self.cache["correction_rules"] = {}
            correction_rules = self.cache["correction_rules"]
            
            all_apply = False
            all_skip = False
            
            for r in range(st_row, max_row + 1):
                i_cell = ws.Cells(r, 9) # I열 (비고)
                j_cell = ws.Cells(r, 10) # J열 (MSDS)
                g_cell = ws.Cells(r, 7) # G열 (월취급량)
                n_cell = ws.Cells(r, 14) # N열 (1차 결과 전체)
                
                i_val = str(i_cell.Value or "").strip()
                j_val = str(j_cell.Value or "").strip()
                g_raw = str(g_cell.Value or "").strip()
                n_val = str(n_cell.Value or "").strip()
                
                # 수치가 실질적으로 0(0.0, 0 등)인지 판별하는 헬퍼
                def is_zero_value(val_str):
                    try:
                        clean_val = val_str.replace(" ", "").replace(",", "")
                        if not clean_val:
                            return False
                        return float(clean_val) == 0.0
                    except:
                        return False
                
                is_g_zero = is_zero_value(g_raw)
                
                # 1차 결과에서 유효한 CAS 번호와 함께 추출된 물질명 수집
                api_valid_substances = set()
                for m in re.finditer(r'([^[;]+)\[([^(\]]+)(?:\(([^)]*)\))?\]', n_val):
                    sub_name = m.group(1).strip()
                    cas_no = m.group(2).strip()
                    if cas_no and re.match(r'^\d+-\d+-\d+$', cas_no):
                        api_valid_substances.add(normalize_name(sub_name))
                
                if not i_val and not j_val:
                    continue
                    
                i_items = split_i_val(i_val)
                j_items = [x.strip() for x in j_val.split(";") if x.strip()]
                
                # 순수 물질명을 매치메이커 삼아 지능형 일대일 매칭 진행
                used_j_indices = set()
                paired_data = []
                
                for i_item in i_items:
                    parsed_i = parse_substance_item(i_item)
                    i_pure = parsed_i["pure_name"] if parsed_i else extract_pure_substance_name(i_item)
                    matched_j_item = None
                    matched_idx = -1
                    
                    # 1차 완전 일치 검사
                    for idx, j_item in enumerate(j_items):
                        if idx in used_j_indices:
                            continue
                        j_pure = extract_pure_substance_name(j_item)
                        if i_pure == j_pure:
                            matched_j_item = j_item
                            matched_idx = idx
                            break
                            
                    # 2차 부분 포함 일치 검사
                    if matched_j_item is None:
                        for idx, j_item in enumerate(j_items):
                            if idx in used_j_indices:
                                continue
                            j_pure = extract_pure_substance_name(j_item)
                            if i_pure and j_pure and (i_pure in j_pure or j_pure in i_pure):
                                matched_j_item = j_item
                                matched_idx = idx
                                break
                                
                    # 3차 핵심 단어 포함 검사 (예: "바륨 및 그 가용성 화합물" -> "바륨" 이 "염화 바륨"에 포함되는지)
                    if matched_j_item is None:
                        i_core = get_core_chemical_name(i_pure)
                        if i_core:
                            for idx, j_item in enumerate(j_items):
                                if idx in used_j_indices:
                                    continue
                                j_pure = extract_pure_substance_name(j_item)
                                j_core = get_core_chemical_name(j_pure)
                                if (i_core in j_pure) or (j_core in i_pure):
                                    matched_j_item = j_item
                                    matched_idx = idx
                                    break
                                
                    if matched_j_item is not None:
                        used_j_indices.add(matched_idx)
                    else:
                        matched_j_item = ""
                        
                    paired_data.append((i_item, matched_j_item))
                    
                # 매칭 실패로 낙오된 J열 성분들을 추가
                for idx, j_item in enumerate(j_items):
                    if idx not in used_j_indices:
                        paired_data.append(("", j_item))
                        
                row_data = []
                for i_item, j_item in paired_data:
                    # I열 항목이 아예 비어있어 매칭 불능인 낙오 물질 처리
                    if not i_item:
                        self.clean_log(f"⚠️ {r}행: J열 성분 '{j_item}'에 상응하는 비고(I열) 매칭 물질이 누락되어 [누락]으로 표시합니다.")
                        row_data.append({
                            "i_item_final": "[누락]",
                            "j_item": j_item,
                            "category": "측정대상",
                            "sort_code": "ZZZZZZ",
                            "is_red": True
                        })
                        continue
                        
                    parsed_i = parse_substance_item(i_item)
                    if not parsed_i:
                        continue
                    i_sub = parsed_i["pure_name"]
                    category = parsed_i["category"]
                    
                    # 🚨 [V24.3.4.0] 빈 물질명 필터링: 괄호만 존재하여 pure_name이 비어 있는 비정상 고아 항목 무시
                    if not i_sub:
                        self.clean_log(f"⚠️ [건너뜀] {r}행: 알맹이 이름이 없는 고아 항목 '{i_item}' 감지되어 제외 조치합니다.")
                        continue
                    
                    # 🚨 [V24.3.4.0] 영구 교정 기억 장치(사전) 조회 및 자동 대체
                    i_sub_norm = normalize_name(i_sub)
                    if i_sub_norm in correction_rules:
                        corrected_val = correction_rules[i_sub_norm]
                        if corrected_val != i_sub:
                            self.clean_log(f"[*] {r}행: 캐시된 오타 교정 규칙 적용 '{i_sub}' -> '{corrected_val}'")
                            i_sub = corrected_val
                            i_sub_norm = normalize_name(i_sub)
                            
                    # [V24.3.5.0] 지능형 부모-자식 자동 교정 규칙 적용
                    cas = name_to_cas.get(i_sub, "")
                    if cas:
                        siblings = cas_to_names.get(cas, [])
                        # 🚨 [V24.3.5.2] 활석/소우프스톤 계열(CAS 14807-96-6)은 자동 교정에서 강제 제외
                        if cas == "14807-96-6":
                            pass
                        elif len(siblings) > 1:
                            # 동일 CAS를 가진 형제들 중 가장 짧은 명칭을 부모명으로 판단
                            sorted_siblings = sorted(siblings, key=len)
                            parent_name = sorted_siblings[0]
                            if i_sub == parent_name:
                                # 부모명이 자식명 텍스트 내에 포함되는 실질 상세 자식명만 필터링하여 이명(예: 소우프스톤 등)과의 간섭 차단
                                children = [s for s in siblings if s != parent_name and parent_name in s]
                                if len(children) == 1:
                                    target_child = children[0]
                                    self.clean_log(f"[*] {r}행: 부모 물질명 '{i_sub}' ➔ 자식 표준명 '{target_child}' 자동 교정 적용 (유일 자식)")
                                    i_sub = target_child
                                    i_sub_norm = normalize_name(i_sub)

                    # 마스터 DB 표준 풀네임 집합 대조
                    # 🚨 [V24.3.5.2] 활석/소우프스톤 계열(CAS 14807-96-6) 중 대표 부모명("활석")인 경우에만 수동 팝업 강제 호출
                    is_talc_parent = (cas == "14807-96-6" and i_sub == "활석")
                    if i_sub_norm in valid_substances_clean and not is_talc_parent:
                        # 1단계: 사용자 기재 신뢰 (Zero-Popup Pass)
                        pass
                    else:
                        # 마스터 DB에 정확히 일치하지 않거나, 예외 강제 팝업 케이스
                        cas = name_to_cas.get(i_sub, "")
                        candidates = []
                        is_multi_regulation = False
                        
                        if cas:
                            siblings = cas_to_names.get(cas, [])
                            # 🚨 [V24.3.5.2] 활석/소우프스톤 계열은 대표 부모명인 '활석'을 제외하고 팝업 후보 구성
                            if cas == "14807-96-6":
                                candidates = [s for s in siblings if s != "활석"]
                                is_multi_regulation = True
                            # 2단계: 동일 CAS 형제들의 TWA 규제 조건 상이 여부 분석
                            elif len(siblings) > 1:
                                twa_sets = set()
                                for sib in siblings:
                                    info = substance_info_map.get(sib, {})
                                    twa_sets.add((
                                        info.get("특별관리", ""),
                                        info.get("허가대상", ""),
                                        info.get("특검", ""),
                                        info.get("측정", ""),
                                        substance_sort_map.get(sib, "ZZZZZZ")
                                    ))
                                if len(twa_sets) > 1:
                                    candidates = siblings
                                    is_multi_regulation = True
                                else:
                                    # 규제 조건이 동일하다면 대표 성상명으로 자동 매핑
                                    i_sub = siblings[0]
                                    i_sub_norm = normalize_name(i_sub)
                            else:
                                candidates = siblings
                                
                        # CAS 번호가 없거나, 성상 분기가 불필요하며, 여전히 마스터 DB에 없는 오타인 경우
                        if not candidates:
                            # 3단계: 유사도 임계치 cutoff=0.8로 상향하여 오타 후보 구축
                            candidates = list(difflib.get_close_matches(i_sub, list(valid_substances), n=3, cutoff=0.8))
                            for vname in valid_substances:
                                if vname not in candidates and (i_sub in vname or vname in i_sub):
                                    if len(vname) - len(i_sub) in [-2, -1, 0, 1, 2]:
                                        candidates.append(vname)
                                        
                        # 교정 대화상자 호출
                        if candidates and not all_skip:
                            if all_apply:
                                proposed = candidates[0]
                                self.clean_log(f"[교정] {r}행: '{i_sub}' -> '{proposed}' (자동 적용)")
                                i_sub = proposed
                                i_sub_norm = normalize_name(i_sub)
                            else:
                                title = "동일 CAS 다중 규제 물질 선택" if is_multi_regulation else "물질명 오타 교정 제안"
                                dlg = SubstanceCorrectionDialog(r, i_sub, candidates, parent=self)
                                dlg.setWindowTitle(title)
                                dlg.exec_()
                                
                                if dlg.result_action in (SubstanceCorrectionDialog.RESULT_APPLY, SubstanceCorrectionDialog.RESULT_ALL_APPLY):
                                    self.clean_log(f"[교정] {r}행: '{i_sub}' -> '{dlg.corrected_name}' (적용)")
                                    
                                    # 영구 교정 기억 사전에 매핑 정보 등록
                                    i_item_raw_norm = normalize_name(i_sub)
                                    correction_rules[i_item_raw_norm] = dlg.corrected_name
                                    self.save_cache() # 캐시 파일 영구 저장
                                    
                                    i_sub = dlg.corrected_name
                                    i_sub_norm = normalize_name(i_sub)
                                    
                                    if dlg.result_action == SubstanceCorrectionDialog.RESULT_ALL_APPLY:
                                        all_apply = True
                                elif dlg.result_action == SubstanceCorrectionDialog.RESULT_ALL_SKIP:
                                    all_skip = True
                                    self.clean_log(f"[교정] {r}행: '{i_sub}' (이후 모두 건너뛰기 활성화)")
                                else:
                                    self.clean_log(f"[교정] {r}행: '{i_sub}' (건너뜀)")
                                    
                    # 마스터 데이터셋을 바탕으로 수식어 자동 복원 및 우선순위 매핑
                    info = substance_info_map.get(i_sub)
                    sub_prefix = ""
                    if info:
                        is_special = str(info.get("특별관리") or "").strip() == "○"
                        is_permit = str(info.get("허가대상") or "").strip() == "○"
                        is_exam = str(info.get("특검") or "").strip() == "○"
                        is_measure = str(info.get("측정") or "").strip() == "○"
                        
                        if is_special:
                            sub_prefix = "[특별]"
                        elif is_permit:
                            sub_prefix = "[허가]"
                        elif is_exam and not is_measure:
                            sub_prefix = "[특검]"
                    else:
                        sub_prefix = parsed_i["sub_prefix"]
                        
                    # 최종 교정된 물질명 재합성 (괄호 분리를 삭제했으므로 suffix는 붙이지 않음)
                    i_item_final = f"{sub_prefix}{i_sub}"
                    
                    # 정렬 코드 정보 조회
                    sort_code = substance_sort_map.get(i_sub)
                    
                    is_red = False
                    # 최종 완성된 물질명이 마스터 DB 표준 리스트에 없고, 1차 결과(N열) CAS 목록에도 없다면 명백하게 오류(적색 마킹)
                    if i_sub_norm not in valid_substances_clean and i_sub_norm not in api_valid_substances:
                        sort_code = "ZZZZZZ"
                        is_red = True
                        
                    # 🚨 [V24.3.5.3] J열에 함유량(%)이 누락되어 있거나 비어 있는 경우 명백하게 오류(적색 마킹)
                    if not j_item or "%" not in j_item:
                        is_red = True
                        
                    # 🚨 [V24.3.5.6] 보관 카테고리인데 월취급량(G열)이 0이 아니면 비즈니스 룰 위반 오류(적색 마킹)
                    if category == "보관" and not is_g_zero:
                        is_red = True
                        self.clean_log(f"⚠️ {r}행: '보관' 성분 '{i_sub}'이 존재하나 G열(월취급량: '{g_raw}')이 '0'이 아닙니다.")
                        
                    row_data.append({
                        "i_item_final": i_item_final,
                        "j_item": j_item,
                        "category": category,
                        "sort_code": sort_code,
                        "is_red": is_red
                    })
                    
                # 정렬코드로 통합 정렬
                row_data.sort(key=lambda x: x["sort_code"])
                
                # 🚨 [V24.3.5.5] I열/J열 정교한 실시간 인덱스 기반 조립 및 적색/청색 마킹 좌표 추출
                new_i_val = ""
                new_j_val = ""
                red_marks_i = []
                red_marks_j = []
                blue_marks_i = []
                blue_marks_j = []
                
                group_definitions = [
                    ("측정대상", "; ", ""),
                    ("측정 비대상", "; ", "측정 비대상["),
                    ("단시간 및 임시작업", "; ", "단시간 및 임시작업["),
                    ("허용소비량 미만", "; ", "허용소비량 미만["),
                    ("보관", "; ", "보관[")
                ]
                
                # J열 성분을 수식어, 물질명, 함유량으로 정밀 분리하기 위한 패턴
                j_parser_pat = re.compile(r"^(?:(\[특별\]|\[특검\]|\[허가\]))?(.*?)(?:\(([^)]*)\))?$")
                
                first_i = True
                first_j = True
                for cat_name, sep, wrapper in group_definitions:
                    cat_items = [x for x in row_data if x["category"] == cat_name]
                    valid_cat_items_i = [x for x in cat_items if x["i_item_final"]]
                    valid_cat_items_j = [x for x in cat_items if x["j_item"]]
                    
                    if not valid_cat_items_i and not valid_cat_items_j:
                        continue
                        
                    # 1. I열 정교한 실시간 조립 및 오프셋 마킹 계산
                    if valid_cat_items_i:
                        if not first_i:
                            new_i_val += "; "
                        first_i = False
                        
                        if wrapper:
                            new_i_val += wrapper
                            
                        for idx, item in enumerate(valid_cat_items_i):
                            if idx > 0:
                                new_i_val += sep
                            i_item_final = item["i_item_final"]
                            if i_item_final:
                                # 수식어 추출
                                sub_prefix = ""
                                for sp in ["[특별]", "[특검]", "[허가]"]:
                                    if i_item_final.startswith(sp):
                                        sub_prefix = sp
                                        break
                                pure_sub_name = i_item_final[len(sub_prefix):]
                                
                                # 수식어([특별] 등)는 항상 파란색 강조
                                if sub_prefix:
                                    start_pos = len(new_i_val) + 1
                                    blue_marks_i.append((start_pos, len(sub_prefix)))
                                    new_i_val += sub_prefix
                                    
                                # 순수 물질명은 마스터 DB 표준명에 없거나, 또는 비즈니스 룰 위반 오류(is_red == True)인 경우 빨간색 강조 (1차 결과 CAS 포함 완화)
                                if pure_sub_name:
                                    pure_sub_norm = normalize_name(pure_sub_name)
                                    is_i_red = False
                                    if pure_sub_norm not in valid_substances_clean and pure_sub_norm not in api_valid_substances:
                                        is_i_red = True
                                    if item.get("is_red", False):
                                        is_i_red = True
                                        
                                    if is_i_red:
                                        start_pos = len(new_i_val) + 1
                                        red_marks_i.append((start_pos, len(pure_sub_name)))
                                    new_i_val += pure_sub_name
                                    
                        if wrapper:
                            new_i_val += "]"
                            
                    # 2. J열 정교한 실시간 조립 및 오프셋 마킹 계산 (I열 순서와 1:1 완벽 동기화)
                    if valid_cat_items_j:
                        if not first_j:
                            new_j_val += "; "
                        first_j = False
                        
                        for idx, item in enumerate(valid_cat_items_j):
                            if idx > 0:
                                new_j_val += "; "
                            j_item = item["j_item"]
                            if j_item:
                                match = j_parser_pat.match(j_item)
                                if match:
                                    sub_prefix = match.group(1) or ""
                                    pure_sub_name = match.group(2) or ""
                                    concentration = match.group(3) or ""
                                    
                                    # 수식어는 항상 파란색 강조
                                    if sub_prefix:
                                        start_pos = len(new_j_val) + 1
                                        blue_marks_j.append((start_pos, len(sub_prefix)))
                                        new_j_val += sub_prefix
                                        
                                    # 물질명 마킹 (마스터 DB에 없거나, 함유량이 아예 누락되었거나, 비즈니스 룰 위반 오류인 경우 빨간색, 1차 결과 CAS 포함 완화)
                                    if pure_sub_name:
                                        pure_sub_norm = normalize_name(pure_sub_name)
                                        is_sub_red = False
                                        if pure_sub_norm not in valid_substances_clean and pure_sub_norm not in api_valid_substances:
                                            is_sub_red = True
                                        if match.group(3) is None or not concentration.strip():
                                            is_sub_red = True
                                        if item.get("is_red", False):
                                            is_sub_red = True
                                            
                                        if is_sub_red:
                                            start_pos = len(new_j_val) + 1
                                            red_marks_j.append((start_pos, len(pure_sub_name)))
                                        new_j_val += pure_sub_name
                                        
                                    # 함유량 마킹 (함유량이 존재하지만 % 기호가 없거나 비어있는 경우 빨간색)
                                    if match.group(3) is not None:
                                        paren_content = f"({concentration})"
                                        is_conc_red = ("%" not in concentration or not concentration.strip())
                                        start_pos = len(new_j_val) + 1
                                        if is_conc_red:
                                            red_marks_j.append((start_pos, len(paren_content)))
                                        new_j_val += paren_content
                                else:
                                    # 매칭 예외 시 전체 적색 폴백 마킹
                                    start_pos = len(new_j_val) + 1
                                    red_marks_j.append((start_pos, len(j_item)))
                                    new_j_val += j_item
                                
                # 🚨 [V24.3.5.4] 셀 서식 및 맞춤 속성 사전 백업
                def backup_cell_format(cell):
                    try:
                        return {
                            "HorizontalAlignment": cell.HorizontalAlignment,
                            "VerticalAlignment": cell.VerticalAlignment,
                            "WrapText": cell.WrapText,
                            "ShrinkToFit": cell.ShrinkToFit,
                            "FontName": cell.Font.Name,
                            "FontSize": cell.Font.Size,
                            "FontBold": cell.Font.Bold,
                            "FontItalic": cell.Font.Italic,
                            "FontUnderline": cell.Font.Underline,
                            "FontColor": cell.Font.Color
                        }
                    except Exception as e:
                        self.clean_log(f"⚠️ 셀 서식 백업 실패: {e}")
                        return None

                def restore_cell_format(cell, fmt):
                    if not fmt:
                        return
                    try:
                        cell.HorizontalAlignment = fmt["HorizontalAlignment"]
                        cell.VerticalAlignment = fmt["VerticalAlignment"]
                        cell.WrapText = fmt["WrapText"]
                        cell.ShrinkToFit = fmt["ShrinkToFit"]
                        cell.Font.Name = fmt["FontName"]
                        cell.Font.Size = fmt["FontSize"]
                        cell.Font.Bold = fmt["FontBold"]
                        cell.Font.Italic = fmt["FontItalic"]
                        cell.Font.Underline = fmt["FontUnderline"]
                        # 🚨 [V24.3.5.5] 이전 에러 마킹 색상(적색: 255, 청색: 16711680)은 복원하지 않고 검은색(0)으로 초기화
                        if fmt["FontColor"] not in [0, 255, 16711680, -4105]:
                            cell.Font.Color = fmt["FontColor"]
                        else:
                            cell.Font.Color = 0
                    except Exception as e:
                        self.clean_log(f"⚠️ 셀 서식 복원 실패: {e}")

                i_fmt = backup_cell_format(i_cell)
                j_fmt = backup_cell_format(j_cell)

                # 최종 셀 값 대입
                i_cell.Value = new_i_val
                j_cell.Value = new_j_val
                
                # 🚨 [V24.3.5.4] 셀 서식 복원 (일괄 리셋 제거)
                restore_cell_format(i_cell, i_fmt)
                restore_cell_format(j_cell, j_fmt)
                
                # I열 셀 부분 마킹 적용 (단일 셀 동적 바인딩)
                try:
                    import win32com.client.dynamic
                    i_cell_dyn = win32com.client.dynamic.Dispatch(i_cell._oleobj_)
                    i_cell_dyn._FlagAsMethod("Characters")
                except Exception as e:
                    i_cell_dyn = i_cell
                    self.clean_log(f"⚠️ I열 동적 디스패치 래핑 실패: {e}")
                    
                for start, length in red_marks_i:
                    try:
                        i_cell_dyn.Characters(start, length).Font.Color = 255
                    except Exception as ce:
                        self.clean_log(f"⚠️ I열 적색 서식 적용 실패 (위치 {start}): {ce}")
                        
                for start, length in blue_marks_i:
                    try:
                        i_cell_dyn.Characters(start, length).Font.Color = 16711680
                    except Exception as ce:
                        self.clean_log(f"⚠️ I열 청색 서식 적용 실패 (위치 {start}): {ce}")
                        
                # J열 셀 부분 마킹 적용 (단일 셀 동적 바인딩)
                try:
                    import win32com.client.dynamic
                    j_cell_dyn = win32com.client.dynamic.Dispatch(j_cell._oleobj_)
                    j_cell_dyn._FlagAsMethod("Characters")
                except Exception as e:
                    j_cell_dyn = j_cell
                    self.clean_log(f"⚠️ J열 동적 디스패치 래핑 실패: {e}")
                    
                for start, length in red_marks_j:
                    try:
                        j_cell_dyn.Characters(start, length).Font.Color = 255
                    except Exception as ce:
                        self.clean_log(f"⚠️ J열 적색 서식 적용 실패 (위치 {start}): {ce}")
                        
                for start, length in blue_marks_j:
                    try:
                        j_cell_dyn.Characters(start, length).Font.Color = 16711680
                    except Exception as ce:
                        self.clean_log(f"⚠️ J열 청색 서식 적용 실패 (위치 {start}): {ce}")

                # 유아이 반응성 유지
                QApplication.processEvents()
                
            self.clean_log("🟢 화학물질 정리 및 교정 완료!")
            QMessageBox.information(self, "완료", "화학물질 정리 및 교정 프로세스가 정상적으로 완료되었습니다.")
        except Exception as e:
            self.clean_log(f"🔴 오류 발생: {e}")
            err_msg = str(e)
            # 거부(0x8001010A - RPC_E_SERVERCALL_RETRYLATER) 에러에 대한 친절한 처리
            if "거부" in err_msg or "Message filter" in err_msg or "-2147417846" in err_msg or "8001010a" in err_msg.lower():
                QMessageBox.critical(self, "엑셀 편집 오류", 
                                     "엑셀 시트가 편집 모드(셀 더블클릭 상태 등)에 있어서 제어할 수 없습니다.\n"
                                     "엑셀 창에서 Enter 키를 누르거나 편집을 완료(셀 밖 클릭 등)한 후 다시 실행해 주세요.")
            else:
                QMessageBox.critical(self, "오류", f"작업 중 예기치 못한 오류가 발생했습니다:\n{e}")
        finally:
            pythoncom.CoUninitialize()

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
        self.table.cellDoubleClicked.connect(self.on_table_cell_double_clicked)
        
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
        [V15.8.8] 테이블 행 클릭 시 해당 성분이 위치한 PDF 페이지로 자동 이동
        """
        # [V17.3.2.11] 동일 행 내에서 이동 시 페이지 점프 방지 (지연 업데이트 체크)
        if hasattr(self, 'last_selected_row') and self.last_selected_row == row:
            return
        
        # [V17.3.2.11] 다음 이벤트 루프에서 행 번호 업데이트 (sync_pdf_preview와의 간섭 방지)
        QTimer.singleShot(0, lambda: setattr(self, 'last_selected_row', row))

        try:
            target_pdf_path_item = self.table.item(row, COL_IDX_FILEPATH)
            if not target_pdf_path_item: return
            target_pdf_path = target_pdf_path_item.text()
            if not target_pdf_path or not os.path.exists(target_pdf_path): return

            # 1. PDF 로드
            is_new_pdf = False
            if self.preview_pane.current_pdf_path != target_pdf_path:
                self.preview_pane.load_pdf(target_pdf_path)
                is_new_pdf = True

            # 2. 페이지 이동
            page_item = self.table.item(row, COL_IDX_PAGE)
            if page_item and page_item.text().strip():
                try:
                    p_str = re.sub(r'[^0-9]', '', page_item.text())
                    if p_str:
                        target_page = int(p_str)
                        QTimer.singleShot(100, lambda: self.preview_pane.navigate_to_page(target_page))
                except: pass
            elif is_new_pdf:
                self.preview_pane.verticalScrollBar().setValue(0)
        except Exception as e:
            print(f"Row Click Error: {e}")

    def sync_pdf_preview(self):
        """[수정] 선택한 행의 제품명과 일치하는 정확한 PDF 경로 추적"""
        curr_row = self.table.currentRow()
        if curr_row < 0: return
        
        # [V17.3.2.11] 동일 행 내 이동 시 중복 로드 방지 (지연 업데이트 체크)
        if hasattr(self, 'last_selected_row') and self.last_selected_row == curr_row:
            return
        
        # [V17.3.2.11] 다음 이벤트 루프에서 행 번호 업데이트
        QTimer.singleShot(0, lambda: setattr(self, 'last_selected_row', curr_row))

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
            "measure_mapping": self.measure_mapping_panel.get_mapping(),
            "backup_path": self.edit_backup_path.text().strip(),
            "excel_path": self.edit_excel.text().strip(),
            "sheet_name": self.combo_sheet.currentText(),
            "clean_sheet_name": self.combo_clean_sheet.currentText() if hasattr(self, 'combo_clean_sheet') else "",
            "measure_sheet_name": self.combo_measure_sheet.currentText() if hasattr(self, 'combo_measure_sheet') else "",
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
            if "measure_mapping" in config:
                self.measure_mapping_panel.set_mapping(config["measure_mapping"])
            if "backup_path" in config:
                self.edit_backup_path.setText(config["backup_path"])
            
            # 2. 기타 설정 복구
            if "excel_path" in config:
                self.edit_excel.setText(config["excel_path"])
                # 엑셀 경로가 있으면 시트 목록 로드 시도
                if config["excel_path"] and os.path.exists(config["excel_path"]):
                    self._update_sheet_list(
                        config["excel_path"], 
                        config.get("sheet_name"),
                        config.get("clean_sheet_name"),
                        config.get("measure_sheet_name")
                    )

            if "start_row" in config: self.edit_start_row.setText(config["start_row"])
            if "start_num" in config: self.edit_start_num.setText(config["start_num"])
            
            if "pdf_paths" in config:
                self.pdf_paths = config["pdf_paths"]
                if self.pdf_paths:
                    # [V17.3.1.2] 로드 즉시 정렬 강제 (정렬 무결성 확보)
                    self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
                    self.log(f"[*] 이전 세션에서 {len(self.pdf_paths)}개의 PDF 목록을 불러왔습니다.")
                    self.update_file_count_display()
                    
        except Exception as e:
            self.log(f"[!] 설정 복구 실패: {e}")

    def restore_table_from_session(self):
        """[NEW] 저장된 pdf_paths와 cache를 이용해 테이블 UI 복구"""
        if not hasattr(self, 'pdf_paths') or not self.pdf_paths:
            return
            
        self.log("[*] 테이블 데이터를 복구 중입니다...")
        
        # [V17.3.1.2] 복구 전 정렬 상태 강제 확인
        self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
        
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

    def _update_sheet_list(self, path, select_name=None, clean_select_name=None, measure_select_name=None):
        """[V24.3.5.8] 설정 복구 시 시트 목록 자동 갱신 헬퍼 (각 콤보박스 개별 설정 복구)"""
        combos = [self.combo_sheet, self.combo_clean_sheet, self.combo_measure_sheet]
        for c in combos:
            c.blockSignals(True)
            c.clear()
            c.blockSignals(False)
        try:
            wb = openpyxl.load_workbook(path, read_only=True)
            sheets = wb.sheetnames
            wb.close()
            
            # 각 콤보박스별 설정값 및 Fallback 맵 매핑
            targets = [
                (self.combo_sheet, select_name, "Sheet1"),
                (self.combo_clean_sheet, clean_select_name, "Sheet1"),
                (self.combo_measure_sheet, measure_select_name, "측정계획(양식)")
            ]
            
            for combo, target_val, default_val in targets:
                combo.blockSignals(True)
                combo.addItems(sheets)
                if target_val and target_val in sheets:
                    combo.setCurrentText(target_val)
                elif default_val in sheets:
                    combo.setCurrentText(default_val)
                combo.blockSignals(False)
        except:
            for combo, _, default_val in [
                (self.combo_sheet, None, "Sheet1"),
                (self.combo_clean_sheet, None, "Sheet1"),
                (self.combo_measure_sheet, None, "측정계획(양식)")
            ]:
                combo.addItem(default_val)

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
        self.cache = {} # [V17.4.0.9] 메모리 캐시까지 완전 삭제
        if os.path.exists("smu_cache.json"):
            try: os.remove("smu_cache.json")
            except: pass
            
        self.table.setRowCount(0)
        self.log_view.clear()
        self.progress.setValue(0)
        self.update_file_count_display()
        self.log("✅ 모든 데이터와 캐시가 초기화되었습니다.")

    def reload_engine(self):
        """[HOT-RELOAD] 엔진 모듈을 다시 로드하며 캐시도 완전 초기화"""
        try:
            # [V23.0.0.0] 엔진 새로고침 시 사용자 요청에 따라 로그 창 초기화
            if hasattr(self, 'log_view'):
                self.log_view.clear()

            # [V17.4.0.9] 엔진 로직 변경을 즉시 반영하기 위해 캐시 강제 삭제
            if os.path.exists("smu_cache.json"):
                try: os.remove("smu_cache.json")
                except: pass
            self.cache = {}
            self.log("[!] 엔진이 새로고침 되었습니다. (정밀 분석을 위해 캐시 초기화됨)")

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
                # [V17.3.1.2] 추가 즉시 정렬 (뒤죽박죽 방지)
                self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
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
                # [V17.3.1.2] 폴더 로드 시에도 즉시 정렬 강제
                self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
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
            
            self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
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
            combos = [self.combo_sheet, self.combo_clean_sheet, self.combo_measure_sheet]
            for c in combos:
                c.blockSignals(True)
                c.clear()
                c.blockSignals(False)
            try:
                # [Part 3-A] openpyxl을 사용하여 실제 시트 목록 추출
                wb = openpyxl.load_workbook(path, read_only=True, keep_vba=True)
                sheets = wb.sheetnames
                wb.close()
                if sheets:
                    for c in combos:
                        c.blockSignals(True)
                        c.addItems(sheets)
                        c.blockSignals(False)
                    self.log(f"[*] 엑셀 시트 {len(sheets)}개를 성공적으로 로드했습니다.")
                else:
                    for c in combos:
                        c.addItem("Sheet1")
            except Exception as e:
                self.log(f"⚠️ 시트 목록 로드 실패: {e}")
                for c in combos:
                    c.addItem("Sheet1")


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
        
        # 🚨 [V17.3.3.3] 스마트 선택 추출 (Selective Extraction) 로직 도입
        target_paths = []
        is_partial = False
        
        if self.table.rowCount() > 0:
            for r in range(self.table.rowCount()):
                prod_item = self.table.item(r, 2) # 제품명
                cas_item = self.table.item(r, 3)  # CAS 원본
                fn_item = self.table.item(r, 7)   # 파일명
                
                prod_text = prod_item.text().strip() if prod_item else ""
                cas_text = cas_item.text().strip() if cas_item else ""
                
                # 제품명이나 CAS 원본이 비어있거나 '미확인', '오류' 등이 포함된 경우 추출 대상으로 선정
                if not prod_text or not cas_text or "미확인" in prod_text or "오류" in cas_text or "미추출" in prod_text:
                    if fn_item:
                        fn = fn_item.text().strip()
                        full_path = next((p for p in self.pdf_paths if os.path.basename(p) == fn), None)
                        if full_path:
                            target_paths.append(full_path)
            
            if target_paths:
                is_partial = True
                self.log(f"[*] 선택 추출 모드 가동: 전체 {len(target_paths)}건에 대해 재추출을 수행합니다.")
        
        if not is_partial:
            # 전체 추출 모드
            target_paths = self.pdf_paths
            self.table.setRowCount(0)
            self.results = []
            self.progress.setValue(0)

        self.btn_stop.setEnabled(True)
        self.btn_step1.setEnabled(False)
        self.btn_step2.setEnabled(False)
        
        self.worker = ExtractionWorker(self.core, target_paths, cache=self.cache)
        self.worker.update_log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress.setValue)
        # [NEW] 진행 상황 텍스트 업데이트 연결
        self.worker.progress_signal.connect(lambda v: self.lbl_extraction_progress.setText(f"진행 중: {int(v/100*len(self.pdf_paths))}/{len(self.pdf_paths)}건 ({v}%)"))
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
        # [NEW] 진행 상황 텍스트 업데이트 연결
        self.worker.progress_signal.connect(lambda v: self.lbl_extraction_progress.setText(f"검증 중: {int(v/100*len(table_data))}/{len(table_data)}건 ({v}%)"))
        self.worker.result_signal.connect(self.on_validation_result) 
        self.worker.finished_signal.connect(self.on_validation_finished)
        self.worker.start()

    def on_extraction_finished(self, stats):
        """1단계 PDF 추출 완료 요약 보고 (V12.8 통계 대시보드)"""
        self.table.blockSignals(False)
        self.btn_stop.setEnabled(False)
        self.btn_step1.setEnabled(True)
        self.btn_step2.setEnabled(True)
        self.lbl_extraction_progress.setText(f"추출 완료: {len(self.pdf_paths)}건") # [NEW] 완료 표시
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
        
        # [V17.3.0.8] 마스터 DB 로드 에러 사후 안내 (주님 지침: 1단계 종료 후 일괄 보고)
        if hasattr(engine, 'MES_MASTER_LOAD_ERROR') and engine.MES_MASTER_LOAD_ERROR:
             QMessageBox.critical(self, "마스터 DB 로드 실패", 
                                f"[시스템 주의] 성분 명칭 보정용 마스터 DB를 불러오지 못했습니다.\n\n"
                                f"사유: {engine.MES_MASTER_LOAD_ERROR}\n\n"
                                f"조치: DB 파일이 없어도 추출은 계속되나, 명칭이 부정확할 수 있습니다.")


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
            # 캐시 및 결과 메모리에 components 반영
            if target_hash and target_hash in self.cache:
                if "components" in res_data:
                    self.cache[target_hash]["components"] = res_data["components"]
                    self.save_cache()

            self.update_validation_row(
                found_row, 
                v.get("cas_with_content", []), 
                v.get("res_1st", []), 
                v.get("res_2nd", []),
                v.get("work_subjects", ""),
                status=status, # [NEW] 상태값 전달
                components=res_data.get("components")
            )

    def on_validation_finished(self):
        """2단계 API 검증 완료 처리"""
        self.table.blockSignals(False)
        self.btn_stop.setEnabled(False)
        self.btn_step1.setEnabled(True)
        self.btn_step2.setEnabled(True)
        self.lbl_extraction_progress.setText(f"검증 완료: {self.table.rowCount()}건") # [NEW] 완료 표시
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
        """[V15.8.18 수정] 성분명 보수적 정제: 한글명(영문명) 꼬리만 자르고 내부 공백은 보존"""
        if not name: return ""
        name = str(name).strip()
        
        # 문장 끝에 붙은 영문 괄호만 제거하고 내부 띄어쓰기는 철저히 살림
        match = re.match(r'^([가-힣\s\d\w\-\,\.\/]+)\s*\([A-Za-z\s\d,]+\)$', name)
        if match:
            korean_part = match.group(1).strip()
            return korean_part # replace(" ", "") 폭력적 공백 제거 폐기
        
        return name.strip()

    # [V15.5.4] GUI-side character substitution logic (assassin) removed to preserve data integrity.
    # Raw data from the engine is now displayed As-is.

    def add_result_to_table(self, data):
        """1단계 결과를 테이블에 추가 (V7.3 캐시 쉴드 적용)"""
        # [NEW] 워터마크 즉시 숨김
        if hasattr(self, 'lbl_watermark'):
            self.lbl_watermark.hide()
        try:
            f_hash = data.get("f_hash")
            # 🚨 [V17.3.3.3] 기존 행 업데이트 로직 (Selective Extraction 대응)
            existing_row = -1
            if self.table.rowCount() > 0:
                for r in range(self.table.rowCount()):
                    hash_item = self.table.item(r, 8)
                    if hash_item and hash_item.text() == f_hash:
                        existing_row = r
                        break
            
            self.table.blockSignals(True)
            self.table.setSortingEnabled(False)
            
            if existing_row >= 0:
                row = existing_row
                # 기존 결과 객체 업데이트 (메모리 동기화)
                for i, res in enumerate(self.results):
                    if res.get("f_hash") == f_hash:
                        self.results[i] = data
                        break
            else:
                self.results.append(data)
                row = self.table.rowCount()
                self.table.insertRow(row)
            
            # 1. 순번 (신호등 이모지 + 숫자 통합)
            traffic_val = data.get("신호등", "🔴")
            if not traffic_val or traffic_val == "N/A":
                raw_rel = data.get("reliability", "")
                if "[AUTO-PASS]" in raw_rel: traffic_val = "🟢"
                elif "[AI-FIXED]" in raw_rel: traffic_val = "🟡"
                else: traffic_val = "🔴"
            
            # [V17.3.3.2] 텍스트 형 신호등(green/yellow) 수신 시 이모지로 변환
            if str(traffic_val).lower() == "green": traffic_val = "🟢"
            elif str(traffic_val).lower() == "yellow": traffic_val = "🟡"
            elif str(traffic_val).lower() == "red": traffic_val = "🔴"
            
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

            # 2. No (파일명 앞 숫자 추출 및 3자리 제로 패딩 강제 - 정렬 무결성)
            fn = data.get("filename", "")
            match_no = re.match(r"^(\d+)", fn)
            if match_no:
                no_val = f"{int(match_no.group(1)):03d}"
            else:
                no_val = "999"
            
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

    def update_validation_row(self, row, cas_with_content, res_1st_list, res_2nd_list, work_subjects="", status="High-Pass", components=None):
        """2단계 검증 결과를 테이블에 업데이트 (V10.2 파란색 신호등 🔵 제어 추가)"""
        try:
            # Hash를 가져와 캐시 조회
            f_hash = self.table.item(row, 8).text() if self.table.item(row, 8) else ""
            manual = self.cache.get(f_hash, {}).get("manual_data", {})
            
            self.table.blockSignals(True)
            
            # 🚨 [수정: V15.8.16 호환] 신호등 이모지 및 배경색 제어 (1단계 경고 보존)
            traffic_col = 0
            curr_traffic_text = self.table.item(row, traffic_col).text() if self.table.item(row, traffic_col) else ""
            
            # 1. 기존의 이모지(경고 상태)와 순번을 분리
            match = re.match(r'^([🔴🟡🟢⚪])\s*(.*)$', curr_traffic_text)
            existing_emoji = match.group(1) if match else "⚪"
            pure_idx = match.group(2) if match else curr_traffic_text

            # 2. 기본값 세팅
            emoji = existing_emoji 
            bg_color = None

            # 3. 2단계 검증이 끝났을 때의 색상 결정 로직 (덮어쓰기 방어)
            if "검증 완료" in status:
                if existing_emoji in ["🔴", "🟡"]:
                    # 1단계에서 이미 에러/경고가 떴다면, 그 색상을 100% 유지!
                    emoji = existing_emoji 
                    if existing_emoji == "🔴": bg_color = QColor("#ffebeb")
                    elif existing_emoji == "🟡": bg_color = QColor("#fff9db")
                else:
                    # 1단계가 무사 통과(⚪ 또는 🟢)였을 때만 초록불(합격) 마킹
                    emoji = "🟢"
                    bg_color = QColor("#e1f7d5")

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

            # 1:N 성상 물질 분석 및 콤보박스 렌더링 판별
            if components is None:
                components = self.cache.get(f_hash, {}).get("components")

            pending_cas = None
            pending_candidates = []
            pending_range = ""
            
            # components가 있다면 1:N 후보 검색
            if components:
                for c in components:
                    cas_val = c.get("cas", "")
                    candidates = self.find_mes_candidates(cas_val)
                    if len(candidates) == 1:
                        # [버그 수정] 단일 후보인 경우(예: 염화 바륨 -> 바륨 및 가용성 화합물) 자동으로 정규화된 물질 정보 이식
                        first_cand = candidates[0]
                        c["selected_name"] = first_cand.get("측정대상 물질명") or ""
                        c["osh"] = {
                            "is_measured": str(first_cand.get("측정", "")).strip() == "○",
                            "is_special": str(first_cand.get("특검", "")).strip() == "○",
                            "is_special_mgmt": bool(str(first_cand.get("특별관리", "")).strip()),
                            "is_permit": bool(str(first_cand.get("허가대상", "")).strip()),
                            "is_prohibited": False
                        }
                    elif len(candidates) >= 2:
                        # 1:N 매칭 후보 물질 존재!
                        selected_code = manual.get(f"selected_code_{cas_val}")
                        if selected_code:
                            # 과거 캐시된 정렬코드가 있는 경우 -> 콤보박스 생성 없이 확정 적용
                            master_entry = None
                            for entry in candidates:
                                if str(entry.get("정렬코드", "")).strip() == str(selected_code).strip():
                                    master_entry = entry
                                    break
                            if master_entry:
                                c["selected_name"] = master_entry.get("측정대상 물질명") or ""
                                c["osh"] = {
                                    "is_measured": str(master_entry.get("측정", "")).strip() == "○",
                                    "is_special": str(master_entry.get("특검", "")).strip() == "○",
                                    "is_special_mgmt": bool(str(master_entry.get("특별관리", "")).strip()),
                                    "is_permit": bool(str(master_entry.get("허가대상", "")).strip()),
                                    "is_prohibited": False
                                }
                        else:
                            # 캐시된 정렬코드가 없음 -> 콤보박스를 띄워야 함 (PENDING_SELECTION 상태)
                            pending_cas = cas_val
                            pending_candidates = candidates
                            pending_range = c.get("content", "")
                            break # 일단 첫 번째 1:N 매칭 물질만 콤보박스로 띄움

            # 캐시가 반영된 성분들로 1차/2차 결과 재구성
            if components:
                final_res1, final_res2, work_subjects = self.regenerate_validation_results(components)

            # 3. 측정대상 (1% 필터링 반영) 또는 콤보박스 설정
            if pending_cas:
                # [버그 수정] 콤보박스 대신 성상 선택을 유도하는 세련된 QPushButton 생성
                btn_name = "Unknown"
                mes_std_name = engine.MES_MASTER_MAP.get(pending_cas, "")
                if mes_std_name:
                    btn_name = str(mes_std_name)
                    btn_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', btn_name, flags=re.IGNORECASE).strip()
                else:
                    for c in components:
                        if c.get("cas") == pending_cas:
                            btn_name = c.get("name", "Unknown")
                            if re.search(r'[가-힣]', btn_name):
                                btn_name = re.sub(r'\s*\([A-Za-z\s\d,]+\)$', '', btn_name).strip()
                            break
                            
                # 1:N 대상 이외의 다른 측정대상 물질들 추출
                other_subjects = []
                other_non_subjects = []
                if components:
                    for c in components:
                        cas_val = c.get("cas", "")
                        if cas_val == pending_cas:
                            continue
                        
                        name = c.get("name", "Unknown")
                        range_val = c.get("content", "")
                        
                        if re.search(r'[가-힣]', name):
                            name_no_eng = re.sub(r'\s*\([A-Za-z\s\d,]+\)$', '', name)
                            clean_name = name_no_eng.strip()
                        else:
                            clean_name = name.strip()
                            
                        mes_std_name = engine.MES_MASTER_MAP.get(cas_val, "")
                        if mes_std_name:
                            clean_name = str(mes_std_name)
                            clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()
                        
                        if c.get("selected_name"):
                            clean_name = c["selected_name"]

                        osh = c.get("osh", {})
                        is_work = osh.get("is_measured", False)
                        
                        if is_work:
                            if not range_val or str(range_val).strip() == "":
                                range_val = "미기재%"
                            percentage = 0.0
                            nums = re.findall(r'[\d\.]+', range_val)
                            if nums:
                                try: percentage = max(float(n) for n in nums)
                                except: percentage = 0.0
                                if "<" in range_val and percentage <= 1.0: percentage = 0.5
                            else: percentage = 100.0
                            
                            is_ge_1 = (percentage >= 1.0)
                            if is_ge_1:
                                other_subjects.append(f"{clean_name}")
                            else:
                                other_non_subjects.append(f"{clean_name}")
                
                other_subj_str = "; ".join(other_subjects)
                other_non_subj_str = f"측정 비대상[{'; '.join(other_non_subjects)}]" if other_non_subjects else ""
                other_final_str = "; ".join(filter(None, [other_subj_str, other_non_subj_str]))
                
                # 버튼 인스턴스 생성 및 현대적인 디자인 적용
                btn_text = f"🔍 성상 선택 ({btn_name}: {pending_range})"
                btn = QPushButton(btn_text)
                btn.setCursor(QCursor(Qt.PointingHandCursor))
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #e8f0fe;
                        color: #1a73e8;
                        border: 1px solid #1a73e8;
                        border-radius: 4px;
                        padding: 4px 8px;
                        font-family: 'Malgun Gothic';
                        font-size: 9pt;
                        font-weight: bold;
                        min-height: 28px;
                    }
                    QPushButton:hover {
                        background-color: #d2e3fc;
                    }
                """)
                
                # 버튼 내에 데이터 및 콜백 변수 바인딩
                btn.setProperty("cas", pending_cas)
                btn.setProperty("candidates", pending_candidates)
                btn.setProperty("content", pending_range)
                btn.setProperty("other_text", other_final_str)
                btn.setProperty("name", btn_name)
                
                # 클릭 시 다이얼로그 호출
                btn.clicked.connect(lambda checked, r=row, c=pending_cas, cd=pending_candidates, n=btn_name, rg=pending_range: self.show_substance_selector(r, c, cd, n, rg))
                
                # 테이블 측정대상 셀에 버튼 배치
                self.table.setCellWidget(row, 4, btn)
                
                # 최초 로드 시 첫 번째 아이템의 내용으로 1차/2차 결과 임시 동기화 실행 (공란 방지)
                if pending_candidates:
                    first_cand = pending_candidates[0]
                    m_name = first_cand.get("측정대상 물질명") or ""
                    for c in components:
                        if str(c.get("cas", "")).strip() == str(pending_cas).strip():
                            c["selected_name"] = m_name
                            c["osh"] = {
                                "is_measured": str(first_cand.get("측정", "")).strip() == "○",
                                "is_special": str(first_cand.get("특검", "")).strip() == "○",
                                "is_special_mgmt": bool(str(first_cand.get("특별관리", "")).strip()),
                                "is_permit": bool(str(first_cand.get("허가대상", "")).strip()),
                                "is_prohibited": False
                            }
                            break
                    final_res1, final_res2, work_subjects = self.regenerate_validation_results(components)
            else:
                # 일반 텍스트 확정 렌더링
                # setCellWidget에 남아있는 콤보박스 제거
                self.table.removeCellWidget(row, 4)
                final_measure = manual.get("measure", work_subjects)
                item_measure = QTableWidgetItem(final_measure)
                if bg_color: item_measure.setBackground(bg_color)
                self.table.setItem(row, 4, item_measure)

            # 4. 2차 결과 (1% 필터링 반영) - [V17.3.1.0] GUI 줄바꿈 강제 (가독성 최적화)
            raw_reg2 = manual.get("reg2", ";\n".join(final_res2))
            final_reg2_str = ";\n".join([p.strip() for p in raw_reg2.replace(';\n', ';').replace('\n', ';').split(';') if p.strip()])
            item_reg2 = QTableWidgetItem(final_reg2_str)
            if bg_color: item_reg2.setBackground(bg_color)
            self.table.setItem(row, 5, item_reg2)

            # 5. 1차 결과 (1% 필터링 반영) - [V17.3.1.0] GUI 줄바꿈 강제
            raw_reg1 = manual.get("reg1", ";\n".join(final_res1))
            final_reg1_str = ";\n".join([p.strip() for p in raw_reg1.replace(';\n', ';').replace('\n', ';').split(';') if p.strip()])
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

    def find_mes_candidates(self, cas):
        """[1:N 매칭] CAS 번호에 해당하는 마스터 DB의 모든 매칭 후보들을 반환"""
        if not cas: return []
        
        # [수정] 대표 금속/화합물 그룹 CAS 번호 연동용 변환 맵 정의 (간접 매칭 지원)
        # Barium chloride anhydrous(10361-37-2) -> Barium(7440-39-3)
        # Silver nitrate(7761-88-8) -> Silver(7440-22-4)
        cas_redirect_map = {
            "10361-37-2": "7440-39-3",
            "7761-88-8": "7440-22-4",
        }
        
        target_cas = cas_redirect_map.get(str(cas).strip(), cas)
        
        candidates = []
        normalized_cas = re.sub(r'[^0-9]', '', str(target_cas).strip())
        for entry in getattr(self, "mes_master_list", []):
            cas_val = str(entry.get("CAS No.", "")).strip()
            if cas_val and cas_val.lower() != 'nan':
                if re.sub(r'[^0-9]', '', cas_val) == normalized_cas:
                    candidates.append(entry)
        return candidates

    def regenerate_validation_results(self, components):
        """[실시간 갱신] 성분 정보를 기반으로 규제 정보 텍스트를 재생성"""
        res_1st_list = []
        res_2nd_list = []
        res_work_subjects = []
        res_work_non_subjects = []
        
        for c in components:
            name = c.get("name", "Unknown")
            cas = c.get("cas", "")
            range_val = c.get("content", "")
            
            # [V27.5 영문명/기호 완벽 보존 로직 복제]
            if re.search(r'[가-힣]', name):
                name_no_eng = re.sub(r'\s*\([A-Za-z\s\d,]+\)$', '', name)
                clean_name = name_no_eng.strip()
            else:
                clean_name = name.strip()
                
            mes_std_name = engine.MES_MASTER_MAP.get(cas, "")
            if mes_std_name:
                clean_name = str(mes_std_name)
                clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()
            
            # 만약 콤보박스 선택 등으로 변경된 이름이 지정되어 있다면 측정대상용으로 별도 보관
            selected_name = c["selected_name"] if c.get("selected_name") else clean_name

            osh = c.get("osh", {})
            is_work = osh.get("is_measured", False)
            is_spec = osh.get("is_special", False)
            is_mgmt = osh.get("is_special_mgmt", False)
            is_permit = osh.get("is_permit", False)

            prefix = ""
            if is_mgmt: prefix = "[특별]"
            elif is_permit: prefix = "[허가]"
            elif is_spec and not is_work: prefix = "[특검]"

            if not range_val or str(range_val).strip() == "":
                range_val = "미기재%"
            c_str = f"({range_val})"
            
            res_1st_list.append(f"{prefix}{clean_name}[{cas}{c_str}]")
            
            if is_work or is_spec:
                res_2nd_list.append(f"{prefix}{clean_name}{c_str}")
                
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
                    res_work_subjects.append(f"{selected_name}")
                else:
                    res_work_non_subjects.append(f"{selected_name}")

        subj_str = "; ".join(res_work_subjects)
        non_subj_str = f"측정 비대상[{'; '.join(res_work_non_subjects)}]" if res_work_non_subjects else ""
        final_work_str = "; ".join(filter(None, [subj_str, non_subj_str]))
        
        # 보장 로직
        if not res_1st_list: res_1st_list = [""]
        if not res_2nd_list: res_2nd_list = [""]
        
        return res_1st_list, res_2nd_list, final_work_str

    def on_table_cell_double_clicked(self, row, column):
        """[실시간 갱신] 측정대상 셀 더블클릭 시 1:N 매칭 세부 성상 선택 팝업 강제 구동"""
        if column == 4:
            f_hash = self.table.item(row, 8).text() if self.table.item(row, 8) else ""
            if not f_hash: return
            
            components = self.cache.get(f_hash, {}).get("components", [])
            if not components: return
            
            # 해당 행의 components 목록 중 1:N 매칭 후보가 존재하는 CAS 검색
            for c in components:
                cas_val = c.get("cas", "")
                candidates = self.find_mes_candidates(cas_val)
                if len(candidates) >= 2:
                    name = c.get("name", "Unknown")
                    range_val = c.get("content", "")
                    self.show_substance_selector(row, cas_val, candidates, name, range_val)
                    break

    def show_substance_selector(self, row, cas, candidates, name, range_val):
        """[성상 선택 팝업] 다이얼로그를 호출하여 사용자가 선택한 정렬코드를 캐시 및 테이블에 실시간 동기화"""
        dialog = SubstanceSelectDialog("세부 성상 및 규제 정보 선택", name, cas, range_val, candidates, self)
        if dialog.exec_() == QDialog.Accepted:
            code, master_entry = dialog.get_selected_data()
            if code and master_entry:
                f_hash = self.table.item(row, 8).text() if self.table.item(row, 8) else ""
                if not f_hash: return
                
                m_name = master_entry.get("물질명") or master_entry.get("상용명") or ""
                
                # 캐시된 성분 정보 갱신
                components = self.cache.get(f_hash, {}).get("components", [])
                for c in components:
                    if str(c.get("cas", "")).strip() == str(cas).strip():
                        c["selected_name"] = m_name
                        c["osh"] = {
                            "is_measured": str(master_entry.get("측정", "")).strip() == "○",
                            "is_special": str(master_entry.get("특검", "")).strip() == "○",
                            "is_special_mgmt": bool(str(master_entry.get("특별관리", "")).strip()),
                            "is_permit": bool(str(master_entry.get("허가대상", "")).strip()),
                            "is_prohibited": bool(str(master_entry.get("금지대상", "")).strip())
                        }
                        break
                
                # 캐시에 수동 정렬코드 동기화
                if "manual_data" not in self.cache[f_hash]:
                    self.cache[f_hash]["manual_data"] = {}
                self.cache[f_hash]["manual_data"][f"selected_code_{cas}"] = code
                self.save_cache()
                
                # 1차/2차 결과 재합산
                new_res1, new_res2, new_work = self.regenerate_validation_results(components)
                
                # 테이블 UI 실시간 업데이트 (시그널 락)
                self.table.blockSignals(True)
                
                # 측정대상 4번 열의 버튼을 제거하고 확정된 일반 텍스트로 치환 적용
                self.table.removeCellWidget(row, 4)
                
                # update_validation_row 호출을 통해 1차/2차 결과 및 전체 레이아웃 갱신
                self.update_validation_row(
                    row,
                    self.table.item(row, 3).text().split(";\n"),
                    new_res1,
                    new_res2,
                    new_work,
                    status="검증 완료 (캐시)",
                    components=components
                )
                self.table.blockSignals(False)
                self.log(f"[*] 성상 선택 적용 완료: CAS {cas} -> {m_name} (정렬코드: {code})")

    def on_combo_substance_changed(self, row, cas, combo):
        """[실시간 동기화] 콤보박스 선택 변경 시 1차/2차 규제 결과와 캐시 실시간 동기화"""
        try:
            f_hash = self.table.item(row, 8).text() if self.table.item(row, 8) else ""
            if not f_hash: return
            
            code = combo.currentData()
            
            # 마스터 DB에서 해당 코드에 해당하는 entry 탐색
            master_entry = None
            for entry in getattr(self, "mes_master_list", []):
                if str(entry.get("정렬코드", "")).strip() == str(code).strip():
                    master_entry = entry
                    break
            
            if not master_entry: return
            
            m_name = master_entry.get("측정대상 물질명") or ""
            
            # 캐시된 성분 정보 갱신
            components = self.cache.get(f_hash, {}).get("components", [])
            for c in components:
                if str(c.get("cas", "")).strip() == str(cas).strip():
                    c["selected_name"] = m_name
                    # 마스터 DB의 규제 플래그 덮어쓰기
                    c["osh"] = {
                        "is_measured": str(master_entry.get("측정", "")).strip() == "○",
                        "is_special": str(master_entry.get("특검", "")).strip() == "○",
                        "is_special_mgmt": bool(str(master_entry.get("특별관리", "")).strip()),
                        "is_permit": bool(str(master_entry.get("허가대상", "")).strip()),
                        "is_prohibited": False
                    }
                    break
            
            # 변경된 정보를 기반으로 1차/2차 규제 텍스트 재생성
            new_res1, new_res2, new_work = self.regenerate_validation_results(components)
            
            # 테이블 셀 업데이트 (시그널 임시 차단)
            self.table.blockSignals(True)
            
            # 4. 2차 결과 업데이트
            final_reg2_str = ";\n".join([p.strip() for p in ";\n".join(new_res2).replace(';\n', ';').replace('\n', ';').split(';') if p.strip()])
            self.table.setItem(row, 5, QTableWidgetItem(final_reg2_str))
            
            # 5. 1차 결과 업데이트
            final_reg1_str = ";\n".join([p.strip() for p in ";\n".join(new_res1).replace(';\n', ';').replace('\n', ';').split(';') if p.strip()])
            self.table.setItem(row, 6, QTableWidgetItem(final_reg1_str))
            
            self.table.blockSignals(False)
            self._safe_resize_rows()
            
            # 캐시에 선택 정보 영구 저장
            if "manual_data" not in self.cache[f_hash]:
                self.cache[f_hash]["manual_data"] = {}
            self.cache[f_hash]["manual_data"][f"selected_code_{cas}"] = code
            self.save_cache()
            
            self.log(f"[*] 성상 선택 적용 완료: CAS {cas} -> {m_name} (정렬코드: {code})")
        except Exception as e:
            self.table.blockSignals(False)
            self.log(f"[!] 성상 변경 처리 실패: {e}")


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
                    
                    # [버그 수정] QPushButton(성상 미선택 버튼) 또는 일반 텍스트 상태에 따라 데이터 추출
                    measure_widget = self.table.cellWidget(r, 4)
                    
                    if isinstance(measure_widget, QPushButton):
                        # 사용자가 클릭을 안 하고 저장을 누른 경우 -> 첫 번째 후보 데이터로 자동 매칭
                        candidates = measure_widget.property("candidates")
                        cas_no = measure_widget.property("cas")
                        content_val = measure_widget.property("content") or ""
                        other_text = measure_widget.property("other_text") or ""
                        
                        if candidates:
                            first_cand = candidates[0]
                            m_name = first_cand.get("측정대상 물질명") or ""
                            if content_val:
                                combo_val = f"{m_name}({content_val})"
                            else:
                                combo_val = m_name
                                
                            measure_val = combo_val
                            if other_text:
                                measure_val = f"{combo_val}; {other_text}"
                                
                            # 캐시에 선택 정보 영구 저장
                            selected_code = first_cand.get("정렬코드")
                            f_hash = self.table.item(r, 8).text().strip() if self.table.item(r, 8) else ""
                            if f_hash and f_hash in self.cache and cas_no:
                                if "manual_data" not in self.cache[f_hash]:
                                    self.cache[f_hash]["manual_data"] = {}
                                self.cache[f_hash]["manual_data"][f"selected_code_{cas_no}"] = selected_code
                                self.save_cache()
                        else:
                            measure_val = ""
                    else:
                        # 이미 선택 완료되어 텍스트 상태인 경우 셀 텍스트를 즉시 추출
                        measure_val = self.table.item(r, 4).text().strip() if self.table.item(r, 4) else ""
                        
                    table_dict[fn] = {
                        "no": self.table.item(r, 1).text().strip() if self.table.item(r, 1) else "",
                        "product_name": self.table.item(r, 2).text().strip() if self.table.item(r, 2) else "",
                        "cas_sum": self.table.item(r, 3).text().strip() if self.table.item(r, 3) else "",
                        "measure": measure_val,
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
                        # [V17.3.0.9] 주님 지침: GUI는 편집용(줄바꿈), 엑셀은 최종용(한 줄)으로 저장
                        if key in ["CAS 원본", "1차 결과(전체)", "2차 결과(규제)"]:
                            val = str(val).replace('\n', ' ').replace('\r', '').strip()
                            # 연속된 공백 제거 (깔끔한 세미콜론 정렬용)
                            val = re.sub(r'\s{2,}', ' ', val)
                        
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
