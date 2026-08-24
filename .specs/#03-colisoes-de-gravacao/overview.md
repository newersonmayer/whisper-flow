# #03 — Colisões de gravação

Três situações em que uma tecla apertada sem querer estragava (ou parecia
estragar) um ditado em curso. Pedido do Newerson em 24/08/2026.

## O que muda

### 1. `ESC` não cancela mais o mãos-livres

**Supersede a spec #01** (item 7 da jornada e o critério de aceite "ESC durante
a gravação descarta"). Motivo: na prática ele acertava o `ESC` sem querer no
meio da fala e perdia o ditado inteiro — aconteceu várias vezes.

Não existe mais atalho de descarte. Pra descartar, deixe transcrever e ignore o
texto. O `slot_handsfree_cancel` e o sinal `handsfree_cancel` ficam no código de
propósito, sem ninguém emitindo, como caminho pronto se ele quiser o
cancelamento de volta atrás de uma tecla menos perigosa.

### 2. Hotkey de hold apertada durante o mãos-livres → avisa

Isso **já era um no-op seguro**: `slot_start()` sempre saiu no `if _recording`.
O defeito era o silêncio — nada na tela dizia que a tecla não tinha efeito, e
ele parava de falar achando que tinha quebrado a gravação.

Agora a pill mostra `já gravando` por 1,2s **por cima** do estado de gravação:
o ponto REC e o timer continuam, só a onda cede o lugar. Ver
[`_ux-veredito.md`](_ux-veredito.md) para a decisão e as alternativas medidas.

### 3. Gravar de novo durante "transcrevendo/organizando" → a pill nova vence

`show_busy()` e `show_norm()` das duas janelas ganharam o guard `if _recording:
return` que o `show_done()` já tinha. Antes, o worker do ditado anterior
repintava a pill da gravação nova com "organizando…".

O ditado antigo **não é cancelado**: transcreve, normaliza, salva no histórico e
cola normalmente. Só perde a vez no visual.

### 4. Transcrição ganha teto de tempo proporcional ao áudio

Não havia `timeout` na chamada de transcrição, então valia o da SDK:
`DEFAULT_TIMEOUT = httpx.Timeout(timeout=600)` em `openai/_constants.py`. E 600s
é teto de mentira — o `dictate.log` tem **um áudio de 38,6s que ficou 608,7s na
API**: dez minutos de pill travada por meio minuto de fala.

Pior, `DEFAULT_MAX_RETRIES = 2` da SDK **multiplicava** com o `API_RETRIES = 3`
do app: até 9 tentativas por ditado, cada uma podendo ir a 600s.

Agora: `max(25, 10 + duração × 0,20)` segundos por tentativa, e
`with_options(max_retries=0)` na chamada, deixando a repetição só no laço do
app (que loga cada tentativa e o teto usado).

Calibragem, nos 2.892 ditados com timing do histórico:

| faixa de áudio | n | p50 | p99 | teto novo |
|---|---|---|---|---|
| 0–15s | 1063 | 1,5s | 6,1s | 25s |
| 15–30s | 729 | 2,0s | 6,8s | 25s |
| 30–60s | 605 | 2,6s | 8,3s | 25s |
| 60–120s | 351 | 3,7s | 10,4s | 25–34s |
| 120–240s | 121 | 6,2s | 15,2s | 34–58s |
| 240–600s | 23 | 9,4s | 19,8s | 58–130s |

O teto teria abortado **3 ditados de 2.892 (0,10%)** — e os três são exatamente
os patológicos: 608,7s, 209,4s e 34,9s. Áudio abortado não se perde: vai pra
`pendentes/` e é re-transcrito no próximo boot (só não cola).

Mesmo teto aplicado ao `historico.py`, que tem a chamada gêmea.

### 5. `HOTKEY_HANDSFREE` passa a usar lados explícitos

`ctrl+alt+space` era uma armadilha silenciosa: `ctrl` expande para
`{ctrl, ctrl_l, ctrl_r}` e `alt` para `{alt, alt_l, alt_r, alt_gr}` — ou seja,
o chord colidia com o `HOTKEY=alt_gr/ctrl_r` em **duas** teclas, `ctrl_r` **e**
`alt_gr`. Nessas, o hold dispara primeiro (o `on_press` checa ele antes) e o
mãos-livres nunca começa, porque o `slot_handsfree_toggle` sai no
`if _recording and _rec_mode == "hold": return`.

Sintoma enganoso: "o toggle não funciona neste teclado", sem nada no log.

`.env` agora: `HOTKEY_HANDSFREE=ctrl_l+alt_l+space`. Zero tecla em comum.
Alinha com a intenção que já existia no `HOTKEY` — lado direito é o hold, lado
esquerdo é o resto.

E o `_avisar_colisao_de_hotkey()` roda no boot: se as duas hotkeys voltarem a
compartilhar tecla, sai um `[!]` no log dizendo qual.

## O que NÃO muda

- O áudio nunca esteve em risco: o `_end_capture()` entrega os frames por valor
  (race corrigida em ago/2026).
- Nenhum estado novo de pill, nenhuma tela nova, nenhuma navegação nova.
- A colagem do ditado antigo continua caindo no cursor **enquanto** a gravação
  nova acontece. Não quebra nada, mas o texto aparece "sozinho" no meio da fala.
  Deixado como está — mudar isso altera a promessa "cola onde o cursor estiver".

## Pontos de atenção

⚠️ `HOTKEY_HANDSFREE=ctrl+alt+space` usa `ctrl`, que casa com **qualquer** Ctrl,
inclusive o `ctrl_r` que é a hotkey de hold. Se o chord for montado com o Ctrl
**direito**, o hold dispara primeiro e o mãos-livres é engolido. Não foi
alterado nesta spec — some trocando `ctrl` por `ctrl_l` no `.env`.

## Verificação

35 asserções em dois testes descartáveis (offscreen Qt), todas passando:

- **Pill (19):** expiração da nota, no-op em estado não-rec, os quatro guards de
  repintura, `slot_start` com e sem gravação em curso, pintura real com nota, e
  ausência do `ESC`.
- **Timeout e hotkey (16):** as 5 chaves do `.env` preservadas na edição, o teto
  em 6 durações, `timeout` e `max_retries=0` chegando na request, colisão zero na
  config nova e as duas teclas colidentes detectadas na antiga.

Microcopy medido com `QFontMetrics`: `já gravando` = 121px contra 156px de
espaço. O texto originalmente pedido daria 330px.
