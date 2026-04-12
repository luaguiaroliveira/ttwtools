# ttwtools

ttwtools is a Python package for corpus linguistics workflows.

It is designed to support end-to-end pipelines that start with linguistic tagging and continue into quantitative analyses over corpora. The project is intentionally modular so it can grow from a single tagging backend into multiple tagging and analysis strategies.

## Project Scope

ttwtools currently provides:

- Tagging-oriented corpus processing (feature extraction and normalization).
- Key Feature Analysis (KFA) based on effect sizes (Cohen's D).

ttwtools is intended to support diverse corpus linguistics processes, not only one fixed method. The long-term goal is to host multiple tagging approaches and multiple analysis layers in the same package.

## Relationship to Biberplus

The current tagging workflow is implemented on top of a modified Biberplus integration.

- Original project: `biberplus', written by David Jurgens.
- Repository: https://github.com/davidjurgens/biberplus

At this stage, ttwtools uses this modified Biberplus-based tagging path as its main backend. In future versions, the package may include additional taggers and interchangeable tagging pipelines.

## Current API

Primary entry points:

- `ttwtools.tagging.biberplus(...)`
- `ttwtools.analysis.kfa(...)`

Example:

```python
from ttwtools.tagging import biberplus
from ttwtools.analysis import kfa

biberplus("subcorpus_introduction_aphd", usenlp=False)
results = kfa(
      "out_test/teste1_biberfeatures_norm1000.csv",
      "out_test/teste2_biberfeatures_norm1000.csv",
)
```

## Package Structure

- `ttwtools/tagging.py`
   - `biberplus(...)`
   - `extract_biber_features_from_folder(...)`
   - `normalize_biber_features(...)`
- `ttwtools/analysis.py`
   - `kfa(...)`
   - `analyze_key_features(...)`
   - `cohens_d(...)`
   - `pooled_std(...)`
- `examples/`
   - runnable scripts and test corpora
- `docs/`
   - project documentation

## Examples

Run the example pipelines:

```bash
python examples/exemplo1_00_runall.py
python examples/exemplo2_00_runall.py
```

Test corpora used by examples are located at:

- `examples/test_corpora/teste1`
- `examples/test_corpora/teste2`
- `examples/test_corpora/teste_corpus`

## Installation (Local Development)

This repository includes `pyproject.toml` and can be installed in editable mode.

Recommended setup:

```bash
conda create -n ttw314 python=3.12 -y
conda activate ttw314
pip install -e .
python -m spacy download en_core_web_sm
```

Why this extra step?

- The spaCy language model `en_core_web_sm` is required by the current Biberplus-based tagging workflow.
- spaCy models are distributed separately from spaCy itself, so they are not always available immediately after package installation.

If you see an error about missing `en_core_web_sm`, run:

```bash
python -m spacy download en_core_web_sm
```

Note: we do not auto-download language models during package installation because that can fail in offline or restricted environments and may be undesirable in CI/production pipelines.

## Roadmap Direction

Planned evolution includes:

- Additional tagging backends beyond the current Biberplus-based implementation.
- Additional corpus analysis modules beyond KFA.
- More configurable and reusable workflows for different corpus linguistics research designs.

## License

MIT. See [LICENSE](LICENSE).