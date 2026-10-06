---
titulo: Tags dos etiquetadores
resumo: O que cada etiquetador produz e o que cada tag significa.
relacionados: tagset_biber, cohens_d, normalizacao_por_mil
---
Cada [**etiquetador**]{sublinhado azul} (spaCy, Stanza, BiberPlus, MFTE) [marca as palavras do corpus com um **repertório de tags** diferente]{marca amarelo}. Os principais:

- [**UPOS** (Universal Dependencies)]{sublinhado azul}: as classes gramaticais universais — NOUN, VERB, ADJ, ADP, PRON... vale para qualquer idioma.
- [**Penn Treebank (XPOS)**]{sublinhado azul}: classes mais finas do inglês (NN, NNS, VBD, JJ...).
- [**Biber**]{sublinhado azul}: os atributos léxico-gramaticais da análise multidimensional (categorias A a P).
- [**MFTE**]{sublinhado azul}: atributos funcionais do inglês, documentados um a um.

[O que aparece depende de **duas coisas**: do etiquetador e da **configuração** escolhida]{marca amarelo}. Por exemplo, no MFTE só entram as colunas cujos componentes estão ligados; no Stanza em português não há XPOS. Escolha o etiquetador e, quando houver mais de um, o repertório. A tabela mostra a tag, o grupo, a definição e um exemplo.

## Cuidados
- [A etiquetagem é automática: confira alguns exemplos no KWIC antes de tirar conclusões]{marca rosa}.
- Tags de repertórios diferentes têm nomes parecidos; confira no seletor de qual repertório elas vieram.

## Referências
- Universal Dependencies (Nivre et al.): https://universaldependencies.org/u/pos/
- Marcus, M.; Santorini, B.; Marcinkiewicz, M. A. Building a Large Annotated Corpus of English: The Penn Treebank. *Computational Linguistics*, 1993.
- Biber, D. *Variation across Speech and Writing*. Cambridge: Cambridge University Press, 1988.
- MFTE — Multidimensional Functional Tagging of English (Lee et al., 2024).
