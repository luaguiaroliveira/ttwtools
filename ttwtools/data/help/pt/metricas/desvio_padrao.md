---
titulo: Desvio-padrão (SD)
resumo: Mede o quanto, em média, as taxas dos textos se afastam da média; é a "régua" do d de Cohen.
relacionados: kfa, cohens_d, dispersao
---
O desvio-padrão (SD, de *standard deviation*) [mede o quanto, em média, as taxas dos textos se afastam da média]{marca amarelo}. Quanto maior o SD, mais o atributo varia de texto para texto. Ele é construído em quatro passos.

1. Encontre a **média** (M) das taxas.
2. Para cada texto, calcule o **desvio** em relação à média: taxa menos M.
3. **Eleve ao quadrado** cada desvio, some e divida por (n menos 1). Isso é a **variância**.
4. Tire a **raiz quadrada** da variância. Isso é o **SD**.

$$\text{variância} = \frac{\sum (x_i - M)^2}{n - 1}$$
$$SD = \sqrt{\text{variância}}$$

## Exemplo
O Corpus A tem taxas 2, 4, 4, 6, então M = 4. Os desvios são −2, 0, 0, +2, e seus quadrados são 4, 0, 0, 4. A variância é $8/3 \approx 2{,}67$, então $SD \approx 1{,}63$.

O Corpus B tem taxas 0, 4, 4, 8: a mesma média (4), mas maior dispersão. A variância é $32/3 \approx 10{,}67$, então $SD \approx 3{,}27$.

[Duas médias iguais podem esconder dispersões muito diferentes]{marca amarelo}: é por isso que a KFA não compara só as médias.

## Desvio-padrão combinado (na KFA)
O *d* de Cohen divide a diferença entre as médias por [**um único número** que reúne a dispersão dos dois corpora]{sublinhado azul}: o desvio-padrão combinado.

$$\text{kfa:}\quad SD_{\text{combinado}} = \sqrt{\frac{SD_1^2 + SD_2^2}{2}}$$
$$\text{kfa2:}\quad SD_{\text{combinado}} = \sqrt{\frac{(n_1 - 1)\,SD_1^2 + (n_2 - 1)\,SD_2^2}{n_1 + n_2 - 2}}$$

Na kfa os dois corpora pesam igual; na kfa2 (para corpora com números diferentes de textos) o corpus maior pesa mais, porque sua estimativa de variação é mais confiável.

## Como ler
- [SD pequeno: os textos são consistentes]{marca verde}; uma diferença pequena entre as médias já é marcante.
- [SD grande: os textos são heterogêneos]{marca verde}; é preciso uma diferença maior entre as médias para o atributo ser key.
- O SD tem a mesma unidade da taxa (por exemplo, ocorrências por 1.000 palavras).
