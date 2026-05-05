"""ttwtools.taggers — backend tagging modules.

Each backend module exposes:
    tag_folder(folder_path_str, output_dir, save_tagged, copy_originals, **kwargs)
    extract_<backend>_features_from_folder(...)
    normalize_<backend>_features(...)   (where applicable)
    <backend>(...)   — high-level alias

Public re-exports
-----------------
BiberPlus backend is always available.
MFTE backend is imported lazily (torch/stanza not loaded until first use).
"""

from .biberplus import biberplus, extract_biber_features_from_folder, normalize_biber_features

# MFTE is imported lazily so that torch/stanza are NOT loaded at package import
# time.  Callers that don't use MFTE pay zero startup cost.
def mfte(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.mfte on first call."""
    from .mfte import mfte as _mfte
    return _mfte(*args, **kwargs)


def extract_mfte_features_from_folder(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.mfte on first call."""
    from .mfte import extract_mfte_features_from_folder as _fn
    return _fn(*args, **kwargs)


def normalize_mfte_features(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.mfte on first call."""
    from .mfte import normalize_mfte_features as _fn
    return _fn(*args, **kwargs)


# Stanza POS taggers (UPOS / XPOS) are also lazily imported.
def stanza_upos(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.stanza_pos on first call."""
    from .stanza_pos import stanza_upos as _fn
    return _fn(*args, **kwargs)


def stanza_xpos(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.stanza_pos on first call."""
    from .stanza_pos import stanza_xpos as _fn
    return _fn(*args, **kwargs)


def extract_stanza_pos_features_from_folder(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.stanza_pos on first call."""
    from .stanza_pos import extract_stanza_pos_features_from_folder as _fn
    return _fn(*args, **kwargs)


def normalize_stanza_pos_features(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.stanza_pos on first call."""
    from .stanza_pos import normalize_stanza_pos_features as _fn
    return _fn(*args, **kwargs)


def extract_stanza_combined_features_from_folder(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.stanza_pos on first call."""
    from .stanza_pos import extract_stanza_combined_features_from_folder as _fn
    return _fn(*args, **kwargs)


# spaCy POS taggers (UPOS / PTB) are also lazily imported.
def spacy_upos(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.spacy_pos on first call."""
    from .spacy_pos import spacy_upos as _fn
    return _fn(*args, **kwargs)


def spacy_ptb(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.spacy_pos on first call."""
    from .spacy_pos import spacy_ptb as _fn
    return _fn(*args, **kwargs)


def extract_spacy_pos_features_from_folder(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.spacy_pos on first call."""
    from .spacy_pos import extract_spacy_pos_features_from_folder as _fn
    return _fn(*args, **kwargs)


def normalize_spacy_pos_features(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.spacy_pos on first call."""
    from .spacy_pos import normalize_spacy_pos_features as _fn
    return _fn(*args, **kwargs)


def extract_spacy_combined_features_from_folder(*args, **kwargs):
    """Lazy wrapper — imports ttwtools.taggers.spacy_pos on first call."""
    from .spacy_pos import extract_spacy_combined_features_from_folder as _fn
    return _fn(*args, **kwargs)


__all__ = [
    "biberplus",
    "extract_biber_features_from_folder",
    "normalize_biber_features",
    "mfte",
    "extract_mfte_features_from_folder",
    "normalize_mfte_features",
    "stanza_upos",
    "stanza_xpos",
    "extract_stanza_pos_features_from_folder",
    "normalize_stanza_pos_features",
    "extract_stanza_combined_features_from_folder",
    "spacy_upos",
    "spacy_ptb",
    "extract_spacy_pos_features_from_folder",
    "normalize_spacy_pos_features",
    "extract_spacy_combined_features_from_folder",
]
