"""BiberPlus tagging backend for ttwtools.

Produces the canonical JSONL tagged format (see ``ttwtools.tagged_io``) with
character-level offsets into the original ``.txt`` file.

Offset strategy
---------------
When ``usenlp=True`` (spaCy pipeline):
    spaCy provides ``token.idx`` (start) and ``token.tag_`` (Penn-Treebank POS)
    for every token.  Biberplus tags are aligned with spaCy tokens by text match
    in sequential order.

When ``usenlp=False`` (biberplus default, NLTK-based):
    Each biberplus token is located in the source text via sequential
    ``str.find()``, which works correctly for any left-to-right tokeniser.
    ``xpos`` is left empty because NLTK does not produce Penn-Treebank tags here.

HTML stripping
--------------
The raw ``<…>`` markup is removed before tagging (to avoid spurious word
tokens from tag names/attributes).  When the original text contains HTML,
``_build_offset_map()`` remap stripped-text positions back to original-text
positions so the JSONL offsets always refer to the unmodified source file.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pandas as pd
from tqdm.auto import tqdm
from biberplus.tagger import tag_text, load_config, load_pipeline

from ..tagged_io import write_tagged_jsonl

try:
    from importlib.metadata import version as _pkg_version
    _BIBERPLUS_VERSION = _pkg_version("biberplus")
except Exception:
    _BIBERPLUS_VERSION = "unknown"

_has_alnum = re.compile(r"[A-Za-z0-9]")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_tw_word(wdict) -> str:
    """Extract the surface form from a biberplus tagged-word dict."""
    if isinstance(wdict, dict):
        return wdict.get("word") or wdict.get("text") or wdict.get("token") or ""
    return ""


def _build_offset_map(original: str, stripped: str) -> list[int] | None:
    """Map each character position in *stripped* to its position in *original*.

    *stripped* was produced by ``re.sub(r"<[^>]*>", "", original)``.
    Returns ``None`` when the two strings are identical (no mapping needed).
    """
    if original == stripped:
        return None

    offset_map: list[int] = []
    orig_pos = 0

    for ch in stripped:
        # Skip over any HTML/SGML tags in original
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
    """Convert a span in stripped text to a span in original text."""
    if offset_map is None:
        return start, end
    mapped_start = offset_map[start] if start < len(offset_map) else start
    mapped_end = (offset_map[end - 1] + 1) if end > 0 and (end - 1) < len(offset_map) else end
    return mapped_start, mapped_end


def _tokens_with_offsets_spacy(doc, tagged_words: list, offset_map: list[int] | None) -> list[dict]:
    """Align biberplus tags with spaCy token offsets.

    Both *doc* and *tagged_words* were produced from the same stripped text
    using the same spaCy pipeline, so their non-punct tokens are in the same
    order.  We walk both in parallel, advancing past punctuation-only entries.
    """
    # Collect word-like spaCy tokens (have at least one alnum char, not spaces)
    spacy_word_tokens = [
        (t.idx, t.idx + len(t.text), t.tag_, t.text)
        for t in doc
        if not t.is_space and _has_alnum.search(t.text)
    ]

    result = []
    spacy_cursor = 0

    for w in tagged_words:
        word_text = _get_tw_word(w)
        if not _has_alnum.search(word_text):
            continue  # skip pure-punctuation biberplus tokens

        tags = w.get("tags", []) if isinstance(w, dict) else []

        # Advance spaCy cursor to find the matching token by text
        while spacy_cursor < len(spacy_word_tokens):
            st, en, xpos, txt = spacy_word_tokens[spacy_cursor]
            if txt.lower() == word_text.lower():
                break
            spacy_cursor += 1

        if spacy_cursor >= len(spacy_word_tokens):
            # Ran out of spaCy tokens — emit without offset (should not happen)
            result.append({"start_char": -1, "end_char": -1, "word": word_text, "xpos": "", "tags": tags})
            continue

        st, en, xpos, txt = spacy_word_tokens[spacy_cursor]
        spacy_cursor += 1

        mapped_start, mapped_end = _map_span(st, en, offset_map)
        result.append({
            "start_char": mapped_start,
            "end_char": mapped_end,
            "word": txt,
            "xpos": xpos,
            "tags": tags,
        })

    return result


def _tokens_with_offsets_regex(text: str, tagged_words: list, offset_map: list[int] | None) -> list[dict]:
    """Locate each biberplus token in *text* by sequential ``str.find()``.

    Works correctly for any left-to-right tokeniser because we advance the
    search cursor past each found token.  ``xpos`` is left empty because the
    NLTK-based pipeline does not provide Penn Treebank tags.  Punctuation tokens
    are kept, and tokens that cannot be located get a zero-width span, so that
    every tag produced by BiberPlus is preserved.
    """
    result = []
    search_pos = 0

    for w in tagged_words:
        word_text = _get_tw_word(w)
        tags = w.get("tags", []) if isinstance(w, dict) else []

        pos = text.find(word_text, search_pos) if word_text else -1
        if pos == -1:
            # Não achado no texto (forma normalizada pelo tagger): guarda com largura
            # zero para não perder as etiquetas (as contagens batem com tag_text).
            mapped, _ = _map_span(search_pos, search_pos, offset_map)
            result.append({"start_char": mapped, "end_char": mapped, "word": word_text, "xpos": "", "tags": tags})
            continue

        end_pos = pos + len(word_text)
        mapped_start, mapped_end = _map_span(pos, end_pos, offset_map)

        result.append({
            "start_char": mapped_start,
            "end_char": mapped_end,
            "word": word_text,
            "xpos": "",
            "tags": tags,
        })
        search_pos = end_pos

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_biber_features_from_folder(
    folder_path_str: str,
    configdict={"n_processes": 4, "function_words": False},
    usenlp=None,
    save_tagged: bool = False,
    output_dir: str = None,
    copy_originals: bool = False,
):
    """Process all .txt files in a folder, extract Biber features, save CSV.

    Parameters
    ----------
    folder_path_str : path to the corpus folder containing ``.txt`` files.
    configdict      : biberplus configuration dict.
    usenlp          : if True, use spaCy for tokenisation (provides POS tags
                      and better offset accuracy); if False/None, use the
                      biberplus default (NLTK-based).
    save_tagged     : if True, write one ``<stem>_biberplus.jsonl`` per document
                      in ``<output_dir>/<corpus>_tagged/``.
    output_dir      : directory for all output files; defaults to the corpus
                      folder's parent.
    copy_originals  : if True, copy source ``.txt`` files to
                      ``<output_dir>/originals/<corpus>/``.
    """
    corpus_path = Path(folder_path_str).expanduser().resolve()
    if not corpus_path.is_dir():
        print(f"Erro: A pasta '{corpus_path}' nao foi encontrada.")
        return

    if output_dir:
        base_out = Path(output_dir).expanduser().resolve()
        base_out.mkdir(parents=True, exist_ok=True)
    else:
        base_out = corpus_path.parent

    csv_name = f"{corpus_path.name}_biberfeatures_rawcount.csv"
    csv_path = base_out / csv_name

    if save_tagged:
        tagged_dir = base_out / f"{corpus_path.name}_tagged"
        tagged_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Corpus : '{corpus_path.name}'")
    print(f"  Origem : {corpus_path}")
    print(f"  Saida  : {base_out}")
    print(f"{'=' * 60}")

    local_nlp = None
    spacy_model_name = ""
    if usenlp:
        print("  -> Carregando pipeline spaCy para tokenizacao...")
        try:
            import spacy
            try:
                local_nlp = spacy.load("en_core_web_trf", exclude=["ner"])
                spacy_model_name = "en_core_web_trf"
                print("    Pipeline carregado: en_core_web_trf")
            except Exception:
                try:
                    local_nlp = spacy.load("en_core_web_sm", exclude=["ner"])
                    spacy_model_name = "en_core_web_sm"
                    print("    Pipeline carregado (fallback): en_core_web_sm")
                except Exception:
                    print("    Aviso: modelo spaCy nao encontrado; prosseguindo com tokenizacao por regex.")
                    local_nlp = None
            if local_nlp:
                local_nlp.max_length = 2_000_000
        except Exception:
            print("    Aviso: spaCy nao esta instalado no ambiente. Usando tokenizacao por regex.")
            local_nlp = None
    else:
        print("  -> Tokenizacao: biberplus/NLTK (usenlp=False)")

    if copy_originals and output_dir:
        print(f"  -> Copiando arquivos originais para '{base_out}/originals/{corpus_path.name}/'...")
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

    all_records_flat = []
    file_list = list(corpus_path.glob("*.txt"))

    if not file_list:
        print(f"  Aviso: Nenhum arquivo .txt encontrado em '{corpus_path}'.")
        return

    print(f"  -> Extraindo features Biber de {len(file_list)} arquivo(s)...")
    if save_tagged:
        print(f"     Tokens taggeados serao salvos em: {tagged_dir}/")

    for txt_path in tqdm(file_list, desc=f"  Analisando {corpus_path.name}", unit="doc"):
        original_text = txt_path.read_text(encoding="utf-8", errors="ignore")
        text = re.sub(r"<[^>]*>", "", original_text)
        filename = txt_path.name

        doc = None
        if local_nlp:
            try:
                doc = local_nlp(text)
            except Exception:
                doc = None

        if doc is not None:
            list_of_words = [token.text for token in doc if token.is_alpha]
        else:
            list_of_words = re.findall(r"\b[A-Za-z]+\b", text)
        list_of_unique_words = list(set(list_of_words))

        n_words = len(list_of_words)
        n_unique_words = len(list_of_unique_words)
        ttr = n_unique_words / n_words if n_words > 0 else 0

        config = load_config()
        config.update(configdict)
        try:
            pipeline = load_pipeline(config)
        except OSError as exc:
            msg = str(exc)
            if "en_core_web_sm" in msg or "[E050]" in msg:
                raise RuntimeError(
                    "spaCy model 'en_core_web_sm' is required but not installed. "
                    "Install it with: python -m spacy download en_core_web_sm"
                ) from exc
            raise

        if usenlp and local_nlp is not None:
            pipeline = local_nlp

        tagged_words = tag_text(text, pipeline=pipeline, config=config)

        tag_counts = pd.Series(sum([word["tags"] for word in tagged_words], [])).value_counts()

        if save_tagged:
            tagged_file = tagged_dir / f"{txt_path.stem}_biberplus.jsonl"
            try:
                offset_map = _build_offset_map(original_text, text)

                if local_nlp and doc is not None:
                    tok_list = _tokens_with_offsets_spacy(doc, tagged_words, offset_map)
                else:
                    tok_list = _tokens_with_offsets_regex(text, tagged_words, offset_map)

                meta: dict = {
                    "tagger": "biberplus",
                    "tagger_version": _BIBERPLUS_VERSION,
                    "filename": filename,
                }
                if spacy_model_name:
                    meta["spacy_model"] = spacy_model_name

                write_tagged_jsonl(meta, tok_list, tagged_file)
            except Exception:
                pass

        field_name = filename.split(".")[1] if len(filename.split(".")) > 1 else "unknown"
        section_name = filename.split(".")[3] if len(filename.split(".")) > 3 else "unknown"

        record = {
            "filename": filename,
            "field": field_name,
            "section": section_name,
            "Words": n_words,
            "TTR": ttr,
        }
        for tag, count in tag_counts.items():
            record[f"{tag}"] = count

        all_records_flat.append(record)

    if all_records_flat:
        df = pd.DataFrame(all_records_flat)
        df.to_csv(csv_path, index=False)
        print(f"  + Contagens brutas salvas: '{csv_path.name}' ({len(df)} documentos)")
    else:
        print("  Aviso: Nenhum dado foi processado.")


def normalize_biber_features(csv_path_str: str, decimal_places=None):
    """Normalise raw Biber feature counts to per-1000-words values.

    Reads a raw-count CSV produced by ``extract_biber_features_from_folder``
    and writes a ``*_norm1000.csv`` alongside it.
    """
    csv_path = Path(csv_path_str).expanduser().resolve()
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
        col for col in df.columns if col not in ["filename", "field", "section", "Words", "TTR"]
    ]

    df_norm = df.copy()
    for col in cols_to_normalize:
        df_norm[col] = (df[col] * 1000) / df["Words"]
        if decimal_places is not None:
            df_norm[col] = df_norm[col].round(decimal_places)

    df_norm.to_csv(norm_csv_path, index=False)
    print(f"  + Normalizacao concluida: '{norm_csv_path.name}'")


def biberplus(
    folder_path_str: str,
    configdict={"n_processes": 4, "function_words": False},
    usenlp=None,
    save_tagged: bool = False,
    output_dir: str = None,
    copy_originals: bool = False,
):
    """High-level alias for BiberPlus feature extraction and tagging."""
    return extract_biber_features_from_folder(
        folder_path_str=folder_path_str,
        configdict=configdict,
        usenlp=usenlp,
        save_tagged=save_tagged,
        output_dir=output_dir,
        copy_originals=copy_originals,
    )
