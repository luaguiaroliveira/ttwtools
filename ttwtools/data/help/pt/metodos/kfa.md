---
titulo: Análise de Key-Features (KFA)
resumo: Compara dois conjuntos de textos atributo a atributo, pelo tamanho de efeito (d de Cohen).
relacionados: cohens_d, normalizacao_por_mil, tagset_biber, keyness
---
A **análise de Key-Features** (KF analysis, de Egbert e Biber) compara dois conjuntos de textos — dois corpora ou dois grupos do mesmo corpus — e mostra quais **atributos léxico-gramaticais** (tempos verbais, pronomes, passivas, modalizadores...) caracterizam cada lado. Ela responde à pergunta "o que distingue este registro daquele?".

## Como funciona
A KFA segue seis passos:
1. Escolha os dois lados da comparação (alvo × referência, ou dois grupos).
2. Selecione atributos **motivados por uma pergunta linguística** — de preferência atributos já usados na literatura, e não todo o repertório de etiquetas.
3. Conte cada atributo **em cada texto** e normalize (por exemplo, por 1000 palavras).
4. Calcule a média e o desvio-padrão do atributo em cada lado.
5. Calcule o **d de Cohen** do atributo: a diferença das médias expressa em desvios-padrão.
6. Ordene os atributos pelo d e interprete os extremos com exemplos dos próprios textos.

O ponto central é que a unidade de observação é o **texto**, não o corpus inteiro. Quando se compara só a frequência total de dois corpora, perde-se a variação de texto para texto; a KFA mede essa variação no denominador do d. Por isso um atributo só é "key" quando é usado **consistentemente mais** num lado, para além dessa variação natural.

## Como ler
- **Sinal:** positivo = o atributo é mais frequente no lado 1; negativo = mais frequente no lado 2.
- **Tamanho** (convenção de Cohen): |d| ~ 0,2 pequeno; ~ 0,5 médio; 0,8 ou mais grande. São apenas referências: em textos curtos, efeitos grandes podem ser casuais.
- A KFA é **exploratória**: ela ranqueia os atributos pelo tamanho de efeito, mas não decide "significativo / não significativo" como um teste de hipótese.
- Compare com as alternativas: palavras-chave e tags-chave comparam frequências do corpus inteiro; a análise multidimensional (MD) procura dimensões que variam junto. A KFA fica no meio: simples como a keyness, mas olhando cada texto, como a MD.

## Cuidados
- A KFA **não** testa significância: o valor de d não diz se a diferença poderia ser fruto do acaso.
- Atributos raros (quase sempre zero) podem produzir d grande por acaso; um d alto não significa automaticamente "importante".
- A seleção de atributos importa: incluir dezenas de atributos só aumenta a chance de diferenças espúrias. Prefira atributos interpretáveis.
- Todo valor é relativo ao corpus de referência escolhido.
- Interprete sempre o número junto de exemplos reais dos textos (abra o KWIC ou o Leitor), nunca só pela barra do gráfico.

## Referências
- EGBERT, J.; BIBER, D. Key feature analysis: a simple, yet powerful method for comparing text varieties. *Corpora*, v. 18, n. 1, p. 121–133, 2023.
- BIBER, D.; EGBERT, J. *Register Variation Online*. Cambridge: Cambridge University Press, 2018.
- BIBER, D. *Variation across Speech and Writing*. Cambridge: Cambridge University Press, 1988.
- BREZINA, V. *Statistics in Corpus Linguistics: A Practical Guide*. Cambridge: Cambridge University Press, 2018.
