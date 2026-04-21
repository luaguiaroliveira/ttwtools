"""MFTE tagging backend for ttwtools.

Uses the Stanza Python API directly (NOT the MFTE file-based CLI) so that each
token carries ``start_char``/``end_char`` offsets that refer to the unmodified
original ``.txt`` file, satisfying the JSONL canonical-format invariant:

    ``original_text[start_char:end_char] == word``  for every token.

Offset strategy
---------------
1.  HTML/markup (``<…>``) is stripped from the raw file content before tagging,
    using the same ``re.sub(r"<[^>]*>", "", text)`` the BiberPlus backend uses.
2.  Stanza is run on the *stripped* text — its ``word.start_char``/``word.end_char``
    are therefore relative to that stripped text.
3.  ``_build_offset_map(original, stripped)`` maps each stripped-text position
    back to the original-file position so the JSONL offsets are always valid
    against the file on disk.

Sentinel mechanic (MFTE internal)
----------------------------------
``process_sentence()`` uses lists of single-space strings ``[' ', ' ', ...]``
(20 per sentence boundary) as context guards to avoid ``IndexError`` in the
lookahead rules.  Confirmed behaviour: the returned list is **1:1** with the
input — each position is preserved, sentinels included.  After filtering
``[w for w in result if w != " "]`` the remaining entries align 1:1 with the
Stanza tokens (which were inserted without sentinels).

Device selection
----------------
- ``use_gpu=None`` (default) — auto-detect: CUDA > MPS > CPU
- ``use_gpu=True``  — force GPU; warns and falls back to CPU if unavailable
- ``use_gpu=False`` — force CPU

Pipeline caching
----------------
The Stanza ``Pipeline`` object is expensive to construct (~seconds).  A
module-level cache keyed on ``(device, model_dir)`` ensures only one pipeline
is created per process even when tagging many documents.
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
    _MFTE_VERSION = _pkg_version("MFTE")
except Exception:
    _MFTE_VERSION = "unknown"

try:
    from importlib.metadata import version as _pkg_version
    _STANZA_VERSION = _pkg_version("stanza")
except Exception:
    _STANZA_VERSION = "unknown"


# ---------------------------------------------------------------------------
# Device detection
# ---------------------------------------------------------------------------

def _detect_device() -> str:
    """Return the best available device for Stanza: ``"cuda"`` or ``"cpu"``.

    MPS (Apple Silicon) is intentionally excluded: benchmarks show Stanza's
    BiLSTM models run ~2.4× *slower* on MPS than on CPU due to transfer
    overhead for small sequence models.  CUDA is the only GPU device that
    provides a net speedup for Stanza.
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


# ---------------------------------------------------------------------------
# Stanza pipeline (cached per device+model_dir)
# ---------------------------------------------------------------------------

_pipeline_cache: dict = {}


def _load_stanza_pipeline(device: str, model_dir: Optional[str] = None):
    """Return a cached ``stanza.Pipeline`` for the given device.

    Parameters
    ----------
    device    : ``"cuda"`` or ``"cpu"`` (MPS excluded — see ``_detect_device``)
    model_dir : path to a pre-downloaded Stanza model directory; ``None`` uses
                the default ``~/.stanza/`` or ``~/Library/Caches/stanza/``.

    Note
    ----
    Stanza 1.7+ accepts a ``device=`` parameter directly (e.g. ``"cuda:0"``,
    ``"mps"``, ``"cpu"``).  We use ``device=`` rather than the legacy
    ``use_gpu=True`` flag because:
    - ``use_gpu=True`` without CUDA triggers a warning and falls back to CPU
      (it does not activate MPS).
    - ``device="cuda"`` is explicit and quiet.
    """
    import stanza  # noqa: imported lazily — stanza/torch not loaded until first call

    key = (device, model_dir or "")
    if key not in _pipeline_cache:
        kwargs: dict = {
            "processors": "tokenize,pos",
            "device": device,
            "verbose": False,
            "download_method": stanza.DownloadMethod.REUSE_RESOURCES,
        }
        if model_dir:
            kwargs["dir"] = model_dir
        _pipeline_cache[key] = stanza.Pipeline("en", **kwargs)
    return _pipeline_cache[key]


# ---------------------------------------------------------------------------
# Offset helpers (same logic as taggers/biberplus.py)
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
# Core tagging function
# ---------------------------------------------------------------------------

def _tag_document_mfte(
    original_text: str,
    nlp,
    extended: bool = True,
) -> list[dict]:
    """Tag *original_text* with MFTE and return tokens with original-file offsets.

    Parameters
    ----------
    original_text : raw file content (may include ``<…>`` markup).
    nlp           : Stanza ``Pipeline`` instance (``tokenize,pos`` processors).
    extended      : whether to apply the extended MFTE semantic categories.

    Returns
    -------
    List of dicts with keys: ``start_char``, ``end_char``, ``word``, ``xpos``,
    ``tags``.  ``xpos`` is the MFTE-modified Penn Treebank tag (may differ from
    Stanza's original tag because MFTE re-categorises some POS values).
    """
    from MFTE import process_sentence, process_sentence_extended  # noqa: lazy import

    # 1. Strip HTML so markup tokens don't confuse MFTE rules
    text = re.sub(r"<[^>]*>", "", original_text)
    offset_map = _build_offset_map(original_text, text)

    # 2. Stanza tokenisation on stripped text → per-token offsets
    doc = nlp(text)

    # 3. Build MFTE input list + parallel offset list
    all_tokens: list[tuple[int, int, str, str]] = []  # (start, end, word, xpos)
    mfte_input: list[str] = []

    for sentence in doc.sentences:
        mfte_input.extend([" "] * 20)          # sentence-boundary sentinels
        for word in sentence.words:
            mfte_input.append(f"{word.text}_{word.xpos}")
            all_tokens.append((word.start_char, word.end_char, word.text, word.xpos))

    mfte_input.extend([" "] * 20)              # final sentinel

    # 4. Apply MFTE tagging (pure function, no I/O)
    tagged = process_sentence(mfte_input, extended=extended)
    if extended:
        tagged = process_sentence_extended(tagged)

    # 5. Filter out sentinel entries (single-space strings); result is 1:1 with all_tokens
    filtered = [w for w in tagged if w != " "]

    # 6. Reassociate tags with offsets
    result: list[dict] = []
    for i, (st, en, word, stanza_xpos) in enumerate(all_tokens):
        if i >= len(filtered):
            break  # safety — should not happen
        raw = filtered[i]           # e.g. "study_NN NNABSPROC"
        parts = raw.split()
        # MFTE may reclassify the POS (e.g. NNS → NN); use the MFTE version
        mfte_xpos = parts[0].rsplit("_", 1)[-1] if len(parts) > 0 and "_" in parts[0] else stanza_xpos
        tags = parts[1:]            # all tokens after the first word_POS token
        mapped_start, mapped_end = _map_span(st, en, offset_map)
        result.append({
            "start_char": mapped_start,
            "end_char": mapped_end,
            "word": word,
            "xpos": mfte_xpos,
            "tags": tags,
        })

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_mfte_features_from_folder(
    folder_path_str: str,
    output_dir: str = None,
    save_tagged: bool = False,
    copy_originals: bool = False,
    use_gpu=None,
    extended: bool = True,
    model_dir: str = None,
):
    """Process all .txt files in a folder, extract MFTE features, save CSV.

    Parameters
    ----------
    folder_path_str : path to the corpus folder containing ``.txt`` files.
    output_dir      : directory for all outputs; defaults to the corpus
                      folder's parent.
    save_tagged     : if True, write one ``<stem>_mfte.jsonl`` per document
                      in ``<output_dir>/<corpus>_tagged/``.
    copy_originals  : if True, copy source ``.txt`` files to
                      ``<output_dir>/originals/<corpus>/``.
    use_gpu         : ``None`` = auto-detect, ``True`` = force GPU,
                      ``False`` = force CPU.
    extended        : apply extended MFTE semantic-category tagging.
    model_dir       : override path for Stanza model resources.
    """
    corpus_path = Path(folder_path_str).resolve()
    if not corpus_path.is_dir():
        print(f"Erro: A pasta '{corpus_path}' nao foi encontrada.")
        return

    if output_dir:
        base_out = Path(output_dir).resolve()
        base_out.mkdir(parents=True, exist_ok=True)
    else:
        base_out = corpus_path.parent

    csv_name = f"{corpus_path.name}_mfte_rawcount.csv"
    csv_path = base_out / csv_name

    if save_tagged:
        tagged_dir = base_out / f"{corpus_path.name}_tagged"
        tagged_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Corpus : '{corpus_path.name}'")
    print(f"  Origem : {corpus_path}")
    print(f"  Saida  : {base_out}")
    print(f"{'=' * 60}")

    # Resolve device
    if use_gpu is None:
        device = _detect_device()
    elif use_gpu:
        device = _detect_device()
        if device == "cpu":
            print("  Aviso: GPU solicitada mas nao disponivel. Usando CPU.")
    else:
        device = "cpu"

    print(f"  -> Device: {device}  |  extended: {extended}")
    print("  -> Carregando pipeline Stanza (tokenize,pos)...")
    nlp = _load_stanza_pipeline(device, model_dir)
    print(f"     Pipeline carregado (stanza {_STANZA_VERSION})")

    if copy_originals and output_dir:
        print(f"  -> Copiando originais para '{base_out}/originals/{corpus_path.name}/'...")
        try:
            originals_dir = base_out / "originals"
            originals_dir.mkdir(parents=True, exist_ok=True)
            dest = originals_dir / corpus_path.name
            if dest.exists():
                try:
                    shutil.copytree(corpus_path, dest, dirs_exist_ok=True)
                except TypeError:
                    for src in corpus_path.glob("*"):
                        dst = dest / src.name
                        try:
                            if src.is_dir():
                                shutil.copytree(src, dst)
                            else:
                                dst.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(src, dst)
                        except Exception:
                            pass
            else:
                try:
                    shutil.copytree(corpus_path, dest)
                except Exception:
                    dest.mkdir(parents=True, exist_ok=True)
                    for src in corpus_path.glob("*"):
                        try:
                            if src.is_dir():
                                shutil.copytree(src, dest / src.name)
                            else:
                                shutil.copy2(src, dest / src.name)
                        except Exception:
                            pass
        except Exception:
            pass

    file_list = list(corpus_path.glob("*.txt"))
    if not file_list:
        print(f"  Aviso: Nenhum arquivo .txt encontrado em '{corpus_path}'.")
        return

    print(f"  -> Taggeando {len(file_list)} arquivo(s) com MFTE...")
    if save_tagged:
        print(f"     Tokens taggeados serao salvos em: {tagged_dir}/")

    all_records_flat = []

    for txt_path in tqdm(file_list, desc=f"  Analisando {corpus_path.name}", unit="doc"):
        original_text = txt_path.read_text(encoding="utf-8", errors="ignore")
        filename = txt_path.name

        try:
            tokens = _tag_document_mfte(original_text, nlp, extended=extended)
        except Exception as exc:
            print(f"\n  Aviso: falha ao taggar '{filename}': {exc}")
            tokens = []

        # Word count from tagged tokens (real words, not markup)
        word_tokens = [t for t in tokens if re.search(r"[A-Za-z]", t["word"])]
        n_words = len(word_tokens)
        unique_words = {t["word"].lower() for t in word_tokens}
        n_unique_words = len(unique_words)
        ttr = n_unique_words / n_words if n_words > 0 else 0.0

        # Count MFTE feature tags across all tokens
        all_tags = [tag for t in tokens for tag in t["tags"]]
        tag_counts = pd.Series(all_tags).value_counts() if all_tags else pd.Series(dtype=int)

        if save_tagged:
            tagged_file = tagged_dir / f"{txt_path.stem}_mfte.jsonl"
            try:
                meta: dict = {
                    "tagger": "mfte",
                    "tagger_version": _MFTE_VERSION,
                    "stanza_version": _STANZA_VERSION,
                    "stanza_model": "en",
                    "device": device,
                    "extended": extended,
                    "filename": filename,
                }
                write_tagged_jsonl(meta, tokens, tagged_file)
            except Exception:
                pass

        field_name = filename.split(".")[1] if len(filename.split(".")) > 1 else "unknown"
        section_name = filename.split(".")[3] if len(filename.split(".")) > 3 else "unknown"

        record: dict = {
            "filename": filename,
            "field": field_name,
            "section": section_name,
            "Words": n_words,
            "TTR": ttr,
        }
        for tag, count in tag_counts.items():
            record[str(tag)] = count

        all_records_flat.append(record)

    if all_records_flat:
        df = pd.DataFrame(all_records_flat)
        df.to_csv(csv_path, index=False)
        print(f"  + Contagens brutas salvas: '{csv_path.name}' ({len(df)} documentos)")
    else:
        print("  Aviso: Nenhum dado foi processado.")


def normalize_mfte_features(csv_path_str: str, decimal_places=None):
    """Normalise raw MFTE feature counts to per-1000-words values.

    Reads ``*_mfte_rawcount.csv`` produced by
    :func:`extract_mfte_features_from_folder` and writes a companion
    ``*_mfte_norm1000.csv`` where every feature column is divided by the
    document word count and multiplied by 1 000.

    Parameters
    ----------
    csv_path_str:
        Path to the raw-count CSV file.
    decimal_places:
        If given, round normalised values to this many decimal places.
    """
    csv_path = Path(csv_path_str).resolve()
    if not csv_path.is_file():
        print(f"Erro: O arquivo '{csv_path}' nao foi encontrado.")
        return
    norm_csv_name = csv_path.stem.replace("_rawcount", "") + "_norm1000.csv"
    norm_csv_path = csv_path.parent / norm_csv_name
    print(f"\n{'-' * 60}")
    print(f"  Normalizando: '{csv_path.name}'")
    print("  -> Dividindo cada contagem por numero de palavras x 1000")
    print(f"  -> Saida: '{norm_csv_name}'")
    df = pd.read_csv(csv_path)
    cols_to_normalize = [
        col for col in df.columns
        if col not in ("filename", "field", "section", "Words", "TTR")
    ]
    df_norm = df.copy()
    for col in cols_to_normalize:
        df_norm[col] = (df[col] * 1000) / df["Words"]
        if decimal_places is not None:
            df_norm[col] = df_norm[col].round(decimal_places)
    df_norm.to_csv(norm_csv_path, index=False)
    print(f"  + Normalizacao concluida: '{norm_csv_path.name}'")


def mfte(
    folder_path_str: str,
    output_dir: str = None,
    save_tagged: bool = False,
    copy_originals: bool = False,
    use_gpu=None,
    extended: bool = True,
    model_dir: str = None,
):
    """High-level alias for MFTE feature extraction and tagging."""
    return extract_mfte_features_from_folder(
        folder_path_str=folder_path_str,
        output_dir=output_dir,
        save_tagged=save_tagged,
        copy_originals=copy_originals,
        use_gpu=use_gpu,
        extended=extended,
        model_dir=model_dir,
    )
