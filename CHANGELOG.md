# Changelog

All notable changes to ttwtools are documented here.

---

## [Unreleased]

### Added
- Command line `ttwtools` (`python -m ttwtools`): `--version` and subcommands `describe`, `tag`, `tagger-options`, `tagset`, `kwic`, `freq`, `keywords`, `compare`, `help` (stubs for now); standard output as table, `--json` or `--csv` (`ttwtools.cli.emit`).
- Project schema **v0.3**: tables `documents` (text hash), `document_meta`, `layers` (tool, version, model, config, `config_hash`, `text_hash`), `tokens` (indexed by word/lemma/xpos) and `analyses`; `ttwtools.layers` (JSONL → tokens, `config_hash` without performance options). Old projects migrate on open, with a warning, without deleting anything.
- Light projects **`.ttwl`** (corpus in a folder next to the file, checked by hash): `export_corpus_next_to`, `relink_corpus`, `embed_corpus` (`.ttwl` → `.ttwa`), `detach_corpus` (`.ttwa` → `.ttwl`), `check_corpus`; `add_corpus_text`; `save_analysis`/`list_analyses`/`load_analysis`.
- `ttwtools.corpus`: `import_corpus` (folder of .txt, one .txt, CSV with a text column, or pasted text), document metadata from file names (fields + delimiter) and/or a metadata CSV, `filter_documents`/`list_groups` by metadata, simple configurable tokenizer (`TokenizerConfig`: lowercase, punctuation, numbers, contractions) saved per corpus. CLI: `ttwtools import` and `ttwtools documents --where key=value`.
- Layer cache: `tag_corpus(project, corpus, tagger, options, components)` tags one document at a time from the project text and **skips** documents that already have a sufficient layer (same tool, version, model and result-affecting options; same or more components), copies layers between documents with the same text, and resumes after interruption. Per-document adapters in `ttwtools.backends` (spaCy, Stanza, MFTE, BiberPlus); `find_layer`, `build_request`; CLI `ttwtools tag`. spaCy/Stanza/MFTE tokens now also carry `lemma`/`feats` (and `upos` for MFTE) when available.
- Tagger options and tagsets as data: `ttwtools/data/taggers/<tagger>.options.json` (id, group, type, default, values, affects result, explanation, impact, availability, presets "rapido/recomendado/preciso") and `ttwtools/data/tagsets/{upos,ptb,biber,mfte}.tagset.json`, with pt/en texts in `data/i18n` (`ttwtools.i18n`). API `ttwtools.taggers.available()` (availability and reason per tagger, incl. broken torch↔numpy), `.options()`, `.get_tagset()`, `.run()`, `.validate_options()`; `tag_corpus(..., preset=)` validates against the descriptor. CLI `ttwtools tagger-options`, `ttwtools tagset`, `ttwtools tag --set k=v --preset`. spaCy disabled pipes and Stanza language/package/processors are no longer hard-coded; missing models raise `TaggerUnavailable` with the install command instead of downloading silently.
- `ttwtools.formats`: CoNLL-U import (documents + `conllu` layer; text rebuilt from `# text`/`SpaceAfter=No`; multiword tokens and empty nodes handled; HEAD/DEPREL/DEPS/MISC kept) and export from any layer (lossless round trip of the 10 columns); VRT export (CWB/Sketch Engine, document metadata as `<text>` attributes); `word/TAG` import (Brown, LOB); token tables as CSV, JSONL (canonical, one file per document) or Parquet (optional `pyarrow`). CLI `ttwtools import --format conllu|nltk` and `ttwtools export --to conllu|vrt|csv|jsonl|parquet`. Stanza tokens now record the sentence index.
- `ttwtools.describe(project, corpus, layer=None)`: text statistics without a tagger (documents, tokens, types, hapax, TTR, standardised TTR, CTTR, MATTR, word length, document sizes, approximate sentences, top words, Zipf data — flagged as estimates) and, with a layer, POS distribution, lexical density, sentence length, lemmas by class and per-document mean/SD; results cached in `analyses` until texts, layers or parameters change. Stopword lists (`data/stopwords/en.txt`, `pt.txt`, add/replace). CLI `ttwtools describe <project|folder>`.
- `ttwtools.query`: `search`, `kwic` (paginated in SQL, sort by left/right context, sentence and position), `frequency` (form, lemma, word+POS, POS, n-grams; by corpus, document or metadata group), `collocates` (log-likelihood, MI, T-score, frequency; window and position), `dispersion` (Gries' DP, DP_norm, Range, barcode positions). Query syntax: words, phrases, `*`/`?` wildcards, `/regex/`, `lemma=`, `pos=`, `tag=`, `&`. Works without a tagger through a built-in `simple` tokenizer layer. Expression indexes on `lower(word)`/`lower(lemma)`. CLI `search`, `kwic`, `freq`, `collocates`, `dispersion`.
- `ttwtools.keywords(project, corpus, reference, unit, measure, ...)`: keywords against another corpus, a reference frequency list (`.tsv` with a JSON card: language, variety, period, licence, tagger/version, size) or the other groups of the same corpus (`rest:<key>`); log-likelihood (Rayson), log ratio (Hardie), %DIFF, log-odds with z; min frequency and range filters; Bonferroni/FDR correction; structured, translated comparability warnings (language, tagger/version, tokenisation, size, missing lemmas, same data). `make_reference_list`/`read_reference_list`. CLI `ttwtools keywords`, `ttwtools reference-list`. `tag_corpus(filenames=...)`; queries now add the `simple` layer only to documents that have no layer.
- Help system: topics in `data/help/<lang>/<area>/<topic>.md` (title, summary, related; "how to read" and "caveats"), tours in `data/help/tours/*.json`; `ttwtools.help.get/topics/search/tour/render` with English fallback; first topics in pt and en (Cohen's d, per-1,000 normalisation, KWIC, Biber features, keyness, dispersion). CLI `ttwtools help [topic] [--search]`. All CLI subcommands are now implemented.
- `ttwtools.codegen`: CLI command and Python code equivalent to an analysis (`cli_command`, `python_code`; POSIX and Windows quoting) — generated commands reproduce the function results. `describe(cache_only=True)`. The keywords module is now `ttwtools.keyness` (the public function stays `ttwtools.keywords`; the old module name shadowed it).
- `list_corpora`/`layer_summary` (corpus library with layer coverage) and the interface texts (`data/i18n/ui.{pt,en}.json`) served to the Vue UI.
- `plan_tagging` (how many documents would be reused, copied or tagged, without tagging) and `taggers.value_availability` (installed spaCy models / Stanza packages per option value).
- `read_document` (text + layer tokens for the tagged reader) and the Explore screen texts.
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
