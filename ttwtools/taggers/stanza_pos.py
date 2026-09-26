"""Stanza POS tagger backend for ttwtools.

Produces per-document POS-tag frequency tables using Stanza's Universal
Dependencies (UD) POS tagger.  Two modes:

    stanza_upos — counts Universal POS (UPOS) tags: NOUN, VERB, ADJ, …
    stanza_xpos — counts treebank-specific POS (XPOS) tags: NN, VBZ, JJ, …

Both modes run the same Stanza ``tokenize,pos`` pipeline and differ only in
which field is used as the feature column.

Offset strategy
---------------
Stanza provides ``word.start_char`` / ``word.end_char`` on the *stripped* text
(HTML tags removed).  ``_build_offset_map()`` remaps those positions back to
the original file's character positions, satisfying the JSONL invariant:

    ``original_text[start_char:end_char] == word``  for every token.

Pipeline caching
----------------
The Stanza ``Pipeline`` object is cached per ``(device, model_dir)`` to avoid
re-loading the model for every document.  The cache is intentionally separate
from the one in ``mfte.py`` so each module can be used independently, but in
practice both modules share the same Stanza process so only one model is loaded
when both taggers are requested in the same session.

Device selection
----------------
MPS (Apple Silicon) is intentionally excluded — Stanza's BiLSTM models run
~2.4× slower on MPS than on CPU due to transfer overhead.
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
    _STANZA_VERSION = _pkg_version("stanza")
except Exception:
    _STANZA_VERSION = "unknown"


# ---------------------------------------------------------------------------
# Device detection
# ---------------------------------------------------------------------------

def _detect_device() -> str:
    """Return the best available device: ``"cuda"`` or ``"cpu"`` (MPS excluded)."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


# ---------------------------------------------------------------------------
# Stanza pipeline cache
# ---------------------------------------------------------------------------

_pipeline_cache: dict = {}


def _load_stanza_pipeline(device: str, model_dir: Optional[str] = None, *, lang: str | None = None,
                          processors: str = "tokenize,pos", package: str | None = None,
                          download: bool = True, **stanza_options):
    """Return a cached ``stanza.Pipeline`` for the given device.

    Parameters
    ----------
    device    : ``"cuda"`` or ``"cpu"``
    model_dir : path to a pre-downloaded Stanza model directory.
                Resolved in order:
                1. explicit ``model_dir`` argument
                2. ``STANZA_RESOURCES_DIR`` environment variable
                3. Stanza default (``~/stanza_resources/``)
    lang, package, processors : idioma, pacote (treebank) e processadores; padrões do
                descritor ``data/taggers/stanza.options.json`` (en, default).
    download  : se False, não baixa nada: modelo ausente vira TaggerUnavailable com
                o comando para baixar.
    stanza_options : outras opções do Pipeline (tokenize_no_ssplit, pos_batch_size...).
    """
    import os
    import stanza  # noqa: imported lazily

    if model_dir is None:
        model_dir = os.environ.get("STANZA_RESOURCES_DIR") or None

    if lang is None or package is None:
        from .catalog import result_defaults
        defaults = result_defaults("stanza")
        lang = lang or defaults["lang"]
        package = package or defaults["package"]

    key = (device, model_dir or "", lang, package, processors, tuple(sorted(stanza_options.items())))
    if key not in _pipeline_cache:
        if not download:
            from .catalog import TaggerUnavailable, stanza_download_command, stanza_package_installed
            from ..i18n import t
            if not stanza_package_installed(lang, package, processors.split(","), model_dir):
                command = stanza_download_command(lang, package, processors)
                raise TaggerUnavailable("stanza", t("tagger.reason.missing_model", model=f"stanza {lang}/{package}",
                                                    command=command), command)
        kwargs: dict = {
            "processors": processors,
            "package": package,
            "device": device,
            "verbose": False,
            "download_method": stanza.DownloadMethod.REUSE_RESOURCES if download else None,
            **stanza_options,
        }
        if model_dir:
            kwargs["dir"] = model_dir
        _pipeline_cache[key] = stanza.Pipeline(lang, **kwargs)
    return _pipeline_cache[key]


# ---------------------------------------------------------------------------
# Offset helpers
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

def _tag_document_stanza_pos(
    original_text: str,
    nlp,
    mode: str = "upos",
) -> list[dict]:
    """Tag *original_text* with Stanza and return tokens with original-file offsets.

    Parameters
    ----------
    original_text : raw file content (may include ``<…>`` markup).
    nlp           : Stanza ``Pipeline`` instance (``tokenize,pos`` processors).
    mode          : ``"upos"`` to use Universal POS tags as features,
                   ``"xpos"`` to use treebank-specific POS tags as features.

    Returns
    -------
    List of dicts with keys: ``start_char``, ``end_char``, ``word``, ``upos``,
    ``xpos``, ``tags``.  ``tags`` is a single-element list containing the POS
    tag selected by *mode* (the feature used for counting), or an empty list
    for tokens with no tag (e.g. punctuation with ``_``).
    """
    text = re.sub(r"<[^>]*>", "", original_text)
    offset_map = _build_offset_map(original_text, text)
    doc = nlp(text)
    return tag_from_doc_stanza_pos(doc, original_text, offset_map, mode=mode)


def tag_from_doc_stanza_pos(doc, original_text: str, offset_map, mode: str = "upos") -> list[dict]:
    """Extract Stanza POS tokens from a pre-computed Stanza *doc*.

    This is the inner kernel shared by :func:`_tag_document_stanza_pos` and
    :func:`extract_stanza_combined_features_from_folder` so that the Stanza
    ``nlp(text)`` inference call is performed only once when multiple
    Stanza-based taggers are requested together.

    Parameters
    ----------
    doc           : Stanza ``Document`` already produced by the pipeline.
    original_text : raw file content (may include ``<…>`` markup).
    offset_map    : mapping from stripped-text positions to original-text
                    positions, as returned by :func:`_build_offset_map`.
    mode          : ``"upos"`` or ``"xpos"``.
    """
    result: list[dict] = []
    for sentence in doc.sentences:
        for word in sentence.words:
            upos = word.upos or ""
            xpos = word.xpos or ""
            feature_tag = upos if mode == "upos" else xpos
            tags = [feature_tag] if feature_tag and feature_tag != "_" else []
            mapped_start, mapped_end = _map_span(word.start_char, word.end_char, offset_map)
            tok = {
                "start_char": mapped_start,
                "end_char": mapped_end,
                "word": word.text,
                "upos": upos,
                "xpos": xpos,
                "tags": tags,
            }
            if getattr(word, "lemma", None):
                tok["lemma"] = word.lemma
            if getattr(word, "feats", None):
                tok["feats"] = word.feats
            result.append(tok)
    return result


# ---------------------------------------------------------------------------
# Combined multi-tagger folder function (single Stanza pass)
# ---------------------------------------------------------------------------

#: Taggers that all share the same Stanza ``tokenize,pos`` pipeline and can
#: therefore be run in a single pass per document.
STANZA_BASED_TAGGERS = frozenset({"mfte", "mfte_ext", "stanza_upos", "stanza_xpos"})

#: Maps each Stanza-based tagger to the stem suffix used for its raw-count CSV.
_TAGGER_CSV_SUFFIX = {
    "stanza_upos": "stanza_upos",
    "stanza_xpos": "stanza_xpos",
    "mfte":        "mfte",
    "mfte_ext":    "mfte_ext",
}


def extract_stanza_combined_features_from_folder(
    folder_path_str: str,
    taggers: list[str],
    output_dir: str = None,
    save_tagged: bool = False,
    use_gpu=None,
    model_dir: str = None,
) -> dict[str, "Path"]:
    """Process a corpus folder with multiple Stanza-based taggers in **one** Stanza pass.

    Runs ``stanza.Pipeline(tokenize,pos)`` **once per document** regardless of
    how many taggers are requested, avoiding redundant neural-network inference.
    Each tagger's features are derived from the single shared Stanza output.

    Parameters
    ----------
    folder_path_str : path to the corpus folder containing ``.txt`` files.
    taggers         : non-empty subset of ``{"mfte", "mfte_ext", "stanza_upos",
                      "stanza_xpos"}``.  Unknown values are silently ignored.
    output_dir      : directory for output CSVs; defaults to the corpus folder's parent.
    save_tagged     : if True, write one JSONL file per document per tagger in
                      ``<output_dir>/<corpus>_tagged/``.
    use_gpu         : ``None`` = auto-detect, ``True`` = force GPU, ``False`` = CPU.
    model_dir       : override path for Stanza model resources.

    Returns
    -------
    dict mapping each (valid) tagger name to the ``Path`` of its raw-count CSV.
    The caller is responsible for normalisation (call
    :func:`normalize_stanza_pos_features` or
    :func:`~ttwtools.taggers.mfte.normalize_mfte_features` as appropriate) and
    for saving results to the ``.ttwa`` project.
    """
    taggers = [t for t in taggers if t in STANZA_BASED_TAGGERS]
    if not taggers:
        return {}

    mfte_present = any(t.startswith("mfte") for t in taggers)
    if mfte_present:
        # Lazy import — avoids loading torch/MFTE at package import time
        from .mfte import tag_from_doc_mfte as _mfte_kernel

    corpus_path = Path(folder_path_str).resolve()
    if not corpus_path.is_dir():
        print(f"Erro: A pasta '{corpus_path}' nao foi encontrada.")
        return {}

    if output_dir:
        base_out = Path(output_dir).resolve()
        base_out.mkdir(parents=True, exist_ok=True)
    else:
        base_out = corpus_path.parent

    if save_tagged:
        tagged_dir = base_out / f"{corpus_path.name}_tagged"
        tagged_dir.mkdir(parents=True, exist_ok=True)

    # Resolve device
    if use_gpu is None:
        device = _detect_device()
    elif use_gpu:
        device = _detect_device()
        if device == "cpu":
            print("  Aviso: GPU solicitada mas nao disponivel. Usando CPU.")
    else:
        device = "cpu"

    print(f"\n{'=' * 60}")
    print(f"  Corpus  : '{corpus_path.name}'")
    print(f"  Taggers : {', '.join(taggers)}")
    print(f"  Device  : {device}  (passagem única por Stanza)")
    print(f"{'=' * 60}")
    print("  -> Carregando pipeline Stanza (tokenize,pos)...")
    nlp = _load_stanza_pipeline(device, model_dir)
    print(f"     Pipeline carregado (stanza {_STANZA_VERSION})")

    file_list = list(corpus_path.glob("*.txt"))
    if not file_list:
        print(f"  Aviso: Nenhum arquivo .txt encontrado em '{corpus_path}'.")
        return {}

    print(f"  -> Processando {len(file_list)} arquivo(s) ({len(taggers)} tagger(s), 1 passagem Stanza)…")

    # Per-tagger accumulator: tagger_name → list of row-dicts (one per document)
    tagger_records: dict[str, list[dict]] = {t: [] for t in taggers}

    for txt_path in tqdm(file_list, desc=f"  Analisando {corpus_path.name}", unit="doc"):
        original_text = txt_path.read_text(encoding="utf-8", errors="ignore")
        filename = txt_path.name

        # ── Single Stanza pass ────────────────────────────────────────────
        text = re.sub(r"<[^>]*>", "", original_text)
        offset_map = _build_offset_map(original_text, text)
        try:
            doc = nlp(text)
        except Exception as exc:
            print(f"\n  Aviso: Stanza falhou em '{filename}': {exc}")
            for t in taggers:
                tagger_records[t].append(_empty_record(filename))
            continue

        # ── Per-tagger extraction ─────────────────────────────────────────
        for tagger in taggers:
            try:
                if tagger == "stanza_upos":
                    tokens = tag_from_doc_stanza_pos(doc, original_text, offset_map, mode="upos")
                elif tagger == "stanza_xpos":
                    tokens = tag_from_doc_stanza_pos(doc, original_text, offset_map, mode="xpos")
                else:  # "mfte" or "mfte_ext"
                    tokens = _mfte_kernel(doc, original_text, offset_map,
                                         extended=(tagger == "mfte_ext"))
            except Exception as exc:
                print(f"\n  Aviso: falha no tagger '{tagger}' para '{filename}': {exc}")
                tokens = []

            word_tokens = [tok for tok in tokens if re.search(r"[A-Za-z]", tok["word"])]
            n_words = len(word_tokens)
            unique_words = {tok["word"].lower() for tok in word_tokens}
            ttr = len(unique_words) / n_words if n_words > 0 else 0.0

            all_tags = [tag for tok in tokens for tag in tok["tags"]]
            tag_counts = pd.Series(all_tags).value_counts() if all_tags else pd.Series(dtype=int)

            if save_tagged:
                tagged_file = tagged_dir / f"{txt_path.stem}_{tagger}.jsonl"
                try:
                    meta: dict = {
                        "tagger": tagger,
                        "tagger_version": _STANZA_VERSION,
                        "stanza_version": _STANZA_VERSION,
                        "stanza_model": "en",
                        "device": device,
                        "combined_pass": True,
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
            tagger_records[tagger].append(record)

    # ── Write per-tagger raw-count CSVs ──────────────────────────────────
    result_paths: dict[str, Path] = {}
    for tagger in taggers:
        suffix = _TAGGER_CSV_SUFFIX[tagger]
        csv_name = f"{corpus_path.name}_{suffix}_rawcount.csv"
        csv_path = base_out / csv_name
        records = tagger_records[tagger]
        if records:
            df = pd.DataFrame(records)
            df.to_csv(csv_path, index=False)
            print(f"  + [{tagger}] Contagens brutas: '{csv_name}' ({len(df)} documentos)")
        else:
            print(f"  Aviso: [{tagger}] Nenhum dado processado.")
        result_paths[tagger] = csv_path

    return result_paths


def _empty_record(filename: str) -> dict:
    """Return a minimal placeholder row for a document that failed to process."""
    parts = filename.split(".")
    return {
        "filename": filename,
        "field": parts[1] if len(parts) > 1 else "unknown",
        "section": parts[3] if len(parts) > 3 else "unknown",
        "Words": 0,
        "TTR": 0.0,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_stanza_pos_features_from_folder(
    folder_path_str: str,
    mode: str = "upos",
    output_dir: str = None,
    save_tagged: bool = False,
    copy_originals: bool = False,
    use_gpu=None,
    model_dir: str = None,
):
    """Process all .txt files in a folder, extract Stanza POS features, save CSV.

    Parameters
    ----------
    folder_path_str : path to the corpus folder containing ``.txt`` files.
    mode            : ``"upos"`` for Universal POS tags, ``"xpos"`` for
                      treebank-specific POS tags.
    output_dir      : directory for all outputs; defaults to the corpus
                      folder's parent.
    save_tagged     : if True, write one ``<stem>_stanza_<mode>.jsonl`` per
                      document in ``<output_dir>/<corpus>_tagged/``.
    copy_originals  : if True, copy source ``.txt`` files to
                      ``<output_dir>/originals/<corpus>/``.
    use_gpu         : ``None`` = auto-detect, ``True`` = force GPU,
                      ``False`` = force CPU.
    model_dir       : override path for Stanza model resources.
    """
    if mode not in ("upos", "xpos"):
        raise ValueError(f"mode deve ser 'upos' ou 'xpos', não '{mode}'.")

    corpus_path = Path(folder_path_str).resolve()
    if not corpus_path.is_dir():
        print(f"Erro: A pasta '{corpus_path}' nao foi encontrada.")
        return

    if output_dir:
        base_out = Path(output_dir).resolve()
        base_out.mkdir(parents=True, exist_ok=True)
    else:
        base_out = corpus_path.parent

    csv_name = f"{corpus_path.name}_stanza_{mode}_rawcount.csv"
    csv_path = base_out / csv_name

    if save_tagged:
        tagged_dir = base_out / f"{corpus_path.name}_tagged"
        tagged_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Corpus : '{corpus_path.name}'")
    print(f"  Modo   : stanza_{mode}")
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

    print(f"  -> Device: {device}  |  mode: stanza_{mode}")
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

    print(f"  -> Taggeando {len(file_list)} arquivo(s) com Stanza {mode.upper()}...")
    if save_tagged:
        print(f"     Tokens taggeados serao salvos em: {tagged_dir}/")

    all_records_flat = []

    for txt_path in tqdm(file_list, desc=f"  Analisando {corpus_path.name}", unit="doc"):
        original_text = txt_path.read_text(encoding="utf-8", errors="ignore")
        filename = txt_path.name

        try:
            tokens = _tag_document_stanza_pos(original_text, nlp, mode=mode)
        except Exception as exc:
            print(f"\n  Aviso: falha ao taggar '{filename}': {exc}")
            tokens = []

        # Word count from tagged tokens (real alphabetic words only)
        word_tokens = [t for t in tokens if re.search(r"[A-Za-z]", t["word"])]
        n_words = len(word_tokens)
        unique_words = {t["word"].lower() for t in word_tokens}
        n_unique_words = len(unique_words)
        ttr = n_unique_words / n_words if n_words > 0 else 0.0

        # Count POS feature tags across all tokens
        all_tags = [tag for t in tokens for tag in t["tags"]]
        tag_counts = pd.Series(all_tags).value_counts() if all_tags else pd.Series(dtype=int)

        if save_tagged:
            tagged_file = tagged_dir / f"{txt_path.stem}_stanza_{mode}.jsonl"
            try:
                meta: dict = {
                    "tagger": f"stanza_{mode}",
                    "tagger_version": _STANZA_VERSION,
                    "stanza_version": _STANZA_VERSION,
                    "stanza_model": "en",
                    "device": device,
                    "mode": mode,
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


def normalize_stanza_pos_features(csv_path_str: str, decimal_places=None):
    """Normalise raw Stanza POS feature counts to per-1000-words values.

    Reads ``*_stanza_{mode}_rawcount.csv`` produced by
    :func:`extract_stanza_pos_features_from_folder` and writes a companion
    ``*_stanza_{mode}_norm1000.csv`` where every feature column is divided by
    the document word count and multiplied by 1 000.

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


def stanza_upos(
    folder_path_str: str,
    output_dir: str = None,
    save_tagged: bool = False,
    copy_originals: bool = False,
    use_gpu=None,
    model_dir: str = None,
):
    """High-level alias for Stanza UPOS feature extraction."""
    return extract_stanza_pos_features_from_folder(
        folder_path_str=folder_path_str,
        mode="upos",
        output_dir=output_dir,
        save_tagged=save_tagged,
        copy_originals=copy_originals,
        use_gpu=use_gpu,
        model_dir=model_dir,
    )


def stanza_xpos(
    folder_path_str: str,
    output_dir: str = None,
    save_tagged: bool = False,
    copy_originals: bool = False,
    use_gpu=None,
    model_dir: str = None,
):
    """High-level alias for Stanza XPOS feature extraction."""
    return extract_stanza_pos_features_from_folder(
        folder_path_str=folder_path_str,
        mode="xpos",
        output_dir=output_dir,
        save_tagged=save_tagged,
        copy_originals=copy_originals,
        use_gpu=use_gpu,
        model_dir=model_dir,
    )
