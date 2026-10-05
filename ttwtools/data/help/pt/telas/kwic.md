---
titulo: KWIC (concordância)
resumo: Cada ocorrência da busca no centro, com as palavras de cada lado.
relacionados: dispersao, keyness
---
O **KWIC** (*key word in context*) lista cada ocorrência da busca alinhada no centro, com N palavras à esquerda e à direita, o arquivo e a posição no texto.

A busca aceita: palavra (`casa`), frase (`black cat`), curingas (`cas*`), expressão regular (`/^run(s|ning)?$/`), lema (`lemma=run`), classe (`pos=NOUN`) e combinações. O `&` junta condições no mesmo token (`lemma=run&pos=VERB`); o `|` cria alternativas no mesmo campo (`tag=PASS|NN`, `pos=NOUN|VERB`). Lema e classe precisam de uma camada etiquetada.

## Como ler
- Ordenar pela palavra à esquerda ou à direita agrupa os usos parecidos e revela padrões (colocações, construções).
- Clique numa linha para abrir o texto na posição da ocorrência.

## Cuidados
- Uma forma pode ter vários sentidos: leia as linhas antes de concluir.
- A frase mostrada é aproximada (pontuação) quando a camada não traz a segmentação.
