---
titulo: Dispersão (DP de Gries e Range)
resumo: Se uma palavra está espalhada pelo corpus ou concentrada em poucos textos.
relacionados: keyness, kwic
---
[A frequência não diz **onde** a palavra aparece]{marca amarelo}. Duas palavras com 100 ocorrências podem estar em todos os textos ou num só.

- **Range:** em quantos textos a palavra aparece.
- **DP de Gries:** compara a parte das ocorrências em cada texto com a parte que o texto representa no corpus. [DP = ½ Σ |oᵢ − eᵢ|]{sublinhado azul}. **0** = espalhada como o esperado; perto de **1** = concentrada. O DP normalizado vai de 0 a 1 independentemente do número de textos.

O gráfico de "código de barras" mostra cada ocorrência como um traço na posição relativa dentro de cada texto.

## Como ler
- [Palavra-chave com DP alto e range baixo costuma ser tópico de um texto, não do corpus]{marca verde}.

## Cuidados
- [Com poucos textos, o DP varia muito]{marca rosa}.
- Textos de tamanhos muito diferentes pesam diferente no esperado (eᵢ).
