#!/bin/bash
# instalar-macos.sh — equivalente do instalar.bat para macOS.
#
# Cria o venv, instala as dependencias e registra um LaunchAgent que sobe o
# supervisor no login e o mantem vivo (KeepAlive), que e o papel que a Tarefa
# Agendada "Ditador de Voz" cumpre no Windows.
#
# Uso:   ./instalar-macos.sh
# Remover: ./instalar-macos.sh --remover

set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.newersonmayer.whispervoice"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$BASE/venv/bin/python"

# ---------------------------------------------------------------- remover ---
if [[ "${1:-}" == "--remover" ]]; then
  echo "Removendo o LaunchAgent..."
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  pkill -f "$BASE/dictate.py" 2>/dev/null || true
  pkill -f "$BASE/supervisor.py" 2>/dev/null || true
  echo "Pronto. O venv e os seus arquivos (.env, vocabulario.txt, correcoes.txt,"
  echo "preferencias.txt, transcricoes/) NAO foram tocados."
  exit 0
fi

echo "==> whisper-voice — instalacao no macOS"
echo "    pasta: $BASE"
echo

# ------------------------------------------------------------- pre-checks ---
if [[ "$(uname)" != "Darwin" ]]; then
  echo "ERRO: este script e so pra macOS. No Windows use o instalar.bat."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERRO: python3 nao encontrado."
  echo "Instale com:  brew install python@3.11"
  exit 1
fi

PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "==> python3 $PYVER encontrado"

# PyQt5 nao tem wheel pra toda combinacao de Python/arquitetura. Em Apple
# Silicon com Python muito novo o pip tenta compilar do fonte e falha feio;
# avisar antes e melhor do que 200 linhas de erro de compilador.
case "$PYVER" in
  3.9|3.10|3.11|3.12) ;;
  *) echo "    AVISO: PyQt5 costuma ter wheel pronta ate o 3.12."
     echo "    Se a instalacao falhar compilando, use: brew install python@3.11"
     ;;
esac

# --------------------------------------------------------------- ambiente ---
if [[ ! -d "$BASE/venv" ]]; then
  echo "==> criando o venv"
  python3 -m venv "$BASE/venv"
else
  echo "==> venv ja existe, reaproveitando"
fi

echo "==> instalando dependencias (pycaw/comtypes sao puladas: sao do Windows)"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r "$BASE/requirements.txt"

# ------------------------------------------------------------------- .env ---
if [[ ! -f "$BASE/.env" ]]; then
  echo "==> criando .env a partir do exemplo"
  cp "$BASE/.env.example" "$BASE/.env"
  echo
  echo "    !! FALTA A CHAVE: abra o .env e preencha OPENAI_API_KEY."
  echo "    !! Salve como UTF-8 SEM BOM (o BOM quebra a leitura da 1a linha)."
  echo
else
  echo "==> .env ja existe, mantido"
fi

# ------------------------------------------------------------ LaunchAgent ---
echo "==> registrando o LaunchAgent ($LABEL)"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$BASE/supervisor.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$BASE</string>
    <!-- sobe no login -->
    <key>RunAtLoad</key>
    <true/>
    <!-- e volta sozinho se cair: mesmo papel do watchdog da Tarefa Agendada -->
    <key>KeepAlive</key>
    <true/>
    <!-- nao insiste mais que 1x a cada 10s se estiver em crash-loop -->
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>$BASE/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>$BASE/launchd.err.log</string>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
PLISTEOF

chmod 644 "$PLIST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>/dev/null || true

echo
echo "==================================================================="
echo " Instalado. FALTA UM PASSO MANUAL — sem ele a tecla nao funciona:"
echo "==================================================================="
echo
echo " 1) Ajustes do Sistema > Privacidade e Seguranca > ACESSIBILIDADE"
echo "    Adicione e MARQUE o Terminal (ou o app que roda isto)."
echo "    Sem essa permissao o pynput sobe normal e simplesmente nunca"
echo "    recebe tecla — parece bug, mas e permissao."
echo
echo " 2) Ajustes do Sistema > Privacidade e Seguranca > MICROFONE"
echo "    Idem, para gravar."
echo
echo " Depois, confira o boot:"
echo "    tail -5 \"$BASE/dictate.log\""
echo " Tem que aparecer:  whisper-voice pronto (macOS)"
echo
echo " A hotkey padrao (alt_gr/ctrl_r) vira Option direito ou Control direito."
echo " Troque em HOTKEY= no .env se preferir outra."
echo
