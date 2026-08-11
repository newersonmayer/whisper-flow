# Veredito de UX — Preferências de formatação + Correções

**Skill:** `/ux` (modo CONSTRUIR) · **Data:** 2026-08-10
**Escopo:** 4 superfícies novas no app Transcrições (`historico.py`) + 1 estado
novo na pill flutuante (`dictate.py`).

> Estrutura, fluxo e estados. Estética (cor, fonte, motion) é da
> `ui-ux-pro-max`, que roda depois deste arquivo.

---

## 1. O problema central não é "falta uma tela"

O app tem **três alavancas** que resolvem coisas diferentes, com nomes que não
distinguem qual faz o quê — e a hierarquia visual está **invertida em relação
à eficácia real**:

| Arquivo | Mecanismo | Eficácia (medida em 10/08/2026) | Tela hoje |
|---|---|---|---|
| `vocabulario.txt` | vai no `prompt` da API de transcrição | **0 acerto em 8** para `CLAUDE.md`; 0 em 4 para `Isaque` | ✅ tela própria |
| `correcoes.txt` | regex determinístico pós-transcrição | **14 de 14**, 0 ms, sem falso positivo | ❌ nenhuma |
| `preferencias.txt` | prompt do passe de LLM (novo) | funciona quando ligado | ❌ nova |

**A tela que existe é a da alavanca morta.** Quem abre o app hoje vê
"Vocabulário", digita `CLAUDE.md` lá, e o sistema continua escrevendo
"cloud.md" — porque o modelo ignora o prompt. A alavanca que resolve
(`correcoes.txt`) não tem interface: só existe editando arquivo à mão.

Isso é falha de **semântica honesta** (contrato 3 do checklist): o rótulo
promete um resultado que o mecanismo não entrega.

### A decisão de IA

Não criar "mais uma tela". **Reorganizar por problema do usuário**, não por
mecanismo técnico. O usuário tem exatamente dois problemas:

1. *"o sistema escreve essa palavra errada"* → **tela Palavras**
2. *"quero o texto mais limpo/organizado"* → **tela Formatação**

Três arquivos, dois problemas, duas telas. O usuário nunca precisa saber o que
é prompt, regex ou LLM — mas precisa saber **o que é garantia e o que é dica**,
porque isso muda o que ele faz quando um termo sai errado.

---

## 2. Estrutura

### Sidebar (ordem final)

```
Histórico     ← inalterada (entrada padrão)
Gravar        ← inalterada
Palavras      ← era "Vocabulário"; ganha o bloco de Correções
Formatação    ← NOVA (preferências + liga/desliga + limiar)
────────────
Ajustes       ← inalterada (rodapé): clipboard, popup
```

**Por que "Palavras" e não manter "Vocabulário":** o nome tem que cobrir os
dois blocos. "Vocabulário" descreve só o de cima — e é justamente o fraco.

### Tela **Palavras** — dois blocos, hierarquia invertida em relação a hoje

**Ação primária:** adicionar uma correção. É o que resolve o problema real.

```
Palavras
Termos que a transcrição erra.

┌─ Correções automáticas ───────────────── [garantia] ─┐   ← PRIMÁRIO
│  Uma por linha:  errado => certo                      │
│  ┌──────────────────────────────────────────────┐    │
│  │ cloud.md => CLAUDE.md                        │    │
│  │ isaac => Isaque                              │    │
│  └──────────────────────────────────────────────┘    │
│  Troca literal, sempre. Não depende do modelo.        │
│                                          [ Salvar ]   │
└───────────────────────────────────────────────────────┘

┌─ Termos do meu vocabulário ───────────────── [dica] ─┐   ← SECUNDÁRIO
│  Nomes e jargões do seu dia a dia.                    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Claude Code, Anthropic, BullMQ, Prisma...    │    │
│  └──────────────────────────────────────────────┘    │
│  ⓘ  Isto é uma dica para o modelo, não garantia. Se   │
│     um termo sai errado toda vez, suba ele para       │
│     Correções.                    [ Copiar para cima ]│
│                                          [ Salvar ]   │
└───────────────────────────────────────────────────────┘
```

**Correções em primeiro** — inverte a hierarquia atual, que é o defeito.
Quem chega com o problema ("escreve errado") cai direto na solução que funciona.

**"Copiar para cima"** é o atalho que fecha o ciclo: o usuário vê o termo
falhando no vocabulário e promove para correção sem redigitar. É o equivalente
manual do *auto-add* do Wispr Flow — e o caminho natural de aprendizado da
ferramenta.

⚠️ **Rótulos `[garantia]` / `[dica]` são o coração desta tela.** Sem eles, o
usuário não tem como saber por que digitou o termo num campo e continuou
saindo errado. Com eles, a decisão fica óbvia sem explicar mecanismo.

### Tela **Formatação** — o controle mora junto do que ele controla

**Ação primária:** ligar/desligar.

```
Formatação
Depois de transcrever, limpar e organizar o texto.

┌───────────────────────────────────────────────────────┐
│  Organizar o texto automaticamente          [ ○——● ]  │  ← PRIMÁRIO
│  Tira vícios de fala, pontua e quebra em parágrafos.  │
│  Custa ~3 a 6 segundos a mais por ditado.             │
└───────────────────────────────────────────────────────┘

   ── daqui para baixo, desabilitado quando o toggle está off ──

┌───────────────────────────────────────────────────────┐
│  Só em ditados acima de   [ 30 ] segundos             │
│  Ditado curto não compensa a espera. No seu histórico,│
│  58% têm menos de 30s — mas os longos concentram 81%  │
│  do que você fala.                                     │
└───────────────────────────────────────────────────────┘

┌─ Como eu quero o texto ───────────────────────────────┐
│  ┌──────────────────────────────────────────────┐    │
│  │ - Tire vícios de fala: "né", "tá", "tipo"... │    │
│  │ - Mantenha meu tom informal e direto         │    │
│  │ - Não traduza termo técnico em inglês        │    │
│  └──────────────────────────────────────────────┘    │
│  Escreva em português normal, como se pedisse para    │
│  uma pessoa.                             [ Salvar ]   │
└───────────────────────────────────────────────────────┘
```

**Por que o toggle e o limiar NÃO vão em Ajustes:** eles controlam esta
feature e só ela. Separar o interruptor do que ele liga obriga o usuário a
percorrer duas telas para uma decisão só. Ajustes continua com o que é
transversal (clipboard, popup).

**Desabilitar em vez de esconder** o limiar e as preferências quando o toggle
está off: o usuário enxerga o que vai ganhar antes de ligar. Esconder faz a
tela parecer vazia e a feature, inexistente.

---

## 3. Estados (contrato 1 — `loading ≠ empty ≠ error ≠ success`)

Leitura de arquivo local é síncrona e instantânea → **não há estado de
loading** nestas telas. Os que existem de verdade:

| Superfície | empty | error | success |
|---|---|---|---|
| Correções | ⚠️ **estado zero é o mais importante** — arquivo novo nasce vazio. Mostrar 2 exemplos reais em texto fantasma dentro do editor, não placeholder genérico | `InfoBar.error` (padrão que já existe) | `InfoBar.success` "Já vale no próximo ditado" |
| Vocabulário | idem, com exemplos | idem | idem |
| Preferências | nunca vazio (cai no `.example` versionado) | idem | idem |
| Toggle / limiar | — | reverter o controle **e** avisar | `InfoBar.success` |

**Toda escrita confirma** — o padrão `InfoBar.success` já existe em
`historico.py:753` e `:819`, com a microcopy certa ("Já vale no próximo
ditado"). Reusar, não inventar outro.

⚠️ **Regra de validação nas Correções:** linha sem `=>` é ignorada em silêncio
pelo `_parse_correcoes` (`dictate.py:356`). Silêncio aqui é falha de estado:
o usuário digita errado e acha que salvou. **Ao salvar, contar as linhas
válidas e dizer**: *"12 regras salvas · 1 linha ignorada (falta `=>`)"*.

---

## 4. A pill durante a normalização (contrato 5 — discoverability + espera)

**O pedido:** algo que faça não sentir os ~3–6s a mais.

**Estado atual:** `rec` (onda+timer) → `busy` (spinner + "transcrevendo…") →
`done` ("colado ✓"). Um `busy` só, indeterminado.

**Desenho:** duas fases nomeadas, com a primeira **marcada como concluída**.

```
fase 1   ◐  transcrevendo…                     (como hoje)
fase 2   ✓ transcrito  ·  ◐ organizando…       (NOVO)
fim      ✓  colado · 8,4s
```

**O princípio:** a ansiedade da espera não vem da duração, vem de não saber se
está progredindo. Marcar a transcrição como **✓ concluída** comunica que o
trabalho essencial já deu certo e o que falta é polimento — e é literalmente
verdade, porque o passe é fail-open: se falhar, o texto de fase 1 é colado
mesmo assim. O usuário nunca está esperando algo que pode perder.

Isso vale mais que um spinner mais bonito: transforma "está travado?" em
"falta a última etapa".

⚠️ A fase 2 **só aparece quando o passe vai rodar de fato** (toggle ligado
**e** duração acima do limiar). Mostrar "organizando" num ditado que não vai
ser organizado é mentir sobre o estado — o mesmo defeito da tela Vocabulário,
em outra escala.

**Mecanismo:** novo `mode="norm"` no `_draw_pill` (`dictate.py:521`), que é
fonte única do overlay e da pill de mãos-livres — os dois ganham o estado sem
código duplicado. Precisa de um sinal novo no `Bridge` para a thread do worker
avisar a thread da UI (a pill só pode ser pintada na thread do Qt — foi a
causa do travamento investigado em 03/08).

---

## 5. Alternativas rejeitadas

| Alternativa | Por que foi descartada |
|---|---|
| **Fundir os 3 arquivos numa sintaxe única** (uma lista onde a linha vira glossário ou correção conforme tenha `=>`) | Elegante, mas quebra o formato dos arquivos que já funcionam e o comportamento de merge é **diferente** entre eles: correções **somam** (`.example` + local), vocabulário e preferências **substituem**. Unificar a UI sobre semânticas divergentes esconde uma pegadinha em vez de resolvê-la. |
| **Toggle + limiar na aba Ajustes** | Separa o interruptor da coisa que ele liga. O usuário teria que ir a Formatação para escrever as preferências e a Ajustes para ativá-las. |
| **Esconder limiar/preferências quando desligado** | Deixa a tela vazia e faz a feature parecer inexistente. Desabilitado comunica "existe, está off". |
| **Barra de progresso determinada na fase 2** | Não há como estimar: medido 3,1–6,1s variando com o tamanho do texto. Barra que anda errado é pior que spinner honesto. |
| **Colar o texto cru na hora e substituir pelo tratado depois** | Mataria a espera, mas o texto já estaria no editor do usuário — substituir exigiria selecionar e reescrever conteúdo que ele pode já ter editado. Invasivo e sujeito a corromper trabalho. |
| **Manter "Vocabulário" como tela isolada e criar "Correções" separada** | Mantém a alavanca morta com o mesmo peso visual da que funciona, e espalha um problema só ("palavra sai errada") por duas telas. |
| **Auto-add automático** (detectar edição do usuário e virar regra sozinho, como o Wispr Flow) | O app não observa o campo onde colou — não há como detectar a correção. O botão "Copiar para cima" entrega 80% do valor sem inventar telemetria. |

---

## 6. Handoff

Estrutura fechada. Passa para **`ui-ux-pro-max`**: tema quase-preto `#070708`,
acento laranja `#F2A33C`, QFluentWidgets 1.11.2 (`isTransparent=True` nos
`addSubInterface`, senão a lib pinta painel `#272727`).

Pontos que precisam de decisão estética:
- os *chips* `[garantia]` / `[dica]` — peso e cor sem virar semáforo berrante;
- a fase 2 da pill em 240×36 com "✓ transcrito · ◐ organizando…" sem apertar;
- o estado desabilitado dos blocos de Formatação (legível, não apagado).
