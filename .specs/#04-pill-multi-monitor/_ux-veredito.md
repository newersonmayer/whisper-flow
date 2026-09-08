# Veredito de UX — pill visível após mudança de monitor

## Estrutura

A superfície continua sendo a pill flutuante existente. Sua ação primária é
confirmar, sem roubar foco, que a fala está sendo capturada agora. Ela permanece
centralizada na base do monitor onde está o cursor; nenhuma tela, controle ou
hierarquia nova será criada.

## Estados

Os estados atuais permanecem inalterados:

| Estado | O que comunica |
|---|---|
| `rec` | ponto REC, onda e timer confirmam captura ativa |
| `busy` | spinner e `transcrevendo...` confirmam processamento |
| `norm` | check, arco e `organizando...` confirmam a etapa opcional |
| `done` / `fail` | resultado final antes de a pill desaparecer |

O ajuste vale igualmente para o overlay de hold-to-talk e para a pill do modo
mãos-livres. Em todos os estados, a janela deve ficar inteiramente dentro da
área de trabalho atual do monitor escolhido.

## Fluxo

Entrada e saída não mudam: pressionar a hotkey mostra a pill, soltar inicia a
transcrição e o resultado continua sendo colado no campo em foco. A única
mudança é a fonte da coordenada no Windows: a posição será recalculada contra a
área de trabalho que o sistema informa naquele instante, sem depender da
geometria que o processo Qt guardou antes de um hot-plug ou reposicionamento.

Exemplo real: a animação executou 290 atualizações e o Qt marcou a janela como
visível em `y=1462`; a área de trabalho atual do monitor terminava em `y=1362`.
Para uma pill de 36 px com margem de 14 px, a coordenada correta é `y=1312`.

## Alternativas rejeitadas

- **Aumentar contraste, tamanho ou velocidade da animação:** não corrige a causa;
  a janela inteira estava abaixo da borda do monitor.
- **Reiniciar o processo quando os monitores mudarem:** recupera a posição só
  naquele momento e deixa o defeito voltar na próxima mudança de layout.
- **Voltar sempre para o monitor primário:** torna a pill visível, mas quebra o
  contrato de aparecer no monitor onde o usuário está trabalhando.
- **Confiar no `QScreen.availableGeometry()` e apenas ampliar o clamp:** o clamp
  usa os mesmos limites stale e, portanto, valida uma coordenada que já está
  fora da tela real.

## Também vi — fora deste recorte

O visual e os estados da animação estão funcionando: o log registra frames,
nível de áudio e `visible=True`. Não há evidência de falha no painter, timer ou
captura de áudio; redesenhar a pill ampliaria o escopo sem atacar o defeito.
