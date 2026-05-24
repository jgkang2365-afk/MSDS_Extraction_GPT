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
import fitz  # [NEW] PyMuPDF: 二쇰떂???먰븯??臾댁???誘몃━蹂닿린 ?붿쭊
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QRect, QPropertyAnimation, QEasingCurve, QUrl, QTimer
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette, QTextDocument, QCursor, QTextCursor, QImage, QPixmap
from html import escape

import msds_core
import importlib # [HOT-RELOAD] 紐⑤뱢 ?덈줈怨좎묠??from msds_core import MSDSCore
import msds_engine_v5 as engine
import openpyxl  # [V6.994] ?쒗듃 紐⑸줉 異붿텧 諛??ъ쟾 寃利앹슜
import pandas as pd # [V10.5] 留덉뒪??DB 濡쒕뱶??
# [V7.0] ?뚯씠釉?而щ읆 ?몃뜳???뺤쓽 (誘몃━蹂닿린 釉뚮┸吏??
COL_IDX_FILENAME = 7
COL_IDX_HASH = 8
COL_IDX_FILEPATH = 9
COL_IDX_PAGE = 10

# [Part 1] ?먯깋湲??ㅽ????먯뿰?ㅻ윭???뺣젹 (Natural Sort)
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]


# [Part 2] Seamless PDF Preview ?⑤꼸 (諛붿씠?덈━ 媛뺤젣 濡쒕뱶 踰꾩쟾)
class PDFPreviewPanel(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter) 
        self.layout.setContentsMargins(0, 0, 0, 0) # ?щ갚 ?쒓굅 (?쒖씤??洹밸???
        self.layout.setSpacing(5)
        self.setWidget(self.container)
        self.setStyleSheet("background-color: #525659; border: none;")
        self.labels = [] 
        self.current_pdf_path = None
        self.setMinimumWidth(500) # 二쇰떂 ?붿껌: 理쒖냼 ?덈퉬 500px 蹂댁옣
        
        # [NEW] ?ㅼ떆媛?怨좏빐?곷룄 ?쒕뜑留곸슜 ??대㉧ (?깅뒫怨??붿쭏 ?숈떆 ?↔린)
        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.apply_high_res_render)

    def resizeEvent(self, event):
        """[Responsive Zoom] 李??덈퉬 蹂寃???利됱떆 ?뺣?"""
        super().resizeEvent(event)
        self.update_label_sizes()
        self.render_timer.start(300) # ?쒕옒洹?硫덉텛硫?0.3珥????좊챸?섍쾶 ?ㅼ떆 洹몃━湲?
    def load_pdf(self, file_path):
        """[?꾩쟾 ?닿껐] PNG 諛붿씠?덈━ 蹂??濡쒕뱶濡?諛깆? ?꾩긽 ?먯쿇 李⑤떒"""
        # [V17.3.2.11] ?숈씪 ?뚯씪 以묐났 濡쒕뱶 諛⑹? (?ㅽ겕濡????꾩긽 ?닿껐)
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
                
                # [?듭떖] ?щ㎎ mismatch 諛⑹?瑜??꾪빐 PNG ?곗씠?곕줈 異붿텧 ??濡쒕뱶
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                qimg = QImage.fromData(pix.tobytes("png")) # ??諛⑹떇??媛???뺤떎?⑸땲??                
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
        """[V7.0] ?뱀젙 ?섏씠吏濡??ㅽ겕濡??대룞"""
        if 1 <= page_num <= len(self.labels):
            lbl, _ = self.labels[page_num - 1]
            # ?대떦 ?쇰꺼???꾩튂濡??ㅽ겕濡ㅻ컮 ?대룞
            self.verticalScrollBar().setValue(lbl.y())

    def apply_high_res_render(self):
        """[?닿껐] 怨좏빐?곷룄 ?뚮뜑留??쒖뿉??PNG 諛붿씠?덈━ 諛⑹떇 ?곸슜"""
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
                # PNG 諛붿씠?덈━ 異붿텧 濡쒕뱶
                img = QImage.fromData(pix.tobytes("png"))
                lbl.setPixmap(QPixmap.fromImage(img))
                lbl.repaint() # ?붾㈃ 利됱떆 媛깆떊 媛뺤젣
            doc.close()
        except Exception as e:
            print(f"High-Res Render Error: {e}")

    def update_label_sizes(self):
        """李??덈퉬??留욎떠 湲?먮? 二쇰㉨留??섍쾶 ?ㅼ?"""
        if not self.labels: return
        # 酉고룷???덈퉬瑜??뺥솗??怨꾩궛?섏뿬 '諛깆?' ?꾩긽 李⑤떒
        target_width = max(500, self.viewport().width() - 2) 
        self.container.setFixedWidth(target_width)
        for lbl, ratio in self.labels:
            lbl.setFixedWidth(target_width)
            lbl.setFixedHeight(int(target_width * ratio))

class FileDropArea(QLabel):
    """[NEW] PDF ?뚯씪 諛??대뜑 ?쒕옒洹????쒕∼ ?섏떊 ?곸뿭 (?ㅻ뜑 ?듯빀???щ┝ ?붿옄??"""
    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setText("[FILE] PDF ?뚯씪???닿납???쒕옒洹명븯??異붽? (?대뜑 ?쒕엻 媛??")
        self.setAcceptDrops(True)
        self.setFixedHeight(35) 
        self.setFixedWidth(420) # ?덈퉬 ?뺤옣 (湲???섎┝ 諛⑹?)
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
        if index.column() in [3, 4, 5, 6]: # [V17.3.1.1] CAS, 痢≪젙??? 1/2李?寃곌낵 紐⑤몢 硫?곕씪???몄쭛 吏??            editor = QTextEdit(parent)
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
    """[Part 15-B] 怨좊룄?붾맂 ?몃━寃뚯씠?? 諛곌꼍怨??띿뒪???쒕줈??遺꾨━ 諛??ㅼ쨷???몄쭛 吏??""
    
    # --- [V11.0] ?ㅼ쨷 ???몄쭛湲?QTextEdit) 吏??濡쒖쭅 ?댁떇 ---
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
        """[Part 15-C] HTML 臾몄꽌瑜??앹꽦?섍퀬 ?고듃 諛??덈퉬瑜??ㅼ젙??"""
        text = index.data()
        if not text: return None
        
        parts = [p.strip() for p in re.split(r'[;\n]+', text) if p.strip()]
        html_parts = []
        for p in parts:
            p = p.strip()
            if not p: continue
            
            escaped_p = escape(p)
            
            if p.startswith("[?밸퀎]") or p.startswith("[?덇?]"):
                html_parts.append(f"<span style='color:#f56c6c;'>{escaped_p[:4]}</span>{escaped_p[4:]}")
            elif p.startswith("[?밴?]"):
                html_parts.append(f"<span style='color:#409eff;'>{escaped_p[:4]}</span>{escaped_p[4:]}")
            else:
                html_parts.append(escaped_p)
        
        # [V17.3.1.1] 二쇰떂 吏移?諛섏쁺: 媛濡??먮쫫 ????섏쭅 媛쒗뻾(;<br>)???ъ슜?섏뿬 ?깅텇蹂?媛?낆꽦 洹밸???        final_html = f"<html><body style='font-family:Malgun Gothic; font-size:9pt;'>{';<br>'.join(html_parts)}</body></html>"
        
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

LOG_INFO = "?윟"
LOG_WARN = "?윞"
LOG_ERROR = "?뵶"

class SidebarButton(QPushButton):
    """?듭뒪?뚮줈???ㅽ??쇱쓽 ?ъ씠?쒕컮 踰꾪듉 (?щ┝ 紐⑤뱶 吏??"""
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
    """1?④퀎: PDF?먯꽌 ?띿뒪??湲곕컲 異붿텧留??섑뻾 (API ?곕룞 ?놁씠)"""
    update_log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    result_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal(dict)
    cache_update_signal = pyqtSignal(str, dict) # [NEW] 罹먯떆 ?낅뜲?댄듃 ?붿껌??
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
                if i > 0: self.update_log_signal.emit("<span style='color:#5DADE2;'><b>" + "??*70 + "</b></span>") 
                
                # [NEW] 罹먯떆 泥댄겕 (SHA-256 ?댁떆 湲곗?)
                f_hash = self.core.calculate_file_hash(path)
                if not f_hash:  # [V8.3] ?댁떆 ?앹꽦 蹂댁옣 (Fallback)
                    f_hash = f"fallback_{i}_{fn}"
                
                # [V17.2.9.9] 罹먯떆 泥댄겕 濡쒖쭅 媛뺥솕: ?뚯씪 ?댁떆 + ?붿쭊 踰꾩쟾 ?숆린???뺤씤
                if f_hash and getattr(self, 'cache', None) and f_hash in self.cache:
                    cached_data = self.cache[f_hash]
                    manual = cached_data.get("manual_data", {})
                    cached_version = cached_data.get("engine_version", "unknown")
                    
                    # [?듭떖] 踰꾩쟾???ㅻⅤ嫄곕굹, ?섎룞 ?곗씠?곌? ?녿뒗??AI 寃곌낵媛 遺덉셿?꾪븳 寃쎌슦 ?ъ텛異?                    use_cache = True
                    if cached_version != engine.VERSION:
                        self.update_log_signal.emit(f"[*] [{fn}] ?붿쭊 踰꾩쟾 蹂寃?媛먯? ({cached_version} -> {engine.VERSION}): ?ъ텛異쒖쓣 ?섑뻾?⑸땲??")
                        use_cache = False
                    elif not manual and (cached_data.get("product_name") == "?쒗뭹紐??뺤씤 ?꾩슂" or "?ㅻ쪟" in cached_data.get("status", "")):
                        self.update_log_signal.emit(f"[*] [{fn}] 遺덉셿?꾪븳 異붿텧 寃곌낵 媛먯?: API ?ы샇異쒖쓣 ?쒕룄?⑸땲??")
                        use_cache = False
                    # ?슚 [V17.3.3.3] ?ъ슜???붿껌(怨듬?) 媛먯?: ?쒗뭹紐낆씠??CAS ?먮낯??鍮꾩뼱?덉쑝硫?媛뺤젣 ?ъ텛異?                    elif manual.get("product_name") == "" or manual.get("raw_content") == "":
                        self.update_log_signal.emit(f"[*] [{fn}] ?ъ슜???붿껌(怨듬?) 媛먯?: 媛뺤젣 ?ъ텛異쒖쓣 ?섑뻾?⑸땲??")
                        use_cache = False
                    
                    if use_cache:
                        self.update_log_signal.emit(f"[*] [{fn}] 罹먯떆??寃곌낵媛 諛쒓껄?섏뿀?듬땲?? (?ъ텛異?嫄대꼫?)")
                        # [V11.6 濡쒖쭅 ?좎?] manual_data 湲덇퀬 ?뺤씤 諛?理쒖슦????뼱?곌린
                        final_product = manual.get("product_name", cached_data.get("product_name", "誘명솗??))
                        final_content = manual.get("raw_content", cached_data.get("raw_content", ""))

                        res_data = {
                            "filename": fn,
                            "f_hash": f_hash, 
                            "product_name": final_product, 
                            "reliability": cached_data.get("reliability", "N/A"),
                            "?좏샇??: cached_data.get("?좏샇??, "??),
                            "raw_content": final_content, 
                            "status": "?섎룞 ?섏젙?? if manual else "罹먯떆 濡쒕뱶??
                        }
                        self.result_signal.emit(res_data)
                        self.progress_signal.emit(int((i + 1) / total * 100))
                        stats["regex"] += 1
                        continue

                self.update_log_signal.emit("="*20 + f" [{fn} 異붿텧 ?쒖옉] " + "="*20)
                # [V7-Final] ?듯빀???붿쭊?쇰줈 異붿텧 ?섑뻾 (?뺢퇋??媛쒖븞 諛????섎Т 遺꾩꽍 ?곸슜)
                ext_res = engine.analyze_msds(path, log_func=self.update_log_signal.emit)
                
                extracted_data = {
                    "f_hash": f_hash,
                    "product_name": ext_res.get("?쒗뭹紐?, "誘명솗??),
                    "reliability": ext_res.get("?좊ː??, "N/A"),
                    "?좏샇??: ext_res.get("?좏샇??, "??), 
                    "raw_content": ext_res.get("援ъ꽦?깅텇", ext_res.get("援ъ꽦?깅텇 諛??⑥쑀??, "")),
                    # ?슚 [V15.3 ?뚯씠???곌껐] ?붿쭊??媛뺤젣濡??댁＜??'痢≪젙??? ?섏떊!
                    "measure_target": ext_res.get("痢≪젙???, ""), 
                    "full_path": path, 
                    "page": ext_res.get("page", 1), 
                    "used_engine": ext_res.get("used_engine", "regex"),
                    "engine_version": engine.VERSION # [V17.2.9.9] 踰꾩쟾 ?숈씤 李띻린
                }
                
                # [NEW] 罹먯떆??????붿껌
                if f_hash:
                    self.cache_update_signal.emit(f_hash, extracted_data)

                res_data = extracted_data.copy()
                res_data["filename"] = fn
                res_data["status"] = "異붿텧 ?꾨즺"
                
                # ?듦퀎 吏묎퀎
                engine_type = res_data.get("used_engine", "regex")
                if engine_type in stats:
                    stats[engine_type] += 1
                else:
                    stats["regex"] += 1

                self.result_signal.emit(res_data)
                self.progress_signal.emit(int((i + 1) / total * 100))
            except Exception as e:
                self.update_log_signal.emit(f"[!] ?ㅻ쪟 諛쒖깮 ({os.path.basename(path)}): {e}")
                err_data = {
                    "filename": os.path.basename(path),
                    "product_name": "異붿텧 ?ㅻ쪟",
                    "reliability": "[ERROR]",
                    "?좏샇??: "?뵶",
                    "raw_content": f"?ㅻ쪟: {e}",
                    "status": "?ㅻ쪟"
                }
                self.result_signal.emit(err_data)
                self.progress_signal.emit(int((i + 1) / total * 100))
            
            # [吏?ν삎 ?띾룄 議곗젅] ?뚯씪 媛?理쒖냼 1珥덉쓽 媛꾧꺽???먯뼱 RPM ?쒗븳 ?뚰뵾
            time.sleep(1.0)
        
        self.finished_signal.emit(stats)

class ValidationWorker(QThread):
    """2?④퀎: ?뚯씠釉붿쓽 CAS ?곗씠?곕? 湲곕컲?쇰줈 KOSHA API 寃利??섑뻾"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    result_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal()

    def __init__(self, parent_gui, core, table_data):
        super().__init__()
        self.parent_gui = parent_gui # [NEW] DB ?묎렐 諛?濡쒓렇 異쒕젰???꾪븳 遺紐?李몄“
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
                row_idx = data.get("row_idx") # Fallback??                if i > 0: self.log_signal.emit("<span style='color:#5DADE2;'><b>" + "??*70 + "</b></span>")
                
                # [V11.4 ?좉퇋] ?ъ슜?먭? ?뚯씠釉붿쓽 CAS瑜?吏곸젒 ?섏젙??寃쎌슦 (罹먯떆??manual_data ??raw_content 議댁옱) 媛먯?
                is_manual_cas = False
                if f_hash and self.parent_gui.cache.get(f_hash, {}).get("manual_data", {}).get("raw_content"):
                    is_manual_cas = True

                # Case 0: DB 吏??濡쒖쭅 ?쒓굅 (??긽 API ?붿쭊 媛??
                self.log_signal.emit(f"[*] API ?붿쭊 媛?? [{prod}]")
                self.log_signal.emit("="*20 + f" [{prod} API 寃利??쒖옉] " + "="*20)
                # [V8.8] 吏?ν삎 CAS 異붿텧 諛??⑥쑀??蹂댁〈 濡쒖쭅 (?⑥쑀?? 蹂댁옣)
                # [V8.8] 吏?ν삎 CAS 異붿텧 諛??⑥쑀??蹂댁〈 濡쒖쭅 (?⑥쑀?? 蹂댁옣)
                cas_to_content = {}
                preserved_non_cas = [] # [踰꾧렇 ?섏젙] KOSHA????媛?'?곸뾽鍮꾨?' ??蹂댁〈??                
                for item in str(cas_content).split(";"):
                    item = item.strip()
                    if not item: continue
                    
                    match = re.search(r'(\d{2,7}-\d{2}-\d)', item)
                    if match:
                        cas = match.group(1)
                        # ?⑥쑀??愿꾪샇 ?덉쓽 ?댁슜留?異붿텧
                        content_match = re.search(r'\(([^)]+)\)', item)
                        content_val = content_match.group(1) if content_match else ""
                        
                        if content_val and "%" not in content_val and re.search(r'\d', content_val):
                            content_val = f"{content_val}%"
                        cas_to_content[cas] = content_val
                    else:
                        # CAS 踰덊샇 洹쒓꺽???꾨땶 寃??? ?곸뾽鍮꾨?(10%))? 洹몃?濡??듯빐??                        preserved_non_cas.append(item)
                
                pure_cas_list = list(cas_to_content.keys())
                pure_cas_str = "; ".join(pure_cas_list) if pure_cas_list else cas_content

                # [V11.4 ?듭떖] ?섎룞 ?섏젙 ??KOSHA API 罹먯떆(Cache-Hit)??媛뺤젣 ?고쉶
                f_hash_for_api = None if is_manual_cas else f_hash
                if is_manual_cas:
                    self.log_signal.emit(f"[*] CAS ?섎룞 ?섏젙 媛먯?: 怨쇨굅 吏?앹쓣 臾댁떆?섍퀬 KOSHA API瑜??ы샇異쒗빀?덈떎.")

                # [?섏젙] 肄붿뼱 ?몄텧 ??議곌굔遺 f_hash ?뚮씪誘명꽣 ?꾨떖
                raw_val_res = self.core.validate_with_kosha(pure_cas_str, log_func=self.log_signal.emit, full=False, f_hash=f_hash_for_api)
                
                # [V7.0 異붽?] 罹먯떆 ?곸쨷 ???섏쐞 ?뚯떛(components 猷⑦봽 ?? ?꾨㈃ ?고쉶
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
                        "status": "寃利??꾨즺 (罹먯떆)"
                    }
                    self.result_signal.emit(res_data)
                    self.progress_signal.emit(int((i + 1) / total * 100))
                    continue # API ?뚯떛 濡쒖쭅???ㅽ궢?섍퀬 ?ㅼ쓬 ?뚯씪濡?利됱떆 ?대룞
                
                # [V8.5] MSDS Core(components) -> GUI Format(res_1st, res_2nd) 釉뚮━吏 蹂?섍린
                res_1st_list = []
                res_2nd_list = []
                res_work_subjects = []    # 1% ?댁긽 痢≪젙???                res_work_non_subjects = [] # 1% 誘몃쭔 痢≪젙 鍮꾨???                
                for c in raw_val_res.get("components", []):
                    name = c.get("name", "Unknown")
                    cas = c.get("cas", "")
                    
                    # ?붿쭊 ?꾩넚 ???섎씪?덈뜕 ?⑥쑀?됱쓣 ?먮낯?먯꽌 蹂듭썝
                    range_val = cas_to_content.get(cas, c.get("content", ""))
                    
                    # [V27.5 ?곷Ц紐?湲고샇 ?꾨꼍 蹂댁〈 濡쒖쭅 蹂듭젣]
                    # [V15.8.18 ?섏젙] 怨쇰룄??紐낆묶 ?쇱넀 諛⑹? (湲濡쒕쾶 紐낆묶 諛?紐⑤뜽紐? 怨듬갚 蹂댁〈)
                    if re.search(r'[媛-??', name):
                        # 愿꾪샇 ?덉쓽 ?곷Ц??吏?곕릺, (二?, (?? 媛숈? ?뚯궗紐낆씠???꾩닔 湲고샇??蹂댁〈
                        name_no_eng = re.sub(r'\s*\([A-Za-z\s\d,]+\)$', '', name)
                        clean_name = name_no_eng.strip() # replace(" ", "") ?덈? 湲덉?! 怨듬갚 蹂댁〈!
                    else:
                        clean_name = name.strip()
                        
                    # [V11.3 理쒖쥌 吏移? KOSHA API 寃곌낵???붿쭊(V5)???쒖?紐낆묶怨?100% ?숆린??                    mes_std_name = engine.MES_MASTER_MAP.get(cas, "")
                    
                    if mes_std_name:
                        clean_name = str(mes_std_name)
                        # 留덉뒪??DB ?몄씠利??쒓굅 (遺꾩쭊/???깆? 泥좎???蹂댁〈)
                        clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()
                    else:
                        # ?붿쭊 留듭뿉 ?놁쓣 寃쎌슦?먮쭔 GUI 濡쒖뺄 留듭뿉??2李?諛⑹뼱留?媛??                        mes_entry = self.parent_gui.mes_cas_map.get(cas, {})
                        fallback_name = mes_entry.get("臾쇱쭏紐?) or mes_entry.get("?곸슜紐?)
                        if fallback_name and str(fallback_name).lower() != 'nan':
                            clean_name = str(fallback_name)
                            clean_name = re.sub(r'\s*\((?:STEL|TWA|PEL|TLV)\)', '', clean_name, flags=re.IGNORECASE).strip()

                    osh = c.get("osh", {})
                    is_work = osh.get("is_measured", False)
                    is_spec = osh.get("is_special", False)
                    is_mgmt = osh.get("is_special_mgmt", False)
                    is_permit = osh.get("is_permit", False)

                    prefix = ""
                    if is_mgmt: prefix = "[?밸퀎]"
                    elif is_permit: prefix = "[?덇?]"
                    elif is_spec and not is_work: prefix = "[?밴?]"

                    # [V17.3.2.18] ?⑤웾 ?꾨씫 ??'誘멸린??' ?쒖떆 ?뺤떇 ?듯빀
                    if not range_val or str(range_val).strip() == "":
                        range_val = "誘멸린??"
                    c_str = f"({range_val})"
                    
                    # [V9.1] 1李?寃곌낵: [?묐몢??臾쇱쭏紐?CAS(?⑥쑀??)] ?뺤떇 ?꾩닔
                    res_1st_list.append(f"{prefix}{clean_name}[{cas}{c_str}]")
                    
                    # 2. 2李?寃곌낵: ?묒뾽?섍꼍痢≪젙 ?먮뒗 ?뱀닔嫄닿컯吏꾨떒 ??곷쭔 吏묎퀎
                    if is_work or is_spec:
                        res_2nd_list.append(f"{prefix}{clean_name}{c_str}")
                        
                    # 3. 痢≪젙???(1% 湲곗? ?꾪꽣留?諛?鍮꾨???泥섎━)
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
                non_subj_str = f"痢≪젙 鍮꾨???{'; '.join(res_work_non_subjects)}]" if res_work_non_subjects else ""
                final_work_str = "; ".join(filter(None, [subj_str, non_subj_str]))

                val_res = {
                    "res_1st": res_1st_list,
                    "res_2nd": res_2nd_list,
                    "work_subjects": final_work_str,
                    "cas_with_content": str(cas_content).split("; ") if cas_content else [] 
                }

                # [吏?쒖꽌] ?⑹젒(Welding) ?곹솴 ?몄떇???좏빐?몄옄 蹂댁젙 濡쒖쭅 諛쒕룞
                is_welding = ("?⑹젒" in prod) or ("welding" in prod.lower())
                has_iron = "7439-89-6" in cas_to_content
                
                if is_welding and has_iron:
                    # 1. 2李?寃곌낵(reg2) 媛뺤젣 怨좎갑: API 寃곌낵? 臾닿??섍쾶 泥?異붽?
                    iron_content = cas_to_content.get("7439-89-6", "")
                    iron_str = f"泥?{iron_content})"
                    if iron_str not in res_2nd_list:
                        res_2nd_list.append(iron_str)
                    
                    # 2. 痢≪젙???work_subjects) 理쒖슦??湲곗엯: ?⑹젒?? ?고솕泥?遺꾩쭊, ??
                    # 湲곗〈 API 寃곌낵媛 ?덉쑝硫??ㅼ뿉 ?몃?肄쒕줎?쇰줈 ?곌껐
                    welding_hazard = "?⑹젒?? ?고솕泥?遺꾩쭊, ??"
                    if final_work_str:
                        final_work_str = f"{welding_hazard}; {final_work_str}"
                    else:
                        final_work_str = welding_hazard
                        
                    # val_res 媛깆떊
                    val_res["res_2nd"] = res_2nd_list
                    val_res["work_subjects"] = final_work_str

                # [V8.3] ?묐떟 蹂댁옣: 寃곌낵媛 鍮꾩뼱?덉쑝硫?紐낆떆??硫붿떆吏 ?쎌엯 (?⑹젒 蹂댁젙 ?댄썑 理쒖쥌 泥댄겕)
                if not val_res.get("res_1st"):
                    val_res["res_1st"] = [""]
                if not val_res.get("res_2nd"):
                    val_res["res_2nd"] = [""]
                
                res_data = {
                    "row_idx": row_idx,
                    "f_hash": f_hash, # [V8.0] ?댁떆 ?뺣낫 ?좎?
                    "filename": fn,
                    "product_name": prod,
                    "validation": val_res,
                    "status": "寃利??꾨즺"
                }
                self.result_signal.emit(res_data)
                self.progress_signal.emit(int((i + 1) / total * 100))
            except Exception as e:
                self.log_signal.emit(f"[!] ?ㅻ쪟 諛쒖깮 ({fn}): {e}")
        
        self.finished_signal.emit()

class ModernMappingPanel(QGroupBox):
    """媛濡쒗삎(?쇰컲 紐⑸줉) ?꾩슜 ?щ┝ 留ㅽ븨 ?⑤꼸 (D, L, M, N, O 湲곕낯媛?"""
    def __init__(self, title="?곗씠????留ㅽ븨 ?ㅼ젙 (媛濡쒗삎 ?꾩슜)"):
        super().__init__(title)
        self.inputs = {}
        layout = QGridLayout()
        layout.setContentsMargins(15, 20, 15, 10)
        layout.setHorizontalSpacing(15)
        layout.setVerticalSpacing(10)

        # ?ъ슜?먭? ?붿껌??媛濡쒗삎 5? ?듭떖 ??+ 諛붿씤??5媛??꾨뱶
        fields = [
            ("?쒕쾲/No", "A"), ("?쒗뭹紐?, "D"), ("?뚯씪紐?, "P"),
            ("2李?寃곌낵(洹쒖젣)", "L"), ("1李?寃곌낵(?꾩껜)", "N"),
            ("痢≪젙???", "M"), ("痢≪젙???", ""), # 痢≪젙??곸쓣 蹂듭닔濡???ν븯湲??꾪빐 ??移몄쑝濡?遺꾨━
            ("CAS ?먮낯", "O"),
            ("怨듭젙紐?, "B"), ("?쒖“/?ъ슜", "C"),
            ("?ъ슜?⑸룄", "E"), ("?붿랬湲됰웾", "S"), ("?⑥쐞", "T")
        ]

        for i, (name, default) in enumerate(fields):
            # 痢≪젙?????痢≪젙??? 泥섎━ ??媛숈씠 泥섎━?섎?濡?猷⑦봽?먯꽌 嫄대꼫?
            if name == "痢≪젙???": continue
            
            # ?ㅼ젣 ?쒖떆?섎뒗 ?몃뜳??怨꾩궛???꾪빐 蹂댁젙
            idx = sum(1 for f, _ in fields[:i] if f != "痢≪젙???") # 0, 1, 2...
            
            # 3媛쒕? ??以꾩뿉 諛곗튂?섏뿬 醫뚯륫?쇰줈 諛吏?(0, 1 / 2, 3 / 4, 5)
            row = idx // 3
            col_base = (idx % 3) * 2
            
            lbl = QLabel(name if name != "痢≪젙???" else "痢≪젙???)
            lbl.setStyleSheet("font-weight: bold; color: #444; min-width: 85px;")
            layout.addWidget(lbl, row, col_base, Qt.AlignRight)
            
            if name == "痢≪젙???":
                # ?섑룊 ?덉씠?꾩썐?쇰줈 移???媛쒕? 臾띠뼱??洹몃━????移몄뿉 諛곗튂
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
                self.inputs["痢≪젙???"] = edit1
                self.inputs["痢≪젙???"] = edit2
            else:
                edit = self._create_edit(default)
                layout.addWidget(edit, row, col_base + 1, Qt.AlignLeft)
                self.inputs[name] = edit
        
        # 留덉?留?鍮??댁뿉 Stretch瑜?二쇱뼱 ?꾩젽?ㅼ씠 醫뚯륫?쇰줈 諛吏묐릺?꾨줉 ??        layout.setColumnStretch(6, 1)
        # ?섎떒 ?щ갚??梨꾩썙 ?꾨줈 ?뺣젹?섎룄濡???(__init__??留덉?留?
        layout.setRowStretch((len(fields) + 1) // 3 + 1, 1)
        self.setLayout(layout)

    def _create_edit(self, text):
        """[Helper] ?쒖??붾맂 ?낅젰 ?꾨뱶 ?앹꽦"""
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
        """?꾩옱 ?낅젰??紐⑤뱺 留ㅽ븨 ?뺣낫瑜??뺤뀛?덈━濡?諛섑솚"""
        return {k: v.text().strip() for k, v in self.inputs.items()}

    def set_mapping(self, data):
        """??λ맂 ?곗씠?곕? 諛뷀깢?쇰줈 留ㅽ븨 ?낅젰李쎌쓣 梨꾩?"""
        if not data: return
        for k, v in data.items():
            if k in self.inputs:
                self.inputs[k].setText(v)


class SMUGUI(QMainWindow):
    @staticmethod
    def c2i(c):
        """[Utility] ?묒? ??臾몄옄(A, B, C...)瑜?1-based ?몃뜳??1, 2, 3...)濡?蹂??""
        if not c: return 0
        c_str = str(c).strip().upper()
        if not c_str or not c_str.isalpha():
            try: return int(c_str) # ?대? ?レ옄??寃쎌슦
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
        self.last_selected_row = -1 # [NEW] ?숈씪 ???????대룞 ??誘몃━蹂닿린 珥덇린??諛⑹???        self.init_ui()
        
        # [V7.5] ?숆린??臾닿껐???뺣낫瑜??꾪븳 珥덇린???쒖꽌 ?щ같移?        self.load_cache() # 1. 罹먯떆 癒쇱? 濡쒕뱶
        self.load_config() # 2. 洹??ㅼ쓬 ?ㅼ젙 濡쒕뱶 (setText 諛쒖깮 ???쒓렇??利됱떆 諛쒕룞)
        self.load_mes_master() # [NEW] MES 留덉뒪???곗씠?곗뀑 援ъ텞
        self.showMaximized()
        
        # [NEW] ?몄뀡 蹂듦뎄: ?댁쟾 ?뚯씪 紐⑸줉???뚯씠釉붿뿉 蹂듭썝
        self.restore_table_from_session()

    def load_mes_master(self):
        """[Master 吏?쒖꽌] MES 留덉뒪???곗씠?곗뀑 援ъ텞 諛?55媛??ㅻ뜑 蹂?섑솕"""
        self.mes_master_list = [] # ?쒕쾲 湲곕컲 ?꾩껜 由ъ뒪??(?꾨씫 ?놁쓬)
        self.mes_cas_map = {}     # CAS 踰덊샇 湲곕컲 議고쉶 留?(?뺢퇋?붿슜)
        
        mes_file = "?좏빐?몄옄_MES.txt"
        if not os.path.exists(mes_file):
            self.log(f"[!] {mes_file} ?뚯씪??李얠쓣 ???놁뒿?덈떎. 留덉뒪???곗씠?곗뀑???앸왂?⑸땲??")
            return

        try:
            # [V10.5] ?쒕쾲?쇰줈 ?꾨씫?놁씠 ?꾩껜 濡쒕뱶瑜??꾪빐 pandas ?쒖슜
            df_mes = pd.read_csv(mes_file, sep='\t', encoding='cp949')
            
            # 二쇰떂 吏?? CAS 踰덊샇媛 ?녿뒗 ?됰룄 紐⑤몢 ?ы븿
            for idx, row in df_mes.iterrows():
                # 55媛??ㅻ뜑 ?꾩껜瑜??뺤뀛?덈━濡?蹂?섑븯??蹂닿?
                entry = row.to_dict()
                self.mes_master_list.append(entry)
                
                # CAS 踰덊샇媛 ?덈뒗 寃쎌슦 ?뺢퇋??議고쉶 留듭뿉 ?깅줉
                # 而щ읆紐낆씠 源⑥쭏 ???덉쑝誘濡??몃뜳?ㅻ줈 ?묎렐 ?쒕룄 (CAS踰덊샇??7踰덉㎏ 而щ읆)
                cas_key = str(row.iloc[6]).strip() if len(row) > 6 else ""
                if cas_key and cas_key.lower() != 'nan' and re.match(r'^\d{2,7}-\d{2}-\d$', cas_key):
                    # 留뚯빟 以묐났 CAS媛 ?덈떎硫?理쒖큹 諛쒓껄??寃??쒖?) ?곗꽑 ?ъ슜
                    if cas_key not in self.mes_cas_map:
                        self.mes_cas_map[cas_key] = entry
            
            self.log(f"[*] MES 留덉뒪???곗씠?곗뀑 濡쒕뱶 ?꾨즺: {len(self.mes_master_list)}??(CAS 留ㅽ븨: {len(self.mes_cas_map)}嫄?")
        except Exception as e:
            self.log(f"[!] MES 留덉뒪??濡쒕뱶 ?ㅽ뙣: {e}")

    def _setup_sidebar(self):
        """?꾨씪?대㉧由?釉붾（ ?ъ씠?쒕컮 援ъ꽦 (?щ┝ 紐⑤뱶 吏??"""
        self.sidebar_widget = QFrame()
        self.sidebar_widget.setFixedWidth(200)
        self.sidebar_widget.setStyleSheet(f"background-color: {SIDEBAR_BLUE}; border: none;")
        self.sidebar_layout = QVBoxLayout(self.sidebar_widget)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)

        # ?ъ씠?쒕컮 ?곷떒 ?좉? 踰꾪듉
        self.btn_toggle_sidebar = QToolButton()
        self.btn_toggle_sidebar.setText("??)
        self.btn_toggle_sidebar.setFixedSize(60, 50)
        self.btn_toggle_sidebar.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_toggle_sidebar.setStyleSheet("color: white; font-size: 20px; background: transparent; border: none;")
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        self.sidebar_layout.addWidget(self.btn_toggle_sidebar, 0, Qt.AlignLeft)

        self.sidebar_layout.addSpacing(20)

        # 硫붾돱 踰꾪듉 由ъ뒪??        self.menu_buttons = []
        menus = [
            ("異붿텧 諛?寃利?, "[DOC]", 0),
            ("?섍꼍 ?ㅼ젙", "[SET]", 1)
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
        """[Premium] ?섏씠吏 ?꾪솚 諛??ъ씠?쒕컮 踰꾪듉 ?곹깭 ?낅뜲?댄듃"""
        self.stacked_widget.setCurrentIndex(idx)
        for b in self.menu_buttons:
            b.setChecked(False)
            b.update_style(False)
        btn.setChecked(True)
        btn.update_style(True)

        # [V7.5] ??쑝濡??꾪솚 ?? ?쒗듃 紐⑸줉??鍮꾩뼱 ?덉쑝硫?媛뺤젣 媛깆떊 ?쒕룄
        if idx == 0: # 異붿텧 諛?寃利???            path = self.edit_excel.text()
            if path and self.combo_sheet.count() == 0:
                self._update_sheet_list(path)

    def toggle_sidebar(self):
        """[Premium] ?ъ씠?쒕컮 ?щ┝ 紐⑤뱶 <-> ? 紐⑤뱶 ?꾪솚 ?좊땲硫붿씠??""
        self.sidebar_slim = not self.sidebar_slim
        target_width = 60 if self.sidebar_slim else 200
        
        # ?덈퉬 ?좊땲硫붿씠??(理쒖냼/理쒕? ?덈퉬 ?숈떆 ?쒖뼱濡??덉씠?꾩썐 諛湲??④낵 洹밸???
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
        
        self.btn_toggle_sidebar.setText("?? if self.sidebar_slim else "?")

    def _setup_log_section(self):
        """?섎떒 濡쒓렇 李?諛??좉? 踰꾪듉 援ъ꽦"""
        self.log_container = QWidget()
        self.log_v_layout = QVBoxLayout(self.log_container)
        self.log_v_layout.setContentsMargins(0, 0, 0, 0)
        self.log_v_layout.setSpacing(0)

        log_header = QFrame()
        log_header.setFixedHeight(30)
        log_header.setStyleSheet("background-color: #eee; border: none;")
        log_h_layout = QHBoxLayout(log_header)
        log_h_layout.setContentsMargins(10, 0, 10, 0)
        
        lbl_log = QLabel("?쒖뒪??遺꾩꽍 濡쒓렇")
        lbl_log.setStyleSheet("font-size: 11px; font-weight: bold; color: #666;")
        log_h_layout.addWidget(lbl_log)
        
        # [NEW] 吏꾪뻾 ?곹솴 ?띿뒪???쒖떆 ?쇰꺼
        self.lbl_extraction_progress = QLabel("")
        self.lbl_extraction_progress.setStyleSheet("font-size: 11px; font-weight: bold; color: #0078d4; margin-left: 15px;")
        log_h_layout.addWidget(self.lbl_extraction_progress)
        
        log_h_layout.addStretch()

        self.btn_clear_log = QToolButton()
        self.btn_clear_log.setText("?㏏ 濡쒓렇 珥덇린??)
        self.btn_clear_log.setStyleSheet("font-size: 10px; border: 1px solid #ccc; background: white; padding: 2px 5px;")
        log_h_layout.addWidget(self.btn_clear_log)

        self.btn_toggle_log = QToolButton()
        self.btn_toggle_log.setText("??濡쒓렇 ?묎린")
        self.btn_toggle_log.setStyleSheet("font-size: 10px; border: 1px solid #ccc; background: white; padding: 2px 5px;")
        self.btn_toggle_log.clicked.connect(self.toggle_log)
        log_h_layout.addWidget(self.btn_toggle_log)
        
        self.log_v_layout.addWidget(log_header)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #2b2b2b; color: #a9b7c6; font-family: 'Consolas'; border: none;")
        self.log_v_layout.addWidget(self.log_view)

        # [V10.8] ?앹꽦 ?쒖꽌 蹂댁젙: log_view媛 ?뺤쓽?????쒓렇???곌껐 (AttributeError 諛⑹?)
        self.btn_clear_log.clicked.connect(self.log_view.clear)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar { border: none; background: #eee; } QProgressBar::chunk { background-color: #0078d4; }")
        self.log_v_layout.addWidget(self.progress)
        
        self.main_splitter.addWidget(self.log_container)
        self.main_splitter.setSizes([600, 200])

    def toggle_log(self):
        """濡쒓렇 李??④린湲?蹂댁씠湲?(?좊땲硫붿씠???놁씠 利됱떆 ?꾪솚?쇰줈 諛섏쓳???뺣낫)"""
        is_visible = self.log_view.isVisible()
        self.log_view.setVisible(not is_visible)
        self.progress.setVisible(not is_visible)
        self.btn_toggle_log.setText("??濡쒓렇 ?닿린" if is_visible else "??濡쒓렇 ?묎린")
        # ?믪씠 ?쒖빟 ?댁젣?섏뿬 QSplitter媛 ?먮룞?뷀븯?꾨줉 ?꾩엫


    def log(self, message):
        """[V17.4.0.2] 吏?ν삎 ?쒖뒪??濡쒓렇 異쒕젰: ?ъ슜?먭? 寃??以묒씪 ???ㅽ겕濡?怨좎젙"""
        if hasattr(self, 'log_view'):
            # 1. ?꾩옱 ?ㅽ겕濡ㅻ컮 ?곹깭 ?뺤씤 (理쒗븯???щ?)
            v_bar = self.log_view.verticalScrollBar()
            is_at_bottom = v_bar.value() >= v_bar.maximum() - 10 # ?쎄컙??留덉쭊 ?덉슜
            
            # 2. 濡쒓렇 異붽?
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_view.append(f"[{timestamp}] {message}")
            
            # 3. 議곌굔遺 ?먮룞 ?ㅽ겕濡? 理쒗븯?⑥뿉 ?덉뿀???뚮쭔 ?붾㈃???대┝
            if is_at_bottom:
                self.log_view.ensureCursorVisible()
            
        # [臾닿껐?? ?곕???異쒕젰 ??cp949 ?몄퐫???ㅻ쪟 諛⑹? (?대え吏 ?꾪꽣留?諛??띿뒪???쒓렇 蹂??
        try:
            # ?곕??먯슜 ?띿뒪??蹂??留?            tag_map = {
                "??": "[START]", "??: "[OK]", "??: "[FAIL]", 
                "?좑툘": "[WARN]", "?렞": "[TARGET]", "?뵇": "[SEARCH]",
                "?윟": "[PASS]", "?윞": "[CHECK]", "?뵶": "[ERROR]", "?뵷": "[INFO]"
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

        # 1. ?ъ씠?쒕컮
        self._setup_sidebar()

        # 2. 硫붿씤 而⑦뀗痢??곸뿭 (Stretch 1 遺?ы븯???ъ씠?쒕컮媛 諛?대궡??怨듦컙??紐⑤몢 ?먯쑀)
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.main_h_layout.addLayout(self.content_layout, 1)


        self.main_splitter = QSplitter(Qt.Vertical)
        # [V15.8.15] 濡쒓렇李쎄낵 ?뚯씠釉?寃쎄퀎 ?쒖씤??媛뺥솕瑜??꾪븳 ?꾨━誘몄뾼 釉붾（ ?붾컮?대뜑 ?댁떇
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

        # ?섏씠吏 0: 湲곗〈 二??붾㈃
        self.page_extraction = self._create_extraction_page()
        self.stacked_widget.addWidget(self.page_extraction)

        self.page_settings = self._create_settings_page()
        self.stacked_widget.addWidget(self.page_settings)

        # 3. 濡쒓렇 李?        self._setup_log_section()
        

    def _create_settings_page(self):
        """[Page 2] ?곗씠??留듯븨 諛?蹂댁“ 愿由??꾧뎄瑜?紐⑥? ?섍꼍 ?ㅼ젙 ?섏씠吏"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # 1. 而щ읆 留듯븨 ?ㅼ젙 ?곸뿭
        map_group = QGroupBox("?곗씠????留ㅽ븨 ?ㅼ젙 (?묒? 而щ읆 吏??")
        map_layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(400)
        self.mapping_panel = ModernMappingPanel()
        scroll.setWidget(self.mapping_panel)
        map_layout.addWidget(scroll)
        map_group.setLayout(map_layout)
        layout.addWidget(map_group)

        # 2. ?뚯씪 諛?踰덊샇 愿由??곸뿭 (遺媛 湲곕뒫)
        lower_layout = QHBoxLayout()
        
        file_mgmt_group = QGroupBox("?뚯씪 愿由?諛?踰덊샇 遺??(蹂댁“ ?꾧뎄)")
        file_mgmt_layout = QGridLayout()
        file_mgmt_layout.setContentsMargins(15, 15, 15, 15)
        
        file_mgmt_layout.addWidget(QLabel("?쒖옉 踰덊샇:"), 0, 0)
        self.edit_start_num = QLineEdit("1")
        self.edit_start_num.setFixedWidth(50)
        file_mgmt_layout.addWidget(self.edit_start_num, 0, 1)
        
        self.btn_batch_rename = QPushButton("?뚯씪紐??쇨큵 蹂寃?)
        self.btn_batch_rename.setStyleSheet("background-color: #6c757d; min-height: 35px;")
        self.btn_batch_rename.clicked.connect(self.batch_rename_files)
        file_mgmt_layout.addWidget(self.btn_batch_rename, 1, 0, 1, 2)
        
        self.btn_excel_no = QPushButton("?묒? A??踰덊샇 遺??)
        self.btn_excel_no.setStyleSheet("background-color: #e6a23c; min-height: 35px;")
        self.btn_excel_no.clicked.connect(self.assign_excel_numbers)
        file_mgmt_layout.addWidget(self.btn_excel_no, 2, 0, 1, 2)
        
        file_mgmt_group.setLayout(file_mgmt_layout)
        lower_layout.addWidget(file_mgmt_group)
        
        # 罹먯떆 愿由???異붽? ?ㅼ젙 踰꾪듉??諛곗튂 媛??        info_group = QGroupBox("?쒖뒪???뺣낫 諛?罹먯떆")
        info_layout = QVBoxLayout()
        info_layout.addWidget(QLabel("MSDS Intelligence v2.0 - Enterprise Edition"))
        info_layout.addWidget(QLabel(f"?묐룞 紐⑤뱶: 吏?ν삎 諛붿씤???쒖꽦??))
        btn_clear_cache = QPushButton("?뺣? 罹먯떆(Hash) 珥덇린??)
        btn_clear_cache.setStyleSheet("background-color: #f56c6c; color: white;")
        info_layout.addWidget(btn_clear_cache)
        info_group.setLayout(info_layout)
        lower_layout.addWidget(info_group)
        
        layout.addLayout(lower_layout)
        layout.addStretch()
        
        return page

    def _create_extraction_page(self):
        """[Page 0] 理쒖쟻?붾맂 異붿텧 諛?寃利?硫붿씤 ?섏씠吏 (?뚯씠釉??뺤옣??"""
        page = QWidget()
        main_layout = QVBoxLayout(page)

        # A. ?곷떒 ?≪뀡 諛?(?뚯씪 濡쒕뱶 諛??붿쭊 ?쒖뼱)
        header = QHBoxLayout()
        self.drop_area = FileDropArea()
        self.drop_area.filesDropped.connect(self.on_files_dropped)
        header.addWidget(self.drop_area)

        self.lbl_file_count = QLabel("0媛?)
        self.lbl_file_count.setFixedWidth(50)
        self.lbl_file_count.setAlignment(Qt.AlignCenter)
        self.lbl_file_count.setStyleSheet("background-color: #f56c6c; color: white; border-radius: 10px; padding: 2px 5px; font-weight: bold; font-size: 11px;")
        header.addWidget(self.lbl_file_count)

        btn_load = QPushButton("?대뜑/?뚯씪 ?좏깮")
        btn_load.setFixedWidth(110); btn_load.setFixedHeight(35)
        
        menu_load = QMenu(self)
        action_file = menu_load.addAction("?뱞 ?뚯씪 ?좏깮")
        action_folder = menu_load.addAction("?뱚 ?대뜑 ?좏깮")
        action_file.triggered.connect(self.load_pdfs)
        action_folder.triggered.connect(self.load_pdf_folder)
        btn_load.setMenu(menu_load)
        
        header.addWidget(btn_load)

        btn_reset = QPushButton("珥덇린??)
        btn_reset.setFixedWidth(60); btn_reset.setFixedHeight(35)
        btn_reset.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold;")
        btn_reset.clicked.connect(self.reset_all)
        header.addWidget(btn_reset)

        btn_reload = QPushButton("?붿쭊 ?봽")
        btn_reload.setFixedWidth(70); btn_reload.setFixedHeight(35)
        btn_reload.setStyleSheet("background-color: #67c23a; color: white; font-weight: bold;")
        btn_reload.clicked.connect(self.reload_engine)
        header.addWidget(btn_reload)

        header.addSpacing(20)
        self.btn_step1 = QPushButton("1?④퀎 異붿텧")
        self.btn_step1.setFixedHeight(35); self.btn_step1.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold;")
        self.btn_step1.setToolTip("紐⑸줉???덈뒗 PDF ?뚯씪?ㅼ뿉??MSDS ?곗씠?곕? AI濡??먮룞 異붿텧?⑸땲??")
        self.btn_step1.clicked.connect(self.run_extraction)
        header.addWidget(self.btn_step1)

        self.btn_step2 = QPushButton("2?④퀎 寃利?)
        self.btn_step2.setFixedHeight(35); self.btn_step2.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
        self.btn_step2.setToolTip("異붿텧???곗씠?곕? 諛뷀깢?쇰줈 怨듬떒 DB 諛?留덉뒪??DB? ?議고븯??洹쒖젣 ?щ?瑜?寃利앺빀?덈떎.")
        self.btn_step2.clicked.connect(self.run_validation)
        header.addWidget(self.btn_step2)

        self.btn_stop = QPushButton("?ㅽ뻾 以묒?")
        self.btn_stop.setFixedHeight(35); self.btn_stop.setStyleSheet("QPushButton { background-color: #d93025; color: white; font-weight: bold; } QPushButton:disabled { background-color: #eaa9a9; color: #ffffff; }")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_process)
        header.addWidget(self.btn_stop)

        header.addStretch() # 踰꾪듉?ㅼ쓣 ?쇱そ?쇰줈 諛怨??곗륫???щ갚 ?뺣낫

        # [NEW] UX/UI ?⑤낫?? ?꾩?留?踰꾪듉 異붽? (湲곗〈 鍮?以???퉬 諛⑹?瑜??꾪빐 ??以꾨줈 ?몄엯)
        self.btn_help = QToolButton()
        self.btn_help.setText(" ? ")
        self.btn_help.setToolTip("?듭떖 ?ъ슜踰?媛?대뱶瑜??뺤씤?⑸땲??")
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

        # B. ?щ┝ 而⑦듃濡?諛?(?묒? ?ㅼ젙) - 媛濡쒗삎 諛곗튂濡?怨듦컙 ?덉빟
        excel_bar = QHBoxLayout()
        excel_bar.addWidget(QLabel("????묒?:"))
        self.edit_excel = QLineEdit()
        self.edit_excel.setPlaceholderText("寃곌낵瑜???ν븷 ?묒? ?뚯씪???좏깮?섏꽭??..")
        excel_bar.addWidget(self.edit_excel)
        
        btn_ex = QPushButton("李얘린")
        btn_ex.setFixedWidth(50); btn_ex.clicked.connect(self.select_excel)
        excel_bar.addWidget(btn_ex)

        excel_bar.addSpacing(15)
        excel_bar.addWidget(QLabel("?쒗듃:"))
        self.combo_sheet = QComboBox()
        self.combo_sheet.setMinimumWidth(100)
        excel_bar.addWidget(self.combo_sheet)

        excel_bar.addWidget(QLabel("??"))
        self.edit_start_row = QLineEdit("3")
        self.edit_start_row.setFixedWidth(40); self.edit_start_row.setAlignment(Qt.AlignCenter)
        excel_bar.addWidget(self.edit_start_row)

        excel_bar.addSpacing(15)
        btn_save_h = QPushButton("?뱚 ?묒??????)
        btn_save_h.setFixedWidth(130); btn_save_h.setFixedHeight(35)
        btn_save_h.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        btn_save_h.setToolTip("?꾩옱 ?붾㈃???쒖떆???곗씠?곕? ?묒?(Excel) ?뚯씪濡???ν빀?덈떎.")
        btn_save_h.clicked.connect(self.perform_standard_save)
        excel_bar.addWidget(btn_save_h)
        
        self.btn_open_ex = QPushButton("?뱛 ?묒? ?닿린")
        self.btn_open_ex.setFixedWidth(110); self.btn_open_ex.setFixedHeight(35)
        self.btn_open_ex.setStyleSheet("background-color: #17a2b8; color: white; font-weight: bold;")
        self.btn_open_ex.clicked.connect(self.open_saved_excel)
        excel_bar.addWidget(self.btn_open_ex)
        
        main_layout.addLayout(excel_bar)

        # C. 硫붿씤 而⑦뀗痢?(Splitter ?꾩엯: ?뚯씠釉???誘몃━蹂닿린)
        self.content_splitter = QSplitter(Qt.Horizontal)
        
        # [醫뚯륫] ?뚯씠釉??곸뿭 而⑦뀒?대꼫
        self.left_container = QWidget()
        self.left_vbox = QVBoxLayout(self.left_container)
        self.left_vbox.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "?쒕쾲", "No", "?먮낯 ?쒗뭹紐?, "CAS ?먮낯(?섏젙)", 
            "痢≪젙???, "2李?寃곌낵(洹쒖젣)", "1李?寃곌낵(?꾩껜)", "?뚯씪紐?, "Hash", "Full Path", "Page"
        ])
        self.table.horizontalHeaderItem(3).setToolTip("CAS 踰덊샇瑜??대┃?섎㈃ KOSHA ?뷀븰臾쇱쭏?뺣낫 ?섏씠吏濡??대룞?⑸땲??")
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
        # [V7.0] 愿由ъ슜 ?대뱾? 紐⑤몢 ?④? 泥섎━
        for hidden_col in [7, 8, 9, 10]:
            self.table.setColumnHidden(hidden_col, True)
        
        # [V8.6] HTML ?몃━寃뚯씠??蹂듭썝 諛?MultiLineDelegate ?곸슜
        self.table.setItemDelegateForColumn(3, MultiLineDelegate(self))
        for col in [4, 5, 6]:
            self.table.setItemDelegateForColumn(col, HTMLDelegate(self))
            
        # [NEW] ?고겢由?CAS ?꾩슜 蹂듭궗 硫붾돱
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_cas_copy_menu)
        
        # [NEW] ???좏깮 ??誘몃━蹂닿린 ?곕룞
        self.table.itemSelectionChanged.connect(self.sync_pdf_preview)
        # [V7.0] ? ?대┃ ??利됯컖 誘몃━蹂닿린 ?곕룞 (釉뚮┸吏)
        self.table.cellClicked.connect(self.on_row_clicked)
        
        self.table.itemChanged.connect(self.on_table_item_changed)
        
        # [NEW] 鍮??붾㈃ ?뚰꽣留덊겕 (Empty State Label)
        self.lbl_watermark = QLabel("???ш린??PDF ?뚯씪???뚯뼱???볦쑝?몄슂  ?? ??[異붿텧 ?쒖옉] 踰꾪듉???꾨Ⅴ?몄슂", self.table)
        self.lbl_watermark.setAlignment(Qt.AlignCenter)
        self.lbl_watermark.setStyleSheet("color: #b0b0b0; font-size: 16px; font-weight: bold; background: transparent;")
        # ?뚯씠釉?以묒븰???꾩튂?쒗궎湲??꾪빐 ?덉씠?꾩썐 ?몃┃ ?ъ슜
        watermark_layout = QVBoxLayout(self.table)
        watermark_layout.addWidget(self.lbl_watermark)
        self.lbl_watermark.show() # 珥덇린 ?곹깭???몄텧

        self.left_vbox.addWidget(self.table)
        
        self.content_splitter.addWidget(self.left_container)

        # [?곗륫] 誘몃━蹂닿린 ?⑤꼸 (?좉퇋)
        self.preview_pane = PDFPreviewPanel()
        self.content_splitter.addWidget(self.preview_pane)
        self.content_splitter.setSizes([1000, 650]) # 珥덇린 ?덈퉬 ?ㅼ젙 (二쇰떂??議곗젅 媛??

        main_layout.addWidget(self.content_splitter)
        
        return page

    def on_row_clicked(self, row, column):
        """
        [V15.8.8] ?뚯씠釉????대┃ ???대떦 ?깅텇???꾩튂??PDF ?섏씠吏濡??먮룞 ?대룞
        """
        # [V17.3.2.11] ?숈씪 ???댁뿉???대룞 ???섏씠吏 ?먰봽 諛⑹? (吏???낅뜲?댄듃 泥댄겕)
        if hasattr(self, 'last_selected_row') and self.last_selected_row == row:
            return
        
        # [V17.3.2.11] ?ㅼ쓬 ?대깽??猷⑦봽?먯꽌 ??踰덊샇 ?낅뜲?댄듃 (sync_pdf_preview???媛꾩꽠 諛⑹?)
        QTimer.singleShot(0, lambda: setattr(self, 'last_selected_row', row))

        try:
            target_pdf_path_item = self.table.item(row, COL_IDX_FILEPATH)
            if not target_pdf_path_item: return
            target_pdf_path = target_pdf_path_item.text()
            if not target_pdf_path or not os.path.exists(target_pdf_path): return

            # 1. PDF 濡쒕뱶
            is_new_pdf = False
            if self.preview_pane.current_pdf_path != target_pdf_path:
                self.preview_pane.load_pdf(target_pdf_path)
                is_new_pdf = True

            # 2. ?섏씠吏 ?대룞
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
        """[?섏젙] ?좏깮???됱쓽 ?쒗뭹紐낃낵 ?쇱튂?섎뒗 ?뺥솗??PDF 寃쎈줈 異붿쟻"""
        curr_row = self.table.currentRow()
        if curr_row < 0: return
        
        # [V17.3.2.11] ?숈씪 ?????대룞 ??以묐났 濡쒕뱶 諛⑹? (吏???낅뜲?댄듃 泥댄겕)
        if hasattr(self, 'last_selected_row') and self.last_selected_row == curr_row:
            return
        
        # [V17.3.2.11] ?ㅼ쓬 ?대깽??猷⑦봽?먯꽌 ??踰덊샇 ?낅뜲?댄듃
        QTimer.singleShot(0, lambda: setattr(self, 'last_selected_row', curr_row))

        # 7踰????뚯씪紐? 異붿텧
        fn_item = self.table.item(curr_row, 7)
        if not fn_item: return
        fn = fn_item.text().strip()
        
        # ?꾩껜 寃쎈줈 由ъ뒪?몄뿉???뚯씪紐?留ㅼ묶
        path = next((p for p in self.pdf_paths if os.path.basename(p) == fn), None)
        
        if path:
            self.preview_pane.load_pdf(path) # ?댁젣 ?됰슧???⑹젒???????궎 ?쎌뭅媛 ?밸땲??

    def show_cas_copy_menu(self, pos):
        """[?듭떖] ?고겢由????쒖닔 CAS 踰덊샇留?異붿텧?섏뿬 蹂듭궗 湲곕뒫"""
        index = self.table.indexAt(pos)
        if index.isValid() and index.column() == 3:
            menu = QMenu()
            cell_text = self.table.item(index.row(), 3).text()
            cas_list = re.findall(r'\d{2,7}-\d{2}-\d', cell_text)
            
            if cas_list:
                for cas in list(set(cas_list)):
                    action = menu.addAction(f"CAS {cas} 蹂듭궗")
                    action.triggered.connect(lambda _, c=cas: QApplication.clipboard().setText(c))
                menu.addSeparator()
                action_all = menu.addAction("紐⑤뱺 CAS 蹂듭궗 (?몃?肄쒕줎 援щ텇)")
                action_all.triggered.connect(lambda: QApplication.clipboard().setText("; ".join(list(set(cas_list)))))
                
            menu.exec_(self.table.viewport().mapToGlobal(pos))






    def save_config(self):
        """[V6.995] ?꾩옱 ?ㅼ젙??config.json?????""
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
            self.log("[*] ?ㅼ젙??config.json???먮룞 ??λ릺?덉뒿?덈떎.")
        except Exception as e:
            print(f"Config Save Error: {e}")

    def load_config(self):
        """[V6.995] config.json?먯꽌 ?ㅼ젙???쎌뼱 UI 蹂듦뎄"""
        if not os.path.exists("config.json"): return
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
            
            # 1. 留ㅽ븨 ?ㅼ젙 蹂듦뎄
            if "mapping" in config:
                self.mapping_panel.set_mapping(config["mapping"])
            
            # 2. 湲고? ?ㅼ젙 蹂듦뎄
            if "excel_path" in config:
                self.edit_excel.setText(config["excel_path"])
                # ?묒? 寃쎈줈媛 ?덉쑝硫??쒗듃 紐⑸줉 濡쒕뱶 ?쒕룄
                if config["excel_path"] and os.path.exists(config["excel_path"]):
                    self._update_sheet_list(config["excel_path"], config.get("sheet_name"))

            if "start_row" in config: self.edit_start_row.setText(config["start_row"])
            if "start_num" in config: self.edit_start_num.setText(config["start_num"])
            
            if "pdf_paths" in config:
                self.pdf_paths = config["pdf_paths"]
                if self.pdf_paths:
                    # [V17.3.1.2] 濡쒕뱶 利됱떆 ?뺣젹 媛뺤젣 (?뺣젹 臾닿껐???뺣낫)
                    self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
                    self.log(f"[*] ?댁쟾 ?몄뀡?먯꽌 {len(self.pdf_paths)}媛쒖쓽 PDF 紐⑸줉??遺덈윭?붿뒿?덈떎.")
                    self.update_file_count_display()
                    
        except Exception as e:
            self.log(f"[!] ?ㅼ젙 蹂듦뎄 ?ㅽ뙣: {e}")

    def restore_table_from_session(self):
        """[NEW] ??λ맂 pdf_paths? cache瑜??댁슜???뚯씠釉?UI 蹂듦뎄"""
        if not hasattr(self, 'pdf_paths') or not self.pdf_paths:
            return
            
        self.log("[*] ?뚯씠釉??곗씠?곕? 蹂듦뎄 以묒엯?덈떎...")
        
        # [V17.3.1.2] 蹂듦뎄 ???뺣젹 ?곹깭 媛뺤젣 ?뺤씤
        self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
        
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        
        for path in self.pdf_paths:
            if not os.path.exists(path):
                continue
                
            fn = os.path.basename(path)
            f_hash = self.core.calculate_file_hash(path)
            
            # 罹먯떆媛 ?덉쑝硫?罹먯떆 ?곗씠???ъ슜, ?놁쑝硫?湲곕낯 ?뺣낫留??ъ슜
            if f_hash and f_hash in self.cache:
                data = self.cache[f_hash].copy()
                data["filename"] = fn
                data["full_path"] = path
                data["f_hash"] = f_hash
                self.add_result_to_table(data)
                
                # 寃利?寃곌낵???덉쑝硫?諛섏쁺
                if "manual_data" in data or "reliability" in data:
                    row = self.table.rowCount() - 1
                    # add_result_to_table???뺣젹???????덉쑝誘濡??됱쓣 ?ㅼ떆 李얠븘????                    for r in range(self.table.rowCount()):
                        if self.table.item(r, 8) and self.table.item(r, 8).text() == f_hash:
                            row = r
                            break
                    
                    # ?섎룞 ?곗씠?곕굹 寃利?寃곌낵媛 ?덉쑝硫?update_validation_row ?몄텧
                    v_data = data.get("manual_data", {})
                    self.update_validation_row(
                        row,
                        v_data.get("raw_content", data.get("raw_content", "")).split("; "),
                        v_data.get("reg1", "").split(";\n"),
                        v_data.get("reg2", "").split(";\n"),
                        v_data.get("measure", ""),
                        status=data.get("status", "罹먯떆 濡쒕뱶??)
                    )
            else:
                # 罹먯떆 ?녿뒗 ?뚯씪? 湲곕낯 ?됰쭔 異붽?
                data = {
                    "filename": fn,
                    "f_hash": f_hash,
                    "product_name": "誘몃텇??,
                    "reliability": "[NEW]",
                    "?좏샇??: "??,
                    "raw_content": "",
                    "full_path": path,
                    "status": "?湲?以?
                }
                self.add_result_to_table(data)
                
        self.table.blockSignals(False)
        self.update_file_count_display()
        self.log("???몄뀡 蹂듦뎄媛 ?꾨즺?섏뿀?듬땲??")

    def load_cache(self):
        """[NEW] smu_cache.json?먯꽌 ?곴뎄 罹먯떆 濡쒕뱶"""
        if not os.path.exists("smu_cache.json"): return
        try:
            with open("smu_cache.json", "r", encoding="utf-8") as f:
                self.cache = json.load(f)
            self.log(f"[*] {len(self.cache)}嫄댁쓽 遺꾩꽍 罹먯떆瑜?遺덈윭?붿뒿?덈떎.")
        except: pass

    def save_cache(self):
        """[NEW] ?꾩옱 罹먯떆瑜?smu_cache.json?????""
        try:
            with open("smu_cache.json", "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=4)
        except: pass

    def update_cache(self, f_hash, data):
        """[NEW] ?뚯빱濡쒕???諛쏆? ??遺꾩꽍 寃곌낵瑜?罹먯떆?????""
        self.cache[f_hash] = data
        self.save_cache()

    def on_table_item_changed(self, item):
        """[V7.3] ?뚯씠釉?? ?섎룞 ?섏젙 ??罹먯떆(JSON) ?ㅼ떆媛??낅뜲?댄듃 (Gold Shield)"""
        if not self.table.signalsBlocked():
            row = item.row()
            col = item.column()
            
            # 媛먯떆 踰붿쐞 ?뺣?: ?쒗뭹紐?2), CAS(3), 痢≪젙???4), 2李?5), 1李?6)
            if col in [2, 3, 4, 5, 6]:
                hash_item = self.table.item(row, 8) 
                if hash_item:
                    f_hash = hash_item.text().strip()
                    if f_hash in self.cache:
                        new_text = item.text().strip()
                        # manual_data 援ъ“ ?뺣낫
                        if "manual_data" not in self.cache[f_hash]:
                            self.cache[f_hash]["manual_data"] = {}
                        
                        # 媛?而щ읆蹂???留ㅽ븨
                        col_map = {2: "product_name", 3: "raw_content", 4: "measure", 5: "reg2", 6: "reg1"}
                        key = col_map.get(col)
                        
                        if key:
                            # 1. 罹먯떆 ?곴뎄 ???                            if "manual_data" not in self.cache[f_hash]:
                                self.cache[f_hash]["manual_data"] = {}
                            
                            # [V11.4 罹먯떆 ?뺥솕] CAS(raw_content)媛 ?섏젙?섎㈃, 湲곗〈 洹쒖젣 寃곌낵 罹먯떆瑜?紐⑤몢 ??젣
                            if key == "raw_content":
                                for old_k in ["measure", "reg2", "reg1"]:
                                    if old_k in self.cache[f_hash]["manual_data"]:
                                        del self.cache[f_hash]["manual_data"][old_k]
                                        
                            self.cache[f_hash]["manual_data"][key] = new_text
                            self.save_cache()
                            
                            # 2. self.results 硫붾え由??ㅼ떆媛??숆린??(Hot-Sync)
                            for res in self.results:
                                if res.get('f_hash') == f_hash:
                                    res[key] = new_text
                                    break
                            
                            # 3. [Task 5 異붽?] 留뚯빟 ?쒗뭹紐낆씠 ?섏젙?섏뿀?ㅻ㈃ ?ㅻⅨ ?곌? ?뺣낫?ㅻ룄 利됱떆 ?숆린???좎?
                            # (二쇰떂???섎룞?쇰줈 怨좎튇 寃곌낵媛 ?쒖뒪???대? 蹂?섏뿉 利됱떆 媛곸씤??
                            self.log(f"[*] ?ㅼ떆媛??숆린???꾨즺: {key} -> {new_text[:20]}...")

    def _update_sheet_list(self, path, select_name=None):
        """[V6.995] ?ㅼ젙 蹂듦뎄 ???쒗듃 紐⑸줉 ?먮룞 媛깆떊 ?ы띁"""
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
        """[NEW] 紐⑤뱺 ?곗씠??珥덇린??(?뚯씪 紐⑸줉, ?뚯씠釉? 濡쒓렇, 吏꾪뻾諛?"""
        # ?묒뾽 以묒씤 寃쎌슦 ?뺤씤
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, "?뺤씤", "?꾩옱 ?묒뾽??吏꾪뻾 以묒엯?덈떎. ?묒뾽??以묐떒?섍퀬 紐⑤뱺 ?곗씠?곕? 珥덇린?뷀븷源뚯슂?", 
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No: return
            self.worker.terminate()
            self.worker.wait()
            self.log("[!] ?묒뾽???ъ슜???붿껌?쇰줈 以묐떒?섏뿀?듬땲??")

        # 理쒖쥌 ?뺤씤 (?묒뾽 以묒씠 ?꾨땺 ?뚮쭔 蹂꾨룄 ?몄텧??
        else:
            reply = QMessageBox.question(self, "?꾩껜 珥덇린??, "紐⑤뱺 ?뚯씪 紐⑸줉怨?異붿텧 寃곌낵, 濡쒓렇瑜?珥덇린?뷀븯?쒓쿋?듬땲源?", 
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No: return

        # ?곗씠??珥덇린??        self.pdf_paths = []
        self.results = []
        self.cache = {} # [V17.4.0.9] 硫붾え由?罹먯떆源뚯? ?꾩쟾 ??젣
        if os.path.exists("smu_cache.json"):
            try: os.remove("smu_cache.json")
            except: pass
            
        self.table.setRowCount(0)
        self.log_view.clear()
        self.progress.setValue(0)
        self.update_file_count_display()
        self.log("??紐⑤뱺 ?곗씠?곗? 罹먯떆媛 珥덇린?붾릺?덉뒿?덈떎.")

    def reload_engine(self):
        """[HOT-RELOAD] ?붿쭊 紐⑤뱢???ㅼ떆 濡쒕뱶?섎ŉ 罹먯떆???꾩쟾 珥덇린??""
        try:
            # [V23.0.0.0] ?붿쭊 ?덈줈怨좎묠 ???ъ슜???붿껌???곕씪 濡쒓렇 李?珥덇린??            if hasattr(self, 'log_view'):
                self.log_view.clear()

            # [V17.4.0.9] ?붿쭊 濡쒖쭅 蹂寃쎌쓣 利됱떆 諛섏쁺?섍린 ?꾪빐 罹먯떆 媛뺤젣 ??젣
            if os.path.exists("smu_cache.json"):
                try: os.remove("smu_cache.json")
                except: pass
            self.cache = {}
            self.log("[!] ?붿쭊???덈줈怨좎묠 ?섏뿀?듬땲?? (?뺣? 遺꾩꽍???꾪빐 罹먯떆 珥덇린?붾맖)")

            import msds_engine_v5
            importlib.reload(msds_engine_v5)
            importlib.reload(msds_core)
            self.core = msds_core.MSDSCore()
            self.log("???붿쭊 諛?肄붿뼱 紐⑤뱢???깃났?곸쑝濡??щ줈?쒕릺?덉뒿?덈떎.")
            QMessageBox.information(self, "?깃났", "?섏젙???붿쭊??GUI??諛섏쁺?섏뿀?듬땲??")
        except Exception as e:
            self.log(f"???붿쭊 ?щ줈???ㅽ뙣: {e}")
            QMessageBox.critical(self, "?ㅽ뙣", f"?붿쭊 ?щ줈??以??ㅻ쪟 諛쒖깮:\n{e}")

    def stop_worker(self):
        """?꾩옱 ?ㅽ뻾 以묒씤 ?뚯빱 ?ㅻ젅??以묐떒"""
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, "?뺤씤", "吏꾪뻾 以묒씤 紐⑤뱺 ?묒뾽??以묐떒?섏떆寃좎뒿?덇퉴?", 
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.worker.terminate()
                self.worker.wait() # ?ㅻ젅?쒓? 醫낅즺???뚭퉴吏 ?湲?                self.log("[!] ?ъ슜?먯뿉 ?섑빐 ?묒뾽??媛뺤젣 以묐떒?섏뿀?듬땲??")
                self.progress.setValue(0)
                QMessageBox.warning(self, "以묐떒", "?묒뾽??以묐떒?섏뿀?듬땲??")
        else:
            QMessageBox.information(self, "?덈궡", "?꾩옱 ?ㅽ뻾 以묒씤 ?묒뾽???놁뒿?덈떎.")

    def load_pdfs(self):
        """[Part 6] PDF ?뚯씪 ?좏깮 ?ㅼ씠?쇰줈洹?""
        files, _ = QFileDialog.getOpenFileNames(self, "遺꾩꽍??MSDS PDF ?좏깮", "", "PDF Files (*.pdf)")
        if files:
            # [NEW] 以묐났 ?뚯씪 ?쒖쇅 濡쒖쭅
            new_files = []
            for f in files:
                f = os.path.normpath(f).replace('\\', '/')
                if f in self.pdf_paths:
                    self.log(f"[寃쎄퀬] {os.path.basename(f)} ?뚯씪? ?대? 紐⑸줉???덉뒿?덈떎. (異붽? ?쒖쇅??")
                    continue
                new_files.append(f)
            
            if new_files:
                self.pdf_paths.extend(new_files)
                # [V17.3.1.2] 異붽? 利됱떆 ?뺣젹 (?ㅼ＝諛뺤＝ 諛⑹?)
                self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
                self.update_file_count_display()
                self.log(f"[*] {len(new_files)}媛쒖쓽 PDF ?뚯씪??異붽??섏뿀?듬땲??")

    def load_pdf_folder(self):
        """[NEW] ?대뜑 ?좏깮 諛??섏쐞 PDF ?쇨큵 異붽?"""
        folder = QFileDialog.getExistingDirectory(self, "遺꾩꽍??MSDS ?대뜑 ?좏깮")
        if folder:
            all_pdfs = []
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(".pdf"):
                        all_pdfs.append(os.path.normpath(os.path.join(root, f)).replace('\\', '/'))
            
            if not all_pdfs:
                self.log("[!] ?좏깮???대뜑??異붽???PDF ?뚯씪???놁뒿?덈떎.")
                return
                
            new_files = []
            for f in all_pdfs:
                if f in self.pdf_paths:
                    continue
                new_files.append(f)
            
            if new_files:
                self.pdf_paths.extend(new_files)
                # [V17.3.1.2] ?대뜑 濡쒕뱶 ?쒖뿉??利됱떆 ?뺣젹 媛뺤젣
                self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
                self.update_file_count_display()
                self.log(f"[*] ?대뜑?먯꽌 {len(new_files)}媛쒖쓽 PDF ?뚯씪???쇨큵 異붽??섏뿀?듬땲?? (以묐났 ?쒖쇅)")
            else:
                self.log("[寃쎄퀬] ?대떦 ?대뜑 ?댁쓽 紐⑤뱺 PDF媛 ?대? 紐⑸줉???ы븿?섏뼱 ?덉뒿?덈떎.")

    def on_files_dropped(self, paths):
        """[NEW] ?쒕옒洹????쒕∼???뚯씪/?대뜑 泥섎━"""
        all_pdfs = []
        for p in paths:
            if os.path.isfile(p):
                if p.lower().endswith(".pdf"):
                    all_pdfs.append(p)
            elif os.path.isdir(p):
                # ?대뜑 ??紐⑤뱺 PDF ?ш? 寃??                for root, _, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith(".pdf"):
                            all_pdfs.append(os.path.join(root, f))
        
        if all_pdfs:
            # 以묐났 ?쒓굅 諛??꾩쟻 異붽?
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
            self.log(f"[*] ?쒕옒洹????쒕∼?쇰줈 {new_count}媛쒖쓽 PDF ?뚯씪??異붽??섏뿀?듬땲?? (珥?{len(self.pdf_paths)}媛?")

    def update_file_count_display(self):
        """[NEW] 泥⑤????뚯씪 ?섎? UI???낅뜲?댄듃"""
        count = len(self.pdf_paths) if hasattr(self, 'pdf_paths') else 0
        self.lbl_file_count.setText(f"{count}媛?)
        # 0媛쒕㈃ ?뚯깋, 1媛??댁긽?대㈃ 鍮④컙??諛곗?
        if count > 0:
            self.lbl_file_count.setStyleSheet("background-color: #f56c6c; color: white; border-radius: 10px; padding: 2px 5px; font-weight: bold; font-size: 11px; margin-left: -15px;")
        else:
            self.lbl_file_count.setStyleSheet("background-color: #909399; color: white; border-radius: 10px; padding: 2px 5px; font-weight: bold; font-size: 11px; margin-left: -15px;")

        # [NEW] ?뚰꽣留덊겕 ?곹깭 ?곕룞
        if hasattr(self, 'lbl_watermark'):
            if count > 0 or (hasattr(self, 'table') and self.table.rowCount() > 0):
                self.lbl_watermark.hide()
            else:
                self.lbl_watermark.show()

    def batch_rename_files(self):
        """[NEW] PDF ?뚯씪紐??쇨큵 蹂寃?(湲곗〈 踰덊샇 ?쒓굅 ????踰덊샇 遺??"""
        if not hasattr(self, 'pdf_paths') or not self.pdf_paths:
            QMessageBox.warning(self, "寃쎄퀬", "癒쇱? PDF ?뚯씪??異붽???二쇱꽭??")
            return

        try:
            start_num = int(self.edit_start_num.text().strip())
        except ValueError:
            QMessageBox.warning(self, "寃쎄퀬", "?쒖옉 踰덊샇???レ옄留??낅젰 媛?ν빀?덈떎.")
            return

        reply = QMessageBox.question(self, "?뺤씤", 
                                     f"珥?{len(self.pdf_paths)}媛??뚯씪???대쫫??蹂寃쏀븷源뚯슂?\n"
                                     f"(湲곗〈 踰덊샇 ?묐몢?ш? ?덉쑝硫??쒓굅?섍퀬 {start_num:03d}_ ?뺤떇?쇰줈 ?덈줈 遺?ы빀?덈떎.)",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No: return

        new_paths = []
        errors = []
        # ?뚯씪紐?湲곗? ?뺣젹?섏뿬 ?쒖감 踰덊샇 遺??        self.pdf_paths.sort()
        
        for idx, old_path in enumerate(self.pdf_paths):
            dir_name = os.path.dirname(old_path)
            base_name = os.path.basename(old_path)
            
            # 湲곗〈 踰덊샇 ?묐몢???쒓굅 (?? 001_, 12-, 3. ??
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
            QMessageBox.critical(self, "蹂寃??ㅽ뙣 ?덈궡", 
                                 f"?쇰? ?뚯씪紐낆쓣 蹂寃쏀븯吏 紐삵뻽?듬땲?? ?대떦 ?뚯씪???ㅻⅨ ?꾨줈洹몃옩?먯꽌 ?ъ슜 以묒씤吏 ?뺤씤?섍퀬 ?レ? ???ㅼ떆 ?쒕룄??二쇱꽭??\n\n[?ㅽ뙣 ?댁뿭]\n{err_msg}")
        else:
            self.log(f"[*] {len(new_paths)}媛??뚯씪紐??쇨큵 蹂寃??꾨즺 (?쒖옉 踰덊샇: {start_num})")
            QMessageBox.information(self, "?깃났", "?뚯씪紐?蹂寃쎌씠 ?꾨즺?섏뿀?듬땲??")

    def is_file_locked(self, path):
        """[V6.994] ????뚯씪???대? ?ㅻⅨ ?꾨줈洹몃옩?먯꽌 ?대젮 ?덈뒗吏 ?뺤씤"""
        if not os.path.exists(path): return False
        try:
            # ?곌린 紐⑤뱶濡??댁뼱蹂닿퀬 ?ㅽ뙣?섎㈃ ?좉릿 寃껋쑝濡?媛꾩＜
            with open(path, 'a'):
                pass
            return False
        except IOError:
            return True

    def assign_excel_numbers(self):
        """[NEW] ?묒? A?댁뿉 001, 002... ?뺤떇?쇰줈 踰덊샇 ?먮룞 遺??""
        excel_path = self.edit_excel.text().strip()
        if not excel_path or not os.path.exists(excel_path):
            QMessageBox.warning(self, "寃쎄퀬", "癒쇱? ?좏슚???묒? ?뚯씪???좏깮??二쇱꽭??")
            return

        # [V6.994] ?뚯씪 ?좉툑 泥댄겕
        if self.is_file_locked(excel_path):
            QMessageBox.critical(self, "?뚯씪 ?대┝", f"????묒? ?뚯씪({os.path.basename(excel_path)})???대? ?대젮 ?덉뒿?덈떎.\n?뚯씪???レ? ???ㅼ떆 ?쒕룄??二쇱꽭??")
            return

        try:
            start_no = int(self.edit_start_num.text().strip())
            start_row = int(self.edit_start_row.text().strip())
        except ValueError:
            QMessageBox.warning(self, "寃쎄퀬", "?쒖옉 踰덊샇? ?쒖옉 ?됱? ?レ옄?ъ빞 ?⑸땲??")
            return

        count = len(getattr(self, 'pdf_paths', []))
        if count == 0:
            QMessageBox.warning(self, "寃쎄퀬", "遺꾩꽍??PDF ?뚯씪??濡쒕뱶?섏? ?딆븯?듬땲??")
            return

        import pythoncom
        try:
            import win32com.client
        except ImportError:
            QMessageBox.critical(self, "?ㅻ쪟", "win32com ?쇱씠釉뚮윭由ш? ?꾩슂?⑸땲?? (pip install pywin32)")
            return

        pythoncom.CoInitialize()
        excel = None
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
            try: excel.Visible = False
            except AttributeError: pass
            wb = excel.Workbooks.Open(os.path.abspath(excel_path))
            ws = wb.Sheets(self.combo_sheet.currentText())

            # 1. 湲곗〈 媛?泥댄겕 (以묐났 諛??곗씠??議댁옱 ?뺤씤)
            conflicts = []
            for i in range(count):
                cell_val = ws.Cells(start_row + i, 1).Value
                if cell_val is not None and str(cell_val).strip() != "":
                    conflicts.append(f"{start_row + i}?? '{cell_val}'")
            
            if conflicts:
                msg = f"?좏깮??踰붿쐞({start_row}?됰???{count}媛? 以??대? 媛믪씠 議댁옱?섎뒗 ????덉뒿?덈떎:\n\n"
                msg += "\n".join(conflicts[:10])
                if len(conflicts) > 10: msg += f"\n...??{len(conflicts)-10}嫄?
                msg += "\n\n湲곗〈 媛믪쓣 臾댁떆?섍퀬 踰덊샇瑜??덈줈 遺?ы븷源뚯슂?"
                reply = QMessageBox.question(self, "?곗씠??議댁옱 ?뚮┝", msg, QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    wb.Close(False)
                    return

            # 2. 踰덊샇 遺??(留ㅽ븨?????ъ슜)
            mapping = self.mapping_panel.get_mapping()
            col_letter = mapping.get("?쒕쾲/No", "A")
            col_idx = SMUGUI.c2i(col_letter)
            if col_idx < 1: col_idx = 1 # Fallback to A

            for i in range(count):
                val = start_no + i
                # 臾몄옄???щ㎎??('001 ?뺤떇?쇰줈 ?낅젰?섏뿬 ?묒????レ옄濡??먮룞 蹂?섑븯??寃?諛⑹?)
                ws.Cells(start_row + i, col_idx).Value = f"'{val:03d}" 
            
            wb.Save()
            self.log(f"[*] ?묒? A??{start_row}?됰???{count}媛쒖쓽 踰덊샇瑜?遺?ы뻽?듬땲?? (?쒖옉: {start_no:03d})")
            QMessageBox.information(self, "?깃났", "?묒? 踰덊샇 遺?ш? ?꾨즺?섏뿀?듬땲??")
            
        except Exception as e:
            self.log(f"???묒? ?묒뾽 ?ㅻ쪟: {e}")
            QMessageBox.critical(self, "?ㅻ쪟", f"?묒? ?묒뾽 以??ㅻ쪟 諛쒖깮:\n{e}")
        finally:
            if excel:
                try: excel.Visible = True
                except AttributeError: pass
                try: excel.UserControl = True
                except AttributeError: pass
            pythoncom.CoUninitialize()

    def select_excel(self):
        """[V6.994] ?묒? ?좏깮 ???쒗듃 紐⑸줉 ?먮룞 濡쒕뱶"""
        # [V7.1] ?꾩뿭 ?뺤옣???꾪꽣 ?듯빀 (*.xlsx, *.xls, *.xlsm, *.xlsb)
        path, _ = QFileDialog.getOpenFileName(self, "????묒? ?뚯씪 ?좏깮", "", "Excel Files (*.xlsx *.xls *.xlsm *.xlsb)")
        if path:
            self.edit_excel.setText(path)
            self.combo_sheet.clear()
            try:
                # [Part 3-A] openpyxl???ъ슜?섏뿬 ?ㅼ젣 ?쒗듃 紐⑸줉 異붿텧
                wb = openpyxl.load_workbook(path, read_only=True, keep_vba=True)
                sheets = wb.sheetnames
                if sheets:
                    self.combo_sheet.addItems(sheets)
                    self.log(f"[*] ?묒? ?쒗듃 {len(sheets)}媛쒕? ?깃났?곸쑝濡?濡쒕뱶?덉뒿?덈떎.")
                else:
                    self.combo_sheet.addItem("Sheet1")
                wb.close()
            except Exception as e:
                self.log(f"?좑툘 ?쒗듃 紐⑸줉 濡쒕뱶 ?ㅽ뙣: {e}")
                self.combo_sheet.addItem("Sheet1")


    def _update_combo_sheets(self, path, combo_widget):
        """[V7.7] 踰붿슜 ?쒗듃 紐⑸줉 媛깆떊 諛??좏깮媛?吏?ν삎 ?좎?"""
        if not path or not os.path.exists(path):
            return
            
        try:
            # ?꾩옱 ?좏깮???쒗듃紐?湲곗뼲
            original_sheet = combo_widget.currentText()
            
            wb = openpyxl.load_workbook(path, read_only=True, keep_vba=True)
            sheets = wb.sheetnames
            wb.close()
            
            # 紐⑸줉 媛깆떊
            combo_widget.blockSignals(True)
            combo_widget.clear()
            if sheets:
                combo_widget.addItems(sheets)
                # ?댁쟾???좏깮?덈뜕 ?쒗듃媛 ??紐⑸줉?먮룄 ?덈떎硫??ㅼ떆 ?좏깮
                idx = combo_widget.findText(original_sheet)
                if idx >= 0: combo_widget.setCurrentIndex(idx)
            else:
                combo_widget.addItem("Sheet1")
            combo_widget.blockSignals(False)

                    
        except Exception:
            # ?ㅽ뙣 ??pandas fallback (?앸왂 媛?ν븯??臾닿껐???꾪빐 ?좎?)
            try:
                xl = pd.ExcelFile(path, engine='openpyxl')
                sheets = xl.sheet_names
                combo_widget.clear()
                combo_widget.addItems(sheets)
            except: pass

    def run_extraction(self):
        if not hasattr(self, 'pdf_paths') or not self.pdf_paths:
            QMessageBox.warning(self, "寃쎄퀬", "癒쇱? 遺꾩꽍??PDF ?뚯씪???좏깮?섏꽭??")
            return

        self.results = []
        # [Part 1] ?먯깋湲??ㅽ????먯뿰?ㅻ윭???뺣젹 (Natural Sort) ?곸슜
        if hasattr(self, 'pdf_paths') and self.pdf_paths:
            self.pdf_paths.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

        self.table.blockSignals(True) # [NEW] ????묒뾽 ???쒓렇??李⑤떒
        
        # ?슚 [V17.3.3.3] ?ㅻ쭏???좏깮 異붿텧 (Selective Extraction) 濡쒖쭅 ?꾩엯
        target_paths = []
        is_partial = False
        
        if self.table.rowCount() > 0:
            for r in range(self.table.rowCount()):
                prod_item = self.table.item(r, 2) # ?쒗뭹紐?                cas_item = self.table.item(r, 3)  # CAS ?먮낯
                fn_item = self.table.item(r, 7)   # ?뚯씪紐?                
                prod_text = prod_item.text().strip() if prod_item else ""
                cas_text = cas_item.text().strip() if cas_item else ""
                
                # ?쒗뭹紐낆씠??CAS ?먮낯??鍮꾩뼱?덇굅??'誘명솗??, '?ㅻ쪟' ?깆씠 ?ы븿??寃쎌슦 異붿텧 ??곸쑝濡??좎젙
                if not prod_text or not cas_text or "誘명솗?? in prod_text or "?ㅻ쪟" in cas_text or "誘몄텛異? in prod_text:
                    if fn_item:
                        fn = fn_item.text().strip()
                        full_path = next((p for p in self.pdf_paths if os.path.basename(p) == fn), None)
                        if full_path:
                            target_paths.append(full_path)
            
            if target_paths:
                is_partial = True
                self.log(f"[*] ?좏깮 異붿텧 紐⑤뱶 媛?? ?꾩껜 {len(target_paths)}嫄댁뿉 ????ъ텛異쒖쓣 ?섑뻾?⑸땲??")
        
        if not is_partial:
            # ?꾩껜 異붿텧 紐⑤뱶
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
        # [NEW] 吏꾪뻾 ?곹솴 ?띿뒪???낅뜲?댄듃 ?곌껐
        self.worker.progress_signal.connect(lambda v: self.lbl_extraction_progress.setText(f"吏꾪뻾 以? {int(v/100*len(self.pdf_paths))}/{len(self.pdf_paths)}嫄?({v}%)"))
        self.worker.result_signal.connect(self.add_result_to_table)
        self.worker.cache_update_signal.connect(self.update_cache) # [NEW] 罹먯떆 ?낅뜲?댄듃 ?곕룞
        self.worker.finished_signal.connect(self.on_extraction_finished)
        self.worker.start()

    def run_validation(self):
        rowCount = self.table.rowCount()
        if rowCount == 0:
            QMessageBox.warning(self, "寃쎄퀬", "寃利앺븷 ?곗씠?곌? ?놁뒿?덈떎. 癒쇱? 1?④퀎瑜?吏꾪뻾?섏꽭??")
            return

        self.table.blockSignals(True) # [NEW] ?쒓렇???쇱떆 李⑤떒

        # ?뚯씠釉붿뿉???꾩옱 CAS/?⑥쑀???곗씠???쎄린
        table_data = []
        for r in range(rowCount):
            # [V7.9] ?뚯씪 ?댁떆(8踰???瑜?怨좎쑀 ?ㅻ줈 異붿텧
            f_hash = self.table.item(r, 8).text() if self.table.item(r, 8) else ""
            fn = self.table.item(r, 7).text() if self.table.item(r, 7) else ""
            prod = self.table.item(r, 2).text()
            cas_content = self.table.item(r, 3).text()
            table_data.append({"row_idx": r, "f_hash": f_hash, "filename": fn, "prod": prod, "cas_content": cas_content})

        self.progress.setValue(0)
        self.btn_stop.setEnabled(True)
        self.btn_step1.setEnabled(False)
        self.btn_step2.setEnabled(False)
        self.worker = ValidationWorker(self, self.core, table_data) # [Task 2] self(GUI) ?꾨떖 異붽?
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress.setValue)
        # [NEW] 吏꾪뻾 ?곹솴 ?띿뒪???낅뜲?댄듃 ?곌껐
        self.worker.progress_signal.connect(lambda v: self.lbl_extraction_progress.setText(f"寃利?以? {int(v/100*len(table_data))}/{len(table_data)}嫄?({v}%)"))
        self.worker.result_signal.connect(self.on_validation_result) 
        self.worker.finished_signal.connect(self.on_validation_finished)
        self.worker.start()

    def on_extraction_finished(self, stats):
        """1?④퀎 PDF 異붿텧 ?꾨즺 ?붿빟 蹂닿퀬 (V12.8 ?듦퀎 ??쒕낫??"""
        self.table.blockSignals(False)
        self.btn_stop.setEnabled(False)
        self.btn_step1.setEnabled(True)
        self.btn_step2.setEnabled(True)
        self.lbl_extraction_progress.setText(f"異붿텧 ?꾨즺: {len(self.pdf_paths)}嫄?) # [NEW] ?꾨즺 ?쒖떆
        self.log("[*] 1?④퀎 PDF 異붿텧 ?묒뾽???꾨즺?섏뿀?듬땲??")
        
        summary = (
            "?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺\n"
            "   ?뱤 MSDS 異붿텧 媛???꾪솴 蹂닿퀬\n"
            "?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺\n"
            f"??珥?泥섎━ ?뚯씪: {sum(stats.values())}嫄?n\n"
            f"?뵻 REGEX (?뺢퇋??罹먯떆): {stats.get('regex', 0)}嫄?n"
            f"?뵺 FLASH (Gemini 2.5): {stats.get('flash', 0)}嫄?n"
            f"?? BULLDOZER (Fallback): {stats.get('bulldozer', 0)}嫄?n"
            "?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺?곣봺\n"
            "異붿텧???곗씠?곕? ?뺤씤/?섏젙????[2?④퀎 寃利???吏꾪뻾?섏꽭??"
        )
        QMessageBox.information(self, "異붿텧 ?꾨즺 由ы룷??, summary)
        
        # [V17.3.0.8] 留덉뒪??DB 濡쒕뱶 ?먮윭 ?ы썑 ?덈궡 (二쇰떂 吏移? 1?④퀎 醫낅즺 ???쇨큵 蹂닿퀬)
        if hasattr(engine, 'MES_MASTER_LOAD_ERROR') and engine.MES_MASTER_LOAD_ERROR:
             QMessageBox.critical(self, "留덉뒪??DB 濡쒕뱶 ?ㅽ뙣", 
                                f"[?쒖뒪??二쇱쓽] ?깅텇 紐낆묶 蹂댁젙??留덉뒪??DB瑜?遺덈윭?ㅼ? 紐삵뻽?듬땲??\n\n"
                                f"?ъ쑀: {engine.MES_MASTER_LOAD_ERROR}\n\n"
                                f"議곗튂: DB ?뚯씪???놁뼱??異붿텧? 怨꾩냽?섎굹, 紐낆묶??遺?뺥솗?????덉뒿?덈떎.")


    def on_validation_result(self, res_data):
        """[V10.2] ?섏씠釉뚮━??寃利?寃곌낵 泥섎━ (?좏샇???뵷 留덊궧 諛?寃???먯엵 ?ы븿)"""
        target_hash = res_data.get("f_hash")
        v = res_data.get("validation", {})
        fn = res_data.get("filename", "unknown")
        status = res_data.get("status", "High-Pass")
        
        # [DEBUG] ?곗씠???꾨떖 ?щ? ?뺤씤
        self.log(f"[*] API ?묐떟 ?섏쭛?? {fn} (?곹깭: {status})")
        
        # ?꾩옱 ?뚯씠釉붿뿉???댁떆媛 ?쇱튂?섎뒗 ??寃??(??ъ씤??諛붿씤??
        found_row = -1
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 8)
            if item and item.text().strip() == target_hash:
                found_row = r
                break
        
        # [V8.3] ?댁쨷 諛붿씤??(Fallback ?곕룞)
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
                status=status # [NEW] ?곹깭媛??꾨떖
            )

    def on_validation_finished(self):
        """2?④퀎 API 寃利??꾨즺 泥섎━"""
        self.table.blockSignals(False)
        self.btn_stop.setEnabled(False)
        self.btn_step1.setEnabled(True)
        self.btn_step2.setEnabled(True)
        self.lbl_extraction_progress.setText(f"寃利??꾨즺: {self.table.rowCount()}嫄?) # [NEW] ?꾨즺 ?쒖떆
        self.log("[*] 2?④퀎 API 寃利??묒뾽???꾨즺?섏뿀?듬땲??")
        QMessageBox.information(self, "?꾨즺", "2?④퀎 API 寃利앹씠 ?꾨즺?섏뿀?듬땲??")

    def stop_process(self):
        """[NEW] ?꾩옱 吏꾪뻾 以묒씤 ?묒뾽??以묒?"""
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log("?썞 ?ъ슜?먯뿉 ?섑빐 以묒? ?좏샇媛 ?꾨떖?섏뿀?듬땲?? ?좎떆留?湲곕떎??二쇱꽭??..")
            # 媛뺤젣 醫낅즺蹂대떎???덉쟾?섍쾶 猷⑦봽媛 ?앸궇 ?뚭퉴吏 ?湲고븯?꾨줉 ?좊룄
            self.btn_stop.setEnabled(False)

    def open_saved_excel(self):
        """[NEW] ??λ맂 ?묒? ?뚯씪??利됱떆 ?닿린"""
        path = self.edit_excel.text().strip()
        if path and os.path.exists(path):
            try:
                os.startfile(path)
                self.log(f"[*] ?묒? ?뚯씪 ?닿린: {os.path.basename(path)}")
            except Exception as e:
                self.log(f"[!] ?뚯씪 ?닿린 ?ㅽ뙣: {e}")
        else:
            QMessageBox.warning(self, "?뚯씪 ?놁쓬", "吏?뺣맂 ?묒? ?뚯씪??李얠쓣 ???녾굅??寃쎈줈媛 鍮꾩뼱 ?덉뒿?덈떎.")

    def closeEvent(self, event):
        """[V6.995 ?듯빀] ?꾨줈洹몃옩 醫낅즺 ???덉쟾 ?먭? 諛??ㅼ젙 ???""
        # 1. 諛깃렇?쇱슫???묒뾽 泥댄겕
        if hasattr(self, 'active_graph_threads') and self.active_graph_threads:
            active_count = len(self.active_graph_threads)
            reply = QMessageBox.warning(self, '醫낅즺 寃쎄퀬', 
                f"?꾩옱 {active_count}媛쒖쓽 吏??洹몃옒???낅뜲?댄듃媛 諛깃렇?쇱슫?쒖뿉??吏꾪뻾 以묒엯?덈떎.\n"
                "媛뺤젣 醫낅즺 ???곕뇤 DB(吏?앸쭩)媛 ?먯긽?????덉뒿?덈떎. ?뺣쭚 醫낅즺?섏떆寃좎뒿?덇퉴?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            
            if reply == QMessageBox.No:
                event.ignore()
                return

        # 2. ?묒뾽 以?泥댄겕
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, "醫낅즺 ?뺤씤", "?꾩옱 遺꾩꽍 ?묒뾽??吏꾪뻾 以묒엯?덈떎. 以묐떒?섍퀬 醫낅즺?좉퉴??",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
            self.worker.terminate()
            self.worker.wait()

        # 3. ?ㅼ젙 諛?罹먯떆 ???        try:
            self.save_config()
            self.save_cache()
            self.log("[*] 紐⑤뱺 ?ㅼ젙怨?罹먯떆媛 ?덉쟾?섍쾶 ??λ릺?덉뒿?덈떎.")
        except: pass
        
        event.accept()

    def show_help_dialog(self):
        """[Page UX] ?듭떖 ?ъ슜踰?1遺?媛?대뱶 ?앹뾽"""
        help_text = (
            "<h2>?뮕 AI ?뷀븰臾쇱쭏 釉뚮젅???ъ슜 媛?대뱶</h2>"
            "<ol>"
            "<li><b>?뚯씪 ?ｊ린:</b> 諛뷀깢?붾㈃??MSDS PDF瑜????덉쑝濡??쒕옒洹????쒕∼?섏꽭??</li>"
            "<li><b>異붿텧 ?섍린:</b> [異붿텧 ?쒖옉]???꾨Ⅴ硫?AI媛 ?깅텇??遺꾩꽍?⑸땲??</li>"
            "<li><b>援먯감 寃利?</b> ?뚮???CAS 踰덊샇瑜??대┃?섎㈃ <b>?덉쟾蹂닿굔怨듬떒(KOSHA)</b> 李쎌씠 ?대젮 利됱떆 ?뺤씤 媛?ν빀?덈떎.</li>"
            "<li><b>留덉뒪??DB ?곕룞:</b> 留덉뒪?곗뿉 ?녿뒗 臾쇱쭏? [誘몃벑濡??쇰줈 ?쒖떆?⑸땲??</li>"
            "</ol>"
        )
        QMessageBox.information(self, "?ъ슜 ?ㅻ챸??, help_text)


    def _safe_resize_rows(self):
        """[Part 18] ?ш? ?몄텧 諛⑹?瑜??ы븿???덉쟾?????믪씠 議곗젅"""
        try:
            if not hasattr(self, "_resizing_rows") or not self._resizing_rows:
                self._resizing_rows = True
                self.table.resizeRowsToContents()
                self._resizing_rows = False
        except:
            self._resizing_rows = False

    def _clean_comp_name(self, name):
        """[V15.8.18 ?섏젙] ?깅텇紐?蹂댁닔???뺤젣: ?쒓?紐??곷Ц紐? 瑗щ━留??먮Ⅴ怨??대? 怨듬갚? 蹂댁〈"""
        if not name: return ""
        name = str(name).strip()
        
        # 臾몄옣 ?앹뿉 遺숈? ?곷Ц 愿꾪샇留??쒓굅?섍퀬 ?대? ?꾩뼱?곌린??泥좎????대┝
        match = re.match(r'^([媛-??s\d\w\-\,\.\/]+)\s*\([A-Za-z\s\d,]+\)$', name)
        if match:
            korean_part = match.group(1).strip()
            return korean_part # replace(" ", "") ??젰??怨듬갚 ?쒓굅 ?먭린
        
        return name.strip()

    # [V15.5.4] GUI-side character substitution logic (assassin) removed to preserve data integrity.
    # Raw data from the engine is now displayed As-is.

    def add_result_to_table(self, data):
        """1?④퀎 寃곌낵瑜??뚯씠釉붿뿉 異붽? (V7.3 罹먯떆 ?대뱶 ?곸슜)"""
        # [NEW] ?뚰꽣留덊겕 利됱떆 ?④?
        if hasattr(self, 'lbl_watermark'):
            self.lbl_watermark.hide()
        try:
            f_hash = data.get("f_hash")
            # ?슚 [V17.3.3.3] 湲곗〈 ???낅뜲?댄듃 濡쒖쭅 (Selective Extraction ???
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
                # 湲곗〈 寃곌낵 媛앹껜 ?낅뜲?댄듃 (硫붾え由??숆린??
                for i, res in enumerate(self.results):
                    if res.get("f_hash") == f_hash:
                        self.results[i] = data
                        break
            else:
                self.results.append(data)
                row = self.table.rowCount()
                self.table.insertRow(row)
            
            # 1. ?쒕쾲 (?좏샇???대え吏 + ?レ옄 ?듯빀)
            traffic_val = data.get("?좏샇??, "?뵶")
            if not traffic_val or traffic_val == "N/A":
                raw_rel = data.get("reliability", "")
                if "[AUTO-PASS]" in raw_rel: traffic_val = "?윟"
                elif "[AI-FIXED]" in raw_rel: traffic_val = "?윞"
                else: traffic_val = "?뵶"
            
            # [V17.3.3.2] ?띿뒪?????좏샇??green/yellow) ?섏떊 ???대え吏濡?蹂??            if str(traffic_val).lower() == "green": traffic_val = "?윟"
            elif str(traffic_val).lower() == "yellow": traffic_val = "?윞"
            elif str(traffic_val).lower() == "red": traffic_val = "?뵶"
            
            traffic_emoji = traffic_val[0] if traffic_val else "?뵶"
            
            # [V6.96] ?쒓컖??媛뺤“ 濡쒖쭅: ?뱀깋(?윟)? ?앸왂, ?⑹깋(?윞)/?곸깋(?뵶)留?媛뺤“
            bg_color = None
            if traffic_emoji == "?뵶":
                bg_color = QColor("#ffebeb") # ?고븳 鍮④컯
            elif traffic_emoji == "?윞":
                bg_color = QColor("#fff9db") # ?고븳 ?몃옉
            
            # [?섏젙] ??踰덊샇蹂대떎???곗씠?곗쓽 ?쒖닔 ?쒕쾲???꾪빐 row+1 ?ъ슜 (?뺣젹 ?꾩뿉??怨좎쑀?섎룄濡?
            combined_idx = f"{traffic_emoji} {row + 1}"
            
            item_seq = QTableWidgetItem(combined_idx)
            item_seq.setTextAlignment(Qt.AlignCenter)
            if bg_color: item_seq.setBackground(bg_color)
            self.table.setItem(row, 0, item_seq)

            # 2. No (?뚯씪紐????レ옄 異붿텧 諛?3?먮━ ?쒕줈 ?⑤뵫 媛뺤젣 - ?뺣젹 臾닿껐??
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

            # [諛⑺깂] ?쒗뭹紐?NoneType 諛??먮윭 諛⑹뼱 濡쒖쭅
            raw_prod = data.get("product_name")
            if not raw_prod or str(raw_prod).lower() == "none":
                raw_prod = f"誘몄텛異?{data.get('filename')})"
                
            item_prod = QTableWidgetItem(str(raw_prod))
            if bg_color: item_prod.setBackground(bg_color)
            self.table.setItem(row, 2, item_prod)

            # [理쒖쥌 ?뺤젙] CAS ?먮낯 ?댁? PDF 異붿텧 ?먮Ц怨??⑥쑀?됱쓣 100% ?쒖닔 ?좎? (?쒖?紐?蹂묎린 ?먭린)
            raw = str(data.get("raw_content", ""))
            clean_cas_parts = [p.strip() for p in str(raw).split(";") if p.strip()]
            
            item_cas = QTableWidgetItem(";\n".join(clean_cas_parts))
            if bg_color: item_cas.setBackground(bg_color)
            self.table.setItem(row, 3, item_cas)

            # 5. [?섏젙] 怨듬??댁뿀??痢≪젙???4踰??????붿쭊??媛뺤젣濡?蹂대궦 ?곗씠?곌? ?덈떎硫??쎌엯!
            measure_val = data.get("measure_target", "")
            item_measure = QTableWidgetItem(str(measure_val))
            if bg_color: item_measure.setBackground(bg_color)
            self.table.setItem(row, 4, item_measure)

            # 6-7. 2李?1李?寃곌낵 ??5, 6踰???留?2?④퀎瑜??꾪빐 怨듬??쇰줈 鍮꾩썙??            for c_idx in range(5, 7):
                item_blank = QTableWidgetItem("")
                if bg_color: item_blank.setBackground(bg_color)
                self.table.setItem(row, c_idx, item_blank)
            
            # 8. ?뚯씪紐?(?④?)
            item_fn = QTableWidgetItem(fn)
            if bg_color: item_fn.setBackground(bg_color)
            self.table.setItem(row, COL_IDX_FILENAME, item_fn)

            # 9. ?댁떆 (?④?) - [NEW] 罹먯떆 ?낅뜲?댄듃??            f_hash = data.get("f_hash", "")
            item_hash = QTableWidgetItem(f_hash)
            self.table.setItem(row, COL_IDX_HASH, item_hash)

            # 10. [V7.0] Full Path (?④? - 誘몃━蹂닿린 釉뚮┸吏??
            item_path = QTableWidgetItem(data.get("full_path", ""))
            self.table.setItem(row, COL_IDX_FILEPATH, item_path)

            # 11. [V7.0] Page (?④? - 誘몃━蹂닿린 釉뚮┸吏??
            item_page = QTableWidgetItem(str(data.get("page", 1)))
            self.table.setItem(row, COL_IDX_PAGE, item_page)

            # [?듭떖] No(1踰??? 湲곗??쇰줈 ?ㅻ쫫李⑥닚 ?뺣젹 ?쒖꽦
            self.table.setSortingEnabled(True)
            self.table.sortItems(1, Qt.AscendingOrder)
            
            # ???믪씠 ?ъ“??            self._safe_resize_rows()
            self.table.blockSignals(False) # [NEW] ?쒓렇???ш컻
        except Exception as e:
            self.table.blockSignals(False)
            self.log(f"[?먮윭] ?뚯씠釉?異붽? ?ㅽ뙣: {e}")

    def update_validation_row(self, row, cas_with_content, res_1st_list, res_2nd_list, work_subjects="", status="High-Pass"):
        """2?④퀎 寃利?寃곌낵瑜??뚯씠釉붿뿉 ?낅뜲?댄듃 (V10.2 ?뚮????좏샇???뵷 ?쒖뼱 異붽?)"""
        try:
            # Hash瑜?媛?몄? 罹먯떆 議고쉶
            f_hash = self.table.item(row, 8).text() if self.table.item(row, 8) else ""
            manual = self.cache.get(f_hash, {}).get("manual_data", {})
            
            self.table.blockSignals(True)
            
            # ?슚 [?섏젙: V15.8.16 ?명솚] ?좏샇???대え吏 諛?諛곌꼍???쒖뼱 (1?④퀎 寃쎄퀬 蹂댁〈)
            traffic_col = 0
            curr_traffic_text = self.table.item(row, traffic_col).text() if self.table.item(row, traffic_col) else ""
            
            # 1. 湲곗〈???대え吏(寃쎄퀬 ?곹깭)? ?쒕쾲??遺꾨━
            match = re.match(r'^([?뵶?윞?윟??)\s*(.*)$', curr_traffic_text)
            existing_emoji = match.group(1) if match else "??
            pure_idx = match.group(2) if match else curr_traffic_text

            # 2. 湲곕낯媛??명똿
            emoji = existing_emoji 
            bg_color = None

            # 3. 2?④퀎 寃利앹씠 ?앸궗???뚯쓽 ?됱긽 寃곗젙 濡쒖쭅 (??뼱?곌린 諛⑹뼱)
            if "寃利??꾨즺" in status:
                if existing_emoji in ["?뵶", "?윞"]:
                    # 1?④퀎?먯꽌 ?대? ?먮윭/寃쎄퀬媛 ?대떎硫? 洹??됱긽??100% ?좎?!
                    emoji = existing_emoji 
                    if existing_emoji == "?뵶": bg_color = QColor("#ffebeb")
                    elif existing_emoji == "?윞": bg_color = QColor("#fff9db")
                else:
                    # 1?④퀎媛 臾댁궗 ?듦낵(???먮뒗 ?윟)????뚮쭔 珥덈줉遺??⑷꺽) 留덊궧
                    emoji = "?윟"
                    bg_color = QColor("#e1f7d5")

            # ?좏샇???낅뜲?댄듃
            item_seq = QTableWidgetItem(f"{emoji} {pure_idx}")
            item_seq.setTextAlignment(Qt.AlignCenter)
            if bg_color: item_seq.setBackground(bg_color)
            self.table.setItem(row, traffic_col, item_seq)

            # [V12.6] 1% ?꾪꽣 諛곗젣 洹쒖튃 ?쒓굅 (?꾪꽣 ?놁씠 洹몃?濡??듦낵)
            final_res1 = res_1st_list
            final_res2 = res_2nd_list

            # 1. ?쒗뭹紐?            existing_prod = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
            item_prod = QTableWidgetItem(manual.get("product_name", existing_prod))
            if bg_color: item_prod.setBackground(bg_color)
            self.table.setItem(row, 2, item_prod)

            # 2. CAS (異붿텧??寃껋씠???섎룞 ?섏젙蹂?
            api_cas = ";\n".join(cas_with_content) if cas_with_content else "" # 怨듬갚 ?쒓굅
            old_cas = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
            item_cas = QTableWidgetItem(manual.get("raw_content", api_cas if api_cas else old_cas))
            if bg_color: item_cas.setBackground(bg_color)
            self.table.setItem(row, 3, item_cas)

            # 3. 痢≪젙???(1% ?꾪꽣留?諛섏쁺)
            final_measure = manual.get("measure", work_subjects)
            item_measure = QTableWidgetItem(final_measure)
            if bg_color: item_measure.setBackground(bg_color)
            self.table.setItem(row, 4, item_measure)

            # 4. 2李?寃곌낵 (1% ?꾪꽣留?諛섏쁺) - [V17.3.1.0] GUI 以꾨컮轅?媛뺤젣 (媛?낆꽦 理쒖쟻??
            raw_reg2 = manual.get("reg2", ";\n".join(final_res2))
            final_reg2_str = ";\n".join([p.strip() for p in raw_reg2.replace(';\n', ';').replace('\n', ';').split(';') if p.strip()])
            item_reg2 = QTableWidgetItem(final_reg2_str)
            if bg_color: item_reg2.setBackground(bg_color)
            self.table.setItem(row, 5, item_reg2)

            # 5. 1李?寃곌낵 (1% ?꾪꽣留?諛섏쁺) - [V17.3.1.0] GUI 以꾨컮轅?媛뺤젣
            raw_reg1 = manual.get("reg1", ";\n".join(final_res1))
            final_reg1_str = ";\n".join([p.strip() for p in raw_reg1.replace(';\n', ';').replace('\n', ';').split(';') if p.strip()])
            item_reg1 = QTableWidgetItem(final_reg1_str)
            if bg_color: item_reg1.setBackground(bg_color)
            self.table.setItem(row, 6, item_reg1)

            
            # 湲고? ??諛곌꼍??留욎땄
            for c_idx in [1, 7]:
                item = self.table.item(row, c_idx)
                if item and bg_color: item.setBackground(bg_color)

            self.table.blockSignals(False)
            self._safe_resize_rows()
        except Exception as e:
            self.table.blockSignals(False)
            self.log(f"[?먮윭] ?뚯씠釉??낅뜲?댄듃 ?ㅽ뙣: {row}?? {e}")
            self._safe_resize_rows()
        finally:
            # [V8.3] 臾댁“嫄?UI ?쒓렇?????댁젣
            self.table.blockSignals(False)


    def perform_standard_save(self):
        """[Standard] GUI ?뚯씠釉붿쓽 ?곗씠?곕? 吏곸젒 李몄“?섏뿬 ?묒??????(?⑥닚?붾맂 ?뚯씠?꾨씪??"""
        if not hasattr(self, 'results') or not self.results:
            QMessageBox.warning(self, "寃쎄퀬", "??ν븷 寃곌낵 ?곗씠?곌? ?놁뒿?덈떎.")
            return
            
        excel_path = self.edit_excel.text().strip()
        sheet_name = self.combo_sheet.currentText()
        if not excel_path or not os.path.exists(excel_path):
            QMessageBox.warning(self, "寃쎄퀬", "?щ컮瑜??묒? 寃쎈줈瑜?吏?뺥빐 二쇱꽭??")
            return

        if self.is_file_locked(excel_path):
            QMessageBox.critical(self, "?뚯씪 ?대┝", f"????묒? ?뚯씪({os.path.basename(excel_path)})???대? ?대젮 ?덉뒿?덈떎.\n?뚯씪???レ? ???ㅼ떆 ?쒕룄??二쇱꽭??")
            return

        self.log(f"[*] ?묒? ????쒖옉... (??? {os.path.basename(excel_path)})")
        
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
            
            # [V9.7] 以묒븰?붾맂 c2i ?뺤쟻 硫붿꽌???쒖슜 (???臾닿껐??
            raw_mapping = self.mapping_panel.get_mapping()
            mapping = {k: SMUGUI.c2i(v) for k, v in raw_mapping.items()}
            
            try:
                st_row = int(self.edit_start_row.text())
            except:
                st_row = 3

            # ?뚯씠釉??곗씠???ㅻ깄???앹꽦 (?뚯씪紐?湲곗?)
            table_dict = {}
            for r in range(self.table.rowCount()):
                fn_item = self.table.item(r, 7) # ?뚯씪紐?(7踰???
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

            # ?곗씠??湲곗엯 (?쒖감?????
            saved_count = 0
            for row_idx in range(self.table.rowCount()):
                fn_item = self.table.item(row_idx, 7) # ?뚯씪紐?(7踰???
                if not fn_item: continue
                fn = fn_item.text().strip()
                
                if fn not in table_dict:
                    continue
                
                td = table_dict[fn]
                curr_row = st_row + saved_count # ?쒓컖???쒖꽌?濡??곗냽???됱뿉 湲곕줉
                
                # [V12.7] 留ㅽ븨??紐⑤뱺 而щ읆???곗씠??湲곗엯 (?좎뿰???뺤옣)
                for key, c_idx in mapping.items():
                    if not c_idx or c_idx < 1: continue
                    
                    val = None
                    if key == "?쒗뭹紐?: val = td.get("product_name")
                    elif key == "?뚯씪紐?: val = fn
                    elif key == "CAS ?먮낯": val = td.get("cas_sum")
                    elif key == "痢≪젙???" or key == "痢≪젙???": val = td.get("measure")
                    elif key == "2李?寃곌낵(洹쒖젣)": val = td.get("reg2")
                    elif key == "1李?寃곌낵(?꾩껜)": val = td.get("reg1")
                    elif key == "?쒕쾲/No": val = td.get("no")
                    
                    if val is not None:
                        # [V17.3.0.9] 二쇰떂 吏移? GUI???몄쭛??以꾨컮轅?, ?묒?? 理쒖쥌????以??쇰줈 ???                        if key in ["CAS ?먮낯", "1李?寃곌낵(?꾩껜)", "2李?寃곌낵(洹쒖젣)"]:
                            val = str(val).replace('\n', ' ').replace('\r', '').strip()
                            # ?곗냽??怨듬갚 ?쒓굅 (源붾걫???몃?肄쒕줎 ?뺣젹??
                            val = re.sub(r'\s{2,}', ' ', val)
                        
                        ws.Cells(curr_row, c_idx).Value = val


                saved_count += 1

            wb.Save()
            wb.Close()
            excel.Quit()
            self.log(f"[*] ????꾨즺: 珥?{saved_count}嫄댁쓽 ?곗씠?곌? ?묒?({sheet_name})??諛섏쁺?섏뿀?듬땲??")
            QMessageBox.information(self, "????꾨즺", f"珥?{saved_count}嫄댁쓽 ?곗씠?곌? ?깃났?곸쑝濡???λ릺?덉뒿?덈떎.")
            
        except Exception as e:
            self.log(f"[!] ???以??ㅻ쪟 諛쒖깮: {e}")
            if excel:
                try: excel.Quit()
                except: pass
            QMessageBox.critical(self, "?ㅻ쪟", f"???以??ㅻ쪟媛 諛쒖깮?덉뒿?덈떎: {e}")
        finally:
            pythoncom.CoUninitialize()



def global_exception_handler(exctype, value, tb):
    """[Part 20] ?꾩뿭 ?덉쇅 泥섎━湲? 紐⑤뱺 ?ㅻ젅???щ’???щ옒?쒕? ?앹뾽?쇰줈 ?쒖떆"""
    import traceback
    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    print(f"CRITICAL SYSTEM ERROR:\n{err_msg}")
    # ?뚯씪濡쒕룄 湲곕줉
    with open("crash_log.txt", "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now()}]\n{err_msg}\n")
    
    # GUI ?곸뿉???먮윭 硫붿떆吏 ?쒖떆 ?쒕룄
    try:
        QMessageBox.critical(None, "?쒖뒪???ㅻ쪟 諛쒖깮", f"?꾨줈洹몃옩???덉긽移?紐삵븳 ?ㅻ쪟濡?醫낅즺?⑸땲??\n\n{value}")
    except:
        pass
    sys.exit(1)

if __name__ == "__main__":
    # ?쒖뒪???덉쇅 媛濡쒖콈湲??ㅼ젙
    sys.excepthook = global_exception_handler
    
    app = QApplication(sys.argv)
    window = SMUGUI()
    window.show()
    sys.exit(app.exec_())
