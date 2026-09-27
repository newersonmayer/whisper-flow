# whisper-voice — ditador de voz do Newerson

Ferramenta pessoal do Newerson Mayer: segura a hotkey, fala, solta → transcreve via OpenAI e cola o texto onde o cursor estiver.

- **Repo público:** `github.com/newersonmayer/whisper-flow` (branch `main`, remote `origin`)
- **Local:** `D:\28. Amanda Biuger\TECNOLOGIA\whisper-voice`
- **Execução:** Tarefa Agendada do Windows **"Ditador de Voz"** — sobe no login e reinicia sozinha se cair. O processo é um `pythonw.exe` rodando `dictate.py`.

## `.env` — cuidado dobrado

O `.env` (chave OpenAI + `WHISPER_MODEL` + `HOTKEY`) é **gitignored**.

- ⚠️ **Nunca commitar nem versionar.**
- ⚠️ **Gravar sempre em UTF-8 SEM BOM.** O BOM quebra o parse do `python-dotenv` na 1ª linha. **Não usar `Set-Content -Encoding utf8` do PowerShell 5.1** — ele escreve com BOM.

## Hotkey

O parser do `dictate.py` aceita:
- `+` = **E** (combo simultâneo) — ex. `ctrl_l+win`
- `/` = **OU** (alternativas) — ex. `alt_gr/ctrl_r`

Cada token casa com um conjunto de teclas: `ctrl` = qualquer Ctrl; lado específico (`ctrl_r`/`ctrl_l`) casa só aquele lado.

**Config atual:** `alt_gr/ctrl_r` → Alt Gr (notebook) **ou** Ctrl direito (teclado externo). Ctrl esquerdo não dispara, preservando Ctrl+C e afins.

## Runbook — "atualiza o whisper" / "atualiza o ditador de voz"

Quando o Newerson pedir isso, executar nesta ordem:

1. `cd "D:\28. Amanda Biuger\TECNOLOGIA\whisper-voice"` e `git fetch origin` — comparar `main` com `origin/main`. **Se já estiver atualizado, dizer e parar.**
2. `git pull` (working tree deve estar limpo; o `.env` não é tocado por ser gitignored).
3. Se `requirements.txt` mudou no pull: `venv\Scripts\python.exe -m pip install -r requirements.txt`.
4. Reiniciar pra carregar o código novo: matar o `pythonw.exe` cujo command line contém `dictate.py`. A Tarefa Agendada religa em até 1 min, ou forçar com `Restart-ScheduledTask -TaskName "Ditador de Voz"` (precisa admin/UAC).
5. Confirmar no fim do `dictate.log` a linha **"whisper-voice pronto"**.

Nunca sobrescrever nem versionar o `.env` em nenhum desses passos.
