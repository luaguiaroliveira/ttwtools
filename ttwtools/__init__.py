"""ttwtools — etiquetagem, tabelas de atributos e análise de key features.

Os nomes públicos são carregados sob demanda (PEP 562): `import ttwtools` é
rápido e só importa spaCy, pandas, torch etc. quando a função é usada.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import TYPE_CHECKING

from ._version import __version__

_SUBMODULES = ("analysis", "tagging", "taggers", "tagged_io", "project", "layers", "corpus", "backends", "annotate", "formats", "stats", "query", "keyness", "features", "viz", "corpus_catalog", "models", "pipeline", "experimental", "writing", "constructions", "collocations", "sophistication", "examples", "i18n", "help", "codegen", "cli")

# nome público → submódulo que o define
_EXPORTS = {
    # tagging — BiberPlus
    "biberplus": "taggers",
    "extract_biber_features_from_folder": "taggers",
    "normalize_biber_features": "taggers",
    # tagging — MFTE
    "mfte": "taggers",
    "extract_mfte_features_from_folder": "taggers",
    "normalize_mfte_features": "taggers",
    # tagging — Stanza POS (UPOS / XPOS)
    "stanza_upos": "taggers",
    "stanza_xpos": "taggers",
    "extract_stanza_pos_features_from_folder": "taggers",
    "normalize_stanza_pos_features": "taggers",
    "extract_stanza_combined_features_from_folder": "taggers",
    # tagging — spaCy POS (UPOS / PTB)
    "spacy_upos": "taggers",
    "spacy_ptb": "taggers",
    "extract_spacy_pos_features_from_folder": "taggers",
    "normalize_spacy_pos_features": "taggers",
    "extract_spacy_combined_features_from_folder": "taggers",
    # analysis
    "kfa": "analysis",
    "wkfa": "analysis",
    "analyze_key_features": "analysis",
    "cohens_d": "analysis",
    "cohens_d_biber": "analysis",
    "pooled_std": "analysis",
    "pooled_std_biber": "analysis",
    # project / persistence
    "TTWAProject": "project",
    "create_project": "project",
    "open_project": "project",
    "needs_migration": "project",
    "save_project_as": "project",
    "save_corpus_as": "project",
    "compression_of": "project",
    "register_working_copy": "project",
    "checkpoint": "project",
    "save_analysis_to_project": "project",
    "TTWA_MIME_TYPE": "project",
    "TTWA_EXTENSION": "project",
    "TTWA_MODE_FULL": "project",
    "TTWA_MODE_COMPACT": "project",
    "TTWL_EXTENSION": "project",
    "TTWAL_EXTENSION": "project",
    "make_workdir": "project",
    "purge_orphan_workdirs": "project",
    "save_corpora_as": "project",
    "TTWAL_EXTENSION": "project",
    "save_corpora_as": "project",
    "export_corpus_next_to": "project",
    "relink_corpus": "project",
    "embed_corpus": "project",
    "detach_corpus": "project",
    "compact_project": "project",
    "ensure_free_space": "storage",
    "cache_dir": "storage",
    "disk_usage": "storage",
    "purge_orphans": "storage",
    "InsufficientDiskSpace": "storage",
    # corpus: importação, metadados, tokenização simples, filtros
    "import_corpus": "corpus",
    "preview_filenames": "corpus",
    "pending_steps": "pipeline",
    "add_step": "pipeline",
    "remove_step": "pipeline",
    "clear_steps": "pipeline",
    "run_steps": "pipeline",
    "filter_documents": "corpus",
    "list_groups": "corpus",
    "set_document_meta": "corpus",
    "get_document_meta": "corpus",
    "TokenizerConfig": "corpus",
    "tokenize": "corpus",
    "list_corpora": "corpus",
    "layer_summary": "corpus",
    # annotate: etiquetar com cache de camadas
    "tag_corpus": "annotate",
    "find_layer": "annotate",
    "build_request": "annotate",
    "plan_tagging": "annotate",
    # stats: estatísticas descritivas
    "describe": "stats",
    "stopwords": "stats",
    # query: busca, KWIC, frequência, colocados, dispersão
    "search": "query",
    "kwic": "query",
    "frequency": "query",
    "collocates": "query",
    "collocate_examples": "query",
    "dispersion": "query",
    "dispersion_multi": "query",
    "dispersion_compare": "query",
    "read_document": "query",
    "tag_counts": "query",
    "keywords": "keyness",
    "feature_table": "features",
    "kfa_layers": "features",
    "make_reference_list": "keyness",
    "frequency_bands": "keyness",
    "read_reference_list": "keyness",
    # writing: comparar um texto individual com a referência
    "analyze_text": "writing",
    "analyze_file": "writing",
    "extract_text": "writing",
    "text_freqs": "writing",
    # constructions: construções como sequências de classes/etiquetas
    "analyze_patterns": "constructions",
    "corpus_patterns": "constructions",
    "text_patterns": "constructions",
    "tag_text": "constructions",
    # collocations: perfil de colocação do texto vs referência
    "collocate_profile": "collocations",
    "text_collocates": "collocations",
    # sophistication: riqueza lexical e frases
    "lexical_profile": "sophistication",
    "mtld": "sophistication",
    # examples: ocorrências com marcas no texto e no corpus
    "writing_examples": "examples",
    "text_examples": "examples",
    "corpus_examples": "examples",
}

__all__ = ["__version__", *(m for m in _SUBMODULES if m != "cli"), *_EXPORTS]


def __getattr__(name: str):
    if name in _SUBMODULES:
        return importlib.import_module(f".{name}", __name__)
    if name in _EXPORTS:
        value = getattr(importlib.import_module(f".{_EXPORTS[name]}", __name__), name)
        if isinstance(value, ModuleType):   # submódulo com o mesmo nome da função (biberplus, mfte)
            value = getattr(value, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))


if TYPE_CHECKING:  # para editores e verificadores de tipo
    from . import analysis, project, tagged_io, taggers, tagging  # noqa: F401
    from .analysis import analyze_key_features, cohens_d, cohens_d_biber, kfa, wkfa, pooled_std, pooled_std_biber  # noqa: F401
    from .project import (  # noqa: F401
        TTWA_EXTENSION, TTWA_MIME_TYPE, TTWA_MODE_COMPACT, TTWA_MODE_FULL,
        TTWAProject, create_project, open_project, save_analysis_to_project,
        TTWAL_EXTENSION, TTWAL_EXTENSION, TTWL_EXTENSION, detach_corpus, embed_corpus, export_corpus_next_to, relink_corpus,
        compact_project,
    )
    from .corpus import (  # noqa: F401
        TokenizerConfig, filter_documents, get_document_meta, import_corpus, list_groups,
        set_document_meta, tokenize,
    )
    from .annotate import build_request, find_layer, tag_corpus  # noqa: F401
    from .taggers import (  # noqa: F401
        biberplus, extract_biber_features_from_folder, extract_mfte_features_from_folder,
        extract_spacy_combined_features_from_folder, extract_spacy_pos_features_from_folder,
        extract_stanza_combined_features_from_folder, extract_stanza_pos_features_from_folder,
        mfte, normalize_biber_features, normalize_mfte_features, normalize_spacy_pos_features,
        normalize_stanza_pos_features, spacy_ptb, spacy_upos, stanza_upos, stanza_xpos,
    )
