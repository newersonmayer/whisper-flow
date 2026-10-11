# Veredito de UX — microfone que não abre

Superfície única: a pill (`Overlay` 240x36 e `HandsFreeWindow`, mesma `_draw_pill`).
Estados existentes: `rec · busy · norm · done · fail` (ver `#03-colisoes-de-gravacao`).
Nenhum estado novo.

## Estrutura

Ação primária, herdada do #03: **saber se a fala está sendo capturada agora**. O incidente de
10/10/2026 é a violação exata dela — a pill dizia "gravando" (ponto REC + timer) enquanto nada
era capturado, e o Eduardo falou ~2 min no vazio. A onda parada e o bipe de início ausente
eram os únicos sinais, e nenhum dos dois foi percebido.

## Decisão

Se a captura não confirma em `MIC_CONFIRM_SECONDS` (3s) depois do aperto:

| Situação aos 3s | O que a pill faz |
|---|---|
| tecla ainda apertada / mãos-livres gravando | `fail` com `microfone não abriu`, 2.400ms, bipe de erro; ditado cancelado |
| tecla já solta (pill em `busy`) | mesmo `fail` + bipe — o "transcrevendo" mentiria, não há o que transcrever |
| outro ditado já assumiu a pill | não toca na pill nem no som; só loga (caso (b) do #03: quem grava agora vence) |
| captura confirmou antes | nada muda |

Depois do `fail`, soltar a tecla não faz nada (o ditado já foi encerrado); apertar de novo é
um ditado novo.

## Microcopy

`microfone não abriu`. Medido com `QFontMetrics`, Segoe UI 10pt DemiBold, com o `✕  ` do
estado `fail`, a 125% de escala (DPI lógico 120, a tela do Newerson):

| texto | largura | cabe em 240px? |
|---|---|---|
| `✕  microfone não abriu` | **204px** | sim |
| `✕  microfone travou` | 177px | sim, mas mente nas aberturas só lentas (5 de 137 passaram de 3s sem travar) |
| `✕  microfone não respondeu` | 250px | não — cortado nas duas pontas |
| `✕  nada gravado — microfone não respondeu` | 397px | não |

"não abriu" é verdade nos dois casos (lento e travado) e diz o que importa: a fala não foi
gravada.

## Duração e som

2.400ms, acima dos outros flashes (colado 900 · não entendi 1.200 · falhou 1.600). Os outros
aparecem depois de soltar a tecla, quando o olho já está na pill esperando; este aparece no
meio da fala, com a atenção no texto. Pelo mesmo motivo vem com o bipe de erro existente
(`beep(220, 280)`, Basso no macOS): o incidente prova que sinal só visual não é percebido.

## Estados (superfície: pill) — acréscimo ao #03

| Estado | Quando | O que mostra |
|---|---|---|
| `fail` (mic) | captura não confirmou em 3s, **e nada mais gravando** | ✕ + `microfone não abriu`, 2,4s, bipe |

## Fluxo

Sem entrada ou saída nova. Aperto → pill `rec` imediata (como hoje) → captura confirma (como
hoje) **ou** `fail` aos 3s.

## Alternativas rejeitadas

- **Estado "abrindo microfone…" antes de confirmar:** em 99,9% dos ditados a abertura leva
  <1s; o estado piscaria em todo aperto. E o Newerson aprovou manter a pill instantânea.
- **Estado novo, visual próprio:** o `fail` já significa "este ditado não deu". Um vermelho
  diferente para a mesma ideia quebraria a consistência entre os flashes.
- **Avisar só ao soltar a tecla:** é o comportamento que fez o Eduardo perder 2 min.
- **Cancelar sem som:** ver "Duração e som".
- **Mensagem com instrução ("tente de novo"):** não cabe (387px), e logo após um travamento
  real a nova tentativa pode cair na janela de 15s do watchdog e falhar de novo.

## Fora do escopo, registrado

`✕  falhou — audio guardado pra retry` (código `-2.0`, existente) mede 330px a 125% e já é
cortado nas duas pontas da pill de 240px. Não mexido aqui.
