"""
Transcrições — visualizador do histórico do whisper-voice (tema dark).
Lista as transcrições salvas (transcricoes/*.md), com busca e botao Copiar por item.
Abrir digitando "Transcrições" no Menu Iniciar, ou pelo atalho no Desktop.
"""
import os
import re
import sys
import glob
import ctypes

import pyperclip
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QLineEdit, QFrame,
)

BASE = os.path.dirname(os.path.abspath(__file__))
HIST_DIR = os.path.join(BASE, "transcricoes")
ICON_PATH = os.path.join(BASE, "assets", "mic.ico")
LINE_RE = re.compile(r"^- \*\*(\d{2}:\d{2}:\d{2})\*\* — (.*)$")

QSS = """
#root { background: #0f1115; }

#title { color: #f2f4f8; font-size: 19px; font-weight: 600; }
#count { color: #6f7689; font-size: 12px; }

QLineEdit {
    background: #181b22; border: 1px solid #262b35; border-radius: 10px;
    padding: 9px 13px; color: #e6e8ec; font-size: 13px;
    selection-background-color: #2f6f54;
}
QLineEdit:focus { border: 1px solid #57d39a; }

#refresh {
    background: #181b22; border: 1px solid #262b35; border-radius: 10px;
    padding: 9px 16px; color: #cdd2dc; font-size: 13px;
}
#refresh:hover { border-color: #3a414e; color: #ffffff; }
#refresh:pressed { background: #14171d; }

#card { background: #161922; border: 1px solid #232833; border-radius: 13px; }
#card:hover { border-color: #39414f; background: #1a1e28; }

#meta { color: #6c7488; font-size: 11px; }
#body { color: #e4e7ee; font-size: 13.5px; line-height: 150%; }

#copy {
    background: transparent; border: 1px solid #2c313b; border-radius: 9px;
    color: #9aa2b1; padding: 6px 13px; font-size: 12px;
}
#copy:hover { border-color: #57d39a; color: #57d39a; }
#copy[copied="true"] { background: #1d3a2e; border-color: #57d39a; color: #86ecb4; }

#empty { color: #5a6175; font-size: 14px; }

QScrollArea { border: none; background: transparent; }
#qt_scrollarea_viewport { background: transparent; }
#list { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2b313c; border-radius: 5px; min-height: 34px; }
QScrollBar::handle:vertical:hover { background: #3b4350; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def load_entries(limit=400):
    entries = []
    for fp in sorted(glob.glob(os.path.join(HIST_DIR, "*.md")), reverse=True):
        day = os.path.splitext(os.path.basename(fp))[0]
        try:
            lines = open(fp, encoding="utf-8").read().splitlines()
        except Exception:
            continue
        for ln in reversed(lines):
            m = LINE_RE.match(ln.strip())
            if m:
                entries.append((day, m.group(1), m.group(2)))
                if len(entries) >= limit:
                    return entries
    return entries


def dark_titlebar(widget):
    try:
        hwnd = int(widget.winId())
        val = ctypes.c_int(1)
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


class Hist(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("Transcrições")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(600, 680)
        self.setMinimumSize(420, 400)
        self.setStyleSheet(QSS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(14)

        # cabecalho
        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("Transcrições")
        title.setObjectName("title")
        self.count = QLabel("")
        self.count.setObjectName("count")
        refresh = QPushButton("Atualizar")
        refresh.setObjectName("refresh")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self.reload)
        header.addWidget(title)
        header.addWidget(self.count)
        header.addStretch(1)
        header.addWidget(refresh)
        outer.addLayout(header)

        # busca
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar transcrições…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.render)
        outer.addWidget(self.search)

        # lista
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(self.scroll, 1)

        self.entries = []
        self.reload()

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)

    def reload(self):
        self.entries = load_entries()
        self.render()

    def render(self):
        q = self.search.text().lower().strip()
        container = QWidget()
        container.setObjectName("list")
        cv = QVBoxLayout(container)
        cv.setAlignment(Qt.AlignTop)
        cv.setContentsMargins(0, 0, 6, 0)
        cv.setSpacing(8)

        shown = 0
        for day, ts, text in self.entries:
            if q and q not in text.lower():
                continue
            cv.addWidget(self._card(day, ts, text))
            shown += 1

        if shown == 0:
            empty = QLabel("Nenhuma transcrição encontrada.")
            empty.setObjectName("empty")
            empty.setAlignment(Qt.AlignCenter)
            cv.addStretch(1)
            cv.addWidget(empty)
            cv.addStretch(1)

        self.scroll.setWidget(container)
        total = len(self.entries)
        self.count.setText(f"{shown} de {total}" if q else f"{total} no total")

    def _card(self, day, ts, text):
        card = QFrame()
        card.setObjectName("card")
        h = QHBoxLayout(card)
        h.setContentsMargins(14, 12, 12, 12)
        h.setSpacing(10)

        block = QVBoxLayout()
        block.setSpacing(4)
        meta = QLabel(f"{day}  ·  {ts}")
        meta.setObjectName("meta")
        body = QLabel(text)
        body.setObjectName("body")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        block.addWidget(meta)
        block.addWidget(body)

        copy = QPushButton("Copiar")
        copy.setObjectName("copy")
        copy.setCursor(Qt.PointingHandCursor)
        copy.clicked.connect(lambda _, t=text, b=copy: self.copy(t, b))

        h.addLayout(block, 1)
        h.addWidget(copy, 0, Qt.AlignTop)
        return card

    def copy(self, text, button):
        pyperclip.copy(text)
        button.setText("Copiado!")
        button.setProperty("copied", True)
        button.style().unpolish(button)
        button.style().polish(button)

        def reset():
            button.setText("Copiar")
            button.setProperty("copied", False)
            button.style().unpolish(button)
            button.style().polish(button)

        QTimer.singleShot(1300, reset)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    w = Hist()
    w.show()
    sys.exit(app.exec_())
