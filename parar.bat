@echo off
REM Para o Ditador de Voz e o app Transcricoes agora (e impede o reinicio
REM automatico ate o proximo login).
REM Uso normal do dia a dia: clicar no microfone na bandeja > Sair.
powershell -NoProfile -Command "try { Stop-ScheduledTask -TaskName 'Ditador de Voz' -ErrorAction Stop } catch {}; Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | Where-Object { $_.CommandLine -like '*dictate.py*' -or $_.CommandLine -like '*supervisor.py*' -or $_.CommandLine -like '*historico.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Ditador de Voz parado.
