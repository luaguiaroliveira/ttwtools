# Exemplos de uso: ttwtools

Este diretório contém seis exemplos progressivos que demonstram como usar o
pacote **ttwtools** para análise de corpus com features linguísticas.  Cada
exemplo segue a mesma estrutura modular: um script `_00_runall.py` que
orquestra o pipeline completo, um script `_01_*` que realiza o tagging e gera
as tabelas de features, e um script `_02_*` que executa a análise estatística
e produz os gráficos.

---

## Visão geral

| # | Script principal | Tagger(s) | Corpora | Objetivo |
|---|------------------|-----------|---------|----------|
| 1 | `exemplo1_00_runall.py` | BiberPlus | subcorpora pequenos | Uso mínimo — sem diretório de saída explícito |
| 2 | `exemplo2_00_runall.py` | BiberPlus | `teste1`, `teste2` | Pipeline completo com `out_test/` e KFA básica |
| 3 | `exemplo3_00_runall.py` | BiberPlus | CorIFA\_100, BAWE\_100 | Pipeline real com 100 documentos por corpus |
| 4 | `exemplo4_00_runall.py` | MFTE | CorIFA\_100, BAWE\_100 | Mesmo pipeline do exemplo 3, usando MFTE |
| 5 | `exemplo5_00_runall.py` | BiberPlus + MFTE (não ext.) | CorIFA\_100, BAWE\_100 | Comparação metodológica: dois taggers, dois gráficos |
| 6 | `exemplo6_00_runall.py` | BiberPlus + MFTE (ext.) | CorIFA\_100, BAWE\_100 | Comparação com MFTE estendido (mais features) |

---

## Exemplo 1 — Uso mínimo do BiberPlus

**Scripts:** `exemplo1_00_runall.py`, `exemplo1_01_biberplus_tagger_generate_tables_raw_and_norm1000.py`,
`exemplo1_02_biber_kfa_analysis_graph.py`

**Descrição:** Demonstra a chamada mais simples ao BiberPlus, sem especificar
diretório de saída.  Os CSVs de contagem bruta e normalizada são gravados na
pasta-pai de cada corpus (ao lado das pastas dos corpora), e a análise KFA é
executada com argparse para aceitar caminhos via linha de comando.

**Corpora usados:**
- `examples/test_corpora/subcorpus_introduction_aphd` — introduções de teses de doutorado
- `examples/test_corpora/subcorpus_introduction_articles` — introduções de artigos científicos

**Saída gerada:** CSVs `_biberfeatures_rawcount.csv` e `_biberfeatures_norm1000.csv` na
pasta `test_corpora/`; gráfico e CSV da KFA no diretório `out_test/` (padrão do script `_02`).

**Como executar:**
```bash
python examples/exemplo1_00_runall.py
# ou individualmente:
python examples/exemplo1_01_biberplus_tagger_generate_tables_raw_and_norm1000.py
python examples/exemplo1_02_biber_kfa_analysis_graph.py \
    --output-dir out_test --corpus1 subcorpus_introduction_aphd \
    --corpus2 subcorpus_introduction_articles
```

---

## Exemplo 2 — Pipeline BiberPlus com diretório de saída

**Scripts:** `exemplo2_00_runall.py`, `exemplo2_01-tagging_com_tsv.py`,
`exemplo2_02_biber_kfa_analysis_graph.py`

**Descrição:** Introduz o padrão `output_dir` e a função `run_tagging()` reutilizável.
Todos os artefatos gerados (CSVs, tokens taggeados em JSONL, cópias dos originais)
são concentrados em um único diretório de saída `out_test/`.

**Corpora usados:**
- `examples/test_corpora/teste1` — corpus pequeno de teste
- `examples/test_corpora/teste2` — corpus pequeno de teste

**Saída gerada** (em `out_test/`):
- `teste1_biberfeatures_rawcount.csv`, `teste1_biberfeatures_norm1000.csv`
- `teste2_biberfeatures_rawcount.csv`, `teste2_biberfeatures_norm1000.csv`
- `teste1_tagged/` — arquivos `.jsonl` com tokens e tags por documento
- `originals/` — cópias dos arquivos `.txt` originais
- `key_features_analysis_teste1_vs_teste2.png`
- `key_features_analysis_results_teste1_vs_teste2.csv`

**Como executar:**
```bash
python examples/exemplo2_00_runall.py
```

**O que observar:** Com corpora tão pequenos, a KFA provavelmente não encontrará
features estatisticamente significativas.  Este exemplo é para verificar que a
instalação funciona corretamente.

---

## Exemplo 3 — Pipeline BiberPlus com corpora reais

**Scripts:** `exemplo3_00_runall.py`, `exemplo3_01_tagging_com_tsv.py`,
`exemplo3_02_biber_kfa_analysis_graph.py`

**Descrição:** Pipeline de produção com dois corpora de ensaios acadêmicos em
inglês (100 documentos cada), suficientes para a KFA encontrar features
estatisticamente distintivas.  Os resultados mostram diferenças linguísticas
entre escritores L2 (CorIFA) e escritores nativos (BAWE).

**Corpora usados:**
- `examples/test_corpora/CorIFAessaysNE_100` — 100 ensaios do corpus CorIFA (estudantes brasileiros de inglês)
- `examples/test_corpora/essays_bawe_somentetexto_100` — 100 ensaios do corpus BAWE (falantes nativos de inglês)

**Saída gerada** (em `examples/out_exemplo3/`):
- `CorIFAessaysNE_100_biberfeatures_rawcount.csv` / `_norm1000.csv`
- `essays_bawe_somentetexto_100_biberfeatures_rawcount.csv` / `_norm1000.csv`
- `CorIFAessaysNE_100_tagged/` — ~100 arquivos `.jsonl`
- `originals/` — cópias dos arquivos `.txt` originais
- `key_features_analysis_CorIFAessaysNE_100_vs_essays_bawe_somentetexto_100.png`
- `key_features_analysis_results_CorIFAessaysNE_100_vs_essays_bawe_somentetexto_100.csv`

**Como executar:**
```bash
python examples/exemplo3_00_runall.py
```

**O que observar:** O gráfico Cohen's D mostra features com valores positivos
(mais frequentes no corpus 1 — CorIFA) e negativos (mais frequentes no corpus 2 — BAWE).
Features típicas de L2 como uso excessivo de pronomes pessoais ou subuso de
hedges aparecem como features-chave.

---

## Exemplo 4 — Pipeline MFTE com corpora reais

**Scripts:** `exemplo4_00_runall.py`, `exemplo4_01_mfte_tagger_generate_tables_raw_and_norm1000.py`,
`exemplo4_02_mfte_kfa_analysis_graph.py`

**Descrição:** Replica o pipeline do Exemplo 3, mas usando o tagger **MFTE**
(Multi-Feature Tagger for English) em vez do BiberPlus.  O MFTE utiliza Stanza
para tokenização e POS-tagging, produzindo um conjunto de features similar ao
BiberPlus mas com nomenclatura e cobertura próprias.  A variável `EXTENDED`
(padrão: `True`) controla se as categorias semânticas estendidas do MFTE são
aplicadas.

**Corpora usados:** Mesmos do Exemplo 3 — CorIFA\_100 e BAWE\_100.

**Pré-requisitos:**
- `stanza` e modelos de inglês instalados (`stanza.download("en")`)
- Pacote `MFTE` instalado

**Saída gerada** (em `examples/out_exemplo4/`):
- `CorIFAessaysNE_100_mfte_rawcount.csv` / `_norm1000.csv`
- `essays_bawe_somentetexto_100_mfte_rawcount.csv` / `_norm1000.csv`
- `CorIFAessaysNE_100_tagged/` — arquivos `_mfte.jsonl`
- `key_features_analysis_CorIFAessaysNE_100_vs_essays_bawe_somentetexto_100.png`
- `key_features_analysis_results_*.csv`

**Como executar:**
```bash
python examples/exemplo4_00_runall.py
# Para usar GPU (se disponível):
# Edite USE_GPU = True em exemplo4_00_runall.py
```

**O que observar:** Compare os resultados com o Exemplo 3.  O MFTE usa nomes
de features diferentes do BiberPlus, mas ambos partem de categorias Biber.
Semelhanças nas features-chave validam a robustez das diferenças encontradas.

---

## Exemplo 5 — Comparação BiberPlus vs MFTE (não estendido)

**Scripts:** `exemplo5_00_runall.py`, `exemplo5_01_biberplus_and_mfte_noext_tagging.py`,
`exemplo5_02_biber_vs_mfte_noext_kfa_graph.py`

**Descrição:** Realiza o tagging dos mesmos dois corpora com **ambos** os taggers —
BiberPlus e MFTE com `extended=False` — e executa duas KFAs independentes,
gerando um gráfico e um CSV de resultados para cada tagger.  Isso permite
comparar diretamente como cada inventário de features caracteriza as diferenças
entre os grupos.

O MFTE com `extended=False` usa apenas as features Biber originais
(sem categorias semânticas adicionais), tornando a comparação mais direta com
o BiberPlus.

**Corpora usados:** Mesmos do Exemplo 3 — CorIFA\_100 e BAWE\_100.

**Saída gerada** (em `examples/out_exemplo5/`):
- `*_biberfeatures_rawcount.csv` / `_norm1000.csv` (BiberPlus)
- `*_mfte_rawcount.csv` / `_norm1000.csv` (MFTE não estendido)
- `key_features_biber_*.png` e `key_features_biber_results_*.csv`
- `key_features_mfte_noext_*.png` e `key_features_mfte_noext_results_*.csv`

**Como executar:**
```bash
python examples/exemplo5_00_runall.py
```

**O que observar:** Sobreposição de features-chave entre os dois taggers.
Se as mesmas features aparecerem como distintivas em ambas as análises,
isso reforça a robustez dos resultados.  Discrepâncias revelam diferenças
de implementação ou cobertura entre os taggers.

---

## Exemplo 6 — Comparação BiberPlus vs MFTE (estendido)

**Scripts:** `exemplo6_00_runall.py`, `exemplo6_01_biberplus_and_mfte_ext_tagging.py`,
`exemplo6_02_biber_vs_mfte_ext_kfa_graph.py`

**Descrição:** Idêntico ao Exemplo 5, mas com `extended=True` no MFTE.
O MFTE estendido inclui, além das features Biber, categorias semânticas
adicionais (cadeias nominais complexas, construções passivas elaboradas,
carga informacional, etc.), resultando em um inventário de features maior.

Isso pode revelar distinções entre os corpora que o BiberPlus e o MFTE
não estendido não capturam, ao mesmo tempo que permite verificar se as
features Biber tradicionais continuam sendo identificadas como significativas.

**Corpora usados:** Mesmos do Exemplo 3 — CorIFA\_100 e BAWE\_100.

**Saída gerada** (em `examples/out_exemplo6/`):
- `*_biberfeatures_rawcount.csv` / `_norm1000.csv` (BiberPlus)
- `*_mfte_rawcount.csv` / `_norm1000.csv` (MFTE estendido)
- `key_features_biber_*.png` e `key_features_biber_results_*.csv`
- `key_features_mfte_ext_*.png` e `key_features_mfte_ext_results_*.csv`

**Como executar:**
```bash
python examples/exemplo6_00_runall.py
```

**O que observar:** Compare os gráficos do MFTE estendido vs não estendido
(Exemplo 5).  Features adicionais no inventário estendido que aparecem como
distintivas indicam aspectos linguísticos capturados pelas categorias
semânticas do MFTE além das features Biber tradicionais.

---

## Estrutura dos diretórios de saída

```
out_exemploN/
├── <corpus1>_biberfeatures_rawcount.csv   # contagens brutas BiberPlus
├── <corpus1>_biberfeatures_norm1000.csv   # normalizado por 1000 palavras
├── <corpus1>_mfte_rawcount.csv            # contagens brutas MFTE (exemplos 4–6)
├── <corpus1>_mfte_norm1000.csv            # normalizado por 1000 palavras
├── <corpus1>_tagged/                      # tokens taggeados (formato JSONL)
│   └── <documento>_tagged.jsonl
├── originals/                             # cópias dos .txt originais
│   └── <corpus1>/
├── key_features_*.png                     # gráfico Cohen's D
└── key_features_results_*.csv             # features significativas com p-valor
```

### Formato JSONL dos tokens taggeados

Cada arquivo `_tagged.jsonl` contém uma linha de metadados seguida de uma
linha por token:

```jsonl
{"tagger": "biberplus", "filename": "doc.txt", ...}
{"start_char": 0, "end_char": 5, "word": "Hello", "xpos": "UH", "tags": ["INTJ"]}
```

O campo `start_char`/`end_char` corresponde à posição no arquivo `.txt`
original, satisfazendo `original_text[start_char:end_char] == word`.

---

## Corpora de teste incluídos

| Pasta | Documentos | Descrição |
|-------|-----------|-----------|
| `test_corpora/teste1` | ~5 | Corpus mínimo para testes de instalação |
| `test_corpora/teste2` | ~5 | Corpus mínimo para testes de instalação |
| `test_corpora/subcorpus_introduction_aphd` | ~20 | Introduções de teses de doutorado |
| `test_corpora/subcorpus_introduction_articles` | ~20 | Introduções de artigos científicos |
| `test_corpora/CorIFAessaysNE_100` | 100 | Ensaios acadêmicos — estudantes brasileiros de inglês (L2) |
| `test_corpora/essays_bawe_somentetexto_100` | 100 | Ensaios acadêmicos — falantes nativos de inglês (BAWE) |

---

## Dependências por exemplo

| Exemplo | Dependências adicionais |
|---------|------------------------|
| 1–3 | Apenas `ttwtools` (BiberPlus incluso) |
| 4–6 | `ttwtools` + `stanza` + `torch` + modelos Stanza en + pacote `MFTE` |

Para instalar as dependências do MFTE:
```bash
pip install stanza torch MFTE
python -c "import stanza; stanza.download('en')"
```
