---
titulo: Palavras-chave (keyness)
resumo: O que é característico de um corpus quando comparado a uma referência.
relacionados: normalizacao_por_mil, dispersao, kwic
---
Uma **palavra-chave** é mais (ou menos) frequente no corpus-alvo do que se esperaria pela referência. Duas perguntas diferentes:

- **Há evidência de diferença?** → *log-likelihood* (LL). Com 1 grau de liberdade, LL > 3,84 corresponde a p < 0,05 (antes da correção).
- **Qual o tamanho da diferença?** → *log ratio*: 1 = o dobro, 2 = quatro vezes, −1 = metade. *%DIFF* diz o mesmo em porcentagem; *log-odds* dá também um z.

## Como ler
- Olhe evidência (LL, p corrigido) **e** tamanho (log ratio) juntos: palavras muito frequentes têm LL alto mesmo com diferença pequena.
- Itens com sinal "−" são característicos da referência.

## Cuidados
- A referência define o resultado: uma de língua geral mostra gênero e tema; uma do mesmo gênero, diferenças finas.
- Compare corpora etiquetados do mesmo modo (mesmo tagger e versão) quando usar lemas ou classes; o app avisa quando não for o caso.
- Use o filtro de dispersão (número mínimo de textos) para não destacar palavras de um só texto.
