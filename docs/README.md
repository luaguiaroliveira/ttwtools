# ttwtools: notas técnicas e API clássica

Complementa o [guia rápido](guia_rapido.md) (tudo o que o aplicativo faz, em Python e na linha de comando) e a [referência da API](referencia.md) (gerada das docstrings por `gerar_referencia.py`). Aqui: arquitetura, taggers, formato JSONL, a **API clássica da 0.1** (etiquetagem em pastas, tabelas de traços, KFA por CSV), integração do MFTE, empacotamento e licença.

## 1. Arquitetura

Módulos principais: `project.py` (projeto `.ttwa`/`.ttwl`/`.ttwc`… em SQLite; esquema v0.3 com `documents`, `layers`, `tokens`, `layer_blobs`), `layers.py` e `annotate.py` (camadas com cache por texto, ferramenta, versão, modelo e configuração), `layerfmt.py` (camadas colunares `TCL2`, padrão, e `TCL1`), `searchindex.py` (índice de busca em cache), `idquery.py` (consultas por ids nas camadas `TCL2`: `search`, `kwic`, `frequency` e `collocates` sem passar por `tokens`; `TTWTOOLS_ID_QUERIES=0` desliga), `storage.py` (espaço livre, pastas de trabalho, cache), `query.py` (busca, KWIC, frequência, colocados, dispersão), `keyness.py`, `features.py` e `analysis.py` (palavras-chave, KFA), `stats.py`, `experimental.py` (Laboratório), `corpus_catalog.py`, `formats/`, `taggers/` (`biberplus`, `mfte`, `spacy_pos`, `stanza_pos`), `tagged_io.py` (JSONL), `writing.py` e afins (Escrita), `help.py`, `cli.py`. **Import lazy:** `import ttwtools` não carrega torch nem stanza; só a primeira chamada ao backend que precisa deles.

## 2. Taggers

| Tagger | `tagger_type` | Dependências | Features |
|---|---|---|---|
| BiberPlus (regex) | `biberplus` | spaCy (modelo `en_core_web_sm`) | ~67 traços de Biber |
| BiberPlus + spaCy/Stanza | `biberplus_nlp` | spaCy ou Stanza | ~67 |
| MFTE | `mfte` | Stanza, torch, MFTE | ~80 |
| MFTE estendido | `mfte_ext` | idem | ~120 |

Stanza não é um tagger separado: é o tokenizador do MFTE (e opcional do BiberPlus). `pip install "ttwtools[mfte]"` instala `stanza`, `MFTE` e `torch` (~550 MB com modelos), por isso é opcional; modelos: `python -c "import stanza; stanza.download('en', processors='tokenize,pos')"` (~250–300 MB; `STANZA_RESOURCES_DIR` muda a pasta; o pacote usa `REUSE_RESOURCES`, sem atualizar sozinho). **Desempenho** (100 documentos de ~4.500 palavras): BiberPlus regex ~20 s; MFTE em CPU ~80 s; **MPS (Apple Silicon) é ~2,4× mais lento que CPU: não usar**.

**Integração do MFTE (importa a API interna; sem subprocesso):** passar a `process_sentence` uma **lista** de strings `"palavra_xpos"`, com `[' '] * 20` como sentinelas antes de cada frase e no fim (uma string `" " * 20` causa `IndexError`); `process_sentence_extended` preserva 1:1 o tamanho da lista, então filtrar as sentinelas só depois das duas passagens; `processors='tokenize,pos'` basta; `process_sentence` é sem estado (seguro em paralelo), mas `stanza.Pipeline` não é thread-safe (uma instância por processo).

## 3. Formato JSONL das etiquetagens

Uma linha de metadados e uma linha por token, igual para todos os taggers:

```jsonl
{"type":"metadata","tagger":"mfte","tagger_version":"1.0.0.7","stanza_model":"en","device":"cpu","extended":true,"filename":"documento.txt"}
{"start_char":0,"end_char":3,"word":"The","xpos":"DT","tags":[]}
{"start_char":4,"end_char":9,"word":"study","xpos":"NN","tags":["NN","NNABSPROC"]}
```

Campos: `start_char` (inclusivo), `end_char` (exclusivo), `word` (invariante: `texto[start_char:end_char] == word`), `xpos` (Penn Treebank), `tags` (lista). Nomes: `<saida>/<corpus>_tagged/<arquivo>_<tagger>.jsonl`. `tagged_io.read_tagged_jsonl(path)` devolve `(metadados, tokens)`; `export_tagged(path, fmt="tsv"|"csv"|"json")`. O formato antigo (`type|content|tags` em TSV) é detectado pelo cabeçalho, com aviso, e **não** recupera offsets: reprocessar o corpus.

## 4. API clássica (0.1), ainda disponível

```python
import ttwtools
ttwtools.biberplus("corpus/", output_dir="saida", save_tagged=True, usenlp=False)   # regex; True = spaCy
ttwtools.mfte("corpus/", output_dir="saida", save_tagged=True, extended=True, use_gpu=None, model_dir=None)
ttwtools.normalize_biber_features("saida/corpus_biberfeatures_rawcount.csv")        # → *_norm1000.csv
res = ttwtools.kfa("saida/A_biberfeatures_norm1000.csv", "saida/B_biberfeatures_norm1000.csv", min_effect=0.2)
```

Os dois taggers geram CSVs com as mesmas colunas (`filename`, `Words`, `TTR`, traços), então `kfa()` serve a qualquer um. `TTWAProject`: `create`, `open`, `add_corpus_folder`, `save_feature_table(corpus, df, "rawcount"|"norm1000", tagger_type="biberplus", tagger_config=None)`, `load_feature_table`, `list_feature_tables`, `save_kfa_result`, `load_kfa_result`, `export_corpus_to_folder`, `summary`; `save_analysis_to_project(...)` faz tudo de uma vez. Projetos antigos migram ao abrir (`tagger_type='biberplus'` nas linhas sem ele; esquema 0.2 → 0.3 com progresso). **Compatibilidade:** `from ttwtools.tagging import biberplus, normalize_biber_features` continua valendo (`tagging.py` é um shim); `save_tagged=True` agora grava `.jsonl`, **não** `.tsv`. O que o aplicativo faz hoje (camadas, busca, comparação, catálogo) está no guia rápido.

## 5. Empacotamento (PyInstaller) e licença

- **Cenário A, só BiberPlus:** incluir o modelo spaCy no `.spec` (`get_package_path("en_core_web_sm")`) e `hiddenimports += ["spacy", "biberplus"]`.
- **Cenário B, BiberPlus + MFTE em CPU:** baixar os modelos Stanza antes do build; coletar os binários do torch; em app congelado, apontar `os.environ["STANZA_RESOURCES_DIR"]` para `Path(sys._MEIPASS) / "stanza_resources"` antes de `ttwtools.mfte`. O empacotamento real do aplicativo está em `build/ttwtools-app.spec` (repositório do app).
- **Cenário C, `mfte_worker` à parte:** dois executáveis (app sem torch/stanza + worker com torch, Stanza e MFTE); serve a GPU, a bundle menor e à questão de licença abaixo.
- **Variável de ambiente:** `STANZA_RESOURCES_DIR` (`taggers/mfte.py`); outras do pacote no guia rápido.
- **Licença:** o código do `ttwtools` é **MIT** (`LICENSE`); Biberplus (MIT, modificado e incorporado em `taggers/biberplus.py`); Stanza (Apache 2.0, opcional); **MFTE é GPL-3.0** (opcional, não incluído no repositório). Um executável que empacota o MFTE junto é obra combinada sujeita à GPL-3.0: **conferir com assessoria jurídica antes de distribuir o Cenário B**; no Cenário C o worker seria o binário GPL e o app principal, sem código GPL, pode manter outra licença. Ver GPL FAQ, "GPLInProprietarySystem".
- **Checklist de build:** ambiente isolado com versões fixadas; modelos Stanza e spaCy baixados antes; teste de fumaça pós-build com um corpus de 5 documentos; assinar o executável (decisão D4 do plano do aplicativo).
