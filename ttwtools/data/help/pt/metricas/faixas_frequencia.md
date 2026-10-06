---
titulo: Faixas de frequência lexical
resumo: Quanto do texto está entre as palavras mais comuns de uma referência.
relacionados: keyness, normalizacao_por_mil
---
Ordena-se o vocabulário da **referência** da palavra mais frequente para a menos frequente. [Cada palavra do seu corpus cai numa **faixa** pela posição que ocupa ali]{marca amarelo}: entre as 1.000 primeiras, entre 1.001 e 2.000, e assim por diante; o que não aparece na referência fica **fora da lista**. É o *perfil de frequência lexical* de Laufer & Nation (1995).

## Como ler
- **Ocorrências** (%): quanto do texto corrido está em cada faixa. Em inglês geral, [as 2.000 palavras mais frequentes costumam cobrir perto de 80% de um texto]{marca verde}.
- **Tipos** (%): quanto do vocabulário distinto está em cada faixa.
- [Muita coisa **fora da lista** indica vocabulário técnico, nomes próprios, grafias diferentes ou uma referência de outra variedade ou época]{marca verde}.

## Cuidados
- [O resultado depende da referência (tamanho, época, variedade, gênero) e da unidade]{marca rosa}: com **lema**, *ran* e *runs* contam como *run*; com **forma**, não.
- Use a mesma etiquetagem (tagger e versão) no corpus e na referência quando a unidade for lema.
