# Registra o Ditador de Voz como Tarefa Agendada do Windows:
# - sobe sozinho no login
# - reinicia sozinho se o processo cair (o Windows monitora; sem polling)
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
$script   = Join-Path $dir "dictate.py"
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

# encerra qualquer instancia manual e deixa a tarefa subir a versao gerenciada
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*dictate.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName $taskName

Write-Host "Tarefa '$taskName' registrada e iniciada. Pode fechar esta janela."
Start-Sleep -Seconds 3
