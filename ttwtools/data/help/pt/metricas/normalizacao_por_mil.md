---
titulo: Normalização por 1000 palavras
resumo: Frequência relativa que permite comparar textos e corpora de tamanhos diferentes.
relacionados: cohens_d, keyness
---
Um texto de 3000 palavras tende a ter mais ocorrências de qualquer coisa do que um de 500. Para comparar, divide-se a contagem pelo tamanho e multiplica-se por 1000:

    frequência por 1000 = contagem × 1000 / número de palavras

Exemplo: 12 passivas num texto de 2400 palavras = 5 por 1000; 4 passivas em 500 palavras = 8 por 1000. O segundo texto usa **mais** passivas, embora tenha menos ocorrências.

## Como ler
- O número é "quantas vezes a cada 1000 palavras". Para itens raros, use por milhão.
- Nas tabelas de traços (rawcount × norm1000), é a versão normalizada que entra na KFA.

## Cuidados
- Em textos muito curtos, uma ocorrência a mais muda muito o valor.
- O que conta como "palavra" depende da tokenização (tagger); compare números feitos do mesmo jeito.
