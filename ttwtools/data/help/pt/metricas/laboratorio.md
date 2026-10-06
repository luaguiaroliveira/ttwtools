---
titulo: Laboratório: comparar N grupos
resumo: Métodos experimentais para comparar três ou mais grupos de textos pelos atributos de uma camada.
relacionados: cohens_d, keyness
---
[Um **grupo** é um corpus inteiro ou os textos de um corpus com certo metadado (nível, autor, década...)]{marca amarelo}. [Todos os métodos partem da mesma tabela: cada texto com a frequência de cada atributo **por 1000 palavras**]{marca amarelo}.

- **Um contra todos:** o d de Cohen de cada grupo contra os demais juntos. [Diz o que distingue cada grupo]{marca verde}.
- **Par a par:** o d de Cohen de cada par; a matriz mostra a média de $\lvert d\rvert$ (quanto maior, mais distantes).
- **Atributos que variam entre os grupos:** teste de Kruskal-Wallis por atributo, com tamanho de efeito ($\varepsilon^2$: 0,01 pequeno, 0,08 médio, 0,26 grande) e p corrigido.
- **Espaço de perfis:** PCA dos textos, cada ponto colorido pelo grupo.
- **Dendrograma:** agrupa os perfis médios dos grupos (Ward, atributos padronizados): quem se parece com quem.
- **Meu texto contra referências:** o primeiro grupo contra cada um dos outros; a distância é a raiz do $z^2$ médio (0 = igual à média da referência) e os atributos são os que mais afastam.

## Cuidados
- [É **exploratório**: os métodos estão em avaliação e a API pode mudar]{marca rosa}.
- [Muitos atributos × muitos grupos = muitos testes]{marca rosa}: olhe tamanhos de efeito e p corrigido.
- [Grupos com menos de 5 textos dão estimativas instáveis]{marca rosa}; grupos de tamanhos muito diferentes pedem cuidado (a métrica kfa2 pondera pelo tamanho).
