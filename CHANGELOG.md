# Changelog

All notable changes to ttwtools are documented here.

---

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
