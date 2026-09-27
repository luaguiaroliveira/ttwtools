# Guia rápido do `ttwtools`

Tudo o que o aplicativo TTWtools faz, em Python e na linha de comando. Referência completa de cada função: [`referencia.md`](referencia.md) (gerada das docstrings).

## Instalar

```bash
pip install -e libs/ttwtools              # a partir do código do aplicativo (submódulo)
pip install -e "libs/ttwtools[mfte]"      # + Stanza/MFTE (torch)
python -m spacy download en_core_web_sm   # ou: ttwtools catalog download-model en_core_web_sm
```

`import ttwtools` é rápido: spaCy, pandas e torch só são carregados quando uma função precisa deles.

## Conceitos

- **Projeto** (`.ttwa`): um arquivo SQLite com corpora, documentos (texto e metadados), **camadas** de anotação e análises salvas. `.ttwl` guarda os textos numa pasta ao lado; `.ttwt` é o `.ttwa` comprimido.
- **Camada**: o resultado de um tagger sobre um documento (ferramenta, versão, modelo, opções e tokens com forma, lema, UPOS, XPOS, traços, tags). Etiquetar de novo com a mesma configuração reaproveita a camada.
- **Referência**: outro corpus do projeto, um grupo do mesmo corpus (`rest:<metadado>`), uma lista `.tsv` ou uma lista do catálogo (`catalog:<id>`).

## Um fluxo completo em Python

```python
import ttwtools

with ttwtools.create_project("aula.ttwa") as proj:
    # 1. importar: pasta de .txt, metadados pelo nome do arquivo (aluno_nivel_ano.txt)
    ttwtools.import_corpus(proj, "textos/", "redacoes", filename_fields=["aluno", "nivel", "ano"])

    # 2. visão geral (sem tagger) e etiquetagem com cache de camadas
    ttwtools.describe(proj, "redacoes")
    ttwtools.tag_corpus(proj, "redacoes", "spacy", preset="recomendado")
    ttwtools.tag_corpus(proj, "redacoes", "biberplus")

    # 3. explorar
    ttwtools.search(proj, "redacoes", "lemma=make", group_by="nivel")
    ttwtools.kwic(proj, "redacoes", "pos=ADJ ideas", context=6)
    ttwtools.frequency(proj, "redacoes", unit="lemma", top=50)
    ttwtools.collocates(proj, "redacoes", "make", window=(4, 4))
    ttwtools.dispersion(proj, "redacoes", "however")

    # 4. comparar
    ttwtools.keywords(proj, "redacoes", "rest:nivel", where={"nivel": ["C1"]}, unit="lemma")
    ttwtools.kfa_layers(proj, "redacoes", "redacoes", "biberplus",
                        where1={"nivel": ["B1"]}, where2={"nivel": ["C1"]})
```

Português: detecte o idioma e use as opções sugeridas.

```python
from ttwtools.stats import guess_language
from ttwtools.taggers import language_defaults

lang = guess_language(proj, "corpus_pt")                      # "pt"
ttwtools.tag_corpus(proj, "corpus_pt", "spacy", options=language_defaults("spacy", lang))
```

## Catálogo, referências e faixas de frequência

```python
from ttwtools import corpus_catalog as cc, models

cc.set_setting("catalog_url", "https://.../catalogo.json")   # ou TTWTOOLS_CATALOG_URL
cc.install("brown-lista")                                    # só as listas (pequeno)
ttwtools.keywords(proj, "redacoes", "catalog:brown", unit="lemma")
ttwtools.frequency_bands(proj, "redacoes", "catalog:brown", bands=(1000, 2000, 3000, 5000))
models.download_spacy_model("pt_core_news_sm")               # para a pasta de dados
```

## Laboratório (experimental)

```python
from ttwtools import experimental as ex

grupos = ex.groups_by_metadata(proj, "redacoes", "nivel")
ex.compare_groups(proj, grupos, "biberplus", method="one_vs_rest")   # pairwise, anova, profile, dendrogram, nearest
```

A API do módulo `experimental` pode mudar entre versões.

## Formatos

```python
from ttwtools import formats

formats.import_conllu(proj, "ud.conllu", "ud")           # documento + camada conllu
formats.import_nltk_tagged(proj, "brown/", "brown", tagset="brown")
formats.import_tei(proj, "bnc/", "bnc")                  # TEI P5 e BNC XML
formats.import_graf(proj, "MASC-3.0.0/", "masc")         # standoff GrAF (OANC/MASC)
formats.export_conllu(proj, "redacoes", "saida.conllu", tool="spacy")
formats.export_vrt(proj, "redacoes", "saida.vrt", tool="spacy")
formats.export_tokens(proj, "redacoes", "tokens.csv", fmt="csv")
```

## Linha de comando

`ttwtools --help` lista os subcomandos; cada um tem `--help`, e `--json`/`--csv` mudam a saída. O botão **Copiar como código** do aplicativo gera o comando e o trecho Python de cada análise (`ttwtools.codegen`).

| Subcomando | Faz |
|---|---|
| `import`, `documents` | importar textos (txt, CSV, CoNLL-U, palavra/TAG, TEI, GrAF); listar documentos e metadados |
| `tag`, `tagger-options`, `tagset` | etiquetar; opções de cada tagger com explicações; repertório de tags |
| `describe` | estatísticas do corpus e da camada |
| `search`, `kwic`, `freq`, `collocates`, `dispersion` | exploração |
| `keywords`, `bands`, `reference-list` | palavras-chave, faixas de frequência, gerar lista de referência |
| `compare` | KFA entre dois lados; com `--group-by`/`--group`, N grupos (experimental) |
| `export` | camada em CoNLL-U, VRT, CSV, JSONL, Parquet |
| `catalog` | `list`, `install`, `remove`, `update`, `validate`, `references`, `models`, `download-model` |
| `help` | ajuda sobre conceitos e métricas (`ttwtools help cohens_d`) |

## Variáveis de ambiente

| Variável | Efeito |
|---|---|
| `TTWTOOLS_LANG` | idioma dos textos e avisos (`pt` ou `en`) |
| `TTWTOOLS_DATA_DIR` | pasta de dados (corpora e modelos baixados, `settings.json`) |
| `TTWTOOLS_CATALOG_URL` | endereço do catálogo, se não houver em `settings.json` |
| `STANZA_RESOURCES_DIR` | pasta dos modelos do Stanza |
