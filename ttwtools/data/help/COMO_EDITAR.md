# Como editar os verbetes de Aprender

Cada verbete é um arquivo Markdown: `data/help/<idioma>/<área>/<id>.md` (`pt/` e `en/`).
Edite em qualquer editor (o Obsidian serve) e **recarregue a página** do aplicativo: o texto
de um verbete já existente é lido do arquivo a cada abertura. Verbete **novo** pede reiniciar o servidor.

## Cabeçalho

    ---
    titulo: Key Feature Analysis (KFA)
    resumo: uma frase (vira o balão curto e o cartão da lista)
    relacionados: cohens_d, desvio_padrao
    ---

## Texto

`## Título`, `**negrito**`, `*itálico*`, `` `código` ``, listas (`- ` e `1. `), citações (`> `),
tabelas (`| a | b |`), fórmulas (`$d$` no texto; `$$...$$` sozinho na linha),
blocos recolhíveis (`:::details Título` ... `:::`) e linha `---`.
`::cohen-widget::` (sozinho na linha) insere o widget interativo: não apague.

## Destaques animados (rough-notation)

Marque o trecho com colchetes e, logo depois, o estilo entre chaves:

    [método quantitativo]{sublinhado}
    [atributos que distinguem]{circulo azul}
    ==ideia central==                      (atalho de marca-texto)

| Estilo | Efeito | | Cor (opcional) |
|---|---|---|---|
| `marca` | marca-texto | | `laranja` `azul` `verde` |
| `sublinhado` | traço embaixo | | `roxo` `amarelo` `rosa` |
| `circulo` | contorno ao redor | | sem cor = cor dominante do tema |
| `caixa` | retângulo | | |
| `riscado` · `cruz` · `colchete` | riscar, cortar em X, colchete | | |

Estilo e cor podem vir em qualquer ordem (`{azul caixa}`); também valem os nomes em inglês
(`underline`, `circle`, `box`, `blue`...). Os destaques se desenham quando o trecho entra na tela;
o **olho** no alto do verbete os mostra ou oculta (a escolha fica guardada). Use poucos: um ou dois por parágrafo, no que o leitor não pode perder.

## Antes de guardar

    python -m ttwtools help --check          # tradução faltando, relacionados e destaques inválidos

Mantenha `pt/` e `en/` em paralelo. `libs/ttwtools` é outro repositório: commit e push nele primeiro, depois o ponteiro no app.
