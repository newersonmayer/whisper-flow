"""
setmute.py — muta/desmuta a saida de audio padrao via Core Audio (pycaw/COM).

Rodado SEMPRE como subprocesso isolado pelo dictate.py (nunca importado), de
proposito: o caminho COM (IAudioEndpointVolume) ja causou crashes nativos
recorrentes (_ctypes.pyd / 0xC0000005) quando rodava dentro do processo
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
"""
import sys

from pycaw.pycaw import AudioUtilities


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "mute"
    vol = AudioUtilities.GetSpeakers().EndpointVolume
    if action == "mute":
        print(vol.GetMute(), flush=True)   # estado anterior, antes de mutar
        vol.SetMute(1, None)
    elif action == "unmute":
        vol.SetMute(0, None)


if __name__ == "__main__":
    main()
