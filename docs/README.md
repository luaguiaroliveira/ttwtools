# ttwtools — Documentação de Referência

Este diretório concentra a documentação técnica do pacote ttwtools.

Para uma visão geral rápida e o guia de migração, veja o
[README principal](../README.md).

---

## Índice

1. [Arquitetura do pacote](#1-arquitetura-do-pacote)
2. [Taggers disponíveis](#2-taggers-disponíveis)
3. [Formato JSONL de arquivos taggeados](#3-formato-jsonl-de-arquivos-taggeados)
4. [Projetos .ttwa — schema e migração](#4-projetos-ttwa--schema-e-migração)
5. [API completa](#5-api-completa)
6. [PyInstaller — integração em apps](#6-pyinstaller--integração-em-apps)
7. [Compatibilidade retroativa](#7-compatibilidade-retroativa)

---

## 1. Arquitetura do pacote

```
ttwtools/
  taggers/
    __init__.py       — lazy re-exports; torch/stanza NÃO carregados no import
    biberplus.py      — backend BiberPlus/spaCy
    mfte.py           — backend MFTE/Stanza (opcional)
  tagging.py          — shim de compatibilidade (re-exporta de taggers.biberplus)
  analysis.py         — KFA, Cohen's d, pooled_std
  project.py          — persistência .ttwa (SQLite)
  tagged_io.py        — leitura/escrita/export do formato JSONL
  __init__.py         — re-exports de nível de pacote
```

**Princípio de import lazy:** `import ttwtools` não carrega torch nem stanza.
Essas dependências são importadas apenas na primeira chamada a `ttwtools.mfte()`
ou a qualquer função do backend MFTE. Apps que usam apenas BiberPlus têm
custo zero de startup.

---

## 2. Taggers disponíveis

### 2.1 BiberPlus

Backend padrão. Sem dependências opcionais além do spaCy.

```python
import ttwtools

ttwtools.biberplus(
    folder_path_str="caminho/para/corpus",
    output_dir="saida",          # default: pasta pai do corpus
    save_tagged=True,            # grava .jsonl por documento
    copy_originals=False,        # copia .txt originais para saida/originals/
    usenlp=False,                # False = regex (rápido); True = spaCy (mais preciso)
)
ttwtools.normalize_biber_features("saida/corpus_biberfeatures_rawcount.csv")
```

Arquivos gerados:
- `<output_dir>/<corpus>_biberfeatures_rawcount.csv`
- `<output_dir>/<corpus>_biberfeatures_norm1000.csv`
- `<output_dir>/<corpus>_tagged/<stem>_biberplus.jsonl` (se `save_tagged=True`)

### 2.2 MFTE

Backend opcional. Requer `pip install ttwtools[mfte]` e modelos Stanza.

```python
import ttwtools

# Baixar modelos Stanza uma vez (não necessário se já baixados):
# import stanza; stanza.download("en", processors="tokenize,pos")

ttwtools.mfte(
    folder_path_str="caminho/para/corpus",
    output_dir="saida",
    save_tagged=True,
    copy_originals=False,
    use_gpu=None,       # None = auto (CUDA se disponível, senão CPU; MPS excluído)
    extended=True,      # inclui categorias semânticas Biber 2006
    model_dir=None,     # sobrescreve caminho dos modelos Stanza
                        # (ou usar env var STANZA_RESOURCES_DIR)
)
ttwtools.normalize_mfte_features("saida/corpus_mfte_rawcount.csv")
```

Arquivos gerados:
- `<output_dir>/<corpus>_mfte_rawcount.csv`
- `<output_dir>/<corpus>_mfte_norm1000.csv`
- `<output_dir>/<corpus>_tagged/<stem>_mfte.jsonl` (se `save_tagged=True`)

**Performance (referência — 100 docs, ~4500 palavras/doc):**
- BiberPlus (regex): ~20 s
- MFTE (CPU, Stanza BiLSTM): ~80 s
- MFTE (MPS/Apple Silicon): ~2.4× mais lento que CPU — **não use MPS**

---

## 3. Formato JSONL de arquivos taggeados

Todos os taggers gravam no mesmo formato canônico **JSONL** (JSON Lines).
Cada arquivo tem uma linha de metadados seguida de uma linha por token.

### Estrutura

```jsonl
{"type":"metadata","tagger":"mfte","tagger_version":"1.0.0.7","stanza_model":"en","device":"cpu","extended":true,"filename":"documento.txt"}
{"start_char":0,"end_char":3,"word":"The","xpos":"DT","tags":[]}
{"start_char":4,"end_char":9,"word":"study","xpos":"NN","tags":["NN","NNABSPROC"]}
```

### Campos de token

| Campo | Tipo | Descrição |
|---|---|---|
| `start_char` | int | Offset de início no arquivo original (inclusivo) |
| `end_char` | int | Offset de fim no arquivo original (exclusivo) |
| `word` | str | Forma superficial exata. Invariante: `original[start_char:end_char] == word` |
| `xpos` | str | POS tag Penn Treebank. Fonte: `token.tag_` (spaCy) ou `word.xpos` (Stanza) |
| `tags` | list[str] | Tags do tagger. `[]` se nenhuma |

### Leitura e export

```python
from ttwtools import tagged_io

# Ler
meta, tokens = tagged_io.read_tagged_jsonl("doc_mfte.jsonl")

# Verificar invariante de offsets
original = open(meta["filename"]).read()
for tok in tokens:
    assert original[tok["start_char"]:tok["end_char"]] == tok["word"]

# Exportar para TSV ou CSV (gerado ao lado do .jsonl)
tagged_io.export_tagged("doc_mfte.jsonl", fmt="tsv")
tagged_io.export_tagged("doc_mfte.jsonl", fmt="csv")
tagged_io.export_tagged("doc_mfte.jsonl", fmt="json")  # array JSON completo
```

### Nomenclatura de arquivos

```
<output_dir>/originals/<corpus>/documento.txt
<output_dir>/<corpus>_tagged/documento_biberplus.jsonl
<output_dir>/<corpus>_tagged/documento_mfte.jsonl
```

### Arquivos legados (formato antigo `type|content|tags` TSV)

O `tagged_io.read_tagged_jsonl()` detecta o formato antigo pelo cabeçalho e
emite um aviso. Offsets não podem ser recuperados automaticamente — é necessário
re-processar o corpus com o tagger.

---

## 4. Projetos .ttwa — schema e migração

### Schema atual da tabela `feature_tables`

```sql
CREATE TABLE feature_tables (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    corpus_name   TEXT    NOT NULL,
    table_type    TEXT    NOT NULL CHECK(table_type IN ('rawcount', 'norm1000')),
    tagger_type   TEXT    NOT NULL DEFAULT 'biberplus',
    tagger_config TEXT    NOT NULL DEFAULT '{}',   -- JSON
    data          TEXT    NOT NULL,                -- DataFrame em JSON
    UNIQUE (corpus_name, table_type, tagger_type)
);
```

**Mudança em relação à versão anterior:** adição de `tagger_type` e
`tagger_config`. A constraint UNIQUE agora inclui `tagger_type`, permitindo
armazenar tabelas de múltiplos taggers para o mesmo corpus.

### Migração automática

Arquivos `.ttwa` antigos (sem `tagger_type`) são migrados automaticamente ao
serem abertos: as linhas existentes recebem `tagger_type='biberplus'` e
`tagger_config='{}'`. Nenhuma ação necessária no app.

### API

```python
from ttwtools import open_project

proj = open_project("projeto.ttwa")  # migra automaticamente se necessário

# Salvar — tagger_type default é 'biberplus' (compatível com código antigo)
proj.save_feature_table("corpus_A", df, "rawcount")
proj.save_feature_table("corpus_A", df, "norm1000")

# Salvar tabela MFTE para o mesmo corpus
proj.save_feature_table("corpus_A", df_mfte, "rawcount",
                        tagger_type="mfte",
                        tagger_config={"extended": True, "device": "cpu"})

# Carregar — tagger_type default é 'biberplus'
df = proj.load_feature_table("corpus_A", "norm1000")
df_mfte = proj.load_feature_table("corpus_A", "norm1000", tagger_type="mfte")

# Listar todas as tabelas (inclui tagger_type e tagger_config)
proj.list_feature_tables()
# => [{'corpus_name': 'corpus_A', 'table_type': 'norm1000',
#      'tagger_type': 'biberplus', 'tagger_config': {}}, ...]

# Resumo do projeto
proj.summary()
# => {'corpora': {'corpus_A': {'feature_tables': ['norm1000[biberplus]',
#                                                  'norm1000[mfte]', ...]}}}
proj.close()
```

---

## 5. API completa

### ttwtools.biberplus / ttwtools.mfte

```
biberplus(folder_path_str, output_dir=None, save_tagged=False,
          copy_originals=False, usenlp=False)

mfte(folder_path_str, output_dir=None, save_tagged=False,
     copy_originals=False, use_gpu=None, extended=True, model_dir=None)
```

### ttwtools.normalize_biber_features / normalize_mfte_features

```
normalize_biber_features(csv_path_str, decimal_places=None)
normalize_mfte_features(csv_path_str, decimal_places=None)
```

Lê o `*_rawcount.csv` e grava um `*_norm1000.csv` com contagens divididas por
palavas × 1000.

### ttwtools.kfa / analyze_key_features

```
kfa(csv1, csv2, min_effect=0.2, join_method="union") -> pd.DataFrame
analyze_key_features(df1, df2, ...) -> pd.DataFrame
```

Funciona com qualquer CSV de features — independe do tagger.

### ttwtools.tagged_io

```
write_tagged_jsonl(metadata: dict, tokens: list[dict], path)
read_tagged_jsonl(path) -> (metadata: dict, tokens: list[dict])
export_tagged(jsonl_path, fmt: str, out_path=None)
    fmt: "tsv" | "csv" | "json"
```

### ttwtools.TTWAProject

```
TTWAProject.create(path, name, description, overwrite) -> TTWAProject
TTWAProject.open(path) -> TTWAProject
proj.add_corpus_folder(corpus_name, folder_path, encoding, glob)
proj.save_feature_table(corpus_name, df, table_type,
                        tagger_type="biberplus", tagger_config=None)
proj.save_feature_table_from_csv(corpus_name, csv_path, table_type,
                                  tagger_type="biberplus", tagger_config=None)
proj.load_feature_table(corpus_name, table_type="norm1000",
                        tagger_type="biberplus") -> pd.DataFrame | None
proj.list_feature_tables() -> list[dict]
proj.save_kfa_result(corpus1, corpus2, df, min_effect, join_method)
proj.load_kfa_result(corpus1, corpus2, min_effect, join_method)
proj.export_corpus_to_folder(corpus_name, dest_folder)
proj.summary() -> dict
```

---

## 6. PyInstaller — integração em apps

### Variáveis de ambiente reconhecidas

| Variável | Módulo | Efeito |
|---|---|---|
| `STANZA_RESOURCES_DIR` | `taggers/mfte.py` | Diretório raiz dos modelos Stanza; substitui `~/stanza_resources/` |

### Uso em app bundlado

```python
import os, sys, pathlib

if getattr(sys, "frozen", False):
    # Apontar Stanza para os modelos bundlados
    os.environ["STANZA_RESOURCES_DIR"] = str(
        pathlib.Path(sys._MEIPASS) / "stanza_resources"
    )

import ttwtools
ttwtools.mfte(corpus_folder, ...)
```

Veja `todoc.md` na raiz do repositório para:
- Spec completo do Cenário B (bundle CPU com MFTE)
- Arquitetura two-bundle do Cenário C (companion `mfte_worker` para GPU)
- Checklist de build e assinatura de executável

---

## 7. Compatibilidade retroativa

| Código antigo | Status | Observação |
|---|---|---|
| `from ttwtools.tagging import biberplus` | Funciona | `tagging.py` é shim |
| `from ttwtools.tagging import normalize_biber_features` | Funciona | `tagging.py` é shim |
| `ttwtools.biberplus(...)` | Funciona | Equivalente |
| `save_tagged=True` gerando `.tsv` | **Quebrado** | Agora gera `.jsonl` |
| `proj.save_feature_table(name, df, type)` | Funciona | `tagger_type` default = `'biberplus'` |
| `proj.load_feature_table(name, type)` | Funciona | `tagger_type` default = `'biberplus'` |
| `.ttwa` antigos sem `tagger_type` | Migrados | Auto-migração na abertura |
