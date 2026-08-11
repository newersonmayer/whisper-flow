"""
plataforma.py — tudo que difere entre Windows e macOS mora AQUI.

Por que um arquivo so, em vez de `if sys.platform` espalhado: o dictate.py tem
1.700 linhas e a logica de gravacao/hotkey/UI e identica nos dois sistemas. O
que muda sao 6 pontos concretos (bipe, mute, tecla de colar, foco da janela,
interpretador do venv, som de erro). Espalhar o branch por esses 6 pontos faz
cada bug virar "sera que e do SO?"; concentrar aqui deixa o resto do codigo
cego pro sistema operacional.

Regra: NENHUM outro arquivo importa `winsound`, `pycaw`, `ctypes.windll` ou
chama `osascript` direto. Se precisar de algo novo do SO, entra aqui.

⚠️ Nao testado em macOS por quem escreveu (sem Mac a mao). Cada funcao abaixo
tem um comentario dizendo o que precisa ser conferido na primeira execucao —
ver tambem a secao "macOS" no CLAUDE.md.
"""
import os
import sys
import subprocess

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WIN and not IS_MAC

BASE = os.path.dirname(os.path.abspath(__file__))

# Interpretador do venv. No Windows existe o pythonw.exe (roda sem abrir
# console); no macOS nao existe equivalente — o LaunchAgent ja roda sem
# terminal, entao `python` basta.
if IS_WIN:
    VENV_PY = os.path.join(BASE, "venv", "Scripts", "pythonw.exe")
    VENV_PY_CONSOLE = os.path.join(BASE, "venv", "Scripts", "python.exe")
else:
    VENV_PY = os.path.join(BASE, "venv", "bin", "python")
    VENV_PY_CONSOLE = VENV_PY

# Flag pra subprocesso nao piscar console. So existe no Windows; o getattr
# devolve 0 nos outros, que e o valor neutro.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def python_do_venv(console=False):
    """Caminho do interpretador do venv, com fallback pro atual se o venv sumir."""
    alvo = VENV_PY_CONSOLE if console else VENV_PY
    return alvo if os.path.exists(alvo) else sys.executable


# --------------------------------------------------------------------------
# Bipe de inicio/fim/erro da gravacao
# --------------------------------------------------------------------------
# No Windows: winsound.Beep, que aceita frequencia e duracao.
# No macOS: nao ha equivalente. Em vez de sintetizar um tom (que exigiria abrir
# um stream de SAIDA enquanto o de ENTRADA esta gravando — risco de conflito de
# device pra ganho nenhum), usa os sons nativos do sistema via afplay. Sao os
# mesmos que o usuario ja reconhece de outros apps.
_SONS_MAC = {
    "inicio": "/System/Library/Sounds/Tink.aiff",
    "fim": "/System/Library/Sounds/Pop.aiff",
    "erro": "/System/Library/Sounds/Basso.aiff",
}

if IS_WIN:
    import winsound


def beep(freq, ms=110):
    """Bipe curto. `freq` so e usada no Windows; no macOS ela escolhe QUAL som
    nativo tocar (o mapeamento abaixo espelha o uso no dictate.py: 880 = comecou
    a gravar, 440 = parou, 220 = deu erro)."""
    try:
        if IS_WIN:
            winsound.Beep(int(freq), int(ms))
            return
        if IS_MAC:
            nome = "inicio" if freq >= 700 else ("fim" if freq >= 300 else "erro")
            caminho = _SONS_MAC[nome]
            if os.path.exists(caminho):
                subprocess.Popen(
                    ["afplay", caminho],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass   # bipe nunca pode derrubar o ditado


# --------------------------------------------------------------------------
# Tecla de colar
# --------------------------------------------------------------------------
def modificador_de_colar(keyboard):
    """A tecla que, junto com V, cola: Ctrl no Windows, Command no macOS.
    Recebe o modulo `pynput.keyboard` pra nao criar import circular."""
    return keyboard.Key.cmd if IS_MAC else keyboard.Key.ctrl


# --------------------------------------------------------------------------
# Janela em foco (alvo do auto-paste do modo maos-livres)
# --------------------------------------------------------------------------
def janela_em_foco():
    """Handle da janela ativa, pra reforcar o foco antes de colar.

    No Windows: HWND via user32.
    No macOS: devolve None de proposito. A pill sobe com WA_ShowWithoutActivating
    + WindowDoesNotAcceptFocus, entao o app de destino continua sendo o ativo e
    nao ha o que reforcar. Trazer outro app pra frente no macOS exigiria
    AppleScript com permissao de Automacao — uma permissao a mais pedida ao
    usuario pra resolver um problema que provavelmente nao existe la.

    ⚠️ A CONFERIR no Mac: se o auto-paste do maos-livres cair na janela errada,
    e aqui que entra o `osascript -e 'tell application "X" to activate'`.
    """
    if not IS_WIN:
        return None
    try:
        import ctypes
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return None


def focar_janela(handle):
    """Traz a janela de volta pro foco. No macOS e no-op (ver janela_em_foco)."""
    if not IS_WIN or not handle:
        return
    try:
        import ctypes
        ctypes.windll.user32.SetForegroundWindow(handle)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Diagnostico (usado pelo instalador e pelo log de boot)
# --------------------------------------------------------------------------
def nome_do_sistema():
    if IS_WIN:
        return "Windows"
    if IS_MAC:
        return "macOS"
    return sys.platform


def acessibilidade_ok():
    """No macOS o pynput so recebe teclas se o app tiver permissao de
    Acessibilidade. Sem ela o listener sobe LIMPO e simplesmente nunca dispara
    — o sintoma e "aperto a tecla e nao acontece nada", identico a um bug.
    Este check transforma isso numa linha de log explicita.

    Devolve (ok, mensagem). No Windows e sempre (True, "").
    """
    if not IS_MAC:
        return True, ""
    try:
        from pynput import keyboard
        confiavel = getattr(keyboard.Listener, "IS_TRUSTED", None)
        if confiavel is False:
            return False, (
                "macOS: sem permissao de Acessibilidade — a hotkey NAO vai "
                "funcionar. Ajustes do Sistema > Privacidade e Seguranca > "
                "Acessibilidade: adicione o Terminal (ou o app) e marque."
            )
        return True, ""
    except Exception as e:
        return True, f"nao consegui checar Acessibilidade: {str(e)[:60]}"
