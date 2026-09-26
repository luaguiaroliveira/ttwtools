# Changelog

All notable changes to ttwtools are documented here.

---

## [Unreleased]

### Added
- Command line `ttwtools` (`python -m ttwtools`): `--version` and subcommands `describe`, `tag`, `tagger-options`, `tagset`, `kwic`, `freq`, `keywords`, `compare`, `help` (stubs for now); standard output as table, `--json` or `--csv` (`ttwtools.cli.emit`).
- Project schema **v0.3**: tables `documents` (text hash), `document_meta`, `layers` (tool, version, model, config, `config_hash`, `text_hash`), `tokens` (indexed by word/lemma/xpos) and `analyses`; `ttwtools.layers` (JSONL → tokens, `config_hash` without performance options). Old projects migrate on open, with a warning, without deleting anything.
- Light projects **`.ttwl`** (corpus in a folder next to the file, checked by hash): `export_corpus_next_to`, `relink_corpus`, `embed_corpus` (`.ttwl` → `.ttwa`), `detach_corpus` (`.ttwa` → `.ttwl`), `check_corpus`; `add_corpus_text`; `save_analysis`/`list_analyses`/`load_analysis`.
- `ttwtools.corpus`: `import_corpus` (folder of .txt, one .txt, CSV with a text column, or pasted text), document metadata from file names (fields + delimiter) and/or a metadata CSV, `filter_documents`/`list_groups` by metadata, simple configurable tokenizer (`TokenizerConfig`: lowercase, punctuation, numbers, contractions) saved per corpus. CLI: `ttwtools import` and `ttwtools documents --where key=value`.
- `ttwtools.__version__` (from `pyproject.toml`) and a `pytest` suite in `tests/` (smoke tests: project, tagged JSONL, BiberPlus + KFA; CLI).

### Changed
- `import ttwtools` is lazy (PEP 562): public names are unchanged but load on first use (import time 4.2 s → 0.04 s). Python ≥ 3.11.

## [0.1.0] — 2026-04-21

### Added
- **Multi-tagger architecture** — `ttwtools/taggers/` subpackage with separate
  backends for BiberPlus and MFTE; `tagging.py` kept as a compatibility shim.
- **MFTE backend** (`ttwtools.mfte`) — extracts >100 lexico-grammatical features
  via Stanza POS tagging; supports `extended=True/False` and CPU/CUDA/MPS device
  selection.
- `normalize_mfte_features()` and `extract_mfte_features_from_folder()` public
  functions mirroring the BiberPlus equivalents.
- `tagged_io.py` — shared I/O layer for reading/writing tagged files.
- **JSONL tagged-file format** replacing the old `type|content|tags` TSV format;
  richer per-token metadata.
- **`.ttwa` project file migration** — `feature_tables` table gains `tagger_type`
  and `tagger_config` columns; existing files are auto-migrated on `open_project()`.
- Optional dependency group `[mfte]` in `pyproject.toml` (`stanza`, `MFTE`,
  `torch`); BiberPlus-only installs are unaffected.
- Six end-to-end example pipelines in `examples/`:
  - `exemplo1` — BiberPlus, raw corpus → KFA
  - `exemplo2` — BiberPlus, pre-tagged TSV input → KFA
  - `exemplo3` — BiberPlus, pre-tagged TSV input, two corpora → KFA
  - `exemplo4` — MFTE extended, raw corpus → KFA
  - `exemplo5` — BiberPlus + MFTE non-extended, dual KFA
  - `exemplo6` — BiberPlus + MFTE extended, dual KFA
- `examples/about_examples.md` describing the six pipelines.
- `docs/README.md` expanded with migration guide and new API reference.

### Changed
- `ttwtools/__init__.py` now imports from `taggers/` instead of `tagging.py`.
- `pyproject.toml` bumped to `version = "0.1.0"`.
- `requirements.txt` updated to reflect optional MFTE dependencies.

### Migration
Code that imports directly from `ttwtools.tagging` continues to work via the
shim. New code should import from the top-level package:

```python
import ttwtools
ttwtools.biberplus(...)
ttwtools.mfte(...)
```

---

## [0.0.0] — initial

### State at this version
- Single-tagger library wrapping **BiberPlus** (spaCy tokenisation).
- `ttwtools/tagging.py` — all tagging logic; `biberplus()` entry point.
- `ttwtools/analysis.py` — Key Feature Analysis (`kfa()`, `analyze_key_features()`,
  `cohens_d()`, `pooled_std()`); tagger-agnostic.
- `ttwtools/project.py` — SQLite-backed `.ttwa` project files (`TTWAProject`,
  `create_project`, `open_project`, `save_analysis_to_project`).
- `ttwtools/__init__.py` — re-exported `biberplus`, `normalize_biber_features`,
  `extract_biber_features_from_folder`, and the analysis/project API.
- Tagged output format: plain TSV with `type|content|tags` columns.
- Three example scripts (`exemplo1`, `exemplo2`, `exemplo3`) covering
  BiberPlus-only workflows.
- No MFTE support; no multi-tagger infrastructure.
