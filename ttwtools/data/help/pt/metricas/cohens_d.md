---
titulo: d de Cohen
resumo: Tamanho da diferença entre dois grupos, em desvios-padrão. É a medida da KFA.
relacionados: normalizacao_por_mil, tagset_biber
---
O **d de Cohen** diz quanto as médias de dois grupos se afastam, medido em desvios-padrão:

    d = (média₁ − média₂) / desvio-padrão combinado

Na KFA (Biber & Egbert) cada traço é contado por texto (por 1000 palavras) e o d compara o corpus 1 com o corpus 2. O desvio combinado padrão da KFA é √((s₁² + s₂²)/2); a variante "KFA2" pondera pelo tamanho de cada grupo.

## Como ler
- **Sinal:** positivo = o traço é mais frequente no corpus 1; negativo = no corpus 2.
- **Tamanho** (convenção de Cohen): ~0,2 pequeno, ~0,5 médio, ~0,8 ou mais grande.
- Um d de 1,0 quer dizer que as médias estão a um desvio-padrão de distância: as distribuições ainda se sobrepõem bastante.

## Cuidados
- Com poucos textos por grupo, o d é instável: um texto atípico muda muito o valor.
- O d não diz se a diferença é "significativa"; ele mede tamanho, não evidência.
- Traços raros (quase sempre zero) podem dar d grande por acaso.
