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
import time
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

from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from PyQt5.QtCore import Qt, QObject, pyqtSignal, QRect, QTimer
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QIcon
from PyQt5.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu, QAction

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))

SR = 16000


def _resolve_hotkey(name):
    """Converte o nome da tecla (vindo do .env) num objeto de tecla do pynput.
    Recomendado: teclas de funcao (f1..f12). Letras atrapalham a digitacao."""
    name = (name or "f9").strip().lower()
    key = getattr(keyboard.Key, name, None)
    if key is not None:
        return key
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    return keyboard.Key.f9


HOTKEY = _resolve_hotkey(os.getenv("HOTKEY", "f9"))
HOTKEY_LABEL = (os.getenv("HOTKEY", "f9")).strip().upper()
MIN_DURATION = 0.3
LANGUAGE = "pt"
# Modelo de transcricao. Default whisper-1 (acesso garantido em qualquer projeto).
# Pra usar gpt-4o-mini-transcribe / gpt-4o-transcribe (mais precisos), libere o
# acesso ao modelo no projeto da OpenAI e troque WHISPER_MODEL no .env.
MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
API_RETRIES = 3
BLOCK = 320           # 20ms por bloco -> ~50 updates/s (onda fluida)
N_POINTS = 46
MUTE_WHILE_RECORDING = True   # silencia a saida de audio enquanto grava
LOG_PATH = os.path.join(BASE, "dictate.log")
HIST_DIR = os.path.join(BASE, "transcricoes")
PEND_DIR = os.path.join(BASE, "pendentes")   # audios salvos antes de transcrever (sobrevivem a quedas)
ICON_PATH = os.path.join(BASE, "assets", "mic.ico")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
kb = keyboard.Controller()

bridge = None
overlay = None

_frames = []
_stream = None
_recording = False
_last_level = 0.0
_state_lock = threading.Lock()


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


_prev_mute = None


def _get_volume():
    enum = AudioUtilities.GetDeviceEnumerator()
    dev = enum.GetDefaultAudioEndpoint(0, 1)  # eRender, eMultimedia
    itf = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(itf, POINTER(IAudioEndpointVolume))


def mute_system():
    global _prev_mute
    if not MUTE_WHILE_RECORDING:
        return
    try:
        vol = _get_volume()
        _prev_mute = vol.GetMute()
        vol.SetMute(1, None)
    except Exception as e:
        log(f"mute falhou: {e}")


def unmute_system():
    global _prev_mute
    if not MUTE_WHILE_RECORDING or _prev_mute is None:
        return
    try:
        _get_volume().SetMute(_prev_mute, None)
    except Exception as e:
        log(f"unmute falhou: {e}")
    _prev_mute = None


def save_history(text):
    try:
        os.makedirs(HIST_DIR, exist_ok=True)
        now = datetime.datetime.now()
        oneline = " ".join(text.split())
        with open(os.path.join(HIST_DIR, f"{now:%Y-%m-%d}.md"), "a", encoding="utf-8") as f:
            f.write(f"- **{now:%H:%M:%S}** — {oneline}\n")
    except Exception as e:
        log(f"historico falhou: {e}")


class Bridge(QObject):
    start = pyqtSignal()
    stop = pyqtSignal()
    done = pyqtSignal(float)   # segundos da transcricao; <0 = sem texto/erro


class Overlay(QWidget):
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
        self.setFixedSize(212, 30)
        self.mode = "rec"
        self.levels = deque([0.0] * N_POINTS, maxlen=N_POINTS)
        self.rec_start = 0.0
        self._n = 0
        self._max = 0.0
        self._repaint = QTimer(self)
        self._repaint.setInterval(33)   # ~30 fps garantido
        self._repaint.timeout.connect(self._tick)

    def _tick(self):
        self.levels.append(_last_level)
        self._n += 1
        if _last_level > self._max:
            self._max = _last_level
        self.update()

    def reposition(self):
        scr = QApplication.primaryScreen().availableGeometry()
        x = scr.x() + (scr.width() - self.width()) // 2
        y = scr.y() + scr.height() - self.height() - 10
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
        self.mode = "busy"
        self._repaint.stop()
        self.update()

    def show_done(self, secs):
        if _recording:   # uma nova gravacao ja comecou; nao esconde o overlay dela
            return
        self.hide_it()

    def hide_it(self):
        self._repaint.stop()
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 235))
        p.drawRoundedRect(self.rect(), 9, 9)

        w, h = self.width(), self.height()
        cy = h / 2

        if self.mode == "busy":
            p.setPen(QColor(150, 200, 255))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(self.rect(), Qt.AlignCenter, "transcrevendo…")
            return

        # gravando: onda em tempo real + timer de gravacao ao lado
        timer_w = 40
        pad = 16
        area_w = w - pad - timer_w - 8
        spacing = area_w / (N_POINTS - 1)
        pen = QPen(QColor(90, 220, 160), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        amp = h * 0.38
        for i, lvl in enumerate(self.levels):
            ext = max(0.8, lvl * amp)
            x = pad + i * spacing
            p.drawLine(int(x), int(cy - ext), int(x), int(cy + ext))

        # ponto REC
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(235, 70, 70))
        p.drawEllipse(7, int(cy - 3), 6, 6)

        # timer de gravacao (conta enquanto fala)
        elapsed = time.time() - self.rec_start
        p.setPen(QColor(220, 220, 225))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRect(w - timer_w - 6, 0, timer_w, h),
                   Qt.AlignVCenter | Qt.AlignRight, f"{elapsed:0.1f}s")


def slot_start():
    global _recording, _stream, _frames, _last_level
    with _state_lock:
        if _recording:
            return
        _frames = []
        _recording = True
    _last_level = 0.0
    overlay.show_recording()   # visual instantaneo, antes de abrir o audio (que pode demorar a frio)
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
    global _recording, _stream
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
    threading.Thread(target=worker, daemon=True).start()


def transcribe_bytes(bio):
    """Transcreve um buffer WAV (BytesIO). Retorna (texto, erro)."""
    err = None
    for attempt in range(API_RETRIES):
        try:
            bio.seek(0)
            r = client.audio.transcriptions.create(
                model=MODEL, file=("audio.wav", bio, "audio/wav"), language=LANGUAGE
            )
            return (r.text or "").strip(), None
        except Exception as e:
            err = str(e)[:90]
            log(f"api tentativa {attempt + 1} falhou: {err}")
            time.sleep(0.5)
    return "", err


def worker():
    try:
        if not _frames:
            bridge.done.emit(-1.0)
            return
        audio = np.concatenate(_frames, axis=0)
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
        t0 = time.time()
        bio = io.BytesIO()
        sf.write(bio, audio, SR, format="wav")
        text, err = transcribe_bytes(bio)
        elapsed = time.time() - t0

        if err or not text:
            bridge.done.emit(-1.0)
            if err:
                log("Falhou na API (audio guardado em pendentes/ pra retry no boot).")
            else:
                log("Transcricao vazia.")
                # vazio nao e queda — descarta o pendente pra nao re-tentar a toa
                _safe_remove(wav_path)
            beep(220, 280)
            return

        bridge.done.emit(elapsed)
        save_history(text)
        log(f"({elapsed:.1f}s) -> {text}")
        _safe_remove(wav_path)   # transcreveu com sucesso: remove o pendente
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
                save_history(text)
                log(f"recuperado [{name}] -> {text}")
                _safe_remove(fp)
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


def on_press(key):
    if key == HOTKEY and not _recording:
        bridge.start.emit()


def on_release(key):
    if key == HOTKEY and _recording:
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

    # pre-aquece audio (PortAudio) e COM do mute (pycaw) pro 1o F9 ser instantaneo
    try:
        _get_volume()
    except Exception as e:
        log(f"warmup vol: {e}")
    try:
        sd.query_devices()   # inicializa o PortAudio (parte fria) sem ocupar o microfone
    except Exception as e:
        log(f"warmup audio: {e}")

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    # recupera audios que ficaram pendentes de uma queda anterior (em background)
    threading.Thread(target=recover_pending, daemon=True).start()

    log(f"whisper-voice pronto. Segura {HOTKEY_LABEL}, fala, solta.")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
