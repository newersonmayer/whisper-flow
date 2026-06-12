# Registra o Ditador de Voz como Tarefa Agendada do Windows:
# - sobe sozinho no login (roda o supervisor.py, que por sua vez roda o dictate.py)
# - o supervisor relanca o dictate em ~2s se ele cair (inclusive crash nativo, que
#   o "restart on failure" do Agendador nao pegava de forma confiavel)
# Criar tarefa exige admin: se nao estiver elevado, pede UAC automaticamente.
$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Pedindo permissao de administrador (aceite o UAC)..."
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$PSCommandPath`""
    exit
}

$dir      = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw      = Join-Path $dir "venv\Scripts\pythonw.exe"
$script   = Join-Path $dir "supervisor.py"   # o supervisor cuida de subir/relancar o dictate.py
$taskName = "Ditador de Voz"

if (-not (Test-Path $pyw)) {
    Write-Host "[ERRO] venv nao encontrado. Rode instalar.bat primeiro."
    Start-Sleep -Seconds 3
    exit 1
}

$action = New-ScheduledTaskAction -Execute $pyw -Argument ('"{0}"' -f $script) -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description "Ditador de voz (F9). Sobe no login e reinicia sozinho se cair." -Force | Out-Null

# remove o atalho antigo da pasta Inicializar (versao anterior), se existir
$old = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Ditador de Voz.lnk"
if (Test-Path $old) { Remove-Item $old -Force }

# encerra qualquer instancia manual (supervisor e dictate) e deixa a tarefa subir a versao gerenciada
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*dictate.py*' -or $_.CommandLine -like '*supervisor.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName $taskName

# atalho "Transcricoes" no Menu Iniciar e no Desktop (historico + gravacao livre + vocabulario)
$hist = Join-Path $dir "historico.py"
$ico  = Join-Path $dir "assets\mic.ico"
$ws   = New-Object -ComObject WScript.Shell
foreach ($lnkDir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
    $lnk = $ws.CreateShortcut((Join-Path $lnkDir "Transcricoes.lnk"))
    $lnk.TargetPath       = $pyw
    $lnk.Arguments        = ('"{0}"' -f $hist)
    $lnk.WorkingDirectory = $dir
    $lnk.IconLocation     = $ico
    $lnk.Description      = "Transcricoes do ditador de voz (historico, gravacao livre e vocabulario)"
    $lnk.Save()
}

# o app sobe residente (escondido) no login: abrir frio levava ~25-30s entre
# antivirus e disco; residente, "abrir" e so mostrar a janela (instantaneo)
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) "Transcricoes (segundo plano).lnk"
$lnk = $ws.CreateShortcut($startup)
$lnk.TargetPath       = $pyw
$lnk.Arguments        = ('"{0}" --hidden' -f $hist)
$lnk.WorkingDirectory = $dir
$lnk.IconLocation     = $ico
$lnk.Description      = "Mantem o app Transcricoes residente pra abrir na hora"
$lnk.Save()

# gera o trecho pronto pra colar no CLAUDE.md de quem usa Claude Code (com o caminho real)
$tpl = @'
## Ditador de voz (whisper-voice) - auto-update

Esta ferramenta esta instalada em: `__DIR__`
Repo: https://github.com/newersonmayer/whisper-flow (branch main, remote origin)
Ela tem DOIS programas: o ditador (dictate.py, atalho de teclado global) e o app
Transcricoes (historico.py, residente em segundo plano).

Quando o usuario pedir pra atualizar essa ferramenta ("atualize o whisper",
"atualiza a ferramenta de voz", "veja a ferramenta whisper voice e atualize"):
1. Navegue ate a pasta `__DIR__`.
2. Rode `git fetch` e compare `main` com `origin/main`. Se ja estiver atualizado, avise e pare.
3. Rode `git pull`.
4. Se `requirements.txt` mudou no pull: `venv\Scripts\python.exe -m pip install -r requirements.txt`.
5. Se `instalar.bat` ou `registrar-tarefa.ps1` mudaram no pull: rode `instalar.bat`
   de novo (recria tarefa agendada e atalhos; pede UAC - avise o usuario antes).
6. Reinicie os dois programas:
   - encerre os `pythonw.exe` cujo command line contem `dictate.py` (o supervisor religa em ~2s);
   - encerre os `pythonw.exe` cujo command line contem `historico.py` e relance:
     `venv\Scripts\pythonw.exe historico.py --hidden`
   - cada programa aparece como DOIS processos (launcher do venv + Python real) - encerre todos do filtro.
7. Confirme a linha "whisper-voice pronto" no fim de `dictate.log`.

PRESERVAR SEMPRE (gitignored - nunca editar, versionar, sobrescrever ou recriar):
`.env` (chave da API + HOTKEY com a tecla preferida do usuario + modelo),
`vocabulario.txt` (vocabulario pessoal), `transcricoes/`, `audios/`, `*.log`.
'@
$snippet = $tpl.Replace('__DIR__', $dir)
Set-Content -Path (Join-Path $dir "INSTRUCAO-CLAUDE-CODE.md") -Value $snippet -Encoding UTF8

Write-Host "Tarefa '$taskName' registrada e iniciada. Pode fechar esta janela."
Start-Sleep -Seconds 3
