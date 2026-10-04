---
titulo: d de Cohen
resumo: Tamanho da diferença entre dois grupos, em desvios-padrão. É a medida da KFA.
relacionados: kfa, normalizacao_por_mil, tagset_biber
---
O **d de Cohen** é uma medida de **tamanho de efeito**: diz quão distantes estão as médias de dois grupos, medido em unidades de desvio-padrão. Foi proposto por Jacob Cohen (1988) e é a medida que a KFA usa para comparar dois conjuntos de textos.

Na análise de corpus, o "grupo" é um conjunto de textos e a "observação" é a taxa do atributo em cada texto, normalmente por 1000 palavras:

    d = (média₁ − média₂) / desvio-padrão combinado

O numerador é o **sinal**: o quanto os dois lados estão distantes. O denominador é o **ruído**: o quanto os textos variam dentro de cada lado. Assim, d é uma razão sinal/ruído — um d grande quer dizer que a diferença entre os lados é grande *em relação* à variação entre os textos.

## O desvio-padrão combinado
Há duas formas de juntar os desvios dos dois lados, e a escolha depende de os lados terem ou não o mesmo número de textos:

- **KFA (Biber & Egbert):** média simples das variâncias — `Spooled = √((s₁² + s₂²) / 2)`; use quando os dois lados têm o **mesmo número de textos**.
- **KFA ponderada:** pondera cada variância pelo número de textos do lado — `Spooled = √(((n₁−1)·s₁² + (n₂−1)·s₂²) / (n₁+n₂−2))`; indicada quando os lados têm **números diferentes de textos**.

## Um exemplo
Egbert e Biber (2023) comparam verbos de comunicação em blogs pessoais (lado 1) e outros registros online (lado 2). Média₁ = 61,53 (s₁ = 27,23) e média₂ = 26,48 (s₂ = 23,08):

    Spooled = √((27,23² + 23,08²) / 2) = 25,24
    d = (61,53 − 26,48) / 25,24 = 1,39

Um d de 1,39 é um efeito grande: a média dos blogs está cerca de 1,4 desvio-padrão acima da dos outros registros.

## Como ler
- **Sinal:** positivo = o atributo é mais frequente no lado 1; negativo = no lado 2.
- **Tamanho** (convenção de Cohen): ~0,2 pequeno, ~0,5 médio, ~0,8 ou mais grande.
- d é contínuo e comparável entre atributos, mesmo que uns sejam raros e outros frequentes.
- Um d de 1,0 quer dizer que as médias estão a um desvio-padrão de distância: as distribuições ainda se sobrepõem bastante.
- O gráfico interativo "Como o d de Cohen muda" mostra essa sobreposição variando o d.

## Cuidados
- O d **não** é um teste de significância: ele mede o tamanho da diferença, não a evidência de que ela exista. Significância, importância prática e relevância linguística são coisas distintas (Brezina 2018).
- Com poucos textos por lado, o d é instável: um texto atípico muda muito o valor. O ideal é reportar também um intervalo de confiança.
- O cálculo supõe taxas aproximadamente normais e variâncias parecidas. Muitos atributos têm muitos zeros e poucos valores altos (distribuição assimétrica); nesses casos o d é só uma aproximação, e existe uma versão robusta (médias aparadas e desvios winsorizados).
- Atributos raros (quase sempre zero) podem dar d grande por acaso.
- Interprete o d sempre junto com exemplos dos textos, não pelo número isolado.

## Referências
- BREZINA, V. *Statistics in Corpus Linguistics: A Practical Guide*. Cambridge: Cambridge University Press, 2018. (cap. 6 e 8: tamanho de efeito, d e r)
- EGBERT, J.; BIBER, D. Key feature analysis: a simple, yet powerful method for comparing text varieties. *Corpora*, v. 18, n. 1, p. 121–133, 2023.
- GRIES, S. Th. *Statistics for Linguistics with R: A Practical Introduction*. 2. ed. Berlim: De Gruyter Mouton, 2013.
- COHEN, J. *Statistical Power Analysis for the Behavioral Sciences*. 2. ed. Hillsdale: Erlbaum, 1988.
