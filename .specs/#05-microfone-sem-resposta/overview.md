# #05 — Microfone que não responde não pode prender o ditado

Origem: relato do Eduardo (macOS) em 10/10/2026, ~21:24 — pill presa em "transcrevendo"
depois de ~2 min de fala, ditado perdido. Recorrência do card
`816cfd96-5f57-44a3-9324-cd2864703d05` (PR #8, 16/09/2026).

## Como vai ficar depois de implementado

- **Watchdog do driver** (`dictate.py`, `_no_driver` + `_vigia_do_driver`): toda chamada ao
  PortAudio que abre, para, fecha ou reinicia o microfone tem prazo de `MIC_NATIVE_TIMEOUT`
  (`.env`, padrão 15s). Passou do prazo: loga a fase e encerra o processo; o `supervisor.py`
  religa em ~2s com o driver zerado.
- **Confirmação da captura** (`_confirmar_captura`): a pill continua aparecendo na hora do
  aperto. Se em `MIC_CONFIRM_SECONDS` (padrão 3s) a captura não começou, o ditado é
  cancelado, a pill vira `✕ microfone não abriu` e toca o bipe de erro.
- **Geração por ditado** (`_rec_gen`/`_cap_gen`): cada aperto ganha um número. Uma abertura
  atrasada só captura se ainda for a do aperto atual; um stop só encerra a captura que é dele.
- **(a) Mudança no existente:** `_begin_capture`, `_end_capture`, `_start_audio` e
  `_stop_and_transcribe` passam a receber a geração; `show_done` ganha o código `-4.0`.
- **(b) Pontos de atenção:** o processo pode se reiniciar sozinho (linha
  `[audio] ... travou no driver` no `dictate.log` e `rc=75` no `supervisor.log`).
  Um ditado anterior ainda transcrevendo nesse instante não cola: o áudio já está em
  `pendentes/` e volta pelo histórico no boot.
- **(c) Decisões locais:** prazos calibrados pelo log (abaixo); código de saída 75.

## O que você aprovou

- **Pill instantânea + erro se a captura não confirmar em ~3s** (Newerson, 11/10/2026,
  "ok, corrija" sobre a recomendação). Troca até 2 min de fala no vazio por 3s e um aviso.
- **Reinício do processo quando uma chamada nativa trava.** Python não interrompe uma
  chamada C presa; reiniciar é a única saída que não depende do driver colaborar.

## Por que o PR #8 não bastou

O PR #8 serializou abrir/parar/fechar. Isso tirou a corrida, mas não pôs prazo na chamada
nativa. No CoreAudio, `stop()`/`close()` caem em `FinishStoppingStream` →
`BlockWhileAudioUnitIsRunning`, que pesquisa a cada 100ms **sem timeout**
(`src/hostapi/coreaudio/pa_mac_core.c`). Se a unidade nunca reporta parada (Bluetooth
trocando, Mac acordando), a chamada fica presa — e desde o PR #8 presa **segurando o
`_capture_lock`**. Linha do tempo (exemplo fictício, horários do print):

| hora | o que acontece |
|---|---|
| 21:22:05 | keeper fecha o microfone ocioso; `stop()` entra no loop sem prazo |
| 21:22:30 | Eduardo aperta: pill "gravando" aparece; `_begin_capture` espera o lock |
| 21:24:20 | solta: pill "transcrevendo"; `_end_capture` também espera o lock |
| sempre | nada foi gravado, nada vai pra `pendentes/`; todo ditado seguinte trava igual |

Com esta spec: em 21:22:20 (15s depois de o `stop()` travar) o watchdog reinicia o
processo, e o aperto das 21:22:30 já encontra um driver novo e grava normalmente. Se o
aperto cair dentro da janela de 15s — ou se quem travar for a própria abertura —, a pill
vira `✕ microfone não abriu` com bipe 3s depois do aperto, em vez de contar tempo no vazio.

## Calibragem (dictate.log do Windows, 11/10/2026)

137 aberturas a frio registradas (só as >300ms entram no log) em ~4.600 ditados:
p50 620ms · p90 1.090ms · p99 5.272ms · máx 7.094ms. Acima de 3s: 5 (0,11% dos
ditados); acima de 10s: 0.

- `MIC_CONFIRM_SECONDS=3`: as 5 aberturas lentas virariam aviso + nova tentativa (o
  microfone já estará quente, então a segunda abre na hora). Aceito: o custo da
  alternativa é o ditado inteiro perdido.
- `MIC_NATIVE_TIMEOUT=15`: ~2× o pior caso medido. Nenhuma abertura saudável chegaria lá.
- ⚠️ Não há medição do macOS: o log do Eduardo não estava disponível. Os dois valores são
  ajustáveis por `.env` sem mexer no código.

## Alternativas rejeitadas

- **Só aumentar o lock (mais serialização):** o defeito não é corrida, é chamada sem prazo.
- **Isolar o áudio num subprocesso:** resolveria sem reiniciar o app inteiro, mas é refatoração
  grande do pipeline de captura (callback, encoder em streaming, frames). Reiniciar o processo
  custa ~2s e só acontece quando o driver já travou.
- **Timeout no `_end_capture` em vez do watchdog:** desbloqueia a pill, mas deixa o processo
  com o lock preso para sempre — todo ditado seguinte falharia até alguém reiniciar.
- **`abort()` no lugar de `stop()`:** também passa por `FinishStoppingStream`; mesma espera.
- **`MIC_WARM_SECONDS` alto no Mac (nunca fechar):** reduz o número de `stop()`, mas o
  stream morre na suspensão e o descarte dele chama o mesmo `stop()`.
