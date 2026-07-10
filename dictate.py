"""
whisper-voice — ditador de voz (Gordon/Amber)

Segura F9, fala, solta -> transcreve via OpenAI whisper-1 e cola no campo ativo.
Overlay discreto (onda em tempo real, fundo preto) embaixo no centro da tela.
Mostra o tempo da transcricao ao terminar. Icone na bandeja com "Sair".

- Instancia unica. Sobe sozinho no boot (atalho na pasta Startup).
- Overlay nao rouba foco. Cola via clipboard (preserva acentos) e restaura.
"""
import os
import io
import re
import sys
import glob
import math
import time
import shutil
import socket
import subprocess
import threading
import ctypes
import datetime
import traceback
from collections import deque

import numpy as np
import sounddevice as sd
import soundfile as sf
import pyperclip
import winsound
from dotenv import load_dotenv
from pynput import keyboard
from openai import OpenAI

from PyQt5.QtCore import Qt, QObject, pyqtSignal, QRect, QTimer
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QIcon, QCursor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QMenu, QAction, QPushButton,
)

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))

SR = 16000


# Aliases -> variantes do pynput. Cada token vira um CONJUNTO de teclas aceitas
# (esq/dir/generico) porque o pynput entrega ctrl_l/ctrl_r/cmd_l... distintos,
# nunca o generico Key.ctrl. Combo = "tecla1+tecla2" (ex: ctrl_l+win).
_KEY_ALIASES = {
    "win": ("cmd", "cmd_l", "cmd_r"),
    "super": ("cmd", "cmd_l", "cmd_r"),
    "meta": ("cmd", "cmd_l", "cmd_r"),
    "cmd": ("cmd", "cmd_l", "cmd_r"),
    "ctrl": ("ctrl", "ctrl_l", "ctrl_r"),
    "control": ("ctrl", "ctrl_l", "ctrl_r"),
    "ctrl_l": ("ctrl_l",),   # lado especifico casa SO com aquele lado:
    "ctrl_r": ("ctrl_r",),   # o Ctrl esquerdo (Ctrl+C etc) nao pode acionar.
    "alt": ("alt", "alt_l", "alt_r", "alt_gr"),
    "shift": ("shift", "shift_l", "shift_r"),
    "cmd_l": ("cmd_l",),
    "cmd_r": ("cmd_r",),
}
_LABELS = {
    "ctrl": "Ctrl", "ctrl_l": "Ctrl", "ctrl_r": "Ctrl direito", "control": "Ctrl",
    "win": "Win", "cmd": "Win", "super": "Win", "meta": "Win",
    "cmd_l": "Win", "cmd_r": "Win direito", "shift": "Shift",
    "alt": "Alt", "alt_l": "Alt", "alt_r": "Alt direito", "alt_gr": "Alt Gr",
    "space": "Espaço",
}


def _resolve_token(name):
    """Um token (ex: 'ctrl_l') -> conjunto de teclas pynput aceitas pra ele."""
    name = name.strip().lower()
    keys = set()
    for v in _KEY_ALIASES.get(name, (name,)):
        k = getattr(keyboard.Key, v, None)
        if k is not None:
            keys.add(k)
    if not keys and len(name) == 1:
        keys.add(keyboard.KeyCode.from_char(name))
    return keys


def _resolve_hotkey(spec):
    """Converte 'f9', 'ctrl_l+win' ou 'alt_gr/ctrl_r' num combo: lista de
    conjuntos de teclas. Dispara quando ao menos uma tecla de CADA conjunto
    esta pressionada.
    - '+' = E (combo simultaneo): 'ctrl_l+win' exige as duas juntas.
    - '/' = OU (alternativas): 'alt_gr/ctrl_r' aciona com qualquer uma das duas.
    Recomendado: tecla de funcao (f9), combo de modificadores (ctrl_l+win) ou
    alternativas (alt_gr/ctrl_r) pra teclados diferentes.
    Modificador sozinho (ctrl/alt) atrapalha atalhos - evite."""
    spec = (spec or "f9").strip().lower()
    combo = []
    for part in spec.split("+"):
        keys = set()
        for alt in part.split("/"):
            if alt.strip():
                keys |= _resolve_token(alt)
        if keys:
            combo.append(keys)
    return combo or [{keyboard.Key.f9}]


def _hotkey_label(spec):
    spec = (spec or "f9").strip().lower()
    parts = []
    for part in spec.split("+"):
        alts = [_LABELS.get(a.strip(), a.strip().upper())
                for a in part.split("/") if a.strip()]
        if alts:
            parts.append(" ou ".join(alts))
    return " + ".join(parts) or "F9"


_HOTKEY_SPEC = os.getenv("HOTKEY", "f9")
HOTKEY = _resolve_hotkey(_HOTKEY_SPEC)
HOTKEY_LABEL = _hotkey_label(_HOTKEY_SPEC)
# Atalho do modo maos-livres (toggle: aperta uma vez, grava sem segurar; aperta
# de novo ou clica Parar pra parar). Teclas nomeadas evitam ambiguidade de letra
# sob modificador no pynput; ctrl+alt+space nao colide com atalho do Windows.
_HANDSFREE_SPEC = os.getenv("HOTKEY_HANDSFREE", "ctrl+alt+space")
HANDSFREE_HOTKEY = _resolve_hotkey(_HANDSFREE_SPEC)
HANDSFREE_LABEL = _hotkey_label(_HANDSFREE_SPEC)
MIN_DURATION = 0.3
LANGUAGE = "pt"
# Modelo de transcricao. Default whisper-1 (acesso garantido em qualquer projeto).
# Pra usar gpt-4o-mini-transcribe / gpt-4o-transcribe (mais precisos), libere o
# acesso ao modelo no projeto da OpenAI e troque WHISPER_MODEL no .env.
MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
API_RETRIES = 3
BLOCK = 320           # 20ms por bloco -> ~50 updates/s (onda fluida)
N_POINTS = 56
MUTE_WHILE_RECORDING = True   # silencia a saida de audio enquanto grava
LOG_PATH = os.path.join(BASE, "dictate.log")
HIST_DIR = os.path.join(BASE, "transcricoes")
PEND_DIR = os.path.join(BASE, "pendentes")   # audios salvos antes de transcrever (sobrevivem a quedas)
AUDIO_DIR = os.path.join(BASE, "audios")     # acervo dos audios ja transcritos (retencao rolling)
AUDIO_RETENTION_DAYS = 7
VOCAB_PATH = os.path.join(BASE, "vocabulario.txt")           # editavel pelo app Transcricoes
VOCAB_EXAMPLE = os.path.join(BASE, "vocabulario.example.txt")
ICON_PATH = os.path.join(BASE, "assets", "mic.ico")
WARMUP_EVERY_MS = 240_000     # ping leve pra manter DNS/TLS/processo quentes

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
kb = keyboard.Controller()

bridge = None
overlay = None
hf_window = None

_frames = []
_stream = None
_recording = False
_last_level = 0.0
_state_lock = threading.Lock()
_pressed = set()   # teclas atualmente pressionadas (so a thread do listener mexe)
_t_press = None    # perf_counter do apertar da tecla -> mede tecla->overlay
_rec_mode = None   # None | "hold" | "handsfree" — quem esta gravando agora
_handsfree_combo_active = False  # True enquanto o chord maos-livres esta 100% pressionado (anti-repeat)
_hf_target_hwnd = None           # janela em foco quando o atalho maos-livres foi apertado (pro auto-paste)


def log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def beep(freq, ms=110):
    threading.Thread(target=lambda: _beep(freq, ms), daemon=True).start()


def _beep(freq, ms):
    try:
        winsound.Beep(freq, ms)
    except Exception:
        pass


_muted_by_us = False
_prev_mute = "0"           # estado do mute ANTES de mutarmos (preserva mute manual)
_audio_lock = threading.Lock()
SETMUTE = os.path.join(BASE, "setmute.py")
# Interpretador do subprocesso de mute: o pythonw do venv (que tem pycaw),
# nao sys.executable — o dictate.py as vezes roda pelo Python global, que pode
# nao ter pycaw instalado. Fallback pro interpretador atual se o venv sumir.
_VENV_PY = os.path.join(BASE, "venv", "Scripts", "pythonw.exe")
MUTE_PY = _VENV_PY if os.path.exists(_VENV_PY) else sys.executable


def _setmute(action):
    """Roda o SetMute (pycaw/COM) num subprocesso Python isolado — ver setmute.py.
    Isola o processo principal dos crashes nativos (0xC0000005) que o COM
    in-process causava, e NAO dispara o OSD de volume do Windows (a tecla de
    midia disparava, atrapalhando enxergar o overlay). Retorna o stdout
    (estado anterior, no caso de 'mute')."""
    try:
        r = subprocess.run(
            [MUTE_PY, SETMUTE, action],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode != 0:
            log(f"setmute {action} returncode={r.returncode}: {r.stderr.strip()}")
        return r.stdout.strip()
    except Exception as e:
        log(f"setmute {action} falhou: {e}")
        return ""


def _apply_mute(action):
    # Serializado: o unmute (stop) so roda depois do mute (start) terminar, mesmo
    # com spawn assincrono — evita race em ditado curto.
    global _prev_mute
    with _audio_lock:
        if action == "mute":
            _prev_mute = _setmute("mute")
        elif _prev_mute != "1":      # so desmuta se NAO ja estava mutado pelo usuario
            _setmute("unmute")


def mute_system():
    # Mute via subprocesso (pycaw/COM isolado) em thread daemon: nao bloqueia o
    # caminho de gravacao e nao dispara o OSD do Windows.
    global _muted_by_us
    if not MUTE_WHILE_RECORDING or _muted_by_us:
        return
    _muted_by_us = True
    threading.Thread(target=_apply_mute, args=("mute",), daemon=True).start()


def unmute_system():
    global _muted_by_us
    if not MUTE_WHILE_RECORDING or not _muted_by_us:
        return
    _muted_by_us = False
    threading.Thread(target=_apply_mute, args=("unmute",), daemon=True).start()


def save_history(text, now=None):
    try:
        os.makedirs(HIST_DIR, exist_ok=True)
        now = now or datetime.datetime.now()
        oneline = " ".join(text.split())
        with open(os.path.join(HIST_DIR, f"{now:%Y-%m-%d}.md"), "a", encoding="utf-8") as f:
            f.write(f"- **{now:%H:%M:%S}** — {oneline}\n")
    except Exception as e:
        log(f"historico falhou: {e}")


def read_vocab():
    """Vocabulario (termos que a transcricao costuma errar) -> prompt da API.
    Lido a cada gravacao: editar/salvar no app Transcricoes ja vale na proxima,
    sem reiniciar nada. Sem vocabulario.txt, cai no .example versionado."""
    for path in (VOCAB_PATH, VOCAB_EXAMPLE):
        try:
            with open(path, encoding="utf-8") as f:
                vocab = " ".join(f.read().split())
            if vocab:
                return vocab[:4000]
        except OSError:
            continue
    return ""


_warmup_busy = threading.Lock()


def warmup_api(quiet=False):
    """Ping leve na API (GET /models). O log mostrou que a 1a transcricao apos
    boot/idle leva 12-15s e as seguintes 1-3s — conexao/processo frios. Alem do
    ping periodico, e chamado ao INICIAR a gravacao: enquanto o usuario fala,
    DNS/TLS/processo esquentam em paralelo."""
    def run():
        if not _warmup_busy.acquire(blocking=False):
            return
        try:
            t0 = time.perf_counter()
            client.models.list()
            ms = (time.perf_counter() - t0) * 1000
            if not quiet or ms > 2000:
                log(f"[t] warmup api {ms:.0f}ms")
        except Exception as e:
            log(f"warmup api falhou: {str(e)[:80]}")
        finally:
            _warmup_busy.release()
    threading.Thread(target=run, daemon=True).start()


def archive_audio(wav_path, now):
    """Move o wav transcrito de pendentes/ pro acervo audios/<dia>/<HHMMSS>.wav
    (mesmo timestamp do historico — e assim que o app acha o audio do item)."""
    if not wav_path or not os.path.exists(wav_path):
        return
    try:
        day_dir = os.path.join(AUDIO_DIR, f"{now:%Y-%m-%d}")
        os.makedirs(day_dir, exist_ok=True)
        dest = os.path.join(day_dir, f"{now:%H%M%S}.wav")
        i = 1
        while os.path.exists(dest):
            dest = os.path.join(day_dir, f"{now:%H%M%S}-{i}.wav")
            i += 1
        shutil.move(wav_path, dest)
    except Exception as e:
        log(f"falha ao arquivar audio: {e}")


def prune_old_audios():
    """Apaga pastas de audio com mais de AUDIO_RETENTION_DAYS dias (o texto do
    historico fica pra sempre; so o audio e rolling)."""
    try:
        cutoff = datetime.date.today() - datetime.timedelta(days=AUDIO_RETENTION_DAYS)
        for d in glob.glob(os.path.join(AUDIO_DIR, "????-??-??")):
            try:
                day = datetime.date.fromisoformat(os.path.basename(d))
            except ValueError:
                continue
            if day < cutoff:
                shutil.rmtree(d, ignore_errors=True)
    except Exception as e:
        log(f"prune audios: {e}")


class Bridge(QObject):
    start = pyqtSignal()
    stop = pyqtSignal()
    done = pyqtSignal(float)   # segundos da transcricao; <0 = sem texto/erro
    handsfree_toggle = pyqtSignal()   # aperto do atalho maos-livres OU clique no Parar
    handsfree_cancel = pyqtSignal()   # ESC: descarta sem transcrever
    handsfree_done = pyqtSignal(float)   # segundos; <0 = erro/vazio (pill maos-livres)


class Overlay(QWidget):
    """Pill flutuante embaixo da tela. Estados: rec (onda + timer), busy
    (spinner + "transcrevendo"), done ("colado" verde) e fail (erro vermelho).
    done/fail piscam rapido e somem — feedback de sucesso/erro que antes nao
    existia (o overlay simplesmente sumia)."""

    W, H = 240, 36

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.W, self.H)
        self.mode = "rec"
        self.msg = ""
        self.levels = deque([0.0] * N_POINTS, maxlen=N_POINTS)
        self.rec_start = 0.0
        self._n = 0
        self._max = 0.0
        self._repaint = QTimer(self)
        self._repaint.setInterval(33)   # ~30 fps garantido
        self._repaint.timeout.connect(self._tick)

    def _tick(self):
        if self.mode == "rec":
            self.levels.append(_last_level)
            self._n += 1
            if _last_level > self._max:
                self._max = _last_level
        self.update()

    def reposition(self):
        # Fica no monitor onde o cursor esta (setup multi-monitor): o overlay
        # segue a tela ATIVA em vez de ficar preso na primaria. Antes, ancorado
        # em primaryScreen(), ele (a) aparecia na tela errada quando o foco
        # estava em outro monitor e (b) apos hot-plug de monitor o Qt do processo
        # ja rodando reportava geometria stale da primaria e a pill caia fora da
        # area visivel (ex: y=1822 abaixo da borda do primario -> sumia).
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        scr = screen.availableGeometry()
        x = scr.x() + (scr.width() - self.width()) // 2
        y = scr.y() + scr.height() - self.height() - 14
        # clamp defensivo: a pill nunca sai da area visivel da tela escolhida
        x = max(scr.x(), min(x, scr.x() + scr.width() - self.width()))
        y = max(scr.y(), min(y, scr.y() + scr.height() - self.height()))
        self.move(x, y)

    def show_recording(self):
        self.mode = "rec"
        self.rec_start = time.time()
        self.levels = deque([0.0] * N_POINTS, maxlen=N_POINTS)
        self._n = 0
        self._max = 0.0
        self.reposition()
        self.show()
        self.raise_()
        self._repaint.start()
        self.update()

    def show_busy(self):
        log(f"[diag] updates={self._n} maxlvl={self._max:.3f} "
            f"visible={self.isVisible()} geo={self.x()},{self.y()} {self.width()}x{self.height()}")
        self.mode = "busy"   # repaint continua rodando: anima o spinner
        self.update()

    def show_done(self, secs):
        if _recording:   # uma nova gravacao ja comecou; nao esconde o overlay dela
            return
        if secs >= 0:
            self._flash("done", f"colado · {secs:.1f}s", 900)
        elif secs == -2.0:
            self._flash("fail", "falhou — audio guardado pra retry", 1600)
        elif secs == -3.0:
            self._flash("fail", "nao entendi nada", 1200)
        else:
            self.hide_it()   # curto/sem audio: some em silencio, como antes

    def _flash(self, mode, msg, ms):
        self.mode = mode
        self.msg = msg
        if not self.isVisible():
            self.reposition()
            self.show()
            self.raise_()
        if not self._repaint.isActive():
            self._repaint.start()
        self.update()
        QTimer.singleShot(ms, lambda: self._end_flash(mode))

    def _end_flash(self, mode):
        if self.mode == mode and not _recording:
            self.hide_it()

    def hide_it(self):
        self._repaint.stop()
        self.hide()

    # ---- pintura ----

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cy = h / 2

        # pill: fundo quase 100% preto + borda sutil
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        p.setBrush(QColor(6, 6, 7, 250))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), h / 2 - 1, h / 2 - 1)

        if self.mode == "busy":
            self._paint_busy(p, w, h, cy)
        elif self.mode in ("done", "fail"):
            ok = self.mode == "done"
            p.setPen(QColor("#D8D8DC") if ok else QColor("#F87171"))
            p.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
            mark = "✓  " if ok else "✕  "
            p.drawText(self.rect(), Qt.AlignCenter, mark + self.msg)
        else:
            self._paint_rec(p, w, h, cy)

    def _paint_busy(self, p, w, h, cy):
        # spinner: arco girando (cinza, minimalista)
        ang = int((time.time() * 320) % 360)
        pen = QPen(QColor("#A6A6AC"), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(QRect(15, int(cy - 6), 12, 12), -ang * 16, 110 * 16)
        # "transcrevendo" + reticencias andando
        dots = "." * (int(time.time() * 2.5) % 4)
        p.setPen(QColor("#C9C9CE"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRect(36, 0, w - 48, h), Qt.AlignVCenter | Qt.AlignLeft,
                   f"transcrevendo{dots}")

    def _paint_rec(self, p, w, h, cy):
        # ponto REC vermelho pulsando — unica cor do overlay
        pulse = 0.5 + 0.5 * math.sin(time.time() * 3.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(235, 70, 70, int(130 + 125 * pulse)))
        p.drawEllipse(13, int(cy - 3), 7, 7)

        # onda espelhada em cinza
        timer_w = 46
        x0 = 28
        area_w = w - x0 - timer_w - 10
        spacing = area_w / (N_POINTS - 1)
        amp = h * 0.32
        pen = QPen(QColor("#9A9AA0"), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        for i, lvl in enumerate(self.levels):
            ext = max(1.0, lvl * amp)
            x = x0 + i * spacing
            p.drawLine(int(x), int(cy - ext), int(x), int(cy + ext))

        # timer de gravacao (cinza quase branco)
        e = time.time() - self.rec_start
        txt = f"{int(e // 60)}:{int(e % 60):02d}" if e >= 60 else f"{e:0.1f}s"
        p.setPen(QColor("#E3E3E7"))
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        p.drawText(QRect(w - timer_w - 13, 0, timer_w, h),
                   Qt.AlignVCenter | Qt.AlignRight, txt)


class HandsFreeWindow(QWidget):
    """Pill do modo maos-livres: mesmo visual preto do Overlay, mas com um botao
    Parar clicavel. Nao rouba foco (WS_EX_NOACTIVATE via WindowDoesNotAcceptFocus
    + WA_ShowWithoutActivating) — recebe clique de mouse sem ativar, o que faz o
    auto-paste cair na janela de tras, nao nela. Estados: rec (onda+timer+Parar),
    busy (transcrevendo), done ("colado") e fail (erro). Parar e a hotkey de novo
    fazem a mesma coisa (toggle), ambos via bridge.handsfree_toggle."""

    W, H = 300, 48
    BTN_W = 74

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.W, self.H)
        self.mode = "rec"
        self.msg = ""
        self.levels = deque([0.0] * N_POINTS, maxlen=N_POINTS)
        self.rec_start = 0.0

        self.btn = QPushButton("■  Parar", self)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setFocusPolicy(Qt.NoFocus)   # nunca segura foco de teclado
        self.btn.setStyleSheet(
            "QPushButton { color: #E8E8EC; background: rgba(235,70,70,40);"
            " border: 1px solid rgba(235,70,70,120); border-radius: 12px;"
            " font: 600 10pt 'Segoe UI'; padding: 0 4px; }"
            "QPushButton:hover { background: rgba(235,70,70,90); }"
        )
        self.btn.setGeometry(self.W - self.BTN_W - 10, 11, self.BTN_W, self.H - 22)
        self.btn.clicked.connect(lambda: bridge.handsfree_toggle.emit())

        self._repaint = QTimer(self)
        self._repaint.setInterval(33)
        self._repaint.timeout.connect(self._tick)

    def _tick(self):
        if self.mode == "rec":
            self.levels.append(_last_level)
        self.update()

    def reposition(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        scr = screen.availableGeometry()
        x = scr.x() + (scr.width() - self.width()) // 2
        y = scr.y() + scr.height() - self.height() - 14
        x = max(scr.x(), min(x, scr.x() + scr.width() - self.width()))
        y = max(scr.y(), min(y, scr.y() + scr.height() - self.height()))
        self.move(x, y)

    def show_recording(self):
        self.mode = "rec"
        self.rec_start = time.time()
        self.levels = deque([0.0] * N_POINTS, maxlen=N_POINTS)
        self.btn.setText("■  Parar")
        self.btn.show()
        self.reposition()
        self.show()
        self.raise_()
        self._repaint.start()
        self.update()

    def show_busy(self):
        self.mode = "busy"
        self.btn.hide()   # transcrevendo: nao ha o que parar
        self.update()

    def show_done(self, secs):
        if _recording and _rec_mode == "handsfree":
            return   # uma nova gravacao maos-livres ja comecou
        self.btn.hide()
        if secs >= 0:
            self._flash("done", f"colado · {secs:.1f}s", 900)
        elif secs == -2.0:
            self._flash("fail", "falhou — audio guardado pra retry", 1600)
        elif secs == -3.0:
            self._flash("fail", "nao entendi nada", 1200)
        else:
            self.hide_it()

    def _flash(self, mode, msg, ms):
        self.mode = mode
        self.msg = msg
        if not self.isVisible():
            self.reposition()
            self.show()
            self.raise_()
        if not self._repaint.isActive():
            self._repaint.start()
        self.update()
        QTimer.singleShot(ms, lambda: self._end_flash(mode))

    def _end_flash(self, mode):
        if self.mode == mode and not (_recording and _rec_mode == "handsfree"):
            self.hide_it()

    def hide_it(self):
        self._repaint.stop()
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cy = h / 2
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        p.setBrush(QColor(6, 6, 7, 250))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 16, 16)

        if self.mode == "busy":
            ang = int((time.time() * 320) % 360)
            pen = QPen(QColor("#A6A6AC"), 2.0)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(QRect(18, int(cy - 7), 14, 14), -ang * 16, 110 * 16)
            dots = "." * (int(time.time() * 2.5) % 4)
            p.setPen(QColor("#C9C9CE"))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(QRect(42, 0, w - 54, h), Qt.AlignVCenter | Qt.AlignLeft,
                       f"transcrevendo{dots}")
            return
        if self.mode in ("done", "fail"):
            ok = self.mode == "done"
            p.setPen(QColor("#D8D8DC") if ok else QColor("#F87171"))
            p.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
            mark = "✓  " if ok else "✕  "
            p.drawText(self.rect(), Qt.AlignCenter, mark + self.msg)
            return

        # rec: ponto vermelho + onda + timer (a onda para antes do botao)
        pulse = 0.5 + 0.5 * math.sin(time.time() * 3.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(235, 70, 70, int(130 + 125 * pulse)))
        p.drawEllipse(15, int(cy - 4), 8, 8)

        timer_w = 46
        x0 = 32
        area_w = w - x0 - timer_w - self.BTN_W - 22
        spacing = area_w / (N_POINTS - 1)
        amp = h * 0.30
        pen = QPen(QColor("#9A9AA0"), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        for i, lvl in enumerate(self.levels):
            ext = max(1.0, lvl * amp)
            x = x0 + i * spacing
            p.drawLine(int(x), int(cy - ext), int(x), int(cy + ext))

        e = time.time() - self.rec_start
        txt = f"{int(e // 60)}:{int(e % 60):02d}" if e >= 60 else f"{e:0.1f}s"
        p.setPen(QColor("#E3E3E7"))
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        p.drawText(QRect(x0 + int(area_w) + 4, 0, timer_w, h),
                   Qt.AlignVCenter | Qt.AlignRight, txt)


def _get_foreground():
    """HWND da janela em foco agora (o alvo do auto-paste no modo maos-livres)."""
    try:
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return None


def _focus_and_paste(text, hwnd):
    """Reforca o foco na janela-alvo e cola. Como a pill e NOACTIVATE, o alvo
    normalmente JA e o foreground — o SetForegroundWindow e rede de seguranca
    (ex: se eu troquei de janela no meio, cola na que estava no inicio)."""
    try:
        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.05)
    except Exception as e:
        log(f"set foreground falhou: {e}")
    paste(text)


def _begin_capture():
    """Abre o stream, muta, warmup, beep. Seta _recording. Retorna False se ja
    grava (miolo compartilhado entre hold-to-talk e maos-livres)."""
    global _recording, _stream, _frames, _last_level
    with _state_lock:
        if _recording:
            return False
        _frames = []
        _recording = True
    _last_level = 0.0
    warmup_api(quiet=True)   # esquenta a conexao ENQUANTO o usuario fala
    beep(880)

    def callback(indata, frames_count, time_info, status):
        global _last_level
        _frames.append(indata.copy())
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
        _last_level = min(1.0, rms * 70.0)   # ganho p/ a onda encher (fala ~0.005-0.02)

    _stream = sd.InputStream(
        samplerate=SR, channels=1, dtype="int16", blocksize=BLOCK, callback=callback
    )
    _stream.start()
    mute_system()
    return True


def _end_capture():
    """Fecha o stream, desmuta, beep. Retorna os frames por valor (evita a race
    do _frames global). None se nao estava gravando."""
    global _recording, _stream, _frames
    with _state_lock:
        if not _recording:
            return None
        _recording = False
    try:
        _stream.stop()
        _stream.close()
    except Exception:
        pass
    unmute_system()
    beep(440)
    frames, _frames = _frames, []
    return frames


def slot_handsfree_toggle():
    """Aperto do atalho OU clique no Parar. Decide start/stop conforme o estado.
    Um ditado por vez: se o hold-to-talk grava, ignora."""
    if _recording and _rec_mode == "hold":
        return
    if _recording and _rec_mode == "handsfree":
        _handsfree_stop()
    elif not _recording:
        _handsfree_start()


def _handsfree_start():
    global _rec_mode, _hf_target_hwnd
    _hf_target_hwnd = _get_foreground()   # captura o alvo ANTES de abrir a pill
    hf_window.show_recording()            # visual instantaneo (pill nao rouba foco)
    if _begin_capture():
        _rec_mode = "handsfree"
        log("Gravando (maos-livres)...")
    else:
        hf_window.hide_it()


def _handsfree_stop():
    global _rec_mode
    frames = _end_capture()
    _rec_mode = None
    hf_window.show_busy()
    threading.Thread(
        target=worker, args=(frames,),
        kwargs=dict(mode="handsfree", target_hwnd=_hf_target_hwnd), daemon=True,
    ).start()


def slot_handsfree_cancel():
    """ESC durante a gravacao maos-livres: descarta (nao transcreve/cola/salva)."""
    global _rec_mode
    if _recording and _rec_mode == "handsfree":
        _end_capture()   # fecha stream/desmuta; frames sao descartados
        _rec_mode = None
        hf_window.hide_it()
        log("Maos-livres cancelado (ESC).")


def slot_start():
    global _rec_mode
    overlay.show_recording()   # visual instantaneo, antes de abrir o audio (que pode demorar a frio)
    if _t_press:
        log(f"[t] tecla->overlay {(time.perf_counter() - _t_press) * 1000:.0f}ms")
    if _begin_capture():
        _rec_mode = "hold"
        log("Gravando...")
    else:
        overlay.hide_it()


def slot_stop():
    global _rec_mode
    frames = _end_capture()
    _rec_mode = None
    overlay.show_busy()
    # frames entregues por valor pra evitar a race do _frames global (uma nova
    # gravacao zerava o audio da anterior — ver _end_capture).
    threading.Thread(target=worker, args=(frames,), daemon=True).start()


def _norm_for_echo(s):
    """Normaliza pra comparar eco: minusculas, sem pontuacao, espaco colapsado."""
    return " ".join(re.sub(r"[^\w\s]", " ", s.lower()).split())


def _looks_like_vocab_echo(text, vocab):
    """True quando a transcricao e, na verdade, um trecho do vocabulario e nao
    a fala. O whisper-1 opera como GPT base e imita o estilo do prompt: com o
    vocabulario (uma lista de termos) as vezes 'cai na lista' e ecoa termos do
    prompt em vez de transcrever (investigacao jul/2026 — ~25% dos ditados). A
    fala em si e decodificavel; so a saida com prompt sai errada.
    Deteccao: a saida (3+ palavras) e uma SUBSEQUENCIA ordenada do vocabulario —
    toda palavra dela aparece no vocab, na mesma ordem (o modelo as vezes pula
    termos, entao 'contido' exato nao basta). Fala real tem palavras funcionais
    (de, que, nao, ta...) fora do vocab, logo nao casa. gpt-4o-transcribe nao
    faz isso, mas o guard protege se o modelo voltar pro whisper-1."""
    t = _norm_for_echo(text).split()
    if len(t) < 3:
        return False
    i = 0
    for w in _norm_for_echo(vocab).split():
        if i < len(t) and t[i] == w:
            i += 1
    return i == len(t)


def transcribe_bytes(bio):
    """Transcreve um buffer WAV (BytesIO). Retorna (texto, erro)."""
    err = None
    base_kwargs = dict(model=MODEL, file=("audio.wav", bio, "audio/wav"), language=LANGUAGE)
    kwargs = dict(base_kwargs)
    vocab = read_vocab()
    if vocab:
        # contexto pro modelo acertar termos do dia a dia ("CLAUDE.md", nao
        # "cloud.md"). gpt-4o-(mini-)transcribe usa o prompt inteiro como
        # contexto; whisper-1 so considera os ultimos 224 tokens.
        kwargs["prompt"] = vocab
    for attempt in range(API_RETRIES):
        try:
            bio.seek(0)
            r = client.audio.transcriptions.create(**kwargs)
            text = (r.text or "").strip()
            # guard anti-eco: se a saida for um trecho do vocabulario, o modelo
            # ecoou o prompt em vez de transcrever. Refaz sem prompt — a fala e
            # decodificavel, so o prompt sabotou (ver _looks_like_vocab_echo).
            if vocab and text and _looks_like_vocab_echo(text, vocab):
                log("saida parece eco do vocabulario; refazendo sem prompt")
                bio.seek(0)
                r = client.audio.transcriptions.create(**base_kwargs)
                text = (r.text or "").strip()
            return text, None
        except Exception as e:
            err = str(e)[:90]
            log(f"api tentativa {attempt + 1} falhou: {err}")
            time.sleep(0.5)
    return "", err


def _emit_done(mode, secs):
    """Sinaliza o fim pra pill certa: overlay (hold) ou HandsFreeWindow (maos-livres)."""
    if mode == "handsfree":
        bridge.handsfree_done.emit(secs)
    else:
        bridge.done.emit(secs)


def worker(frames, mode="hold", target_hwnd=None):
    try:
        if not frames:
            _emit_done(mode, -1.0)
            return
        audio = np.concatenate(frames, axis=0)
        duration = len(audio) / SR
        if duration < MIN_DURATION:
            log(f"Muito curto ({duration:.2f}s), ignorado.")
            _emit_done(mode, -1.0)
            return

        # salva o audio em disco ANTES de transcrever — se o processo cair no
        # meio, o audio fica em pendentes/ e e re-transcrito no proximo boot.
        wav_path = None
        try:
            os.makedirs(PEND_DIR, exist_ok=True)
            wav_path = os.path.join(PEND_DIR, f"{datetime.datetime.now():%Y%m%d-%H%M%S-%f}.wav")
            sf.write(wav_path, audio, SR)
        except Exception as e:
            log(f"falha ao salvar audio pendente: {e}")
            wav_path = None

        log(f"Transcrevendo {duration:.1f}s...")
        t_enc = time.time()
        bio = io.BytesIO()
        sf.write(bio, audio, SR, format="wav")
        t0 = time.time()
        text, err = transcribe_bytes(bio)
        elapsed = time.time() - t0
        log(f"[t] encode {(t0 - t_enc) * 1000:.0f}ms | api {elapsed:.1f}s | audio {duration:.1f}s")

        if err or not text:
            if err:
                _emit_done(mode, -2.0)
                log("Falhou na API (audio guardado em pendentes/ pra retry no boot).")
            else:
                _emit_done(mode, -3.0)
                log("Transcricao vazia.")
                # vazio nao e queda — descarta o pendente pra nao re-tentar a toa
                _safe_remove(wav_path)
            beep(220, 280)
            return

        _emit_done(mode, elapsed)
        now = datetime.datetime.now()
        save_history(text, now)
        log(f"({elapsed:.1f}s) -> {text}")
        archive_audio(wav_path, now)   # guarda o audio pra ouvir/re-transcrever no app
        if mode == "handsfree":
            _focus_and_paste(text + " ", target_hwnd)   # reforca o foco no alvo antes do Ctrl+V
        else:
            paste(text + " ")
    except Exception:
        # blindagem: qualquer erro inesperado vira log com traceback em vez de
        # matar a thread/processo em silencio (foi o que aconteceu no crash de 11:38).
        log("ERRO inesperado no worker:\n" + traceback.format_exc())
        try:
            _emit_done(mode, -1.0)
        except Exception:
            pass
        beep(220, 280)


def _safe_remove(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            log(f"falha ao remover {os.path.basename(path)}: {e}")


def recover_pending():
    """No boot, re-transcreve audios que ficaram em pendentes/ por uma queda.
    Salva no historico (NAO cola — o cursor ja esta em outro lugar)."""
    try:
        files = sorted(glob.glob(os.path.join(PEND_DIR, "*.wav")))
    except Exception:
        return
    if not files:
        return
    log(f"Recuperando {len(files)} audio(s) pendente(s) de uma queda anterior...")
    for fp in files:
        name = os.path.basename(fp)
        try:
            data, sr = sf.read(fp, dtype="int16")
            bio = io.BytesIO()
            sf.write(bio, data, sr, format="wav")
            text, err = transcribe_bytes(bio)
            if text and not err:
                now = datetime.datetime.now()
                save_history(text, now)
                log(f"recuperado [{name}] -> {text}")
                archive_audio(fp, now)
            else:
                log(f"nao recuperei {name} ({err or 'vazio'}); mantendo pra proxima.")
        except Exception:
            log(f"erro recuperando {name}:\n" + traceback.format_exc())


def paste(text):
    try:
        previous = pyperclip.paste()
    except Exception:
        previous = ""
    pyperclip.copy(text)
    time.sleep(0.08)
    with kb.pressed(keyboard.Key.ctrl):
        kb.press("v")
        kb.release("v")
    time.sleep(0.35)
    try:
        pyperclip.copy(previous)
    except Exception:
        pass


def _combo_held():
    """True quando ao menos uma tecla de cada conjunto do HOTKEY esta pressionada."""
    return all(_pressed & token for token in HOTKEY)


def _handsfree_held():
    """True quando o chord do atalho maos-livres esta 100% pressionado."""
    return all(_pressed & token for token in HANDSFREE_HOTKEY)


def on_press(key):
    global _t_press, _handsfree_combo_active
    _pressed.add(key)

    # hold-to-talk (level-triggered): grava enquanto segura a HOTKEY
    if not _recording and _combo_held():
        _t_press = time.perf_counter()
        bridge.start.emit()

    # maos-livres (edge-triggered): um toque no chord alterna start/stop.
    # Trava anti-repeat: o auto-repeat da tecla nao dispara de novo ate soltar.
    if _handsfree_held():
        if not _handsfree_combo_active:
            _handsfree_combo_active = True
            bridge.handsfree_toggle.emit()

    # ESC cancela — so quando o maos-livres esta gravando (a pill nao tem foco de
    # teclado por ser NOACTIVATE, entao o ESC vem do listener global, nao dela)
    if key == keyboard.Key.esc and _recording and _rec_mode == "handsfree":
        bridge.handsfree_cancel.emit()


def on_release(key):
    global _handsfree_combo_active
    _pressed.discard(key)

    # hold-to-talk para so quando quem grava e o hold (nao o maos-livres)
    if _recording and _rec_mode == "hold" and not _combo_held():
        bridge.stop.emit()

    # rearma o maos-livres quando o chord e solto
    if _handsfree_combo_active and not _handsfree_held():
        _handsfree_combo_active = False


def _log_uncaught(exc_type, exc_value, exc_tb):
    log("EXCECAO NAO TRATADA:\n" + "".join(
        traceback.format_exception(exc_type, exc_value, exc_tb)))


def _thread_excepthook(args):
    log("EXCECAO EM THREAD:\n" + "".join(
        traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


def main():
    # captura qualquer erro nao tratado num log com traceback (pythonw nao tem console)
    sys.excepthook = _log_uncaught
    threading.excepthook = _thread_excepthook

    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        guard.bind(("127.0.0.1", 49732))
    except OSError:
        log("Ja existe uma instancia rodando. Saindo.")
        sys.exit(0)

    if not os.getenv("OPENAI_API_KEY"):
        log("OPENAI_API_KEY ausente no .env. Abortando.")
        sys.exit(1)

    global bridge, overlay, hf_window
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    bridge = Bridge()
    overlay = Overlay()
    hf_window = HandsFreeWindow()
    bridge.start.connect(slot_start)
    bridge.stop.connect(slot_stop)
    bridge.done.connect(overlay.show_done)
    bridge.handsfree_toggle.connect(slot_handsfree_toggle)
    bridge.handsfree_cancel.connect(slot_handsfree_cancel)
    bridge.handsfree_done.connect(hf_window.show_done)

    # icone na bandeja (cara de programa instalado + botao Sair)
    tray = QSystemTrayIcon(QIcon(ICON_PATH), app)
    tray.setToolTip(
        f"whisper-voice — segura {HOTKEY_LABEL} pra ditar · "
        f"{HANDSFREE_LABEL} pra maos-livres"
    )
    menu = QMenu()
    act_quit = QAction("Sair", app)
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.show()

    # pre-aquece o audio (PortAudio) pro 1o acionamento ser instantaneo
    try:
        sd.query_devices()   # inicializa o PortAudio (parte fria) sem ocupar o microfone
    except Exception as e:
        log(f"warmup audio: {e}")

    # pre-aquece a API (1a chamada fria levava 12-15s vs 1-3s quente) e mantem
    # quente com ping periodico leve
    warmup_api()
    warm_timer = QTimer()
    warm_timer.setInterval(WARMUP_EVERY_MS)
    warm_timer.timeout.connect(lambda: warmup_api(quiet=True))
    warm_timer.start()

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    # recupera audios que ficaram pendentes de uma queda anterior (em background)
    threading.Thread(target=recover_pending, daemon=True).start()
    # apaga audios alem da janela de retencao (texto fica; so o wav e rolling)
    threading.Thread(target=prune_old_audios, daemon=True).start()

    log(f"whisper-voice pronto. Segura {HOTKEY_LABEL}, fala, solta. "
        f"Maos-livres: {HANDSFREE_LABEL} (toggle).")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
