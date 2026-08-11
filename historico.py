"""
Transcrições — app do whisper-voice (QFluentWidgets, tema dark quase-preto,
sidebar de navegação estilo Fluent/WinUI), com três telas:

  • Histórico    — transcrições salvas (transcricoes/*.md) agrupadas por dia,
                   com busca e Copiar. Card de estatísticas ao lado.
  • Gravar       — gravação LIVRE: clica pra começar, fala e mexe na tela à
                   vontade (sem segurar tecla nenhuma), clica de novo pra parar.
                   Transcreve, mostra o texto, copia pro clipboard e salva.
  • Vocabulário  — termos que a transcrição costuma errar (CLAUDE.md, nomes,
                   siglas). Vira o prompt da API. Salvou, valeu na próxima
                   gravação — o dictate.py lê o arquivo a cada transcrição.

Abrir digitando "Transcricoes" no Menu Iniciar, ou pelo atalho no Desktop.
"""
import os
import re
import io
import sys
import json
import glob
import time
import socket
import threading
import datetime
from collections import deque

GUARD_PORT = 49734   # instancia unica (dictate usa 49732, supervisor 49733)

if __name__ == "__main__":
    # Se ja existe uma instancia residente, acorda a janela dela e sai AGORA —
    # antes de pagar os imports pesados (PyQt/qfluentwidgets). E o que faz o
    # "abrir de novo" ser instantaneo.
    try:
        socket.create_connection(("127.0.0.1", GUARD_PORT), timeout=1.0).close()
        sys.exit(0)
    except OSError:
        pass

# numpy/sounddevice/soundfile/openai sao pesados e so precisam quando grava ou
# transcreve — importados sob demanda pra janela abrir rapido (o gargalo do
# boot frio e disco/antivirus escaneando o venv; quanto menos import, melhor).
import pyperclip
from dotenv import load_dotenv
from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt5.QtGui import QIcon, QFont, QPainter, QColor, QPen
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame,
)
from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition, setTheme, Theme,
    setThemeColor, SearchLineEdit, PrimaryPushButton, TransparentPushButton,
    PushButton, PlainTextEdit, CardWidget, SmoothScrollArea, InfoBar,
    InfoBarPosition, SwitchButton,
)

BASE = os.path.dirname(os.path.abspath(__file__))
HIST_DIR = os.path.join(BASE, "transcricoes")
VOCAB_PATH = os.path.join(BASE, "vocabulario.txt")
VOCAB_EXAMPLE = os.path.join(BASE, "vocabulario.example.txt")
# Correcoes SOMAM (.example versionado + .txt local); vocabulario e preferencias
# SUBSTITUEM (local ganha do .example). A tela deixa isso explicito no texto.
CORRECOES_PATH = os.path.join(BASE, "correcoes.txt")
CORRECOES_EXAMPLE = os.path.join(BASE, "correcoes.example.txt")
PREFS_PATH = os.path.join(BASE, "preferencias.txt")
PREFS_EXAMPLE = os.path.join(BASE, "preferencias.example.txt")
SETTINGS_PATH = os.path.join(BASE, "settings.json")
ICON_PATH = os.path.join(BASE, "assets", "mic.ico")
LINE_RE = re.compile(r"^- \*\*(\d{2}:\d{2}:\d{2})\*\* — (.*)$")
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

load_dotenv(os.path.join(BASE, ".env"))
SR = 16000
LANGUAGE = "pt"
MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
HOTKEY_LABEL = (os.getenv("HOTKEY", "f9") or "f9").strip().upper()
API_RETRIES = 3
MIN_DURATION = 0.3

_client = None


def get_client():
    """Cliente OpenAI preguicoso (o import e caro; so paga quem transcreve)."""
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

DEFAULT_VOCAB = (
    "Contexto: ditado de trabalho em português (Brasil), com termos técnicos "
    "de tecnologia em inglês.\n"
    "Termos frequentes: Claude, Claude Code, CLAUDE.md, Anthropic, OpenAI, "
    "whisper, API, MCP, deploy, commit, push, pull request, branch, merge, "
    "frontend, backend, webhook, endpoint, dashboard, sprint, Monday."
)

# ---- paleta quase-preto ----
BG = "#070708"          # fundo da janela (quase 100% black)
HOVER = "#141416"       # hover das linhas
HAIR = "#1A1A1E"        # divisórias
INK = "#E8E8EC"         # texto principal
MUTE = "#8E8E96"        # texto secundário
FAINT = "#6E6E76"       # texto apagado (hora, cabeçalho de dia)
ORANGE = "#F2A33C"      # acento
# Tokens da tela Palavras/Formatacao (ver .specs/#02-.../_estetica-veredito.md).
# Hierarquia por LUMINANCIA, nao por sombra: o Qt nao tem box-shadow em QWidget.
CARD1 = "#0E0E10"       # bloco primario (7% mais claro que o fundo)
CARD2 = "#0A0A0B"       # bloco secundario (3%)
DISABLED = "#7E7E86"    # texto de bloco desligado — 4,79:1, legivel de proposito
DISABLED_HINT = "#5E5E66"

# QSS só pros pedaços custom (o resto é o tema dark do QFluentWidgets)
QSS = f"""
#dayHeader {{
    color: {FAINT}; font-size: 10.5px; font-weight: 700;
    letter-spacing: 1px; padding: 12px 8px 2px 8px;
}}
#row {{ background: transparent; border-radius: 10px; }}
#row:hover {{ background: {HOVER}; }}
#rowTime {{ color: {FAINT}; font-size: 11.5px; padding-top: 5px; }}
#body {{ color: {INK}; font-size: 13.5px; }}
#divider {{ background: {HAIR}; border: none; }}
#empty {{ color: {MUTE}; font-size: 13.5px; }}
#hint {{ color: {MUTE}; font-size: 12.5px; }}
#pageTitle {{ color: {INK}; font-size: 17px; font-weight: 600; }}
#statValue {{ color: #F2F2F5; font-size: 21px; font-family: Georgia, 'Times New Roman'; }}
#statLabel {{ color: {MUTE}; font-size: 11px; }}
#saveStatus {{ color: {MUTE}; font-size: 12.5px; }}
#recStatus {{ color: {MUTE}; font-size: 13px; }}
#recBtn {{
    background: {ORANGE}; border: none; border-radius: 12px;
    color: #2A2105; font-size: 15px; font-weight: 600; padding: 15px 24px;
}}
#recBtn:hover {{ background: #EE9728; }}
#recBtn:disabled {{ background: #4A3B1E; color: #8E7B4F; }}
#recBtn[recording="true"] {{ background: #D64545; color: #FFFFFF; }}
#recBtn[recording="true"]:hover {{ background: #C03B3B; }}

/* ---- blocos das telas Palavras e Formatacao ---- */
#cardPrimario {{
    background: {CARD1}; border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
}}
#cardSecundario {{
    background: {CARD2}; border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
}}
#blocoTitulo {{ color: {INK}; font-size: 14px; font-weight: 600; }}
#blocoTituloSec {{ color: #C9C9CE; font-size: 13.5px; font-weight: 500; }}

/* Chips: a diferenca e PESO (preenchido x contorno), nao matiz. Semaforo
   verde/vermelho grita em tema quase-preto e sugere "erro" onde o certo e
   "mais fraco" — a dica nao esta errada, ela so nao e garantida. */
#chipGarantia {{
    color: {ORANGE}; background: rgba(242,163,60,0.14);
    border: 1px solid rgba(242,163,60,0.38); border-radius: 9px;
    font-size: 10.5px; font-weight: 600; padding: 2px 8px;
}}
#chipDica {{
    color: {MUTE}; background: transparent;
    border: 1px solid rgba(255,255,255,0.14); border-radius: 9px;
    font-size: 10.5px; font-weight: 500; padding: 2px 8px;
}}

/* Desabilitado = MENOS CONTRASTE, nunca opacity: opacity apaga a borda junto e
   o bloco vira mancha. O usuario precisa LER as preferencias pra decidir ligar. */
QWidget:disabled #blocoTitulo,
QWidget:disabled #body {{ color: {DISABLED}; }}
QWidget:disabled #hint {{ color: {DISABLED_HINT}; }}
"""


# ---------------- dados ----------------

def load_entries(limit=300):
    """Histórico mais recente primeiro: [{day, ts, text}]."""
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
                entries.append({"day": day, "ts": m.group(1), "text": m.group(2)})
                if len(entries) >= limit:
                    return entries
    return entries


def day_label(day):
    try:
        d = datetime.date.fromisoformat(day)
    except ValueError:
        return day
    today = datetime.date.today()
    if d == today:
        return "HOJE"
    if d == today - datetime.timedelta(days=1):
        return "ONTEM"
    return f"{DIAS[d.weekday()].upper()}, {d:%d/%m}"


def compute_stats():
    """(palavras, transcrições, dias seguidos) varrendo todos os .md."""
    words = count = 0
    days = set()
    for fp in glob.glob(os.path.join(HIST_DIR, "*.md")):
        day = os.path.splitext(os.path.basename(fp))[0]
        try:
            lines = open(fp, encoding="utf-8").read().splitlines()
        except Exception:
            continue
        for ln in lines:
            m = LINE_RE.match(ln.strip())
            if m:
                count += 1
                words += len(m.group(2).split())
                days.add(day)
    streak = 0
    d = datetime.date.today()
    while f"{d:%Y-%m-%d}" in days:
        streak += 1
        d -= datetime.timedelta(days=1)
    return words, count, streak


def fmt_k(n):
    if n >= 1000:
        s = f"{n / 1000:.1f}".rstrip("0").rstrip(".")
        return f"{s}K"
    return str(n)


def save_history(text):
    """Salva no mesmo formato que o dictate.py usa, pra aparecer na lista."""
    os.makedirs(HIST_DIR, exist_ok=True)
    now = datetime.datetime.now()
    oneline = " ".join(text.split())
    with open(os.path.join(HIST_DIR, f"{now:%Y-%m-%d}.md"), "a", encoding="utf-8") as f:
        f.write(f"- **{now:%H:%M:%S}** — {oneline}\n")


def read_vocab():
    """Mesma regra do dictate.py: vocabulario.txt > exemplo versionado."""
    for path in (VOCAB_PATH, VOCAB_EXAMPLE):
        try:
            with open(path, encoding="utf-8") as f:
                vocab = " ".join(f.read().split())
            if vocab:
                return vocab[:4000]
        except OSError:
            continue
    return ""


def load_texto(path, exemplo, default=""):
    """Le o arquivo local; se nao existir/estiver vazio, cai no .example
    versionado. Mesma regra do dictate.py."""
    for p in (path, exemplo):
        try:
            with open(p, encoding="utf-8") as f:
                txt = f.read().strip()
            if txt:
                return txt
        except OSError:
            continue
    return default


def salvar_texto(path, texto):
    with open(path, "w", encoding="utf-8") as f:
        f.write(texto.strip() + "\n")


def contar_regras(texto):
    """(validas, ignoradas) — mesma leitura do _parse_correcoes do dictate.py.
    Linha sem '=>' e ignorada em SILENCIO la; aqui a gente conta e avisa, senao
    o usuario digita errado e acha que salvou."""
    validas = ignoradas = 0
    for linha in (texto or "").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if not linha:
            continue
        if "=>" in linha and linha.split("=>", 1)[0].strip():
            validas += 1
        else:
            ignoradas += 1
    return validas, ignoradas


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_setting(key, value):
    """Grava uma preferencia. O dictate.py le o settings.json a cada ditado —
    salvar aqui ja vale no proximo, sem reiniciar nada."""
    s = load_settings()
    s[key] = value
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def load_vocab_editor():
    """Texto pro editor (com quebras de linha preservadas)."""
    for path in (VOCAB_PATH, VOCAB_EXAMPLE):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return DEFAULT_VOCAB


def transcribe(audio, sr=SR):
    """audio: np.int16 mono. Retorna (texto, erro)."""
    import soundfile as sf
    bio = io.BytesIO()
    sf.write(bio, audio, sr, format="wav")
    kwargs = dict(model=MODEL, file=("audio.wav", bio, "audio/wav"), language=LANGUAGE)
    vocab = read_vocab()
    if vocab:
        kwargs["prompt"] = vocab
    err = None
    for attempt in range(API_RETRIES):
        try:
            bio.seek(0)
            r = get_client().audio.transcriptions.create(**kwargs)
            return (r.text or "").strip(), None
        except Exception as e:
            err = str(e)[:140]
            time.sleep(0.5)
    return "", err


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


# ---------------- widgets ----------------

class WaveWidget(QWidget):
    """Onda do áudio em tempo real (preto e cinza, igual o overlay)."""
    N = 64

    def __init__(self):
        super().__init__()
        self.setFixedHeight(72)
        self.level = 0.0                 # nível atual (setado pela callback de áudio)
        self.levels = deque([0.0] * self.N, maxlen=self.N)
        self.active = False
        self._timer = QTimer(self)
        self._timer.setInterval(33)      # ~30 fps, mas SO enquanto grava
        self._timer.timeout.connect(self._tick)

    def start(self):
        self.active = True
        self._timer.start()

    def stop(self):
        self.active = False
        self.level = 0.0
        self._timer.stop()
        self.levels = deque([0.0] * self.N, maxlen=self.N)
        self.update()

    def _tick(self):
        self.levels.append(self.level if self.active else 0.0)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#1F1F23"), 1))
        p.setBrush(QColor("#0D0D0F"))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)

        w, h = self.width(), self.height()
        cy = h / 2
        pad = 16
        area = w - pad * 2
        n = len(self.levels)
        spacing = area / (n - 1) if n > 1 else area
        color = QColor("#B9B9C0") if self.active else QColor("#2A2A2E")
        pen = QPen(color, 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        amp = h * 0.40
        for i, lvl in enumerate(self.levels):
            ext = max(1.0, lvl * amp)
            x = pad + i * spacing
            p.drawLine(int(x), int(cy - ext), int(x), int(cy + ext))


class RecordBridge(QObject):
    done = pyqtSignal(str, str)   # (texto, erro)


class RecordPanel(QWidget):
    """Tela Gravar — gravação livre (clica pra começar, clica pra parar)."""

    def __init__(self, on_saved=None):
        super().__init__()
        self.setObjectName("recordPage")
        self.setStyleSheet(QSS)
        self.on_saved = on_saved          # callback pra atualizar a lista
        self._recording = False
        self._frames = []
        self._stream = None
        self._rec_start = 0.0
        self._last_text = ""

        self.bridge = RecordBridge()
        self.bridge.done.connect(self._on_done)

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(13)

        title = QLabel("Gravar")
        title.setObjectName("pageTitle")
        v.addWidget(title)

        hint = QLabel(
            "Clica em Gravar e fala à vontade — pode clicar, rolar a tela e "
            "trocar de janela enquanto grava. Clica de novo pra parar e transcrever."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.btn = QPushButton("●  Gravar")
        self.btn.setObjectName("recBtn")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self.toggle)
        v.addWidget(self.btn)

        self.wave = WaveWidget()
        v.addWidget(self.wave)

        self.status = QLabel("Pronto pra gravar.")
        self.status.setObjectName("recStatus")
        v.addWidget(self.status)

        self.result = PlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setPlaceholderText("A transcrição aparece aqui.")
        v.addWidget(self.result, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.copy_btn = TransparentPushButton(FluentIcon.COPY, "Copiar")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self.copy_result)
        row.addWidget(self.copy_btn)
        v.addLayout(row)

        # timer do "Gravando… Ns"
        self._tick = QTimer(self)
        self._tick.setInterval(250)
        self._tick.timeout.connect(self._update_elapsed)

    # ---- gravação ----
    def toggle(self):
        if self._recording:
            self.stop()
        else:
            self.start()

    def start(self):
        self._frames = []
        try:
            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=SR, channels=1, dtype="int16", callback=self._callback
            )
            self._stream.start()
        except Exception as e:
            self.status.setText(f"Erro ao abrir o microfone: {e}")
            return
        self._recording = True
        self._rec_start = time.time()
        self.btn.setText("■  Parar")
        self._set_recording_style(True)
        self.status.setText("Gravando…  0.0s")
        self.wave.start()
        self._tick.start()

    def _callback(self, indata, frames, time_info, status):
        import numpy as np   # cacheado pelo sys.modules; custo ~zero por chamada
        self._frames.append(indata.copy())
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
        self.wave.level = min(1.0, rms * 70.0)   # ganho p/ a onda encher

    def stop(self):
        self._recording = False
        self._tick.stop()
        self.wave.stop()
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._stream = None
        self.btn.setText("●  Gravar")
        self._set_recording_style(False)

        if not self._frames:
            self.status.setText("Nada gravado.")
            return
        import numpy as np
        audio = np.concatenate(self._frames, axis=0)
        duration = len(audio) / SR
        if duration < MIN_DURATION:
            self.status.setText("Gravação muito curta, ignorada.")
            return

        self.status.setText(f"Transcrevendo {duration:.1f}s…")
        self.btn.setEnabled(False)
        threading.Thread(target=self._worker, args=(audio,), daemon=True).start()

    def _worker(self, audio):
        text, err = transcribe(audio)
        self.bridge.done.emit(text, err or "")

    def _on_done(self, text, err):
        self.btn.setEnabled(True)
        if err or not text:
            self.status.setText("Falhou: " + (err or "transcrição vazia."))
            return
        self._last_text = text
        self.result.setPlainText(text)
        self.copy_btn.setEnabled(True)
        try:
            pyperclip.copy(text)
            self.status.setText("Pronto — transcrito, copiado e salvo no histórico.")
        except Exception:
            self.status.setText("Pronto — transcrito e salvo (falha ao copiar).")
        try:
            save_history(text)
            if self.on_saved:
                self.on_saved()
        except Exception as e:
            self.status.setText(f"Transcrito, mas falhou ao salvar: {e}")

    def copy_result(self):
        if not self._last_text:
            return
        pyperclip.copy(self._last_text)
        self.copy_btn.setText("Copiado ✓")

        def reset():
            try:
                self.copy_btn.setText("Copiar")
            except RuntimeError:
                pass
        QTimer.singleShot(1300, reset)

    def _set_recording_style(self, on):
        self.btn.setProperty("recording", bool(on))
        repolish(self.btn)

    def _update_elapsed(self):
        self.status.setText(f"Gravando…  {time.time() - self._rec_start:0.1f}s")


class HistPanel(QWidget):
    """Tela Histórico — lista por dia (hora à esquerda, divisórias finas),
    busca, Copiar, e card de estatísticas ao lado."""

    def __init__(self):
        super().__init__()
        self.setObjectName("histPage")
        self.setStyleSheet(QSS)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        # ---- coluna principal ----
        main = QVBoxLayout()
        main.setSpacing(12)
        outer.addLayout(main, 1)

        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("Histórico")
        title.setObjectName("pageTitle")
        refresh = TransparentPushButton(FluentIcon.SYNC, "Atualizar")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self.reload)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(refresh)
        main.addLayout(header)

        self.search = SearchLineEdit()
        self.search.setPlaceholderText("Buscar nas transcrições…")
        self.search.setClearButtonEnabled(True)
        # debounce: re-renderizar a lista a cada tecla travava a digitação
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._on_search)
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        main.addWidget(self.search)

        self.scroll = SmoothScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        main.addWidget(self.scroll, 1)

        # ---- coluna de estatísticas ----
        side = QVBoxLayout()
        side.setSpacing(12)
        card = CardWidget()
        cv = QVBoxLayout(card)
        cv.setContentsMargins(18, 16, 18, 16)
        cv.setSpacing(12)
        self._stat_labels = []
        for _ in range(3):
            val = QLabel("—")
            val.setObjectName("statValue")
            lab = QLabel("")
            lab.setObjectName("statLabel")
            blk = QVBoxLayout()
            blk.setSpacing(1)
            blk.addWidget(val)
            blk.addWidget(lab)
            cv.addLayout(blk)
            self._stat_labels.append((val, lab))
        side.addWidget(card)
        hot = QLabel(f"Atalho global:\nsegura {HOTKEY_LABEL}, fala e solta.")
        hot.setObjectName("hint")
        hot.setWordWrap(True)
        side.addWidget(hot)
        side.addStretch(1)
        wrap = QWidget()
        wrap.setStyleSheet(QSS)
        wrap.setLayout(side)
        wrap.setFixedWidth(180)
        outer.addWidget(wrap)

        self.entries = []
        self._cap = 120         # linhas renderizadas (botão "Mostrar mais" estende)
        self._loading = True
        self.render()           # mostra "Carregando…" na hora
        QTimer.singleShot(50, self.reload)   # dados chegam com a janela já visível

    def _on_search(self):
        self._cap = 120
        self.render()

    def reload(self):
        self.entries = load_entries()
        self._loading = False
        self._cap = 120
        self.render()
        words, count, streak = compute_stats()
        data = [
            (fmt_k(words), "palavras ditadas"),
            (fmt_k(count), "transcrições"),
            (str(streak), "dias seguidos" if streak != 1 else "dia seguido"),
        ]
        for (val, lab), (v_, l_) in zip(self._stat_labels, data):
            val.setText(v_)
            lab.setText(l_)

    def render(self):
        q = self.search.text().lower().strip()
        container = QWidget()
        container.setObjectName("list")
        container.setStyleSheet(QSS)
        cv = QVBoxLayout(container)
        cv.setAlignment(Qt.AlignTop)
        cv.setContentsMargins(0, 0, 6, 0)
        cv.setSpacing(0)

        filtered = [e for e in self.entries if not q or q in e["text"].lower()]

        shown = 0
        current_day = None
        for e in filtered[:self._cap]:
            if e["day"] != current_day:
                current_day = e["day"]
                day = QLabel(day_label(current_day))
                day.setObjectName("dayHeader")
                cv.addWidget(day)
            cv.addWidget(self._row(e))
            div = QFrame()
            div.setObjectName("divider")
            div.setFixedHeight(1)
            cv.addWidget(div)
            shown += 1

        rest = len(filtered) - shown
        if rest > 0:
            more = PushButton(f"Mostrar mais ({rest})")
            more.setCursor(Qt.PointingHandCursor)
            more.clicked.connect(self._show_more)
            wrap_more = QHBoxLayout()
            wrap_more.setContentsMargins(0, 12, 0, 8)
            wrap_more.addStretch(1)
            wrap_more.addWidget(more)
            wrap_more.addStretch(1)
            cv.addLayout(wrap_more)

        if shown == 0:
            if self._loading:
                msg = "Carregando histórico…"
            elif q:
                msg = "Nenhuma transcrição encontrada."
            else:
                msg = "Nada por aqui ainda — segura a tecla e fala."
            empty = QLabel(msg)
            empty.setObjectName("empty")
            empty.setAlignment(Qt.AlignCenter)
            cv.addStretch(1)
            cv.addWidget(empty)
            cv.addStretch(1)

        self.scroll.setWidget(container)

    def _show_more(self):
        self._cap += 200
        self.render()

    def _row(self, e):
        row = QFrame()
        row.setObjectName("row")
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 8, 8, 8)
        h.setSpacing(14)

        ts = QLabel(e["ts"][:5])
        ts.setObjectName("rowTime")
        ts.setFixedWidth(40)
        ts.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        h.addWidget(ts)

        body = QLabel(e["text"])
        body.setObjectName("body")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        h.addWidget(body, 1)

        copy = TransparentPushButton(FluentIcon.COPY, "Copiar")
        copy.setCursor(Qt.PointingHandCursor)
        copy.clicked.connect(lambda _, e=e, b=copy: self._copy(e, b))
        h.addWidget(copy, 0, Qt.AlignTop)
        return row

    # ---- copiar ----
    def _copy(self, e, button):
        pyperclip.copy(e["text"])
        self._flash(button, "Copiado ✓", "Copiar")

    def _flash(self, btn, label, back, ms=1300):
        try:
            btn.setText(label)
        except RuntimeError:
            return

        def reset():
            try:
                btn.setText(back)
                btn.setEnabled(True)
            except RuntimeError:
                pass
        QTimer.singleShot(ms, reset)

def _chip(texto, garantia):
    lab = QLabel(texto)
    lab.setObjectName("chipGarantia" if garantia else "chipDica")
    return lab


def _bloco(titulo, chip_txt, chip_garantia, descricao, primario):
    """Card com titulo + chip + descricao. Devolve (card, layout_do_conteudo)
    pra quem chama empilhar o editor e os botoes."""
    card = QFrame()
    card.setObjectName("cardPrimario" if primario else "cardSecundario")
    v = QVBoxLayout(card)
    v.setContentsMargins(18, 16, 18, 16)
    v.setSpacing(8)

    topo = QHBoxLayout()
    topo.setSpacing(8)
    t = QLabel(titulo)
    t.setObjectName("blocoTitulo" if primario else "blocoTituloSec")
    topo.addWidget(t)
    topo.addWidget(_chip(chip_txt, chip_garantia))
    topo.addStretch(1)
    v.addLayout(topo)

    d = QLabel(descricao)
    d.setObjectName("hint")
    d.setWordWrap(True)
    v.addWidget(d)
    return card, v


class PalavrasPanel(QWidget):
    """Tela Palavras — as duas alavancas de grafia, na ordem da EFICACIA real.

    Correcoes vem PRIMEIRO de proposito. Ate 10/08/2026 esta tela era so
    "Vocabulario", e o vocabulario e a alavanca FRACA: ele vira o `prompt` da
    API de transcricao, que o modelo ignora — medido em 23,5 min de fala real,
    "CLAUDE.md" saiu certo 0 vez em 8, "Isaque" 0 em 4. Quem funciona e o
    passe de regex (correcoes.txt), que acertou 14 de 14 e nao tinha tela
    nenhuma. Colocar a alavanca morta em destaque e prometer um resultado que
    o mecanismo nao entrega."""

    def __init__(self):
        super().__init__()
        self.setObjectName("palavrasPage")
        self.setStyleSheet(QSS)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(14)

        title = QLabel("Palavras")
        title.setObjectName("pageTitle")
        v.addWidget(title)

        sub = QLabel("Termos que a transcrição erra.")
        sub.setObjectName("hint")
        v.addWidget(sub)

        # ---- bloco 1 (PRIMARIO): correcoes — a que funciona ----
        card1, c1 = _bloco(
            "Correções automáticas", "garantia", True,
            "Uma por linha, no formato  errado => certo.  Troca literal, "
            "sempre — não depende do modelo acertar. A ordem importa: do mais "
            "específico pro mais genérico.", primario=True)
        self.ed_corr = PlainTextEdit()
        self.ed_corr.setPlainText(load_texto(CORRECOES_PATH, CORRECOES_EXAMPLE))
        self.ed_corr.setPlaceholderText(
            "cloud.md => CLAUDE.md\nisaac => Isaque")
        c1.addWidget(self.ed_corr, 1)
        r1 = QHBoxLayout()
        self.lbl_corr = QLabel("")
        self.lbl_corr.setObjectName("hint")
        r1.addWidget(self.lbl_corr)
        r1.addStretch(1)
        b1 = PrimaryPushButton(FluentIcon.SAVE, "Salvar correções")
        b1.setCursor(Qt.PointingHandCursor)
        b1.clicked.connect(self.salvar_correcoes)
        r1.addWidget(b1)
        c1.addLayout(r1)
        v.addWidget(card1, 3)

        # ---- bloco 2 (SECUNDARIO): vocabulario — a dica ----
        card2, c2 = _bloco(
            "Termos do meu vocabulário", "dica", False,
            "Nomes e jargões do seu dia a dia. Isto é uma dica pro modelo, "
            "não garantia — ele acerta às vezes. Se um termo sai errado toda "
            "vez, use o botão abaixo pra promovê-lo a correção.", primario=False)
        self.ed_vocab = PlainTextEdit()
        self.ed_vocab.setPlainText(load_vocab_editor())
        c2.addWidget(self.ed_vocab, 1)
        r2 = QHBoxLayout()
        prom = TransparentPushButton(FluentIcon.UP, "Promover termo a correção")
        prom.setCursor(Qt.PointingHandCursor)
        prom.clicked.connect(self.promover)
        r2.addWidget(prom)
        r2.addStretch(1)
        b2 = PushButton(FluentIcon.SAVE, "Salvar vocabulário")
        b2.setCursor(Qt.PointingHandCursor)
        b2.clicked.connect(self.salvar_vocab)
        r2.addWidget(b2)
        c2.addLayout(r2)
        v.addWidget(card2, 2)

        self._atualiza_contagem()
        self.ed_corr.textChanged.connect(self._atualiza_contagem)

    def _atualiza_contagem(self):
        ok, ign = contar_regras(self.ed_corr.toPlainText())
        txt = f"{ok} regra{'s' if ok != 1 else ''}"
        if ign:
            txt += f" · {ign} linha{'s' if ign != 1 else ''} sem \"=>\" (ignorada)"
        self.lbl_corr.setText(txt)

    def promover(self):
        """Leva o termo selecionado no vocabulario pro editor de correcoes, ja
        no formato. Fecha o ciclo 'vi errando -> viro garantia' sem redigitar —
        e o equivalente manual do auto-add do Wispr Flow (o app nao enxerga o
        campo onde colou, entao nao da pra detectar a correcao sozinho)."""
        termo = (self.ed_vocab.textCursor().selectedText() or "").strip()
        if not termo:
            InfoBar.warning("Selecione um termo",
                            "Marque a palavra no vocabulário e clique de novo.",
                            parent=self, position=InfoBarPosition.TOP_RIGHT,
                            duration=3000)
            return
        atual = self.ed_corr.toPlainText().rstrip()
        self.ed_corr.setPlainText(f"{atual}\ncomo sai errado => {termo}".strip())
        InfoBar.success("Termo copiado",
                        f"Escreva à esquerda como \"{termo}\" costuma sair errado.",
                        parent=self, position=InfoBarPosition.TOP_RIGHT,
                        duration=4000)

    def salvar_correcoes(self):
        ok, ign = contar_regras(self.ed_corr.toPlainText())
        try:
            salvar_texto(CORRECOES_PATH, self.ed_corr.toPlainText())
        except Exception as ex:
            InfoBar.error("Falhou ao salvar", str(ex)[:120], parent=self,
                          position=InfoBarPosition.TOP_RIGHT, duration=4000)
            return
        msg = f"{ok} regra{'s' if ok != 1 else ''} ativa{'s' if ok != 1 else ''}."
        if ign:
            msg += f" {ign} linha sem \"=>\" foi ignorada."
        msg += " Já vale no próximo ditado."
        (InfoBar.warning if ign else InfoBar.success)(
            "Correções salvas", msg, parent=self,
            position=InfoBarPosition.TOP_RIGHT, duration=4000 if ign else 3000)

    def salvar_vocab(self):
        try:
            salvar_texto(VOCAB_PATH, self.ed_vocab.toPlainText())
        except Exception as ex:
            InfoBar.error("Falhou ao salvar", str(ex)[:120], parent=self,
                          position=InfoBarPosition.TOP_RIGHT, duration=4000)
            return
        InfoBar.success("Vocabulário salvo",
                        "Já vale a partir da próxima gravação — sem reiniciar nada.",
                        parent=self, position=InfoBarPosition.TOP_RIGHT, duration=3000)


class FormatacaoPanel(QWidget):
    """Tela Formatação — o passe de LLM que limpa o texto depois de transcrever.

    O liga/desliga e o limiar moram AQUI, nao em Ajustes: separar o interruptor
    da coisa que ele liga obriga o usuario a percorrer duas telas pra uma
    decisao so. Ajustes fica com o que e transversal (clipboard, popup)."""

    def __init__(self):
        super().__init__()
        self.setObjectName("formatPage")
        self.setStyleSheet(QSS)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(14)

        title = QLabel("Formatação")
        title.setObjectName("pageTitle")
        v.addWidget(title)

        sub = QLabel("Depois de transcrever, limpar e organizar o texto.")
        sub.setObjectName("hint")
        v.addWidget(sub)

        # ---- interruptor (primario) ----
        card, c = _bloco(
            "Organizar o texto automaticamente", "usa IA", True,
            "Tira vícios de fala, pontua e quebra em parágrafos, seguindo as "
            "suas preferências abaixo. Custa ~3 a 6 segundos a mais por ditado. "
            "Se a API falhar, você recebe o texto sem tratamento — nunca perde "
            "o ditado.", primario=True)
        linha = QHBoxLayout()
        linha.addStretch(1)
        self.sw = SwitchButton()
        self.sw.setChecked(load_settings().get("normalizar_enabled", False))
        self.sw.checkedChanged.connect(self._toggle)
        linha.addWidget(self.sw)
        c.addLayout(linha)
        v.addWidget(card)

        # ---- daqui pra baixo: desabilita junto com o toggle ----
        self.dependentes = QWidget()
        dv = QVBoxLayout(self.dependentes)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(14)

        card_lim, cl = _bloco(
            "Só em ditados longos", "", False,
            "Ditado curto não compensa a espera. No seu histórico, 58% têm "
            "menos de 30 segundos — mas os longos concentram 81% de tudo que "
            "você fala.", primario=False)
        rl = QHBoxLayout()
        rl.setSpacing(8)
        lab = QLabel("Rodar só acima de")
        lab.setObjectName("body")
        rl.addWidget(lab)
        self.spin = SearchLineEdit()
        self.spin.setPlaceholderText("30")
        self.spin.setText(str(load_settings().get("normalizar_min_seg", 30)))
        self.spin.setFixedWidth(90)
        self.spin.setClearButtonEnabled(False)
        self.spin.searchSignal.connect(lambda _: self._salvar_limiar())
        self.spin.editingFinished.connect(self._salvar_limiar)
        rl.addWidget(self.spin)
        seg = QLabel("segundos de fala")
        seg.setObjectName("body")
        rl.addWidget(seg)
        rl.addStretch(1)
        cl.addLayout(rl)
        dv.addWidget(card_lim)

        card_pref, cp = _bloco(
            "Como eu quero o texto", "", False,
            "Escreva em português normal, como se pedisse pra uma pessoa. "
            "Salvou, já vale no próximo ditado.", primario=False)
        self.ed = PlainTextEdit()
        self.ed.setPlainText(load_texto(PREFS_PATH, PREFS_EXAMPLE))
        cp.addWidget(self.ed, 1)
        rp = QHBoxLayout()
        rp.addStretch(1)
        bp = PrimaryPushButton(FluentIcon.SAVE, "Salvar preferências")
        bp.setCursor(Qt.PointingHandCursor)
        bp.clicked.connect(self.salvar)
        rp.addWidget(bp)
        cp.addLayout(rp)
        dv.addWidget(card_pref, 1)

        v.addWidget(self.dependentes, 1)
        # desabilitado (nao escondido): o usuario precisa LER o que vai ganhar
        # antes de decidir ligar. Esconder faz a feature parecer inexistente.
        self.dependentes.setEnabled(self.sw.isChecked())

    def _toggle(self, checked):
        self.dependentes.setEnabled(bool(checked))
        try:
            save_setting("normalizar_enabled", bool(checked))
        except Exception as ex:
            self.sw.setChecked(not checked)   # reverte se nao gravou
            InfoBar.error("Falhou ao salvar", str(ex)[:120], parent=self,
                          position=InfoBarPosition.TOP_RIGHT, duration=4000)
            return
        InfoBar.success(
            "Formatação ligada" if checked else "Formatação desligada",
            "Já vale no próximo ditado." if checked
            else "Os ditados voltam a ser colados como saem da transcrição.",
            parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2500)

    def _salvar_limiar(self):
        txt = (self.spin.text() or "").strip()
        try:
            seg = int(float(txt))
            if seg < 0:
                raise ValueError
        except ValueError:
            self.spin.setText(str(load_settings().get("normalizar_min_seg", 30)))
            InfoBar.warning("Valor inválido", "Use um número de segundos (ex: 30).",
                            parent=self, position=InfoBarPosition.TOP_RIGHT,
                            duration=3000)
            return
        try:
            save_setting("normalizar_min_seg", seg)
        except Exception as ex:
            InfoBar.error("Falhou ao salvar", str(ex)[:120], parent=self,
                          position=InfoBarPosition.TOP_RIGHT, duration=4000)
            return
        InfoBar.success("Limiar salvo", f"Só ditados acima de {seg}s são organizados.",
                        parent=self, position=InfoBarPosition.TOP_RIGHT, duration=2500)

    def salvar(self):
        try:
            salvar_texto(PREFS_PATH, self.ed.toPlainText())
        except Exception as ex:
            InfoBar.error("Falhou ao salvar", str(ex)[:120], parent=self,
                          position=InfoBarPosition.TOP_RIGHT, duration=4000)
            return
        InfoBar.success("Preferências salvas", "Já valem no próximo ditado.",
                        parent=self, position=InfoBarPosition.TOP_RIGHT, duration=3000)


class SettingsPanel(QWidget):
    """Tela Ajustes — preferencias que o dictate.py le a cada ditado (salvou,
    ja vale no proximo — sem reiniciar nada)."""

    def __init__(self):
        super().__init__()
        self.setObjectName("settingsPage")
        self.setStyleSheet(QSS)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(12)

        title = QLabel("Ajustes")
        title.setObjectName("pageTitle")
        v.addWidget(title)

        v.addWidget(self._card(
            "Manter a transcrição no clipboard",
            "Ligado: depois de colar, o texto fica no Ctrl+V (útil se o foco "
            "estava no campo errado). Desligado: o que você tinha copiado antes "
            "de ditar volta pro clipboard após a colagem.",
            "keep_clipboard", True))
        v.addWidget(self._card(
            "Popup flutuante com a transcrição",
            "Depois de cada ditado, um popup mostra o começo do texto com um "
            "botão Copiar (substitui o \"colado ✓\" da pill). Arraste o popup "
            "uma vez pro canto/tela onde quer que ele sempre apareça — a "
            "posição fica salva.",
            "popup_enabled", True))
        v.addStretch(1)

    def _card(self, title, desc, key, default):
        card = CardWidget()
        cv = QHBoxLayout(card)
        cv.setContentsMargins(18, 14, 18, 14)
        cv.setSpacing(14)

        col = QVBoxLayout()
        col.setSpacing(3)
        lab = QLabel(title)
        lab.setObjectName("body")
        d = QLabel(desc)
        d.setObjectName("hint")
        d.setWordWrap(True)
        col.addWidget(lab)
        col.addWidget(d)
        cv.addLayout(col, 1)

        switch = SwitchButton()
        switch.setChecked(load_settings().get(key, default))
        switch.checkedChanged.connect(lambda c, k=key: self._save(k, c))
        cv.addWidget(switch, 0, Qt.AlignVCenter)
        return card

    def _save(self, key, checked):
        try:
            save_setting(key, bool(checked))
        except Exception as ex:
            InfoBar.error("Falhou ao salvar", str(ex)[:120], parent=self,
                          position=InfoBarPosition.TOP_RIGHT, duration=4000)
            return
        InfoBar.success("Ajuste salvo", "Já vale no próximo ditado.",
                        parent=self, position=InfoBarPosition.TOP_RIGHT,
                        duration=2500)


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Transcrições")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(1000, 680)
        self.setMinimumSize(780, 520)

        # fundo quase 100% preto (sem mica/acrílico)
        try:
            self.setMicaEffectEnabled(False)
        except Exception:
            pass
        self.setCustomBackgroundColor(QColor(BG), QColor(BG))

        self.hist = HistPanel()
        self.record = RecordPanel(on_saved=self.hist.reload)
        self.vocab = PalavrasPanel()
        self.formatacao = FormatacaoPanel()
        # isTransparent: sem o painel cinza da lib — o conteudo mostra o fundo
        # quase-preto da janela
        self.addSubInterface(self.hist, FluentIcon.HISTORY, "Histórico",
                             isTransparent=True)
        self.addSubInterface(self.record, FluentIcon.MICROPHONE, "Gravar",
                             isTransparent=True)
        self.addSubInterface(self.vocab, FluentIcon.DICTIONARY, "Palavras",
                             isTransparent=True)
        self.addSubInterface(self.formatacao, FluentIcon.FONT, "Formatação",
                             isTransparent=True)
        self.settings = SettingsPanel()
        self.addSubInterface(self.settings, FluentIcon.SETTING, "Ajustes",
                             position=NavigationItemPosition.BOTTOM,
                             isTransparent=True)

        # sidebar com rótulos visíveis (estilo Wispr), sem colapsar
        try:
            self.navigationInterface.setExpandWidth(168)
            self.navigationInterface.setMinimumExpandWidth(780)
            self.navigationInterface.expand(useAni=False)
        except Exception:
            pass

        # entrou no Histórico: recarrega (pega o que foi ditado pelo atalho
        # enquanto o app estava aberto em outra tela)
        self.stackedWidget.currentChanged.connect(self._on_page)

    def _on_page(self, i):
        if self.stackedWidget.widget(i) is self.hist:
            self.hist.reload()

    def bring_to_front(self):
        """Chamado quando o usuário 'abre' o app e já existe instância viva."""
        self.hist.reload()
        self.show()
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized)
                            | Qt.WindowActive)
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        # fechar = esconder. O processo fica residente (com os imports e o
        # cache de disco quentes) e a proxima abertura e instantanea — abrir
        # frio levava ~25-30s entre antivirus e disco. Pra encerrar de
        # verdade: parar.bat.
        e.ignore()
        self.hide()


class WakeListener(QObject):
    """Escuta o guard port: outra instância tentou abrir -> mostra a janela."""
    wake = pyqtSignal()

    def __init__(self, sock):
        super().__init__()
        self._sock = sock
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        self._sock.listen(4)
        while True:
            try:
                conn, _ = self._sock.accept()
                conn.close()
                self.wake.emit()
            except OSError:
                return


def notify_existing():
    """Pede pra instância viva mostrar a janela. True se ela existe."""
    try:
        socket.create_connection(("127.0.0.1", GUARD_PORT), timeout=1.5).close()
        return True
    except OSError:
        return False


if __name__ == "__main__":
    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        guard.bind(("127.0.0.1", GUARD_PORT))
    except OSError:
        # ja tem uma instancia rodando: acorda a janela dela e sai
        notify_existing()
        sys.exit(0)

    setTheme(Theme.DARK)
    setThemeColor(ORANGE)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # fechar a janela nao mata o processo
    app.setFont(QFont("Segoe UI", 10))
    w = MainWindow()
    listener = WakeListener(guard)
    listener.wake.connect(w.bring_to_front)
    if "--hidden" not in sys.argv:   # --hidden: sobe residente no login, sem janela
        w.show()
    sys.exit(app.exec_())
