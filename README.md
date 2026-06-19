# Ditador de Voz (F9)

Segure **F9**, fale, solte — o que você falou vira texto e é colado sozinho onde o
cursor estiver (WhatsApp, e-mail, navegador, qualquer campo). Uma ondinha discreta
aparece embaixo no centro da tela enquanto grava — e confirma com um **"✓ colado"**
quando termina. O programa fica na bandeja do Windows (ícone de microfone) e sobe
sozinho toda vez que o PC liga.

Acompanha o app **Transcrições** (atalho no Menu Iniciar e no Desktop), com três abas:
- **Gravar** — gravação livre por clique (pra ditar enquanto mexe na tela);
- **Histórico** — tudo que foi transcrito, por dia, com busca e **Copiar**;
- **Vocabulário** — termos que a transcrição costuma errar (nomes, siglas, jargão).
  Salvou, valeu na próxima gravação — sem reiniciar nada.

A transcrição usa a API de áudio da OpenAI (`gpt-4o-mini-transcribe` por padrão).

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

**Opção A — `git clone` (recomendada se você usa Claude Code):** permite atualizar
depois com um comando. No Prompt, dentro de uma pasta fixa:

```
git clone https://github.com/newersonmayer/whisper-flow.git
```

(se não tiver git: rode `winget install Git.Git`, feche e abra o Prompt)

**Opção B — Download ZIP (mais simples):** no GitHub, **Code → Download ZIP**,
descompacte numa pasta fixa. As atualizações depois serão manuais.

Não rode de dentro do .zip.

### 3. Rode o instalador

Dê **dois cliques em `instalar.bat`**. Ele:
- cria o ambiente e instala tudo,
- cria o arquivo `.env` (onde vai a chave),
- configura pra abrir no boot e se reiniciar sozinho se cair.

> No fim vai aparecer um **pedido de permissão do Windows (UAC)** — clique **Sim**.
> É só pra registrar a inicialização automática.

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
- **Ver/ouvir o que já foi transcrito:** abra **Transcricoes** pelo Menu Iniciar
  (ou pelo atalho no Desktop). O app fica **residente** (sobe escondido no login):
  abrir é instantâneo, e **fechar a janela só esconde** — pra encerrar de verdade,
  rode `parar.bat`.

## Palavras saindo erradas? Ensine o vocabulário

Se a transcrição troca termos seus (ex: "CLAUDE.md" virando "cloud.md"), abra o
app **Transcrições → aba Vocabulário**, liste os nomes/siglas/jargões do seu dia a
dia e clique **Salvar**. Esse texto vira contexto pra API em toda gravação — a
próxima já sai certa, sem reinstalar nem reiniciar nada.

## Como fechar

- Clique no ícone do microfone na bandeja → **Sair**.
- Ou rode **`parar.bat`**.

## Tirar a inicialização automática

- Rode **`desinstalar.bat`** (a pasta e o `.env` continuam onde estão).

## Trocar a tecla de atalho

Por padrão é **F9**. Pra mudar, abra o arquivo `.env`, edite a linha `HOTKEY=` com a
tecla desejada (ex: `HOTKEY=f8`) e salve. Depois rode `parar.bat` e `instalar.bat`
de novo (ou reinicie o PC). Use **teclas de função (f1..f12)** — letras atrapalham a
digitação normal.

## O que é seu e nenhuma atualização toca

Estes arquivos são **locais** (ignorados pelo git) e guardam as suas preferências.
Atualizar a ferramenta nunca mexe neles — e quem for atualizar (você ou o Claude
Code) **não deve** sobrescrevê-los, versioná-los nem recriá-los:

| Arquivo | O que guarda |
|---|---|
| `.env` | Chave da API, **tecla de atalho** (`HOTKEY`) e modelo (`WHISPER_MODEL`) |
| `vocabulario.txt` | Seu vocabulário pessoal (editável pela tela Vocabulário do app) |
| `transcricoes/` e `audios/` | Seu histórico de transcrições e os áudios |
| `*.log` | Logs de execução |

## Como atualizar

Se você **clonou com git** (recomendado), o passo a passo completo — escrito pra
servir tanto pra um humano quanto pra um Claude Code executar de ponta a ponta:

1. Na pasta da ferramenta, rode `git fetch` e compare `main` com `origin/main`.
   Se já estiverem iguais, não há atualização — pare aqui e avise.
2. Rode `git pull`. As preferências da tabela acima são gitignored e ficam
   intactas. (Se houver modificação local em arquivo *versionado*, resolva antes
   — não descarte trabalho local sem avisar.)
3. **Se `requirements.txt` mudou no pull:** rode
   `venv\Scripts\python.exe -m pip install -r requirements.txt`.
4. **Se `instalar.bat` ou `registrar-tarefa.ps1` mudaram no pull:** rode
   `instalar.bat` de novo — ele recria a tarefa agendada e os atalhos sem tocar
   no `.env` nem no `vocabulario.txt` (vai pedir permissão de administrador/UAC).
5. Reinicie os dois programas pra carregar o código novo:
   - **Ditador:** encerre os processos `pythonw.exe` cujo command line contém
     `dictate.py` — o supervisor religa sozinho em ~2 segundos.
   - **App Transcricoes:** encerre os processos `pythonw.exe` cujo command line
     contém `historico.py` e relance em segundo plano:
     `venv\Scripts\pythonw.exe historico.py --hidden`
   - Obs.: cada programa aparece como **dois** processos (o launcher do venv e o
     Python real, com o mesmo command line) — encerre todos que casarem no filtro.
6. Confirme a linha `whisper-voice pronto` no fim do `dictate.log`.

Se você **baixou o ZIP**: baixe o ZIP novo, substitua os arquivos na pasta
**mantendo os da tabela acima**, e rode `instalar.bat` de novo.

## Para quem usa Claude Code (instalar e atualizar por chat)

Instale via `git clone` (necessário pro auto-update). O `instalar.bat` gera o
arquivo **`INSTRUCAO-CLAUDE-CODE.md`** com o caminho da instalação já preenchido
e o passo a passo de atualização acima embutido.

No Claude Code, diga **uma vez**:

> "Leia o arquivo `INSTRUCAO-CLAUDE-CODE.md` em `<pasta onde você clonou>` e
> adicione essa instrução ao meu `CLAUDE.md`."

O próprio Claude escreve a instrução no seu `CLAUDE.md` — você não edita nada na
mão. A partir daí, basta dizer algo como **"atualiza a ferramenta whisper voice"**
no chat que ele sozinho: confere se há novidade no repositório, roda o `git pull`,
reinstala dependências se mudaram, recria atalhos se o instalador mudou, reinicia
os dois programas e confirma no log — **preservando sua tecla de atalho, sua chave
e seu vocabulário**.

---

## Detalhes técnicos

- **Stack:** Python 3.11 + PyQt5 (overlay/bandeja) + QFluentWidgets (UI do app
  Transcrições, tema dark), `sounddevice` (captura), `openai` (transcrição),
  `pynput` (hotkey global F9).
- **Inicialização:** Tarefa Agendada do Windows (`registrar-tarefa.ps1`), com
  gatilho *no login* e *reinício automático* se o processo cair — monitorado pelo
  próprio Windows, sem polling. Instância única garantida por um lock na porta
  `127.0.0.1:49732`.
- **Resiliência:** cada áudio é salvo em `pendentes/` **antes** de ir pra API.
  Se o processo cair no meio de uma transcrição, o áudio é re-transcrito no próximo
  boot e salvo no histórico (não é colado, porque o cursor já estará em outro lugar).
  Erros inesperados são gravados com traceback no `dictate.log`.
- **Latência:** a primeira chamada de API após boot/idle era 12–15s (conexão fria)
  contra 1–3s quente. O programa pré-aquece a conexão no boot, a cada 4 min e no
  momento em que você **começa** a gravar (esquenta enquanto fala). Linhas `[t]` no
  `dictate.log` medem tecla→overlay, encode e tempo de API.
- **Histórico:** toda transcrição vai pra `transcricoes/AAAA-MM-DD.md` (texto, pra
  sempre). O áudio original fica guardado em `audios/AAAA-MM-DD/HHMMSS.wav` por
  **7 dias** (rolling), como backup pra conferência manual.
- **Vocabulário:** `vocabulario.txt` (criado a partir do `vocabulario.example.txt`)
  é enviado como `prompt` da API em toda transcrição — nos modelos `gpt-4o-*-transcribe`
  ele vale inteiro como contexto; no `whisper-1` só os últimos 224 tokens contam.
  Lido a cada gravação: editar/salvar já vale na próxima.
- **Modelo:** configurável pelo `.env` (`WHISPER_MODEL`). Vem com
  `gpt-4o-mini-transcribe` (mais preciso que o whisper-1). Se a chave não tiver
  acesso a ele (erro 403), troque por `whisper-1` no `.env`.

## Arquivos

| Arquivo | Função |
|---|---|
| `dictate.py` | O programa principal (hotkey, gravação, transcrição, colagem) |
| `historico.py` | App Transcrições (gravação livre, histórico com áudio, vocabulário) |
| `supervisor.py` | Relança o `dictate.py` se ele cair (a Tarefa Agendada roda ele) |
| `instalar.bat` | Instala tudo e configura a inicialização |
| `registrar-tarefa.ps1` | Cria a Tarefa Agendada e os atalhos (chamado pelo instalador) |
| `parar.bat` | Para o programa |
| `desinstalar.bat` | Remove a inicialização automática |
| `.env.example` | Modelo do arquivo de configuração |
| `vocabulario.example.txt` | Modelo do vocabulário (vira o seu `vocabulario.txt`) |

## Solução de problemas

- **Apertei F9 e não colou nada:** verifique se a chave está correta no `.env` e se
  há internet. Veja o fim do `dictate.log` pra mensagem de erro.
- **App Transcricoes demorou a abrir:** a primeira abertura depois do boot paga o
  custo de disco/antivírus (até ~30s). Depois disso ele fica residente e as próximas
  são instantâneas. No login ele já sobe sozinho em segundo plano.
- **"Python não encontrado":** instale o Python 3.11 (passo 1) e abra o Prompt de novo.
- **Quero ver o que foi transcrito:** abra o `historico.py` (dois cliques, se o Python
  estiver associado) ou os arquivos em `transcricoes/`.
