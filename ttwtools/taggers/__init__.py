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

__all__ = [
    "biberplus",
    "extract_biber_features_from_folder",
    "normalize_biber_features",
]
