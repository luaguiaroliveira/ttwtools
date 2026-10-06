---
titulo: Key Feature Analysis (KFA)
resumo: Método quantitativo que identifica os atributos léxico-gramaticais que distinguem duas variedades de texto, pelo d de Cohen.
relacionados: desvio_padrao, cohens_d, normalizacao_por_mil, tagset_biber, keyness
---
> **Em uma frase:** a análise de KF é um [método quantitativo]{sublinhado azul} para identificar os [atributos léxico-gramaticais que distinguem]{marca amarelo} duas variedades de texto.

**Definição.** A análise de KF (Key Feature Analysis, de Egbert e Biber) é um método exploratório e quantitativo para comparar duas variedades de texto (corpora ou sub-corpora). Ela parte de um conjunto de [atributos léxico-gramaticais funcionalmente motivados]{sublinhado azul}, [mede a taxa de ocorrência de cada atributo em cada texto]{marca amarelo} e identifica os que distinguem as duas variedades por meio do *d* de Cohen, que expressa [a diferença entre os dois corpora em relação à variação entre os textos]{marca amarelo}.

**Como usar esta página.** Clique no título de uma caixa para ver uma explicação extra e [mova os controles da seção 4]{marca verde} para ver como o *d* muda.

---

## 1. A resposta em 30 segundos
| Passo | Pergunta        | Resposta                                                                                                         |
| :---- | :-------------- | :--------------------------------------------------------------------------------------------------------------- |
| 1     | O que eu tenho? | Duas variedades de texto (corpora) e um conjunto de atributos funcionalmente motivados                           |
| 2     | O que eu quero? | Os atributos léxico-gramaticais que distinguem as duas variedades                                                |
| 3     | Como é medido?  | A diferença entre os dois corpora, padronizada pelo quanto o atributo varia entre os textos (**o *d* de Cohen**) |
| 4     | Como leio?      | $\lvert d\rvert$ grande = forte marcador de um corpus; $\lvert d\rvert$ pequeno = parecido nos dois              |

## 2. Quando usar
- Comparar dois registros ou variedades de texto.
- Comparar duas plataformas, autores ou grupos.
- Escolher atributos para ensinar ou para analisar em detalhe.

:::details Qual é a diferença em relação à análise de palavras-chave?
A análise de palavras-chave procura palavras (ou classes gramaticais) significativamente mais ou menos usadas em todo um corpus. A análise de KF [trabalha **por texto**, com **atributos escolhidos funcionalmente**, e reporta um **tamanho de efeito**]{marca amarelo} (o quanto a diferença é grande), [não uma decisão de sim/não sobre significância]{marca rosa}.
:::

## 3. O *d* de Cohen na análise de KF: a ideia
Na análise de KF, [calculamos um valor de *d* de Cohen para **cada atributo**]{marca amarelo}, e cada valor compara o mesmo atributo em dois corpora. O eixo x é a taxa do atributo em um texto; cada texto do corpus fornece um ponto, e a curva é a distribuição dessas taxas. As duas curvas são o mesmo atributo medido no Corpus 1 e no Corpus 2, nunca dois atributos diferentes.
- [**O centro da curva**]{sublinhado azul} é a média (M): a taxa média do atributo entre os textos daquele corpus.
- [**A largura da curva**]{sublinhado azul} é a dispersão das taxas em torno dessa média, resumida pelo desvio-padrão (SD): o quanto o atributo varia de texto para texto.
- [$d = \dfrac{\text{diferença entre as médias}}{\text{dispersão}}$]{marca amarelo}. Um $\lvert d\rvert$ grande [significa que o atributo é distintivo de um corpus em comparação com o outro]{marca verde}.

:::details Por que dividir pela dispersão?
[A dispersão é a régua]{sublinhado azul}. [A mesma distância entre as duas médias vale mais quando os textos são consistentes (dispersão pequena) e menos quando são heterogêneos (dispersão grande)]{marca verde}. Uma diferença de 3 ocorrências por 1.000 palavras é um marcador forte se os textos variam cerca de 2, mas fraco se variam cerca de 15.
:::

## 4. Como o *d* é calculado (passo a passo)
$$d = \frac{M_1 - M_2}{SD_{\text{combinado}}}$$

- **$M_1$, $M_2$**: as médias do atributo (a taxa média entre os textos) nos dois corpora.
- **$SD_{\text{combinado}}$**: o desvio-padrão combinado, [um único número para o quanto os textos variam dentro dos dois corpora]{marca amarelo}. É o denominador do *d*, então [define a unidade (a régua) com que a diferença entre as médias é medida]{marca verde}. Veja o cartão **Desvio-padrão (SD)**.

$$SD_{\text{combinado}} = \sqrt{\frac{SD_1^2 + SD_2^2}{2}}$$

**Exemplo resolvido.** Atributo: pronomes de primeira pessoa (por 1.000 palavras).
- Taxas do Corpus 1: 2, 4, 6 → média 4.
- Taxas do Corpus 2: 5, 7, 9 → média 7.

:::details Passo 1. As médias
$M_1 = 4$; $M_2 = 7$.
:::
:::details Passo 2. A distância (numerador)
$M_1 - M_2 = 4 - 7 =$ **$-3$**. [O sinal negativo indica que o atributo é mais frequente no **Corpus 2**]{marca verde}.
:::
:::details Passo 3. A dispersão (denominador)
Cada corpus tem desvio-padrão 2. O desvio-padrão combinado é $\sqrt{(2^2 + 2^2)/2} =$ **$2$**.
:::
:::details Passo 4. Divida
$d = -3/2 =$ **$-1{,}5$** → [efeito grande: o atributo é fortemente distintivo do Corpus 2]{marca verde}.
:::

**Experimente.** Mova os controles para ver como as duas médias e o desvio-padrão combinado mudam o *d*.

::cohen-widget::

## 5. Como ler o valor de *d*
| $\lvert d\rvert$ | Leitura | Sobreposição entre os corpora |
| :--------------- | :------ | :---------------------------- |
| < 0,20           | não key | quase total                   |
| ≈ 0,20           | pequeno | alta                          |
| ≈ 0,50           | médio   | moderada                      |
| ≥ 0,80           | grande  | baixa                         |

- [O **sinal** indica a direção: **positivo → Corpus 1**, **negativo → Corpus 2**]{marca verde}.
- [Esses pontos de corte são convenções, não leis fixas]{marca rosa}.

:::details Um atributo raro pode ser key?
Sim. [Um atributo raro pode ser fortemente key se for usado de forma consistente em um corpus e quase ausente no outro]{marca amarelo}. [A frequência sozinha não decide a keyness]{marca amarelo}.
:::

## 6. Qual método usar: kfa ou kfa2?
| Seus dois corpora            | Use                   |
| :--------------------------- | :-------------------- |
| mesmo número de textos       | **kfa** (Biber, 2023) |
| números diferentes de textos | **kfa2** (ponderada)  |

:::details O que muda no kfa2?
No kfa2, o desvio-padrão combinado é [**ponderado pelo tamanho do corpus**]{sublinhado azul}:

$$SD_{\text{combinado}} = \sqrt{\frac{(n_1 - 1)\,SD_1^2 + (n_2 - 1)\,SD_2^2}{n_1 + n_2 - 2}}$$

[O corpus maior recebe mais peso, porque sua estimativa de variação é mais confiável]{marca verde}.
:::

## 7. Teste você mesmo
:::details 1) Um atributo tem *d* = 0,05. Ele é key?
Não. $\lvert d\rvert$ está abaixo de 0,20 (desprezível).
:::
:::details 2) *d* = −0,70. Qual corpus usa mais o atributo?
O Corpus 2 (o sinal é negativo).
:::
:::details 3) O atributo A tem $\lvert d\rvert$ = 0,30; o atributo B tem $\lvert d\rvert$ = 1,20. Qual é mais distintivo?
O atributo B.
:::
:::details 4) Os corpora têm 50 e 120 textos. Qual método?
kfa2, porque os corpora têm números diferentes de textos.
:::

## 8. Análise funcional
A parte quantitativa termina com o ranking por $\lvert d\rvert$. Esse ranking diz **quais** atributos são key e **para qual corpus**, [mas não diz **por quê**]{marca rosa}. [A última etapa é qualitativa: interpretamos a função que cada atributo key desempenha na variedade]{marca amarelo}, com base em exemplos dos textos.
- [Parta de **exemplos dos dois corpora**, e não apenas do valor de *d*]{marca verde}.
- Baseie a interpretação na **gramática**, em **pesquisas anteriores** e na **situação** da variedade (quem comunica, com quem e com que propósito).
- [Pergunte o que o atributo **ajuda o autor ou falante a fazer** naquela variedade]{marca verde}.
- Apresente a interpretação com **evidências** (padrões e linhas de concordância, no KWIC ou no Leitor).

## 9. Avisos
- [O *d* é uma **aproximação**: pressupõe dados aproximadamente normais e variâncias semelhantes]{marca rosa}. Dados linguísticos costumam ser assimétricos.
- [O *d* **não** é um teste de significância: não diz se a diferença pode ser devida ao acaso]{sublinhado vermelho}.
- [Corpora pequenos geram valores instáveis]{marca rosa}.
- Confira sempre **exemplos dos textos**, e não apenas o número.
- [Todo valor é relativo ao corpus usado como referência]{marca rosa}.
