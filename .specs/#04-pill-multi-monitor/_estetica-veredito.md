# Veredito estético — pill visível após mudança de monitor

## Direção

Não haverá redesenho. O defeito é geométrico: a animação existente já recebe
frames e pinta corretamente, mas a janela pode ficar fora da tela. Preservar o
visual evita confundir uma correção de posicionamento com uma mudança de
identidade ou de feedback.

A busca geral da skill sugeriu padrões de landing page (`Horizontal Scroll`,
`Exaggerated Minimalism`, tipografia Inter e fundo claro). Foram rejeitados por
não se aplicarem a uma pill desktop de 240×36 px, temporária e não ativável.

## Paleta escolhida

Tokens existentes, mantidos sem alteração:

| Token | Valor | Uso |
|---|---|---|
| fundo | `#060607` | corpo da pill |
| texto de processamento | `#C9C9CE` | `transcrevendo` e `organizando` |
| onda | `#9A9AA0` | níveis de áudio |
| REC | `#EB4646` | ponto pulsante de gravação |
| timer | `#E3E3E7` | tempo de captura |

## Paletas rejeitadas

- **Preto, branco e dourado sugeridos pela busca genérica:** linguagem de
  landing/luxo; trocaria a semântica já estabelecida de gravação em vermelho.
- **Mais contraste ou cores mais saturadas:** não tornariam visível uma janela
  cuja coordenada está abaixo do monitor.
- **Fundo claro:** quebra a identidade dark discreta e chamaria mais atenção do
  que o necessário durante a fala.

## Contrastes calculados

Medições feitas com `scripts/contrast.py`:

| Par | Razão | Alvo | Resultado |
|---|---:|---:|---|
| `#C9C9CE` sobre `#060607` | `12,28:1` | `4,5:1` | passa |
| `#9A9AA0` sobre `#060607` | `7,24:1` | `4,5:1` | passa |
| `#EB4646` sobre `#060607` | `5,30:1` | `3:1` | passa |
| `#E3E3E7` sobre `#060607` | `15,82:1` | `4,5:1` | passa |

## Par tipográfico

Mantém `Segoe UI`, fonte nativa já usada pela aplicação: 8 pt para estados de
processamento, 9 pt semibold no timer e 10 pt semibold no resultado. Inter foi
rejeitada porque exigiria dependência/instalação e alteraria métricas já medidas
para o espaço útil da pill.

## Interação e motion

- Mantém o repaint de 33 ms (~30 fps), a onda de áudio e o ponto REC pulsante.
- Mantém spinner/arco animado nos estados `busy` e `norm`.
- Não introduz transição de entrada/saída nem anima largura, altura ou posição.
- A posição é recalculada antes de cada `show()`, usando a área de trabalho atual.
- `prefers-reduced-motion` é uma primitiva web e não existe neste stack PyQt.
  Respeitar a preferência equivalente do Windows exigiria decisão própria e não
  faz parte desta correção de visibilidade; o motion existente não será ampliado.

## Checklist do recorte

- Nenhum ícone, botão, cor, fonte ou hierarquia novos.
- Nenhum layout shift: dimensões permanecem 240×36 px no overlay.
- Movimento usa apenas repaint do conteúdo; posicionamento acontece antes da
  exibição e não anima a janela pelo desktop.
- As duas superfícies (`Overlay` e `HandsFreeWindow`) compartilham a mesma regra
  de posicionamento, evitando divergência entre hotkeys.
