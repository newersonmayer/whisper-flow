@echo off
REM Remove a inicializacao automatica (a pasta e o .env continuam onde estao).
powershell -NoProfile -Command "try { Stop-ScheduledTask -TaskName 'Ditador de Voz' -ErrorAction SilentlyContinue } catch {}; try { Unregister-ScheduledTask -TaskName 'Ditador de Voz' -Confirm:$false -ErrorAction Stop } catch {}"
echo Inicializacao automatica removida.
pause
