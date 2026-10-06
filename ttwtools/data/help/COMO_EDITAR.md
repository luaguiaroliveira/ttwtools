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

## Imagens

Coloque o arquivo em `data/help/assets/` e referencie pelo caminho da API:

    ![descrição da imagem](/api/help/assets/nome.png)

A descrição (`alt`) é lida por leitores de tela e aparece se a imagem não carregar; escreva-a
completa. Use imagens pequenas (PNG/JPG) e nome sem espaços.

## Destaques (marca-texto e caneta)

Duas "canetas": **marca-texto** (`marca`) e **caneta de tinta** (`sublinhado`). Marque o trecho com colchetes e,
logo depois, o estilo e a cor entre chaves:

    [diz quão distantes estão as médias]{marca amarelo}
    [razão sinal/ruído]{sublinhado azul}
    ==ideia central==                      (atalho: marca-texto amarelo)

Cores: `amarelo` `rosa` `verde` `azul` `laranja` `roxo` `vermelho` `preto` (ou em inglês: `yellow` `pink` `green`
`blue` `orange` `purple` `red` `black`). Também vale hexadecimal: `{marca #ffd400}`. Sem cor: marca amarela e tinta azul.
Estilo e cor podem vir em qualquer ordem. **Use as mesmas cores em `pt/` e `en/`.**

Convenção dos verbetes (para o leitor aprender o código de cores):

| Uso | Estilo |
|---|---|
| ideia central, definição | `marca amarelo` |
| como ler, o que fazer | `marca verde` |
| cuidado, limite | `marca rosa` |
| termo-chave, fórmula | `sublinhado azul` |
| alerta forte (o erro mais comum) | `sublinhado vermelho` |

Os destaques começam **ocultos**: o leitor clica no **olho** no alto do verbete para vê-los, e cada trecho se desenha
(como escrito à mão) ao entrar na tela. Use poucos: um ou dois por parágrafo, só no que não pode ser perdido.

## Fórmulas

Sempre em KaTeX, nunca em código nem em texto solto: `$d$`, `$S_{\text{comb}}$` no meio do texto e `$$d = \frac{M_1 - M_2}{SD}$$` sozinho na linha.
Uma fórmula também pode receber destaque: `[$d = \dfrac{a}{b}$]{marca amarelo}`. Evite bloco indentado (vira código) e crases para fórmulas.

## Antes de guardar

    python -m ttwtools help --check          # tradução faltando, relacionados e destaques inválidos

Mantenha `pt/` e `en/` em paralelo. `libs/ttwtools` é outro repositório: commit e push nele primeiro, depois o ponteiro no app.
