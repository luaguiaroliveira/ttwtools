# ttwtools

Pacote Python de linguística de corpus usado pelo aplicativo [TTWtools](https://github.com/luaguiaroliveira/ttwtools-app): projetos `.ttwa` com camadas de anotação reaproveitáveis (spaCy, Stanza, BiberPlus, MFTE), busca, KWIC, frequência, colocados, dispersão, palavras-chave, faixas de frequência, KFA, comparação de N grupos (experimental), catálogo de corpora e importação/exportação (CoNLL-U, VRT, TEI, GrAF...). Tudo também pela linha de comando `ttwtools`.

*A Python corpus-linguistics package (used by the TTWtools app): reusable annotation layers, search, KWIC, frequency, collocates, dispersion, keywords, frequency bands, KFA, N-group comparison, corpus catalog and import/export — also as the `ttwtools` command.*

- **Guia rápido:** [`docs/guia_rapido.md`](docs/guia_rapido.md)
- **Referência de todas as funções públicas** (gerada das docstrings): [`docs/referencia.md`](docs/referencia.md) — `python docs/gerar_referencia.py` para atualizar
- **Mudanças:** [`CHANGELOG.md`](CHANGELOG.md)

```bash
pip install -e .              # + [mfte] para Stanza/MFTE (torch); no Mac Intel use Python 3.11 e torch 2.2.2
ttwtools --help
```

---

## Histórico: notas da versão 0.1 (API clássica de etiquetagem e KFA)

As seções abaixo descrevem a API anterior, baseada em pastas de arquivos etiquetados (JSONL) e tabelas de traços; ela continua disponível.

## What changed in this version

This version introduces **multi-tagger support**. If your application uses ttwtools
as a submodule, read the [Migration Guide](#migration-guide) below.

### Summary of changes

| Area | Change |
|---|---|
| Package structure | `ttwtools/taggers/` subpackage; `tagging.py` becomes a compatibility shim |
| New tagger | MFTE backend (`ttwtools.mfte`) via Stanza API |
| Tagged file format | JSONL replaces the old `type\|content\|tags` TSV format |
| Project files (.ttwa) | `feature_tables` table gains `tagger_type` and `tagger_config` columns; old files auto-migrated on open |
| New functions | `normalize_mfte_features()`, `extract_mfte_features_from_folder()` |
| PyInstaller | `STANZA_RESOURCES_DIR` env var respected by MFTE backend |

---

## Installation

### BiberPlus only (default)

```bash
pip install -e .
python -m spacy download en_core_web_sm
```

### With MFTE backend (optional)

```bash
pip install -e ".[mfte]"
# MFTE requires Stanza models — download once:
python -c "import stanza; stanza.download('en', processors='tokenize,pos')"
```

`[mfte]` installs `stanza`, `MFTE`, and `torch`. These are heavy dependencies
(~300 MB of models + 250 MB of torch CPU) and are intentionally optional so
apps that only need BiberPlus pay no startup cost.

---

## Quick start

### BiberPlus

```python
import ttwtools

# Tag corpus and save raw feature counts
ttwtools.biberplus("path/to/corpus", output_dir="out", save_tagged=True)

# Normalize to per-1000-words
ttwtools.normalize_biber_features("out/corpus_biberfeatures_rawcount.csv")

# Key Feature Analysis
results = ttwtools.kfa(
    "out/corpus_A_biberfeatures_norm1000.csv",
    "out/corpus_B_biberfeatures_norm1000.csv",
)
```

### MFTE

```python
import ttwtools

# Tag corpus with MFTE (Stanza + MFTE feature rules)
ttwtools.mfte("path/to/corpus", output_dir="out", save_tagged=True)

# Normalize to per-1000-words
ttwtools.normalize_mfte_features("out/corpus_mfte_rawcount.csv")
```

Both taggers produce identical CSV column structure (`filename`, `Words`, `TTR`,
feature columns) so `ttwtools.kfa()` works unchanged with either output.

---

## Migration Guide

### 1. Import paths — no breaking change

Code using the old paths continues to work:

```python
# These still work — tagging.py is now a compatibility shim
from ttwtools.tagging import biberplus, normalize_biber_features
```

The preferred paths going forward are:

```python
import ttwtools
ttwtools.biberplus(...)           # preferred
ttwtools.normalize_biber_features(...)
ttwtools.mfte(...)                # new
ttwtools.normalize_mfte_features(...)  # new
```

### 2. Tagged file format — JSONL replaces TSV

Old format (`*_tagged.tsv`, one `type|content|tags` row per token) is **no longer
generated**. `save_tagged=True` now writes one `.jsonl` file per document.

**New JSONL format** — first line is metadata, each subsequent line is one token:

```jsonl
{"type":"metadata","tagger":"biberplus","tagger_version":"...","filename":"doc.txt"}
{"start_char":0,"end_char":3,"word":"The","xpos":"DT","tags":[]}
{"start_char":4,"end_char":9,"word":"study","xpos":"NN","tags":["NN","NNABSPROC"]}
```

Key fields per token:
- `start_char` / `end_char`: character offsets into the original file.
  Invariant: `original_text[start_char:end_char] == word`.
- `word`: exact surface form from the original file.
- `xpos`: Penn Treebank POS tag.
- `tags`: list of tagger-specific feature tags.

Read tagged files with `ttwtools.tagged_io`:

```python
from ttwtools import tagged_io

meta, tokens = tagged_io.read_tagged_jsonl("doc_biberplus.jsonl")
for tok in tokens:
    print(tok["start_char"], tok["word"], tok["tags"])

# Export to TSV or CSV on demand
tagged_io.export_tagged("doc_biberplus.jsonl", fmt="tsv")
tagged_io.export_tagged("doc_biberplus.jsonl", fmt="csv")
```

**Legacy TSV files** are detected automatically on read and a warning is shown.
Offsets cannot be recovered from the old format without re-processing.

### 3. Project files (.ttwa) — tagger metadata added

`feature_tables` now stores which tagger produced each table. Old `.ttwa` files
are **automatically migrated** when opened: existing rows receive
`tagger_type='biberplus'` and `tagger_config='{}'` as defaults.

**No code change needed** for apps that only use BiberPlus — the default
argument `tagger_type="biberplus"` is unchanged:

```python
# Old code — still works
proj.save_feature_table(corpus_name, df, "rawcount")
proj.load_feature_table(corpus_name, "norm1000")
```

For mixed-tagger projects:

```python
# Save MFTE table alongside BiberPlus table for the same corpus
proj.save_feature_table(corpus_name, df_mfte, "rawcount",
                        tagger_type="mfte",
                        tagger_config={"extended": True, "device": "cpu"})

# Load by tagger
df = proj.load_feature_table(corpus_name, "norm1000", tagger_type="mfte")

# List all tables (now includes tagger_type and tagger_config)
proj.list_feature_tables()
# [{'corpus_name': 'A', 'table_type': 'norm1000',
#   'tagger_type': 'biberplus', 'tagger_config': {}}, ...]
```

### 4. PyInstaller — STANZA_RESOURCES_DIR

The MFTE backend respects the `STANZA_RESOURCES_DIR` environment variable for
locating Stanza models in bundled applications:

```python
import os, sys, pathlib
if getattr(sys, "frozen", False):
    os.environ["STANZA_RESOURCES_DIR"] = str(
        pathlib.Path(sys._MEIPASS) / "stanza_resources"
    )
```

See `todoc.md` for complete PyInstaller `.spec` templates and the two-bundle
(companion process) strategy for GPU-capable apps.

---

## Package Structure

```
ttwtools/
  taggers/
    __init__.py           — lazy re-exports for all taggers
    biberplus.py          — BiberPlus/spaCy backend
    mfte.py               — MFTE/Stanza backend (optional; torch not loaded unless used)
  tagging.py              — compatibility shim (re-exports from taggers.biberplus)
  analysis.py             — KFA, Cohen's d, pooled_std
  project.py              — .ttwa project persistence (SQLite)
  tagged_io.py            — JSONL read/write/export
  __init__.py             — top-level re-exports
```

### Public API

**Tagging — BiberPlus**
- `ttwtools.biberplus(folder, output_dir, save_tagged, copy_originals, usenlp)`
- `ttwtools.extract_biber_features_from_folder(...)`
- `ttwtools.normalize_biber_features(csv_path, decimal_places)`

**Tagging — MFTE** *(requires `pip install ttwtools[mfte]`)*
- `ttwtools.mfte(folder, output_dir, save_tagged, copy_originals, use_gpu, extended, model_dir)`
- `ttwtools.extract_mfte_features_from_folder(...)`
- `ttwtools.normalize_mfte_features(csv_path, decimal_places)`

**Analysis**
- `ttwtools.kfa(csv1, csv2, min_effect, join_method)`
- `ttwtools.analyze_key_features(df1, df2, ...)`
- `ttwtools.cohens_d(a, b)` / `ttwtools.pooled_std(a, b)`

**Tagged I/O**
- `ttwtools.tagged_io.write_tagged_jsonl(metadata, tokens, path)`
- `ttwtools.tagged_io.read_tagged_jsonl(path)` → `(metadata, tokens)`
- `ttwtools.tagged_io.export_tagged(jsonl_path, fmt)` — fmt: `"tsv"`, `"csv"`, `"json"`

**Project (.ttwa)**
- `ttwtools.create_project(path, name)` / `ttwtools.open_project(path)`
- `TTWAProject.add_corpus_folder(corpus_name, folder_path)`
- `TTWAProject.save_feature_table(corpus_name, df, table_type, tagger_type, tagger_config)`
- `TTWAProject.load_feature_table(corpus_name, table_type, tagger_type)`
- `TTWAProject.save_kfa_result(...)` / `TTWAProject.load_kfa_result(...)`
- `ttwtools.save_analysis_to_project(...)` — all-in-one convenience function

---

## Examples

```bash
python examples/exemplo1_00_runall.py   # BiberPlus pipeline
python examples/exemplo2_00_runall.py
python examples/exemplo3_00_runall.py
```

Test corpora: `examples/test_corpora/`

---

## License

ttwtools source code is released under the **MIT License**. See [LICENSE](LICENSE).

### Third-party dependencies

| Component | License | Relationship |
|---|---|---|
| [Biberplus](https://github.com/davidjurgens/biberplus) (modified) | MIT | Modified code incorporated into `ttwtools/taggers/biberplus.py` |
| [Stanza](https://github.com/stanfordnlp/stanza) | Apache 2.0 | Optional runtime dependency (`ttwtools[mfte]`) |
| [MFTE](https://github.com/mshakirDr/MFTE) | GPL 3.0 | Optional runtime dependency (`ttwtools[mfte]`) |

**GPL 3.0 note:** the ttwtools source does not include MFTE code, so the MIT
license applies to this repository. However, if you build a bundled executable
(e.g. via PyInstaller) that packages MFTE together with ttwtools, that
executable is a combined work subject to GPL 3.0. See `todoc.md` for build
guidance.


### Third-party dependencies

| Component | License | Relationship |
|---|---|---|
| [Biberplus](https://github.com/davidjurgens/biberplus) (modified) | MIT | Modified code incorporated into `ttwtools/taggers/biberplus.py` |
| [Stanza](https://github.com/stanfordnlp/stanza) | Apache 2.0 | Optional runtime dependency (`ttwtools[mfte]`) |
| [MFTE](https://github.com/mshakirDr/MFTE) | GPL 3.0 | Optional runtime dependency (`ttwtools[mfte]`) |

**GPL 3.0 note:** the ttwtools source does not include MFTE code, so the MIT
license applies to this repository. However, if you build a bundled executable
(e.g. via PyInstaller) that packages MFTE together with ttwtools, that
executable is a combined work subject to GPL 3.0. See `todoc.md` for build
guidance.