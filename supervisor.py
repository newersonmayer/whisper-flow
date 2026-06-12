"""
Supervisor do whisper-voice — garante que o ditador volte sozinho se cair.

Existe porque o dictate.py pode sofrer crash NATIVO (violacao de acesso em libs
C, ex: o antigo caminho COM do mute) que o try/except do Python nao captura, e o
"restart on failure" do Agendador de Tarefas do Windows se mostrou nao-confiavel
na pratica (ja deixou a ferramenta horas fora do ar). Aqui o relancamento e
garantido: roda o dictate.py, espera ele morrer, e sobe de novo.

A Tarefa Agendada "Ditador de Voz" deve apontar pra ESTE arquivo, nao pro
dictate.py. Roda com pythonw (sem console).
"""
import os
import sys
import time
import socket
import subprocess
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(BASE, "venv", "Scripts", "pythonw.exe")
SCRIPT = os.path.join(BASE, "dictate.py")
LOG = os.path.join(BASE, "supervisor.log")

MIN_UPTIME = 5                  # rodou menos que isso = falhou no boot
BACKOFF = [2, 5, 15, 30, 60]   # espera crescente entre quedas rapidas seguidas
GUARD_PORT = 49733             # instancia unica do supervisor (dictate usa 49732)


def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    # instancia unica: se ja existe um supervisor, sai
    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        guard.bind(("127.0.0.1", GUARD_PORT))
    except OSError:
        log("Ja existe um supervisor rodando. Saindo.")
        return

    if not os.path.exists(PYW):
        log(f"pythonw do venv nao encontrado em {PYW}. Abortando.")
        return

    log("supervisor iniciado.")
    fails = 0
    while True:
        t0 = time.time()
        try:
            proc = subprocess.Popen([PYW, SCRIPT], cwd=BASE)
        except Exception as e:
            log(f"falha ao lancar dictate: {e}")
            time.sleep(10)
            continue
        proc.wait()
        uptime = time.time() - t0
        rc = proc.returncode
        if uptime < MIN_UPTIME:
            fails = min(fails + 1, len(BACKOFF) - 1)
        else:
            fails = 0
        wait = BACKOFF[fails]
        log(f"dictate saiu (rc={rc}) apos {uptime:.0f}s; relancando em {wait}s.")
        time.sleep(wait)


if __name__ == "__main__":
    main()
