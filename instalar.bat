@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   Instalando o Ditador de Voz (F9)
echo ============================================
echo.

REM --- 1. Localiza o Python ---
set "PY="
py -3.11 --version >nul 2>&1 && set "PY=py -3.11"
if not defined PY ( py --version >nul 2>&1 && set "PY=py" )
if not defined PY ( python --version >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo [ERRO] Python nao encontrado. Instale o Python 3.11:
  echo    No Prompt de Comando rode:  winget install Python.Python.3.11
  echo    Depois feche e abra esta janela e rode instalar.bat de novo.
  echo.
  pause & exit /b 1
)
echo Python encontrado: %PY%

REM --- 2. Cria o .env a partir do exemplo (se ainda nao existir) ---
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo [ATENCAO] Criei o arquivo .env. Abra ele com o Bloco de Notas e
  echo           cole a chave da API da OpenAI ^(peca ao Sr. Mayer^).
  echo           Sem a chave o programa nao transcreve.
  echo.
)

REM --- 3. Ambiente virtual + dependencias ---
echo Criando ambiente e instalando dependencias (pode demorar alguns minutos)...
%PY% -m venv venv
if errorlevel 1 ( echo [ERRO] Falha ao criar o ambiente. & pause & exit /b 1 )
"venv\Scripts\python.exe" -m pip install --upgrade pip
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo [ERRO] Falha ao instalar dependencias. & pause & exit /b 1 )

REM --- 4. Tarefa agendada: sobe no login e reinicia sozinho se cair ---
echo Configurando inicializacao automatica...
echo (vai aparecer um pedido de permissao do Windows - clique SIM)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0registrar-tarefa.ps1"

echo.
echo ============================================
echo   Pronto! Segure F9, fale e solte.
echo   O microfone aparece na bandeja (perto do relogio).
echo   Sobe sozinho toda vez que ligar o PC.
echo.
echo   Se ainda nao colou a chave no .env: cole agora
echo   e rode parar.bat e depois instalar.bat de novo.
echo ============================================
echo.
pause
endlocal
