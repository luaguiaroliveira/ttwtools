---
titulo: Normalização por 1000 palavras
resumo: Frequência relativa que permite comparar textos e corpora de tamanhos diferentes.
relacionados: cohens_d, keyness
---
Um texto de 3000 palavras tende a ter mais ocorrências de qualquer coisa do que um de 500. Para comparar, [divide-se a contagem pelo tamanho e multiplica-se por 1000]{marca amarelo}:

$$\text{frequência por 1000} = \frac{\text{contagem} \times 1000}{\text{número de palavras}}$$

Exemplo: 12 passivas num texto de 2400 palavras: $12 \times 1000 / 2400 = 5$ por 1000; 4 passivas em 500 palavras: $4 \times 1000 / 500 = 8$ por 1000. [O segundo texto usa **mais** passivas, embora tenha menos ocorrências]{marca verde}.

## Como ler
- O número é "[quantas vezes a cada 1000 palavras]{marca verde}". Para itens raros, use por milhão.
- Nas tabelas de atributos (rawcount × norm1000), [é a versão normalizada que entra na KFA]{marca verde}.

## Cuidados
- [Em textos muito curtos, uma ocorrência a mais muda muito o valor]{marca rosa}.
- O que conta como "palavra" depende da tokenização (tagger); compare números feitos do mesmo jeito.
