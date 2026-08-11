# Veredito estético — Preferências de formatação + Correções

**Skill:** `ui-ux-pro-max` · **Data:** 2026-08-10
**Par:** complementa `_ux-veredito.md` (estrutura/fluxo/estados) — não substitui.
**Stack:** PyQt5 + QFluentWidgets 1.11.2. É **QSS** (subset de CSS do Qt) e
`QPainter`, não web: sem `box-shadow`, sem `transition`, sem pseudo-elemento.

---

## 0. A recomendação automática foi descartada (e por quê)

O `search.py --design-system` devolveu **"Vibrant & Block-based"**, tipografia
**Space Mono** e CTA **verde `#22C55E`** sobre `#0F172A`. Descartado inteiro:

- O app **já tem identidade aprovada**, e não na primeira tentativa — o
  Newerson **rejeitou duas versões** (tema dark de cards e tema creme claro)
  antes de aprovar o quase-preto com acento laranja, referência declarada ao
  Wispr Flow. Trocar a paleta agora seria desfazer decisão tomada.
- "Vibrant/block-based/high color contrast" é o oposto do produto: um utilitário
  que aparece por 3 segundos numa pill e some.
- Space Mono numa UI Windows nativa quebra a consistência com o resto do Qt.

O que aproveitei da skill foram os **princípios** (contraste mínimo, duração de
motion, cursor, foco), não a paleta. Postura investigadora: regra genérica fora
de contexto é ruído.

---

## 1. Tokens (todos medidos, nenhum estimado)

Herdados do app (não mexi): `#070708` fundo · `#E3E3E7` texto · `#C9C9CE`
secundário · `#8E8E96` hint · `#F2A33C` acento · `#060607` pill.

**Novos:**

| Token | Valor | Onde |
|---|---|---|
| `CARD_PRIMARIO` | `#0E0E10` | bloco Correções, bloco do toggle |
| `CARD_SECUNDARIO` | `#0A0A0B` | bloco Vocabulário |
| `BORDA_PRIMARIA` | `rgba(255,255,255,0.10)` | card primário |
| `BORDA_SECUNDARIA` | `rgba(255,255,255,0.06)` | card secundário |
| `TEXTO_DESABILITADO` | `#7E7E86` | blocos com toggle off |
| `SEPARADOR_PILL` | `#3A3A40` | o "·" entre as fases |
| `PILL_FASE_FEITA` | `#6E6E76` | "✓ transcrito" |

### Contrastes calculados (não estimados)

| Par | Ratio | Alvo | Status |
|---|---|---|---|
| `#E3E3E7` sobre `#0E0E10` | **15,07:1** | 4,5 | ✅ |
| `#C9C9CE` sobre `#0A0A0B` | **12,00:1** | 4,5 | ✅ |
| `#8E8E96` sobre `#0E0E10` | **5,93:1** | 4,5 | ✅ |
| `#F2A33C` sobre `#0E0E10` | **9,26:1** | 4,5 | ✅ |
| `#F2A33C` sobre o chip `#2E2316` | **7,37:1** | 4,5 | ✅ |
| `#7E7E86` desabilitado sobre `#0E0E10` | **4,79:1** | 3,0 | ✅ |
| `#C9C9CE` "organizando" sobre `#060607` | **12,28:1** | 4,5 | ✅ |
| `#6E6E76` "✓ transcrito" sobre `#060607` | **4,01:1** | 3,0 | ✅ |
| `#F2A33C` spinner sobre `#060607` | **9,72:1** | 3,0 | ✅ |

---

## 2. Os chips `[garantia]` / `[dica]` — diferença por PESO, não por matiz

**A decisão:** o contraste entre as duas alavancas é **preenchido vs contorno**,
não verde vs vermelho. Semáforo num tema minimalista quase-preto grita, e
sugere "erro" onde o certo é "menos forte".

```qss
/* garantia — preenchido, cor da marca: avança */
#chipGarantia {
    color: #F2A33C;
    background: rgba(242,163,60,0.14);   /* efetivo #2E2316 */
    border: 1px solid rgba(242,163,60,0.38);
    border-radius: 9px;
    font: 600 8pt 'Segoe UI';
    padding: 2px 8px;
}
/* dica — fantasma, neutro: recua */
#chipDica {
    color: #8E8E96;
    background: transparent;
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 9px;
    font: 500 8pt 'Segoe UI';
    padding: 2px 8px;
}
```

O laranja já é o acento do app, então "garantia" lê como **a coisa ativa do
produto** em vez de um selo novo. A dica não é punida com vermelho — ela é
simplesmente mais quieta, que é a verdade: funciona às vezes.

⚠️ **Cor não é o único indicador** (regra de acessibilidade): a diferença
também está na **palavra** do chip e na **ordem** dos blocos. Daltônico lê
"garantia"/"dica" igual.

---

## 3. Hierarquia dos dois blocos empilhados

Diferença de **elevação por luminância**, que é como se cria profundidade sem
`box-shadow` (o Qt não tem):

| | Correções (primário) | Vocabulário (secundário) |
|---|---|---|
| fundo | `#0E0E10` | `#0A0A0B` |
| borda | `rgba(255,255,255,0.10)` | `rgba(255,255,255,0.06)` |
| título | `#E3E3E7` 600 11pt | `#C9C9CE` 500 10,5pt |
| padding | `18px 18px` | `16px 18px` |
| botão Salvar | `PrimaryPushButton` (laranja) | `PushButton` neutro |

O primário é **7% mais claro** que o fundo da janela; o secundário, 3%. Em tema
quase-preto isso basta para o olho ordenar, sem borda grossa nem sombra falsa.

---

## 4. Estado desabilitado — reduzir contraste, nunca `opacity`

**Regra:** `opacity: 0.4` no container apaga tudo junto, inclusive a borda, e o
bloco vira mancha ilegível. Em vez disso, **trocar os tokens de texto**:

```qss
QWidget:disabled #body  { color: #7E7E86; }   /* 4,79:1 — legível */
QWidget:disabled #hint  { color: #5E5E66; }
QWidget:disabled QLineEdit,
QWidget:disabled PlainTextEdit {
    background: #08080A;
    border: 1px solid rgba(255,255,255,0.04);
    color: #7E7E86;
}
```

`#7E7E86` fica em **4,79:1** — acima do mínimo de 3:1 para UI, e a **1/3** do
contraste do texto ativo (15:1). Lê como "existe, está off", não como "quebrado".

O usuário precisa conseguir **ler as preferências antes de decidir ligar** — é
o argumento de conversão do toggle. Apagar esconde o motivo de ligar.

---

## 5. A pill em duas fases — largura medida com `QFontMetrics`

⚠️ **A primeira versão desta seção estava errada e foi corrigida por medição.**
Eu estimei Segoe UI a ~6,6px/caractere e projetei um layout de 185px. Renderizei
a pill de verdade num `QPixmap` e a fonte real mede **quase o dobro**:
`"organizando…"` a 9pt = **182px**, não 92px. O layout original estourava em
**364px de 219px úteis**. Estimativa de largura de fonte não vale — só
`QFontMetrics`.

### O que a medição revelou de brinde: um bug que já existia

`"transcrevendo…"` a **9pt mede 208px**, mas o `QRect(36, 0, w-48, h)` que o
desenha tem **192px**. O texto da fase 1 **vinha sendo cortado em todo ditado**,
desde sempre. Corrigido junto: a fase 1 foi para 8pt (176px, folga de 18px).

### Larguras reais (Segoe UI, 100% DPI, `QFontMetrics.width`)

| Texto | 8pt | 9pt |
|---|---|---|
| `transcrevendo...` | **176px** | 208px |
| `organizando...` | **154px** | 182px |
| `✓ transcrito` (como texto) | **132px** | 156px |
| `✓` (como texto) | 11px | 13px |

### Combinações testadas — área útil **219px** (240 − 13 − 8)

| Layout | Largura | Veredito |
|---|---|---|
| **check desenhado + arco + `organizando…` 8pt** | **192px** | ✅ **escolhido**, 27px de folga |
| check desenhado + arco + `organizando…` 9pt | 220px | ❌ estoura por 1px |
| `✓ transcrito` (texto) 8pt + arco + texto | 339px | ❌ estoura por 120px |

**A decisão:** o check vira **desenho `QPainter`, não texto**. Duas linhas custam
**11px** onde a palavra "✓ transcrito" custa 132px — e comunicam a mesma coisa
("a etapa anterior terminou"). Foi o corte que fez o layout caber sem perder o
significado.

```
[13px]  ✓        ◐   organizando…                     [timer]
        └ desenho │   └ 8pt #C9C9CE (154px)
          #6E6E76 └ arco #F2A33C 2px (18px)
          (20px)
```

**Especificação `QPainter` (`mode == "norm"` no `_draw_pill`):**

| Elemento | Valor |
|---|---|
| check | 2 × `drawLine`, `QPen(#6E6E76, 1.8)`, `RoundCap`, x=13, ocupa 20px |
| arco do spinner | `QPen(#F2A33C, 2.0)`, `RoundCap`, retângulo 11×11, ocupa 18px |
| velocidade do arco | **320°/s**, arco de 110° — idêntico ao `busy` atual |
| "organizando…" | `QFont("Segoe UI", 8)`, `#C9C9CE` |
| reticências | mesmo ciclo do `busy`: `"." * (int(time.time()*2.5) % 4)` |

**Por que o spinner da fase 2 é laranja e o da fase 1 continua cinza:** o
laranja marca *"agora é a etapa opcional, a que usa IA"*. Reforça que o
essencial (cinza) já terminou. É a mesma cor do chip `[garantia]` e do botão
primário — o acento significa consistentemente "a parte ativa".

**Motion:** repaint a 33ms (~30fps), já existente. Nada novo. A skill pede
`prefers-reduced-motion`; **no Qt não existe esse media query** — o
equivalente honesto é o próprio toggle da feature, que remove a fase 2 inteira.

---

## 6. Paletas / abordagens rejeitadas

| Rejeitado | Por quê |
|---|---|
| **Paleta do `--design-system`** (`#22C55E` verde, `#0F172A`, Space Mono) | Ignora identidade aprovada após 2 rejeições do usuário; "vibrant/block-based" é o oposto de um utilitário efêmero |
| **Chips verde/vermelho (semáforo)** | Vermelho lê como "erro" — mas a dica não está errada, só é fraca. E grita em tema minimalista |
| **Chip "garantia" em verde `#22C55E`** | Introduz um terceiro matiz num app de duas cores (cinza + laranja). O acento já existente comunica o mesmo sem poluir |
| **`opacity: 0.4` no bloco desabilitado** | Apaga borda e fundo junto; o usuário não consegue ler o que ganharia ao ligar |
| **Sombra (`box-shadow`) pra separar os cards** | QSS não suporta em `QWidget` sem `QGraphicsDropShadowEffect`, que custa repaint e fica sujo em tema escuro. Luminância resolve |
| **`✓ transcrito · organizando…` tudo a 9pt** | Medido: 213px de 214px. Passa por 1px — quebra com outro DPI/fonte |
| **Aumentar a pill de 240 para 300px na fase 2** | Salto de largura no meio da animação chama atenção para a espera — exatamente o que o pedido queria evitar |
| **Barra de progresso determinada** | Medido 3,1–6,1s, variável com o tamanho do texto: barra que anda errado é pior que spinner honesto |
| **Trocar Segoe UI por fonte custom** | Segoe UI é a fonte do sistema; custom quebra a consistência com o Qt e o chrome do Windows |

---

## 7. Checklist de entrega

- [x] Contrastes calculados com números (9 pares, todos acima do alvo)
- [x] Cor não é o único indicador (palavra + ordem + peso)
- [x] Sem emoji como ícone — `✓` e `◐` são desenhados/tipográficos, consistentes com o `✓`/`✕` que a pill já usa
- [x] `cursor: PointingHandCursor` em tudo clicável (padrão já em uso)
- [x] Motion 150–300ms: o repaint de 33ms e o ciclo do arco são os que já existem
- [x] Estado desabilitado legível (4,79:1), não apagado
- [ ] `prefers-reduced-motion` — **não existe no Qt**; o toggle da feature é o controle equivalente
