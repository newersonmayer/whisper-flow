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
import sys
import glob
import math
import time
import shutil
import socket
import threading
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
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QIcon
from PyQt5.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu, QAction

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
    "cmd_l": "Win", "cmd_r": "Win direito", "alt": "Alt", "shift": "Shift",
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
    """Converte 'f9' ou 'ctrl_l+win' num combo: lista de conjuntos de teclas.
    Dispara quando ao menos uma tecla de CADA conjunto esta pressionada.
    Recomendado: tecla de funcao (f9) ou combo de modificadores (ctrl_l+win).
    Modificador sozinho (ctrl/alt) atrapalha atalhos - evite."""
    spec = (spec or "f9").strip().lower()
    combo = [s for s in (_resolve_token(t) for t in spec.split("+") if t.strip()) if s]
    return combo or [{keyboard.Key.f9}]


def _hotkey_label(spec):
    spec = (spec or "f9").strip().lower()
    parts = [_LABELS.get(t.strip(), t.strip().upper()) for t in spec.split("+") if t.strip()]
    return " + ".join(parts) or "F9"


_HOTKEY_SPEC = os.getenv("HOTKEY", "f9")
HOTKEY = _resolve_hotkey(_HOTKEY_SPEC)
HOTKEY_LABEL = _hotkey_label(_HOTKEY_SPEC)
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

_frames = []
_stream = None
_recording = False
_last_level = 0.0
_state_lock = threading.Lock()
_pressed = set()   # teclas atualmente pressionadas (so a thread do listener mexe)
_t_press = None    # perf_counter do apertar da tecla -> mede tecla->overlay


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


def mute_system():
    # Muta pela tecla de midia do Windows (pynput -> SendInput), NAO pela API COM
    # IAudioEndpointVolume (pycaw). Aquele caminho COM era a causa dos crashes
    # nativos recorrentes (_ctypes.pyd / 0xC0000005) e ainda deixava o controle
    # de volume do Windows travado. A tecla de mute e um toggle, entao guardamos
    # que fomos nos que mutamos pra desmutar certo no fim.
    global _muted_by_us
    if not MUTE_WHILE_RECORDING or _muted_by_us:
        return
    try:
        kb.tap(keyboard.Key.media_volume_mute)
        _muted_by_us = True
    except Exception as e:
        log(f"mute falhou: {e}")


def unmute_system():
    global _muted_by_us
    if not MUTE_WHILE_RECORDING or not _muted_by_us:
        return
    try:
        kb.tap(keyboard.Key.media_volume_mute)
    except Exception as e:
        log(f"unmute falhou: {e}")
    _muted_by_us = False


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
        scr = QApplication.primaryScreen().availableGeometry()
        x = scr.x() + (scr.width() - self.width()) // 2
        y = scr.y() + scr.height() - self.height() - 14
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


def slot_start():
    global _recording, _stream, _frames, _last_level
    with _state_lock:
        if _recording:
            return
        _frames = []
        _recording = True
    _last_level = 0.0
    overlay.show_recording()   # visual instantaneo, antes de abrir o audio (que pode demorar a frio)
    if _t_press:
        log(f"[t] tecla->overlay {(time.perf_counter() - _t_press) * 1000:.0f}ms")
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
    log("Gravando...")


def slot_stop():
    global _recording, _stream, _frames
    with _state_lock:
        if not _recording:
            return
        _recording = False
    try:
        _stream.stop()
        _stream.close()
    except Exception:
        pass
    unmute_system()
    beep(440)
    overlay.show_busy()
    # entrega os frames pro worker por argumento: se uma nova gravacao comecar
    # antes da transcricao ler os frames, o `_frames = []` do slot_start nao
    # apaga o audio desta (race que ja perdeu gravacao na pratica).
    frames, _frames = _frames, []
    threading.Thread(target=worker, args=(frames,), daemon=True).start()


def transcribe_bytes(bio):
    """Transcreve um buffer WAV (BytesIO). Retorna (texto, erro)."""
    err = None
    kwargs = dict(model=MODEL, file=("audio.wav", bio, "audio/wav"), language=LANGUAGE)
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
            return (r.text or "").strip(), None
        except Exception as e:
            err = str(e)[:90]
            log(f"api tentativa {attempt + 1} falhou: {err}")
            time.sleep(0.5)
    return "", err


def worker(frames):
    try:
        if not frames:
            bridge.done.emit(-1.0)
            return
        audio = np.concatenate(frames, axis=0)
        duration = len(audio) / SR
        if duration < MIN_DURATION:
            log(f"Muito curto ({duration:.2f}s), ignorado.")
            bridge.done.emit(-1.0)
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
                bridge.done.emit(-2.0)
                log("Falhou na API (audio guardado em pendentes/ pra retry no boot).")
            else:
                bridge.done.emit(-3.0)
                log("Transcricao vazia.")
                # vazio nao e queda — descarta o pendente pra nao re-tentar a toa
                _safe_remove(wav_path)
            beep(220, 280)
            return

        bridge.done.emit(elapsed)
        now = datetime.datetime.now()
        save_history(text, now)
        log(f"({elapsed:.1f}s) -> {text}")
        archive_audio(wav_path, now)   # guarda o audio pra ouvir/re-transcrever no app
        paste(text + " ")
    except Exception:
        # blindagem: qualquer erro inesperado vira log com traceback em vez de
        # matar a thread/processo em silencio (foi o que aconteceu no crash de 11:38).
        log("ERRO inesperado no worker:\n" + traceback.format_exc())
        try:
            bridge.done.emit(-1.0)
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


def on_press(key):
    global _t_press
    _pressed.add(key)
    if not _recording and _combo_held():
        _t_press = time.perf_counter()
        bridge.start.emit()


def on_release(key):
    _pressed.discard(key)
    if _recording and not _combo_held():
        bridge.stop.emit()


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

    global bridge, overlay
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    bridge = Bridge()
    overlay = Overlay()
    bridge.start.connect(slot_start)
    bridge.stop.connect(slot_stop)
    bridge.done.connect(overlay.show_done)

    # icone na bandeja (cara de programa instalado + botao Sair)
    tray = QSystemTrayIcon(QIcon(ICON_PATH), app)
    tray.setToolTip(f"whisper-voice — segura {HOTKEY_LABEL} pra ditar")
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

    log(f"whisper-voice pronto. Segura {HOTKEY_LABEL}, fala, solta.")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
