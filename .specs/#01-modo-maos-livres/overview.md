# #01 — Modo mãos-livres (toggle com janelinha + auto-paste)

**Autor:** Newerson · **Pra implementar:** Theo · **Data:** 2026-07-10
**Arquivo alterado:** `dictate.py` (só ele). `historico.py`, `supervisor.py`, `setmute.py` **não** mudam.

---

## 1. Contexto — por que essa feature existe

Hoje o whisper-voice tem **duas** formas de ditar:

1. **Hold-to-talk** (`dictate.py`) — segura a `HOTKEY` (`alt_gr/ctrl_r`), fala, solta. Transcreve e **cola no cursor** automaticamente. É o meu uso principal.
2. **Tela "Gravar" do app** (`RecordPanel`, `historico.py:312`) — abro o app, clico Gravar, falo à vontade (posso mexer na tela), clico Parar. Transcreve, **copia e salva no histórico, mas NÃO cola** (a janela do app tem foco).

Falta um **terceiro modo** que junta o melhor dos dois: acionar por **atalho global** (sem abrir o app, sem segurar tecla), com uma **janelinha flutuante já gravando**, e ao parar **colar no cursor** igual ao hold-to-talk e **fechar sozinha**. Serve pro ditado longo em que segurar a tecla cansa, sem precisar tirar o foco do documento indo abrir o app.

---

## 2. O que fica intacto (NÃO mexer)

- **Hold-to-talk** inteiro: `on_press`/`on_release` (`dictate.py:721`), `slot_start`/`slot_stop`, overlay pill (`Overlay`, `dictate.py:324`). A `HOTKEY` atual do `.env` não muda.
- **Pipeline de transcrição**: `worker` (`dictate.py:602`), `transcribe_bytes`, vocabulário (`read_vocab`), guard anti-eco (`_looks_like_vocab_echo`), retries, warmup, mute, histórico (`save_history`), acervo de áudio 7d (`archive_audio`/`prune_old_audios`), `recover_pending`. **O modo novo REUSA tudo isso.**
- **`paste()`** (`dictate.py:699`) — copia pro clipboard, Ctrl+V, restaura o clipboard anterior.
- **App `historico.py`** e a tela Gravar dele — intactos.

O delta é **aditivo**: um novo caminho de acionamento dentro do `dictate.py` que compartilha o motor de captura/transcrição/paste.

---

## 3. Comportamento end-to-end (o que eu quero sentir)

1. Aperto **`Ctrl+Alt+Space`** em qualquer lugar.
2. Aparece uma **pill preta** embaixo da tela (mesmo estilo do overlay) **já gravando** — ponto vermelho pulsando, onda em tempo real, timer, e um **botão "Parar"**. A pill **não rouba o foco** do meu documento.
3. Falo à vontade (posso rolar a tela; o foco de teclado continua no documento).
4. Paro de duas formas, o que estiver à mão: **clico "Parar"** ou **aperto `Ctrl+Alt+Space` de novo**.
5. A pill mostra **"transcrevendo…"**, transcreve (mesmo pipeline), **cola no cursor** e **pisca "colado ✓"** por ~1s.
6. A pill **fecha sozinha**. O texto ficou no documento **e** no clipboard (se eu quiser, dou Ctrl+V de novo em outro lugar).
7. Se eu me arrepender no meio da gravação, **aperto `ESC`** → descarta: fecha, não transcreve, não cola, não salva.

---

## 4. Decisões fechadas no brainstorm

1. **Auto-paste no cursor + fecha sozinha** (não painel de texto manual). O clipboard segurando o texto é o fallback de "copiar de novo". *(Pergunta 1 → A)*
2. **Hotkey `Ctrl+Alt+Space`** — teclas todas nomeadas (sem ambiguidade de letra sob modificador no pynput), **zero conflito** com atalho nativo do Windows. Não usar `Win+letra` de 2 teclas (quase todos reservados; o pynput não suprime o atalho do Windows, os dois disparam). *(Pergunta 2 → A)*
3. **Parar por botão OU pela hotkey de novo (toggle)** — os dois disponíveis. *(Pergunta 3 → ambos)*
4. **`ESC` cancela** (descarta sem transcrever/colar/salvar). *(Pergunta 4 → sim)*
5. **Pisca "colado ✓" e fecha** depois do paste (não fica aberta com o texto). *(Pergunta 5 → A)*
6. **Um ditado por vez** — mutuamente exclusivo com o hold-to-talk (o `_recording`/`_state_lock` já garante).
7. **Reusa** o motor de captura, transcrição, vocabulário, mute, warmup, beep, histórico, acervo e `paste()`. Nada disso é reimplementado.

---

## 5. Detalhe técnico

Tudo em `dictate.py`. As afirmações sobre comportamento de `WS_EX_NOACTIVATE`/`SetForegroundWindow` são **conhecimento prévio marcado pra confirmar no E2E** (ver §6 e critérios de aceite) — não validei contra doc oficial da MS/Qt neste brainstorm.

### 5.1 Config (`.env`)

Nova env var, sem tocar a `HOTKEY` atual:

```
HOTKEY_HANDSFREE=ctrl+alt+space
```

⚠️ **Gravar o `.env` em UTF-8 SEM BOM** — o `Set-Content -Encoding utf8` do PS 5.1 grava BOM e corrompe o parse do dotenv (já queimou no projeto; ver memória `whisper-voice-setup`). Se ausente no `.env`, cair num default `ctrl+alt+space` no código.

No topo, junto do parse atual (`dictate.py:115-117`), reusa o `_resolve_hotkey`/`_hotkey_label` que já existem:

```python
_HANDSFREE_SPEC = os.getenv("HOTKEY_HANDSFREE", "ctrl+alt+space")
HANDSFREE_HOTKEY = _resolve_hotkey(_HANDSFREE_SPEC)
HANDSFREE_LABEL  = _hotkey_label(_HANDSFREE_SPEC)
```

### 5.2 Estado — distinguir o modo de gravação

Hoje só existe `_recording` (bool). O `on_release` do hold usa `if _recording and not _combo_held()` pra parar — isso **não pode** disparar quando quem está gravando é o mãos-livres. Adiciona um modo:

```python
_rec_mode = None   # None | "hold" | "handsfree"
_handsfree_combo_active = False   # True enquanto o chord do mãos-livres está 100% pressionado (anti-repeat)
_hf_target_hwnd = None            # janela que tinha foco quando apertei o atalho (pro auto-paste)
```

### 5.3 Detecção da hotkey (edge-triggered, separada do hold)

O hold é *level-triggered* (grava enquanto segura). O mãos-livres é *edge-triggered* (um toque = alterna). Como modificadores repetem eventos de tecla enquanto segurados, precisa de guarda anti-repeat (`_handsfree_combo_active`).

```python
def _handsfree_held():
    return all(_pressed & token for token in HANDSFREE_HOTKEY)

def on_press(key):
    global _t_press, _handsfree_combo_active
    _pressed.add(key)

    # --- hold-to-talk (INALTERADO) ---
    if not _recording and _combo_held():
        _t_press = time.perf_counter()
        bridge.start.emit()

    # --- mãos-livres: dispara UMA vez na borda de subida do chord ---
    if _handsfree_held():
        if not _handsfree_combo_active:
            _handsfree_combo_active = True
            bridge.handsfree_toggle.emit()   # decide start/stop no slot

    # --- ESC cancela (só quando o mãos-livres está gravando) ---
    if key == keyboard.Key.esc and _rec_mode == "handsfree":
        bridge.handsfree_cancel.emit()

def on_release(key):
    global _handsfree_combo_active
    _pressed.discard(key)

    # hold-to-talk para (só quando o modo é "hold")
    if _recording and _rec_mode == "hold" and not _combo_held():
        bridge.stop.emit()

    # rearma o mãos-livres quando o chord é solto
    if _handsfree_combo_active and not _handsfree_held():
        _handsfree_combo_active = False
```

**Nota de foco (ESC):** a pill é `WS_EX_NOACTIVATE`, então **não recebe foco de teclado** → um `keyPressEvent` do Qt não dispararia o ESC. Por isso o ESC é tratado no **listener global** (pynput), não na janela. Mesma razão pela qual "parar pela hotkey de novo" passa pelo listener.

### 5.4 Sinais (Bridge)

Adiciona à classe `Bridge` (`dictate.py:318`):

```python
class Bridge(QObject):
    start = pyqtSignal()
    stop  = pyqtSignal()
    done  = pyqtSignal(float)          # (hold) — INALTERADO
    handsfree_toggle = pyqtSignal()    # aperto do atalho OU clique no Parar
    handsfree_cancel = pyqtSignal()    # ESC
    handsfree_done   = pyqtSignal(float)   # segundos; <0 = erro/vazio
```

### 5.5 Motor de captura compartilhado

Extrair o miolo de `slot_start`/`slot_stop` pra dois helpers, pra os dois modos reusarem (abrir/fechar stream, mute, warmup, beep, frames). O comportamento fica idêntico ao de hoje — é refactor, não mudança:

```python
def _begin_capture():
    """Abre o stream, muta, warmup, beep. Seta _recording. (miolo do slot_start atual)"""
    global _recording, _stream, _frames, _last_level
    with _state_lock:
        if _recording:
            return False
        _frames = []
        _recording = True
    _last_level = 0.0
    warmup_api(quiet=True)
    beep(880)
    def callback(indata, frames_count, time_info, status):
        global _last_level
        _frames.append(indata.copy())
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
        _last_level = min(1.0, rms * 70.0)
    _stream = sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=BLOCK, callback=callback)
    _stream.start()
    mute_system()
    return True

def _end_capture():
    """Fecha o stream, desmuta, beep. Retorna os frames (por valor). (miolo do slot_stop)"""
    global _recording, _stream, _frames
    with _state_lock:
        if not _recording:
            return None
        _recording = False
    try:
        _stream.stop(); _stream.close()
    except Exception:
        pass
    unmute_system()
    beep(440)
    frames, _frames = _frames, []
    return frames
```

`slot_start`/`slot_stop` (hold) passam a chamar esses helpers + cuidar do `_rec_mode="hold"` e do overlay, mantendo o `_t_press` log e o `overlay.show_recording()` **antes** do `_begin_capture` (visual instantâneo, como hoje).

### 5.6 Slots do mãos-livres

```python
def slot_handsfree_toggle():
    # se o hold está gravando, ignora (um ditado por vez)
    if _recording and _rec_mode == "hold":
        return
    if _recording and _rec_mode == "handsfree":
        _handsfree_stop()
    elif not _recording:
        _handsfree_start()

def _handsfree_start():
    global _rec_mode, _hf_target_hwnd
    _hf_target_hwnd = _get_foreground()      # captura o alvo ANTES de abrir a pill
    hf_window.show_recording()               # visual instantâneo (pill não rouba foco)
    if _begin_capture():
        _rec_mode = "handsfree"
    else:
        hf_window.hide_it()

def _handsfree_stop():
    global _rec_mode
    frames = _end_capture()
    _rec_mode = None
    hf_window.show_busy()
    threading.Thread(target=worker, args=(frames,),
                     kwargs=dict(mode="handsfree", target_hwnd=_hf_target_hwnd),
                     daemon=True).start()

def slot_handsfree_cancel():
    """ESC: descarta sem transcrever/colar/salvar."""
    global _rec_mode
    if _recording and _rec_mode == "handsfree":
        _end_capture()          # fecha stream/desmuta; frames são jogados fora
        _rec_mode = None
        hf_window.hide_it()
```

### 5.7 Captura e reforço de foco (ctypes — sem dependência nova)

```python
import ctypes
_user32 = ctypes.windll.user32

def _get_foreground():
    try:
        return _user32.GetForegroundWindow()
    except Exception:
        return None

def _focus_and_paste(text, hwnd):
    """Reforça o foco na janela-alvo e cola. Como a pill é NOACTIVATE, o alvo
    normalmente JÁ é o foreground — o SetForegroundWindow é rede de segurança
    (ex: se eu tiver trocado de janela de propósito, cola na que estava no início)."""
    try:
        if hwnd:
            _user32.SetForegroundWindow(hwnd)
            time.sleep(0.05)
    except Exception:
        pass
    paste(text)   # reusa o paste() existente (clipboard + Ctrl+V + restaura)
```

### 5.8 `worker` — parametrizar por modo

Assinatura passa a `worker(frames, mode="hold", target_hwnd=None)`. O caminho de sucesso diverge só no fim:

- **`mode == "hold"`** (INALTERADO): `bridge.done.emit(elapsed)` + `paste(text + " ")`.
- **`mode == "handsfree"`**: `_focus_and_paste(text + " ", target_hwnd)` e depois `bridge.handsfree_done.emit(elapsed)` (a pill pisca "colado ✓" e fecha). Erro/vazio: `bridge.handsfree_done.emit(-2.0/-3.0)` (mensagem de falha, mesma semântica do overlay).

Histórico, acervo de áudio e `pendentes/` (retry no boot) funcionam igual pros dois modos — **não** duplicar essa lógica.

### 5.9 Janela mãos-livres (`HandsFreeWindow`)

Nova classe no estilo do `Overlay` (preto quase 100%, ponto vermelho, onda, timer — meu gosto visual documentado), **um pouco maior** pra caber o botão Parar (ex ~300×48). Mesmas flags de não-ativação + um `QPushButton` clicável:

- Flags: `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus`; `WA_TranslucentBackground`; `WA_ShowWithoutActivating`. (Isso mapeia pra `WS_EX_NOACTIVATE` — janela não rouba foco, mas **recebe clique de mouse**; é o que faz o auto-paste acertar o alvo.)
- Botão "Parar": `QPushButton` filho; `clicked` → `bridge.handsfree_toggle.emit()` (mesmo caminho da hotkey; o slot decide que é stop). Estética alinhável depois com a `ui-ux-pro-max`, mas o mínimo é um quadradinho "■ Parar" cinza/vermelho coerente com a pill.
- Estados (espelham o `Overlay`): `rec` (onda+timer+botão), `busy` ("transcrevendo…"), flash `done` ("colado ✓") e `fail` (erro). Reusar `reposition()` (monitor do cursor) e a lógica de onda/timer — dá pra fatorar helpers comuns ou copiar o mínimo; **não** transformar o `Overlay` do hold em algo com botão (mantém ele simples).
- Posição: bottom-center do monitor onde está o cursor (igual overlay).

**Considerado e descartado — reusar o `Overlay` direto:** o `Overlay` é paint-only, sem widgets filhos, e proposital não-interativo. Enfiar um botão clicável nele mistura as responsabilidades e arrisca o caminho do hold que já está estável. Uma classe separada que copia o estilo é mais barata de manter.

### 5.10 Fiação no `main()`

Depois de criar `bridge`/`overlay` (`dictate.py:765`):

```python
hf_window = HandsFreeWindow()
bridge.handsfree_toggle.connect(slot_handsfree_toggle)
bridge.handsfree_cancel.connect(slot_handsfree_cancel)
bridge.handsfree_done.connect(hf_window.show_done)
```

`hf_window` como global (igual `overlay`). Atualizar o tooltip da tray e o log final de boot pra mencionar os dois atalhos (ex: `"Segura {HOTKEY_LABEL} pra ditar · {HANDSFREE_LABEL} pra mãos-livres"`).

---

## 6. Pontos de atenção / riscos

1. **Clique num `WS_EX_NOACTIVATE` (o mais crítico).** A premissa central da Opção A é: a pill não ativa (não rouba foco de teclado), mas o botão Parar **recebe clique de mouse**, e por isso o Ctrl+V do paste cai no documento, não na pill. Isso é o comportamento esperado de janela no-activate (no-activate ≠ no-input), mas **confirmar no E2E**: clicar Parar e ver o texto cair no editor de trás, não sumir.
2. **`SetForegroundWindow` tem restrições no Windows** (regra anti-focus-stealing). Como a pill nunca vira foreground, o alvo normalmente continua sendo o foreground e o `SetForegroundWindow` é no-op de segurança. Se no E2E o foco não voltar de forma confiável, o plano B é o truque `AttachThreadInput` antes do `SetForegroundWindow` — só implementar se o caminho simples falhar (YAGNI até provar).
3. **Convivência com o hold.** Testar: apertar `Ctrl+Alt+Space` **enquanto** seguro o hold → ignorado; e vice-versa. O `_rec_mode` + `_recording` cobrem, mas validar na prática.
4. **Repeat de tecla no chord.** Segurar `Ctrl+Alt+Space` não pode alternar start→stop→start em loop — o `_handsfree_combo_active` trava até soltar. Testar segurando alguns segundos.
5. **Modelo/latência:** reusa o warmup existente; nada novo.

---

## 7. Critérios de aceite

- [ ] `HOTKEY_HANDSFREE` no `.env` (UTF-8 sem BOM) parseado; ausente → default `ctrl+alt+space`.
- [ ] `Ctrl+Alt+Space` abre a pill **já gravando**, sem roubar foco do documento.
- [ ] Onda + timer + ponto vermelho + botão "Parar" aparecem; visual coerente com o overlay preto.
- [ ] Parar por **clique no botão** funciona e o texto cai no cursor do documento de trás.
- [ ] Parar pela **hotkey de novo** funciona (toggle).
- [ ] Após parar: "transcrevendo…" → cola no cursor → pisca "colado ✓" → **fecha sozinha**.
- [ ] Texto também fica no **clipboard** (Ctrl+V manual funciona depois).
- [ ] **ESC** durante a gravação descarta: fecha, não transcreve, não cola, não salva no histórico.
- [ ] **Um por vez:** acionar mãos-livres enquanto o hold grava (e vice-versa) é ignorado, sem travar nenhum dos dois.
- [ ] Hold-to-talk **inalterado** — segurar `alt_gr/ctrl_r` continua gravando/colando como antes.
- [ ] Histórico e acervo de áudio (`audios/`, retenção 7d) gravam igual pros dois modos; falha de API cai em `pendentes/` e recupera no boot.
- [ ] **Dono da ponta a ponta:** rodar o fluxo em produção (matar o `pythonw` do `dictate.py`, supervisor religa), ditar uma frase real pelo mãos-livres num editor de texto, ver colar certo, e conferir no fim do `dictate.log` a linha `whisper-voice pronto`. Sem exceção no log.
