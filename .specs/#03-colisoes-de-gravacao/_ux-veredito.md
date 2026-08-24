# Veredito de UX — colisões de gravação na pill

Contexto: três colisões de teclado no ditador. A pill (`Overlay`, 240x36) e a
janela do mãos-livres (`HandsFreeWindow`) já têm os estados `rec · busy · norm ·
done · fail`. Nenhum estado novo foi criado — a decisão foi onde NÃO criar.

## Estrutura

Ação primária em toda a superfície: **saber se a fala está sendo capturada
agora**. Tudo o mais (transcrevendo, organizando, colado) é secundário — é
trabalho que já aconteceu. Isso decide os dois casos abaixo.

## Caso (a) — hold pressionado durante o mãos-livres

Hoje é no-op silencioso: `slot_start()` sai no `if _recording: return`. Não
quebra; só não avisa.

**Decisão: flash efêmero SOBRE o estado `rec`, não um estado novo.**
O `mode` continua `"rec"`; um campo `note` com validade de 1,2s desenha o texto
na área da onda. O ponto REC pulsante e o timer continuam na tela o tempo todo.

Por quê: a gravação está viva. Trocar o `mode` esconderia onda e timer, e uma
pill sem onda lê como "parou" — seria pior que o silêncio de hoje, porque
mentiria sobre o estado (semântica honesta).

**Microcopy: `já gravando`.**
Orçamento: a área da onda são 156px (`w - x0 - timer_w - 10` = 240-28-46-10),
igual nas duas janelas (`HandsFreeWindow.PILL_W = Overlay.W = 240`).
Medido com `QFontMetrics`, Segoe UI 8pt:

| texto | largura | cabe em 156px? |
|---|---|---|
| `já gravando` | **121px** | sim, 35px de folga |
| `pode falar` | 110px | sim, mas não explica por que a tecla não fez nada |
| `já gravando — pode falar` | 264px | não |
| `gravação em andamento, aguarde` | **330px** | não — 2,1× o espaço |

## Caso (b) — nova gravação enquanto o ditado anterior transcreve

**Decisão: a gravação nova vence a pill; o ditado antigo termina invisível.**
`show_busy()` e `show_norm()` do `Overlay` ganham o mesmo guard que o
`show_done()` já tem (`if _recording: return`). O ditado antigo segue inteiro —
transcreve, normaliza, salva no histórico e cola.

Por quê: quem está falando agora precisa ver que está sendo capturado. O
progresso do ditado anterior é informação sobre trabalho que já terminou.

## Estados (superfície: pill)

| Estado | Quando | O que mostra |
|---|---|---|
| `rec` | capturando | ponto REC + onda + timer |
| `rec` + nota | hotkey redundante apertada | ponto REC + `já gravando` + timer, 1,2s |
| `busy` | transcrevendo, **e nada gravando** | spinner + "transcrevendo" |
| `norm` | organizando, **e nada gravando** | ✓ + arco + "organizando…" |
| `done` / `fail` | fim, **e nada gravando** | ✓/✕ + mensagem, pisca e some |

## Fluxo

Sem mudança de entrada/saída. Nenhuma tela nova, nenhuma navegação nova.

## Alternativas rejeitadas

- **`gravação em andamento, aguarde`** (o texto que o Newerson sugeriu): 330px
  medidos contra 156px de espaço — 2,1× o disponível. Mesma classe de erro que
  já obrigou a trocar "✓ transcrito" pelo check desenhado. E "aguarde" é falso:
  ele não deve esperar, deve continuar falando.
- **Estado novo `blocked`**: esconderia onda e timer durante gravação viva.
  Rejeitado pelo motivo do caso (a).
- **Só beep, sem visual**: ele pediu visual, e um beep durante o ditado entra
  no áudio que está sendo gravado.
- **Mostrar as duas pills (antiga + nova)**: não cabe em 240x36 e cria duas
  hierarquias concorrentes sem ação primária.
- **Cancelar o ditado antigo quando começa um novo**: é exatamente o que ele
  pediu para NÃO acontecer.
- **Segurar a colagem do ditado antigo até a gravação nova acabar**: muda a
  promessa do produto ("cola onde o cursor estiver") e cria uma ordenação
  implícita entre ditados. Deixado em aberto — decisão dele, não minha.

## Estética

Nenhuma superfície visual nova. A nota reusa os tokens já estabelecidos da
pill: `Segoe UI 8pt`, `#C9C9CE` (mesma cor do texto "organizando…"). Não há
paleta, tipografia ou componente a decidir, então não há passe estético a
rodar aqui.

## Fora deste recorte — também vi

- `HANDSFREE_HOTKEY=ctrl+alt+space` usa `ctrl`, que casa com **qualquer** Ctrl,
  inclusive o `ctrl_r` que é a hotkey de hold. Montar o chord com o Ctrl
  direito faz o hold disparar primeiro e o mãos-livres ser engolido. Some
  trocando `ctrl` por `ctrl_l`.
- A colagem do ditado antigo cai no cursor enquanto a gravação nova acontece.
  Não quebra, mas o texto aparece "sozinho" no meio da fala.
