---
titulo: d de Cohen
resumo: Tamanho da diferença entre dois grupos, em desvios-padrão. É a medida da KFA.
relacionados: kfa, desvio_padrao, normalizacao_por_mil, tagset_biber
---
O **d de Cohen** é uma medida de [**tamanho de efeito**]{sublinhado azul}: [diz quão distantes estão as médias de dois grupos, medido em unidades de desvio-padrão]{marca amarelo}. Foi proposto por Jacob Cohen (1988) e é a medida que a KFA usa para comparar dois conjuntos de textos.

Na análise de corpus, o "grupo" é um conjunto de textos e a "observação" é a taxa do atributo em cada texto, normalmente por 1000 palavras:

$$d = \frac{\text{média}_1 - \text{média}_2}{\text{desvio-padrão combinado}}$$

[O numerador é o **sinal**: o quanto os dois lados estão distantes]{sublinhado azul}. [O denominador é o **ruído**: o quanto os textos variam dentro de cada lado]{sublinhado azul}. Assim, [d é uma razão sinal/ruído]{sublinhado azul} — [um d grande quer dizer que a diferença entre os lados é grande *em relação* à variação entre os textos]{marca amarelo}.

## O desvio-padrão combinado
Há duas formas de juntar os desvios dos dois lados, e a escolha depende de os lados terem ou não o mesmo número de textos:

- **KFA (Biber & Egbert):** média simples das variâncias — $S_{\text{comb}} = \sqrt{\frac{s_1^2 + s_2^2}{2}}$; use quando os dois lados têm o [**mesmo número de textos**]{sublinhado azul}.
- **KFA ponderada:** pondera cada variância pelo número de textos do lado — $S_{\text{comb}} = \sqrt{\frac{(n_1 - 1)\,s_1^2 + (n_2 - 1)\,s_2^2}{n_1 + n_2 - 2}}$; indicada quando os lados têm [**números diferentes de textos**]{sublinhado azul}.

## Um exemplo
Egbert e Biber (2023) comparam verbos de comunicação em blogs pessoais (lado 1) e outros registros online (lado 2). Média₁ = 61,53 (s₁ = 27,23) e média₂ = 26,48 (s₂ = 23,08):

$$S_{\text{comb}} = \sqrt{\frac{27{,}23^2 + 23{,}08^2}{2}} = 25{,}24$$

$$d = \frac{61{,}53 - 26{,}48}{25{,}24} = 1{,}39$$

[Um d de 1,39 é um efeito grande]{marca verde}: a média dos blogs está cerca de 1,4 desvio-padrão acima da dos outros registros.

## Como ler
- **Sinal:** [positivo = o atributo é mais frequente no lado 1; negativo = no lado 2]{marca verde}.
- **Tamanho** (convenção de Cohen): [~0,2 pequeno, ~0,5 médio, ~0,8 ou mais grande]{marca verde}.
- d é contínuo e comparável entre atributos, mesmo que uns sejam raros e outros frequentes.
- [Um d de 1,0 quer dizer que as médias estão a um desvio-padrão de distância: as distribuições ainda se sobrepõem bastante]{marca verde}.
- O gráfico interativo "Como o d de Cohen muda" mostra essa sobreposição variando o d.

## Cuidados
- [O d **não** é um teste de significância]{sublinhado vermelho}: ele mede o tamanho da diferença, não a evidência de que ela exista. Significância, importância prática e relevância linguística são coisas distintas (Brezina 2018).
- [Com poucos textos por lado, o d é instável]{marca rosa}: um texto atípico muda muito o valor. O ideal é reportar também um intervalo de confiança.
- O cálculo supõe taxas aproximadamente normais e variâncias parecidas. Muitos atributos têm muitos zeros e poucos valores altos (distribuição assimétrica); nesses casos o d é só uma aproximação, e existe uma versão robusta (médias aparadas e desvios winsorizados).
- [Atributos raros (quase sempre zero) podem dar d grande por acaso]{marca rosa}.
- [Interprete o d sempre junto com exemplos dos textos, não pelo número isolado]{marca rosa}.

## Referências
- BREZINA, V. *Statistics in Corpus Linguistics: A Practical Guide*. Cambridge: Cambridge University Press, 2018. (cap. 6 e 8: tamanho de efeito, d e r)
- EGBERT, J.; BIBER, D. Key feature analysis: a simple, yet powerful method for comparing text varieties. *Corpora*, v. 18, n. 1, p. 121–133, 2023.
- GRIES, S. Th. *Statistics for Linguistics with R: A Practical Introduction*. 2. ed. Berlim: De Gruyter Mouton, 2013.
- COHEN, J. *Statistical Power Analysis for the Behavioral Sciences*. 2. ed. Hillsdale: Erlbaum, 1988.
