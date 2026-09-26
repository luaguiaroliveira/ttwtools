"""spaCy POS tagger backend for ttwtools.

Produces per-document POS-tag frequency tables using spaCy's English pipeline.
Two modes:

    spacy_upos — counts Universal POS (UPOS) tags via ``token.pos_``:
                 NOUN, VERB, ADJ, PROPN, …
    spacy_ptb  — counts Penn Treebank tags via ``token.tag_``:
                 NN, VBZ, JJ, RB, …

Both modes load the same spaCy pipeline and differ only in which token
attribute is used as the feature column.  When both are requested together,
:func:`extract_spacy_combined_features_from_folder` runs ``nlp.pipe`` over the
entire corpus **once**, deriving both tag sets from the same spaCy docs.

Offset strategy
---------------
spaCy provides ``token.idx`` (start char) on the *stripped* text (HTML tags
removed).  End char = ``token.idx + len(token.text)``.
``_build_offset_map()`` remaps those positions back to the original file's
character positions, satisfying the JSONL invariant:

    ``original_text[start_char:end_char] == token.text``  for every token.

Pipeline caching
----------------
The spaCy model object is cached per model name to avoid re-loading it on
every call.  Disable ``ner`` and ``parser`` for speed — POS tagging only
requires the ``tok2vec`` and ``tagger`` components.

Batch processing
----------------
:func:`extract_spacy_combined_features_from_folder` feeds all files through
``nlp.pipe`` in a single streaming pass (``batch_size=32`` by default), which
is significantly faster than calling ``nlp(text)`` per document.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd
from tqdm.auto import tqdm

from ..tagged_io import write_tagged_jsonl

try:
    from importlib.metadata import version as _pkg_version
    _SPACY_VERSION = _pkg_version("spacy")
except Exception:
    _SPACY_VERSION = "unknown"

#: Default spaCy English model.  Override via the ``spacy_model`` parameter.
DEFAULT_SPACY_MODEL = "en_core_web_sm"

#: Components disabled by default — POS tagging does not need parser or NER.
_DISABLED = ["ner", "parser"]

# ---------------------------------------------------------------------------
# Pipeline cache
# ---------------------------------------------------------------------------

_pipeline_cache: dict = {}


def _load_spacy_pipeline(model_name: str = DEFAULT_SPACY_MODEL):
    """Return a cached spaCy NLP pipeline for *model_name*."""
    if model_name not in _pipeline_cache:
        import spacy  # noqa: lazy import
        _pipeline_cache[model_name] = spacy.load(model_name, disable=_DISABLED)
    return _pipeline_cache[model_name]


# ---------------------------------------------------------------------------
# Offset helpers  (same logic used by biberplus.py / stanza_pos.py)
# ---------------------------------------------------------------------------

def _build_offset_map(original: str, stripped: str) -> list[int] | None:
    """Map each char position in *stripped* back to its position in *original*.

    *stripped* is produced by ``re.sub(r"<[^>]*>", "", original)``.
    Returns ``None`` when the two strings are identical (no HTML present).
    """
    if original == stripped:
        return None

    offset_map: list[int] = []
    orig_pos = 0

    for ch in stripped:
        while orig_pos < len(original) and original[orig_pos] == "<":
            end = original.find(">", orig_pos)
            if end == -1:
                orig_pos = len(original)
                break
            orig_pos = end + 1
        offset_map.append(orig_pos)
        if orig_pos < len(original):
            orig_pos += 1

    return offset_map


def _map_span(start: int, end: int, offset_map: list[int] | None) -> tuple[int, int]:
    """Remap a span from stripped-text space to original-text space."""
    if offset_map is None:
        return start, end
    mapped_start = offset_map[start] if start < len(offset_map) else start
    mapped_end = (offset_map[end - 1] + 1) if end > 0 and (end - 1) < len(offset_map) else end
    return mapped_start, mapped_end


# ---------------------------------------------------------------------------
# Inner kernels (operate on a pre-computed spaCy Doc)
# ---------------------------------------------------------------------------

def tag_from_doc_spacy_pos(doc, original_text: str, offset_map, mode: str = "upos") -> list[dict]:
    """Extract spaCy POS tokens from a pre-computed spaCy *doc*.

    This inner kernel is shared by :func:`_tag_document_spacy_pos` and the
    combined folder function so that ``nlp.pipe`` runs only once even when
    both ``spacy_upos`` and ``spacy_ptb`` are requested.

    Parameters
    ----------
    doc           : spaCy ``Doc`` already produced by the pipeline.
    original_text : raw file content (may include ``<…>`` markup).
    offset_map    : mapping from stripped-text positions to original-text
                    positions, as returned by :func:`_build_offset_map`.
    mode          : ``"upos"`` → ``token.pos_``;
                    ``"ptb"``  → ``token.tag_``.
    """
    result: list[dict] = []
    for token in doc:
        if token.is_space:
            continue
        upos = token.pos_ or ""
        ptb  = token.tag_  or ""
        feature_tag = upos if mode == "upos" else ptb
        tags = [feature_tag] if feature_tag and feature_tag not in ("", "_", "SP") else []
        start = token.idx
        end   = token.idx + len(token.text)
        mapped_start, mapped_end = _map_span(start, end, offset_map)
        tok = {
            "start_char": mapped_start,
            "end_char":   mapped_end,
            "word":       token.text,
            "upos":       upos,
            "ptb":        ptb,
            "tags":       tags,
        }
        if token.lemma_:
            tok["lemma"] = token.lemma_
        morph = str(token.morph)
        if morph:
            tok["feats"] = morph
        result.append(tok)
    return result


def _tag_document_spacy_pos(original_text: str, nlp, mode: str = "upos") -> list[dict]:
    """Tag a single document and return tokens with original-file offsets."""
    text = re.sub(r"<[^>]*>", "", original_text)
    offset_map = _build_offset_map(original_text, text)
    doc = nlp(text)
    return tag_from_doc_spacy_pos(doc, original_text, offset_map, mode=mode)


# ---------------------------------------------------------------------------
# Tagging set constants
# ---------------------------------------------------------------------------

#: All tagger names that share the spaCy pipeline.
SPACY_BASED_TAGGERS = frozenset({"spacy_upos", "spacy_ptb"})

_TAGGER_CSV_SUFFIX: dict[str, str] = {
    "spacy_upos": "spacy_upos",
    "spacy_ptb":  "spacy_ptb",
}


# ---------------------------------------------------------------------------
# Helper: build one feature-record from a list of token dicts
# ---------------------------------------------------------------------------

def _make_record(filename: str, tokens: list[dict]) -> dict:
    word_tokens = [t for t in tokens if re.search(r"[A-Za-z]", t["word"])]
    n_words = len(word_tokens)
    ttr = len({t["word"].lower() for t in word_tokens}) / n_words if n_words > 0 else 0.0
    all_tags = [tag for t in tokens for tag in t["tags"]]
    tag_counts = pd.Series(all_tags).value_counts() if all_tags else pd.Series(dtype=int)
    parts = filename.split(".")
    record: dict = {
        "filename": filename,
        "field":    parts[1] if len(parts) > 1 else "unknown",
        "section":  parts[3] if len(parts) > 3 else "unknown",
        "Words":    n_words,
        "TTR":      ttr,
    }
    for tag, count in tag_counts.items():
        record[str(tag)] = count
    return record


# ---------------------------------------------------------------------------
# Combined multi-mode folder function (single nlp.pipe pass)
# ---------------------------------------------------------------------------

def extract_spacy_combined_features_from_folder(
    folder_path_str: str,
    taggers: list[str],
    output_dir: str = None,
    save_tagged: bool = False,
    spacy_model: str = DEFAULT_SPACY_MODEL,
    batch_size: int = 32,
) -> dict[str, "Path"]:
    """Process a corpus folder with one or both spaCy POS taggers in **one** pass.

    Feeds all ``.txt`` files through ``nlp.pipe`` **once**, then derives
    ``spacy_upos`` and/or ``spacy_ptb`` feature tables from the same spaCy
    docs — no redundant inference.

    Parameters
    ----------
    folder_path_str : path to the corpus folder.
    taggers         : subset of ``{"spacy_upos", "spacy_ptb"}``.
    output_dir      : directory for output CSVs (defaults to corpus parent).
    save_tagged     : if True, write one JSONL per document per tagger in
                      ``<output_dir>/<corpus>_tagged/``.
    spacy_model     : spaCy model name (default: ``en_core_web_sm``).
    batch_size      : ``nlp.pipe`` batch size.

    Returns
    -------
    dict mapping each (valid) tagger name to its raw-count CSV ``Path``.
    """
    taggers = [t for t in taggers if t in SPACY_BASED_TAGGERS]
    if not taggers:
        return {}

    corpus_path = Path(folder_path_str).resolve()
    if not corpus_path.is_dir():
        print(f"Erro: A pasta '{corpus_path}' nao foi encontrada.")
        return {}

    base_out = Path(output_dir).resolve() if output_dir else corpus_path.parent
    base_out.mkdir(parents=True, exist_ok=True)

    if save_tagged:
        tagged_dir = base_out / f"{corpus_path.name}_tagged"
        tagged_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Corpus  : '{corpus_path.name}'")
    print(f"  Taggers : {', '.join(taggers)}")
    print(f"  Modelo  : {spacy_model}  (passagem única por nlp.pipe)")
    print(f"{'=' * 60}")
    print(f"  -> Carregando modelo spaCy '{spacy_model}'…")
    nlp = _load_spacy_pipeline(spacy_model)
    print(f"     Modelo carregado (spacy {_SPACY_VERSION})")

    file_list = sorted(corpus_path.glob("*.txt"))
    if not file_list:
        print(f"  Aviso: Nenhum arquivo .txt encontrado em '{corpus_path}'.")
        return {}

    print(f"  -> Processando {len(file_list)} arquivo(s) via nlp.pipe (batch_size={batch_size})…")

    # Pre-process all texts (strip HTML, build offset maps)
    originals:   list[str]            = []
    stripped:    list[str]            = []
    offset_maps: list[list[int]|None] = []

    for txt_path in file_list:
        orig = txt_path.read_text(encoding="utf-8", errors="ignore")
        strip = re.sub(r"<[^>]*>", "", orig)
        originals.append(orig)
        stripped.append(strip)
        offset_maps.append(_build_offset_map(orig, strip))

    # Per-tagger accumulators
    tagger_records: dict[str, list[dict]] = {t: [] for t in taggers}

    def _iter_stripped():
        yield from stripped

    for idx, doc in enumerate(
        tqdm(
            nlp.pipe(_iter_stripped(), batch_size=batch_size),
            total=len(file_list),
            desc=f"  Analisando {corpus_path.name}",
            unit="doc",
        )
    ):
        filename   = file_list[idx].name
        orig_text  = originals[idx]
        off_map    = offset_maps[idx]

        for tagger in taggers:
            mode = "upos" if tagger == "spacy_upos" else "ptb"
            tokens = tag_from_doc_spacy_pos(doc, orig_text, off_map, mode=mode)

            if save_tagged:
                tagged_file = tagged_dir / f"{file_list[idx].stem}_{tagger}.jsonl"
                try:
                    meta: dict = {
                        "tagger":         tagger,
                        "tagger_version": _SPACY_VERSION,
                        "spacy_version":  _SPACY_VERSION,
                        "spacy_model":    spacy_model,
                        "combined_pass":  True,
                        "filename":       filename,
                    }
                    write_tagged_jsonl(meta, tokens, tagged_file)
                except Exception:
                    pass

            tagger_records[tagger].append(_make_record(filename, tokens))

    # Write per-tagger raw-count CSVs
    result_paths: dict[str, Path] = {}
    for tagger in taggers:
        suffix   = _TAGGER_CSV_SUFFIX[tagger]
        csv_name = f"{corpus_path.name}_{suffix}_rawcount.csv"
        csv_path = base_out / csv_name
        records  = tagger_records[tagger]
        if records:
            df = pd.DataFrame(records)
            df.to_csv(csv_path, index=False)
            print(f"  + [{tagger}] Contagens brutas: '{csv_name}' ({len(df)} documentos)")
        else:
            print(f"  Aviso: [{tagger}] Nenhum dado processado.")
        result_paths[tagger] = csv_path

    return result_paths


# ---------------------------------------------------------------------------
# Single-mode folder function (used by standalone tagging route)
# ---------------------------------------------------------------------------

def extract_spacy_pos_features_from_folder(
    folder_path_str: str,
    mode: str = "upos",
    output_dir: str = None,
    save_tagged: bool = False,
    spacy_model: str = DEFAULT_SPACY_MODEL,
    batch_size: int = 32,
):
    """Process a corpus folder with a single spaCy POS tagger."""
    tagger = "spacy_upos" if mode == "upos" else "spacy_ptb"
    return extract_spacy_combined_features_from_folder(
        folder_path_str=folder_path_str,
        taggers=[tagger],
        output_dir=output_dir,
        save_tagged=save_tagged,
        spacy_model=spacy_model,
        batch_size=batch_size,
    )


def normalize_spacy_pos_features(csv_path_str: str, decimal_places=None):
    """Normalise raw spaCy POS feature counts to per-1000-words values.

    Reads ``*_spacy_{mode}_rawcount.csv`` and writes
    ``*_spacy_{mode}_norm1000.csv``.
    """
    csv_path = Path(csv_path_str).resolve()
    if not csv_path.is_file():
        print(f"Erro: O arquivo '{csv_path}' nao foi encontrado.")
        return
    norm_csv_name = csv_path.stem.replace("_rawcount", "") + "_norm1000.csv"
    norm_csv_path = csv_path.parent / norm_csv_name
    print(f"\n{'-' * 60}")
    print(f"  Normalizando: '{csv_path.name}'")
    print(f"  -> Saida: '{norm_csv_name}'")
    df = pd.read_csv(csv_path)
    cols = [c for c in df.columns if c not in ("filename", "field", "section", "Words", "TTR")]
    df_norm = df.copy()
    for col in cols:
        df_norm[col] = (df[col] * 1000) / df["Words"]
        if decimal_places is not None:
            df_norm[col] = df_norm[col].round(decimal_places)
    df_norm.to_csv(norm_csv_path, index=False)
    print(f"  + Normalizacao concluida: '{norm_csv_path.name}'")


# ---------------------------------------------------------------------------
# High-level aliases
# ---------------------------------------------------------------------------

def spacy_upos(
    folder_path_str: str,
    output_dir: str = None,
    save_tagged: bool = False,
    spacy_model: str = DEFAULT_SPACY_MODEL,
):
    """High-level alias for spaCy UPOS (``token.pos_``) feature extraction."""
    return extract_spacy_pos_features_from_folder(
        folder_path_str=folder_path_str,
        mode="upos",
        output_dir=output_dir,
        save_tagged=save_tagged,
        spacy_model=spacy_model,
    )


def spacy_ptb(
    folder_path_str: str,
    output_dir: str = None,
    save_tagged: bool = False,
    spacy_model: str = DEFAULT_SPACY_MODEL,
):
    """High-level alias for spaCy Penn Treebank (``token.tag_``) feature extraction."""
    return extract_spacy_pos_features_from_folder(
        folder_path_str=folder_path_str,
        mode="ptb",
        output_dir=output_dir,
        save_tagged=save_tagged,
        spacy_model=spacy_model,
    )
