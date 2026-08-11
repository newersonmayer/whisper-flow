"""
setmute.py — muta/desmuta a saida de audio padrao do sistema.

Rodado SEMPRE como subprocesso isolado pelo dictate.py (nunca importado), de
proposito: no Windows o caminho COM (IAudioEndpointVolume) ja causou crashes
nativos recorrentes (_ctypes.pyd / 0xC0000005) quando rodava dentro do processo
principal. Isolando num subprocesso, um eventual crash morre aqui e NAO derruba
o ditador. E, ao contrario da tecla de midia (Key.media_volume_mute), o SetMute
da API NAO dispara o OSD/notificacao de volume do Windows — que era o que
atrapalhava enxergar o overlay do whisper ao acionar a hotkey.

Uso:
  python setmute.py mute     -> imprime o estado ANTERIOR (0/1) e seta mute
  python setmute.py unmute   -> tira o mute

Saida (stdout) no 'mute': "1" se a saida JA estava mutada antes (pelo usuario),
"0" se estava com som. O dictate.py usa isso pra so desmutar no fim se fomos nos
que mutamos — preservando um mute manual pre-existente.

Windows: pycaw/COM.  macOS: osascript (AppleScript), que e a interface
suportada pra volume do sistema e nao exige dependencia nova nem permissao
extra. O contrato de stdout e IDENTICO nos dois, entao o dictate.py nao sabe
em qual sistema esta.
"""
import sys
import subprocess


def _mac_esta_mutado():
    """'true'/'false' -> '1'/'0'. Em qualquer falha assume '0' (nao mutado):
    errar pra esse lado so faz desmutar algo que ja estava sem som, enquanto o
    contrario deixaria o Mac mudo pra sempre."""
    try:
        r = subprocess.run(
            ["osascript", "-e", "output muted of (get volume settings)"],
            capture_output=True, text=True, timeout=5)
        return "1" if r.stdout.strip().lower() == "true" else "0"
    except Exception:
        return "0"


def _mac_set(mutado):
    subprocess.run(
        ["osascript", "-e",
         "set volume output muted %s" % ("true" if mutado else "false")],
        capture_output=True, timeout=5)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "mute"

    if sys.platform == "darwin":
        if action == "mute":
            print(_mac_esta_mutado(), flush=True)   # estado ANTES de mutar
            _mac_set(True)
        elif action == "unmute":
            _mac_set(False)
        return

    from pycaw.pycaw import AudioUtilities
    vol = AudioUtilities.GetSpeakers().EndpointVolume
    if action == "mute":
        print(vol.GetMute(), flush=True)   # estado anterior, antes de mutar
        vol.SetMute(1, None)
    elif action == "unmute":
        vol.SetMute(0, None)


if __name__ == "__main__":
    main()
