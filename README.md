# Ditador de Voz

Segure uma tecla, fale, solte — o que você falou vira texto e é colado sozinho
onde o cursor estiver (WhatsApp, e-mail, navegador, qualquer campo). Uma ondinha
discreta aparece embaixo no centro da tela enquanto grava — e confirma com um
**"✓ colado"** quando termina. O programa fica na bandeja e sobe sozinho toda vez
que o computador liga.

Roda em **Windows** e **macOS**.

Acompanha o app **Transcrições**, com cinco abas:
- **Gravar** — gravação livre por clique (pra ditar enquanto mexe na tela);
- **Histórico** — tudo que foi transcrito, por dia, com busca e **Copiar**;
- **Palavras** — correções de grafia e vocabulário (veja a diferença abaixo);
- **Formatação** — limpa vícios de fala e organiza o texto (opcional, desligado por padrão);
- **Ajustes** — clipboard e popup.

A transcrição usa a API de áudio da OpenAI (`gpt-transcribe` por padrão).

---

> ## 🤖 Se você é um agente (Claude Code) instalando isto pra alguém
>
> **Antes de qualquer coisa, descubra o sistema operacional.** Os dois caminhos
> são diferentes e o errado falha de forma confusa:
>
> - **macOS** → seção [Instalar no macOS](#instalar-no-macos). Use
>   `./instalar-macos.sh`. **Não** existe `instalar.bat` aqui.
> - **Windows** → seção [Instalação (passo a passo)](#instalação-passo-a-passo).
>   Use `instalar.bat`.
>
> **No macOS, dois passos são MANUAIS e você não consegue fazer por eles** —
> exigem clique nos Ajustes do Sistema. Termine a instalação dizendo isso com
> todas as letras:
> 1. **Privacidade e Segurança → Acessibilidade** (senão a hotkey nunca dispara,
>    e **não aparece erro nenhum** — o programa sobe normal e fica mudo);
> 2. **Privacidade e Segurança → Microfone**.
>
> **Nunca** peça a chave da OpenAI no chat nem a escreva você mesmo: instrua a
> pessoa a colar no `.env`, em **UTF-8 sem BOM** (o BOM corrompe a primeira
> linha e o programa não sobe).
>
> Confirme o sucesso lendo o fim do `dictate.log` — tem que aparecer
> `whisper-voice pronto (macOS)` ou `whisper-voice pronto (Windows)`.

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

## Palavras saindo erradas? Use a aba Palavras

Abra o app **Transcrições → aba Palavras**. Ela tem dois campos, e a diferença
entre eles importa:

| Campo | O que faz | Funciona sempre? |
|---|---|---|
| **Correções automáticas** | troca literal: `cloud.md => CLAUDE.md` | **Sim.** É uma substituição de texto, não depende do modelo |
| **Termos do vocabulário** | manda a lista como contexto pra API | Não. É uma dica — o modelo acerta às vezes |

Se um termo sai errado **toda vez**, ele tem que virar uma **correção**. Medimos
isso em 23,5 min de fala real: com o termo só no vocabulário, "CLAUDE.md" saiu
certo **0 vez em 8**; como correção, 8 de 8.

Selecione o termo no campo de baixo e clique em **"Promover termo a correção"**
para levá-lo pro campo de cima já no formato certo.

Salvou, vale no próximo ditado — sem reiniciar nada.

## Deixar o texto mais limpo (aba Formatação)

Liga um passe que tira vícios de fala ("né", "tá", "tipo"), pontua, quebra em
parágrafos e entende auto-correção falada — se você disse *"às 2… na verdade às
3"*, fica só "às 3".

Custa ~3 a 6 segundos a mais por ditado e roda **só acima do limiar de duração**
que você escolher (padrão: 30s), porque em ditado curto a espera não compensa.
Vem **desligado**.

Se a API falhar, você recebe o texto sem tratamento — o passe nunca custa um
ditado.

## Instalar no macOS

Funciona no macOS (Apple Silicon M1–M5 e Intel). O núcleo é o mesmo; o que muda
por sistema está isolado no `plataforma.py`.

```bash
git clone https://github.com/newersonmayer/whisper-flow.git
cd whisper-flow
chmod +x instalar-macos.sh
./instalar-macos.sh
```

O script cria o venv, instala as dependências (pulando as que são só do
Windows), gera o `.env` e registra um **LaunchAgent** que sobe no login e
religa sozinho se cair — o equivalente da Tarefa Agendada do Windows.

### ⚠️ Dois passos manuais, sem os quais não funciona

1. **Ajustes do Sistema → Privacidade e Segurança → Acessibilidade** — adicione
   e marque o Terminal (ou o app que roda isto).
   **Sem isso a hotkey simplesmente não dispara**, e não aparece erro nenhum:
   o programa sobe normal e nunca recebe tecla. Parece bug, é permissão. O
   `dictate.log` avisa quando detecta essa situação.
2. **Ajustes do Sistema → Privacidade e Segurança → Microfone** — idem, para gravar.

### Diferenças no Mac

| | Windows | macOS |
|---|---|---|
| Hotkey padrão `alt_gr/ctrl_r` | Alt Gr ou Ctrl direito | **Option direito** ou Control direito |
| Colar | Ctrl+V | **Cmd+V** (automático) |
| Mão-livres | Ctrl+Alt+Espaço | igual |
| Bipes | tons gerados | sons do sistema (Tink/Pop/Basso) |
| Sobe no login | Tarefa Agendada | LaunchAgent (`launchctl`) |

Para remover: `./instalar-macos.sh --remover` (não toca no seu `.env` nem nas
transcrições).

Conferir se subiu:

```bash
tail -5 dictate.log     # tem que aparecer: whisper-voice pronto (macOS)
```

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

Instale via `git clone` (necessário pro auto-update). Depois é só dizer no chat:

> "Instala essa ferramenta pra mim: https://github.com/newersonmayer/whisper-flow"

O agente lê este README, **detecta o seu sistema** e segue o caminho certo — o
bloco 🤖 no topo do arquivo existe pra isso. No fim, ele te diz quais permissões
você precisa conceder na mão (no macOS são duas, e sem elas nada funciona).

Os dois instaladores geram um **`INSTRUCAO-CLAUDE-CODE.md`** com o caminho da
instalação já preenchido e o passo a passo de atualização embutido. Para ativar
o auto-update, diga **uma vez**:

> "Leia o arquivo `INSTRUCAO-CLAUDE-CODE.md` em `<pasta onde você clonou>` e
> adicione essa instrução ao meu `CLAUDE.md`."

A partir daí, basta dizer **"atualiza a ferramenta whisper voice"** que ele
sozinho: confere se há novidade no repositório, roda o `git pull`, reinstala
dependências se mudaram, reinicia os dois programas e confirma no log —
**preservando sua tecla de atalho, sua chave, seu vocabulário e suas correções**.

### Reiniciar os programas (o agente precisa disso pra aplicar código novo)

**Windows** — encerre os processos `pythonw.exe` cujo command line contenha
`dictate.py` (o supervisor religa em ~2s) e `historico.py`, e relance o app com
`venv\Scripts\pythonw.exe historico.py --hidden`. Cada programa aparece como
**dois** processos (launcher do venv + Python real) — encerre todos que casarem.

**macOS** — o LaunchAgent religa sozinho:

```bash
launchctl kickstart -k "gui/$(id -u)/com.newersonmayer.whispervoice"
```

Em ambos, confirme no fim do `dictate.log` a linha `whisper-voice pronto`.

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
| `historico.py` | App Transcrições (gravar, histórico, palavras, formatação, ajustes) |
| **`plataforma.py`** | **Tudo que difere entre Windows e macOS.** Nenhum outro arquivo toca API de sistema direto — se precisar de algo do SO, entra aqui |
| `setmute.py` | Muta a saída de áudio durante a gravação (subprocesso isolado) |
| `supervisor.py` | Relança o `dictate.py` se ele cair |
| `instalar.bat` | **Windows** — instala tudo e configura a inicialização |
| `registrar-tarefa.ps1` | **Windows** — cria a Tarefa Agendada e os atalhos |
| `parar.bat` / `desinstalar.bat` | **Windows** — parar / remover a inicialização |
| **`instalar-macos.sh`** | **macOS** — venv, dependências, `.env` e LaunchAgent. `--remover` desfaz |
| `.gitattributes` | Fixa LF nos `.sh` — com CRLF o script não roda no Mac |
| `.env.example` | Modelo do arquivo de configuração |
| `vocabulario.example.txt` | Modelo do vocabulário — **substituído** pelo seu `vocabulario.txt` |
| `correcoes.example.txt` | Correções compartilhadas — **somadas** ao seu `correcoes.txt` |
| `preferencias.example.txt` | Modelo das preferências — **substituído** pelo seu `preferencias.txt` |

⚠️ Repare na diferença: as **correções somam** (você recebe as do repo *e* mantém
as suas), enquanto vocabulário e preferências **substituem** (o seu arquivo local
ganha do `.example`).

## Solução de problemas

- **Apertei F9 e não colou nada:** verifique se a chave está correta no `.env` e se
  há internet. Veja o fim do `dictate.log` pra mensagem de erro.
- **App Transcricoes demorou a abrir:** a primeira abertura depois do boot paga o
  custo de disco/antivírus (até ~30s). Depois disso ele fica residente e as próximas
  são instantâneas. No login ele já sobe sozinho em segundo plano.
- **"Python não encontrado":** instale o Python 3.11 (passo 1) e abra o Prompt de novo.
- **Quero ver o que foi transcrito:** abra o `historico.py` (dois cliques, se o Python
  estiver associado) ou os arquivos em `transcricoes/`.
