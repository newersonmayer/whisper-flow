# Veredito de estética — microfone que não abre

Refinamento dentro de um estado existente. Nada de paleta, fonte ou componente novo.

## Paleta

Reaproveitada do estado `fail` em `_draw_pill`, sem alteração:

| token | valor | onde |
|---|---|---|
| fundo da pill | `#060607` (alpha 250) | pill inteira |
| texto de erro | `#F87171` | `✕  microfone não abriu` |

## Contraste (medido com `scripts/contrast.py`)

| par | ratio | piso |
|---|---|---|
| `#F87171` sobre `#060607` | **7,32:1** | 4,5:1 |

Cor não é o único sinal: o `✕` e o texto carregam o significado, e o bipe de erro reforça.

## Tipografia

Segoe UI 10pt DemiBold, centralizado — a mesma dos flashes `done`/`fail`. Largura medida no
`_ux-veredito.md` (204px de 240px a 125%). No macOS a Segoe UI não existe e o Qt usa a fonte
do sistema; a medição de lá fica pendente (sem hardware).

## Motion e duração

Sem animação nova: o `fail` é estático. Duração 2.400ms (justificativa de UX no
`_ux-veredito.md`). O repaint de 30fps e o `_end_flash` existentes cuidam de sumir.

## Paletas rejeitadas

- **Laranja `#F2A33C` (acento) para diferenciar de "falhou na API":** o acento significa
  "a parte ativa" no produto (ver `#02`); usar em erro quebraria esse sentido.
- **Vermelho mais forte:** 7,32:1 já sobra; mais saturado só competiria com o ponto REC.

## Verificação

Conferido por medição (fonte e contraste). Visual na tela não conferido: o app vivo roda da
pasta principal, não desta worktree.
