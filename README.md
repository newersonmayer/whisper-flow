# Ditador de Voz (F9)

Segure **F9**, fale, solte — o que você falou vira texto e é colado sozinho onde o
cursor estiver (WhatsApp, e-mail, navegador, qualquer campo). Uma ondinha discreta
aparece embaixo no centro da tela enquanto grava. O programa fica na bandeja do
Windows (ícone de microfone) e sobe sozinho toda vez que o PC liga.

A transcrição usa a API de áudio da OpenAI (modelo `whisper-1` por padrão).

---

## Instalação (passo a passo)

> Precisa ser feita só uma vez.

### 1. Instale o Python 3.11

Abra o **Prompt de Comando** e rode:

```
winget install Python.Python.3.11
```

Quando terminar, **feche e abra o Prompt de novo** (pra ele reconhecer o Python).

### 2. Baixe estes arquivos

No GitHub, clique no botão verde **Code** → **Download ZIP**. Descompacte numa
pasta fixa — por exemplo `C:\Ditador-de-Voz`. **Não rode de dentro do .zip.**

### 3. Rode o instalador

Dê **dois cliques em `instalar.bat`**. Ele:
- cria o ambiente e instala tudo,
- cria o arquivo `.env` (onde vai a chave),
- configura pra abrir no boot e se reiniciar sozinho se cair.

### 4. Cole a chave da API

Peça a chave ao **Sr. Mayer**. Abra o arquivo `.env` (com o Bloco de Notas),
substitua o texto depois de `OPENAI_API_KEY=` pela chave recebida e salve.

Depois rode **`parar.bat`** e em seguida **`instalar.bat`** de novo (pra ele subir
já com a chave). Pronto.

---

## Como usar

- **Segure F9, fale, solte.** O texto cola sozinho onde o cursor está.
- O programa fica na **bandeja** (ícone de microfone, perto do relógio).
- Abre sozinho toda vez que liga o PC.

## Como fechar

- Clique no ícone do microfone na bandeja → **Sair**.
- Ou rode **`parar.bat`**.

## Tirar a inicialização automática

- Rode **`desinstalar.bat`** (a pasta e o `.env` continuam onde estão).

---

## Detalhes técnicos

- **Stack:** Python 3.11 + PyQt5 (overlay/bandeja), `sounddevice` (captura),
  `openai` (transcrição), `pynput` (hotkey global F9).
- **Inicialização:** Tarefa Agendada do Windows (`registrar-tarefa.ps1`), com
  gatilho *no login* e *reinício automático* se o processo cair — monitorado pelo
  próprio Windows, sem polling. Instância única garantida por um lock na porta
  `127.0.0.1:49732`.
- **Resiliência:** cada áudio é salvo em `pendentes/` **antes** de ir pra API.
  Se o processo cair no meio de uma transcrição, o áudio é re-transcrito no próximo
  boot e salvo no histórico (não é colado, porque o cursor já estará em outro lugar).
  Erros inesperados são gravados com traceback no `dictate.log`.
- **Histórico:** toda transcrição vai pra `transcricoes/AAAA-MM-DD.md`. O visualizador
  é o `historico.py` (tema dark, busca e botão copiar).
- **Modelo:** configurável pelo `.env` (`WHISPER_MODEL`). Padrão `whisper-1`.
  `gpt-4o-mini-transcribe` / `gpt-4o-transcribe` são mais precisos, mas exigem
  liberar acesso ao modelo no projeto da OpenAI.

## Arquivos

| Arquivo | Função |
|---|---|
| `dictate.py` | O programa principal (hotkey, gravação, transcrição, colagem) |
| `historico.py` | Visualizador das transcrições salvas |
| `instalar.bat` | Instala tudo e configura a inicialização |
| `registrar-tarefa.ps1` | Cria a Tarefa Agendada (chamado pelo instalador) |
| `parar.bat` | Para o programa |
| `desinstalar.bat` | Remove a inicialização automática |
| `.env.example` | Modelo do arquivo de configuração |

## Solução de problemas

- **Apertei F9 e não colou nada:** verifique se a chave está correta no `.env` e se
  há internet. Veja o fim do `dictate.log` pra mensagem de erro.
- **"Python não encontrado":** instale o Python 3.11 (passo 1) e abra o Prompt de novo.
- **Quero ver o que foi transcrito:** abra o `historico.py` (dois cliques, se o Python
  estiver associado) ou os arquivos em `transcricoes/`.
