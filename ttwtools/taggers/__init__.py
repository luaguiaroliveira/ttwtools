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


__all__ = [
    "biberplus",
    "extract_biber_features_from_folder",
    "normalize_biber_features",
    "mfte",
    "extract_mfte_features_from_folder",
    "normalize_mfte_features",
]
