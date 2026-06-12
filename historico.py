"""
Transcrições — app do whisper-voice (QFluentWidgets, tema dark quase-preto,
sidebar de navegação estilo Fluent/WinUI), com três telas:

  • Histórico    — transcrições salvas (transcricoes/*.md) agrupadas por dia,
                   com busca, Copiar, Ouvir (áudio dos últimos dias fica em
                   audios/) e Refazer (re-transcreve o áudio com o vocabulário
                   atual e atualiza o texto salvo). Card de estatísticas ao lado.
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
import glob
import time
import socket
import threading
import datetime
import winsound
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
    InfoBarPosition,
)

BASE = os.path.dirname(os.path.abspath(__file__))
HIST_DIR = os.path.join(BASE, "transcricoes")
AUDIO_DIR = os.path.join(BASE, "audios")
VOCAB_PATH = os.path.join(BASE, "vocabulario.txt")
VOCAB_EXAMPLE = os.path.join(BASE, "vocabulario.example.txt")
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
"""


# ---------------- dados ----------------

def load_entries(limit=300):
    """Histórico mais recente primeiro: [{day, ts, text, audio, dur}].
    O áudio é casado por um índice montado UMA vez (1 listdir por dia),
    em vez de um glob por entrada. Duração fica None (calculada ao Ouvir)."""
    audio_idx = {}
    for d in glob.glob(os.path.join(AUDIO_DIR, "*")):
        if os.path.isdir(d):
            try:
                audio_idx[os.path.basename(d)] = sorted(os.listdir(d))
            except OSError:
                pass

    def audio_of(day, ts):
        prefix = ts.replace(":", "")
        for f in audio_idx.get(day, ()):
            if f.startswith(prefix) and f.endswith(".wav"):
                return os.path.join(AUDIO_DIR, day, f)
        return None

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
                entries.append({"day": day, "ts": m.group(1), "text": m.group(2),
                                "audio": audio_of(day, m.group(1)), "dur": None})
                if len(entries) >= limit:
                    return entries
    return entries


def audio_duration(path):
    try:
        import soundfile as sf
        return sf.info(path).duration
    except Exception:
        return None


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


def update_history_line(day, ts, old_text, new_text):
    """Troca o texto de um item no md do dia (usado pelo Refazer)."""
    fp = os.path.join(HIST_DIR, f"{day}.md")
    try:
        lines = open(fp, encoding="utf-8").read().splitlines()
    except Exception:
        return False
    target = f"- **{ts}** — {old_text}"
    for i, ln in enumerate(lines):
        if ln.strip() == target:
            lines[i] = f"- **{ts}** — {' '.join(new_text.split())}"
            with open(fp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return True
    return False


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


class RedoBridge(QObject):
    done = pyqtSignal(object)   # {entry, body, btn, text, err}


class HistPanel(QWidget):
    """Tela Histórico — lista por dia (hora à esquerda, divisórias finas),
    busca, Copiar / Ouvir / Refazer, e card de estatísticas ao lado."""

    def __init__(self):
        super().__init__()
        self.setObjectName("histPage")
        self.setStyleSheet(QSS)
        self._play_btn = None
        self._play_token = 0
        self.redo_bridge = RedoBridge()
        self.redo_bridge.done.connect(self._on_redone)

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
        self._stop_playback()
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

        acts = QHBoxLayout()
        acts.setSpacing(2)
        if e["audio"]:
            play = TransparentPushButton(FluentIcon.PLAY, "Ouvir")
            play.setCursor(Qt.PointingHandCursor)
            play.clicked.connect(lambda _, e=e, b=play: self._toggle_play(e, b))
            acts.addWidget(play)

            redo = TransparentPushButton(FluentIcon.SYNC, "Refazer")
            redo.setCursor(Qt.PointingHandCursor)
            redo.setToolTip("Re-transcreve o áudio com o vocabulário atual e atualiza o texto salvo.")
            redo.clicked.connect(lambda _, e=e, b=body, btn=redo: self._retranscribe(e, b, btn))
            acts.addWidget(redo)

        copy = TransparentPushButton(FluentIcon.COPY, "Copiar")
        copy.setCursor(Qt.PointingHandCursor)
        copy.clicked.connect(lambda _, e=e, b=copy: self._copy(e, b))
        acts.addWidget(copy)

        actw = QWidget()
        actw.setLayout(acts)
        h.addWidget(actw, 0, Qt.AlignTop)
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

    # ---- ouvir ----
    def _toggle_play(self, e, btn):
        if self._play_btn is btn:
            self._stop_playback()
            return
        self._stop_playback()
        try:
            winsound.PlaySound(e["audio"], winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            self._flash(btn, "Erro no áudio", "Ouvir", ms=1600)
            return
        self._play_btn = btn
        self._play_token += 1
        tok = self._play_token
        btn.setText("Parar")
        if e["dur"] is None:
            e["dur"] = audio_duration(e["audio"])   # preguicoso: so de quem toca
        if e["dur"]:
            QTimer.singleShot(int(e["dur"] * 1000) + 300, lambda: self._auto_stop(tok))

    def _auto_stop(self, tok):
        if tok == self._play_token and self._play_btn is not None:
            self._stop_playback()

    def _stop_playback(self):
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        btn, self._play_btn = self._play_btn, None
        self._play_token += 1
        if btn is not None:
            try:
                btn.setText("Ouvir")
            except RuntimeError:
                pass   # lista foi re-renderizada enquanto tocava

    # ---- refazer (re-transcrever com o vocabulário atual) ----
    def _retranscribe(self, e, body, btn):
        btn.setEnabled(False)
        btn.setText("Transcrevendo…")

        def run():
            try:
                import soundfile as sf
                data, sr = sf.read(e["audio"], dtype="int16")
                text, err = transcribe(data, sr)
            except Exception as ex:
                text, err = "", str(ex)[:140]
            self.redo_bridge.done.emit(
                {"entry": e, "body": body, "btn": btn, "text": text, "err": err})
        threading.Thread(target=run, daemon=True).start()

    def _on_redone(self, d):
        e, btn = d["entry"], d["btn"]
        if d["err"] or not d["text"]:
            self._flash(btn, "Falhou", "Refazer", ms=1800)
            return
        new = " ".join(d["text"].split())
        if new == e["text"]:
            self._flash(btn, "Saiu igual", "Refazer", ms=1600)
            return
        if not update_history_line(e["day"], e["ts"], e["text"], new):
            self._flash(btn, "Não achei no arquivo", "Refazer", ms=2000)
            return
        e["text"] = new
        try:
            d["body"].setText(new)
        except RuntimeError:
            pass
        self._flash(btn, "Atualizado ✓", "Refazer", ms=1600)


class VocabPanel(QWidget):
    """Tela Vocabulário — o prompt que a API recebe em toda transcrição."""

    def __init__(self):
        super().__init__()
        self.setObjectName("vocabPage")
        self.setStyleSheet(QSS)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(12)

        title = QLabel("Vocabulário")
        title.setObjectName("pageTitle")
        v.addWidget(title)

        hint = QLabel(
            "Nomes, siglas e jargões que a transcrição costuma errar (ex: CLAUDE.md "
            "virando \"cloud.md\"). Esse texto é enviado como contexto pra API em toda "
            "gravação — do atalho de teclado e da tela Gravar. Salvou, valeu: a próxima "
            "gravação já usa, sem reiniciar nada."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.editor = PlainTextEdit()
        self.editor.setPlainText(load_vocab_editor())
        v.addWidget(self.editor, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.save_btn = PrimaryPushButton(FluentIcon.SAVE, "Salvar")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.save)
        row.addWidget(self.save_btn)
        v.addLayout(row)

    def save(self):
        try:
            with open(VOCAB_PATH, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText().strip() + "\n")
        except Exception as ex:
            InfoBar.error("Falhou ao salvar", str(ex)[:120], parent=self,
                          position=InfoBarPosition.TOP_RIGHT, duration=4000)
            return
        InfoBar.success("Vocabulário salvo",
                        "Já vale a partir da próxima gravação — sem reiniciar nada.",
                        parent=self, position=InfoBarPosition.TOP_RIGHT, duration=3000)


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
        self.vocab = VocabPanel()
        # isTransparent: sem o painel cinza da lib — o conteudo mostra o fundo
        # quase-preto da janela
        self.addSubInterface(self.hist, FluentIcon.HISTORY, "Histórico",
                             isTransparent=True)
        self.addSubInterface(self.record, FluentIcon.MICROPHONE, "Gravar",
                             isTransparent=True)
        self.addSubInterface(self.vocab, FluentIcon.DICTIONARY, "Vocabulário",
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
