# compatibility shim — the implementation has moved to ttwtools.taggers.biberplus.
# This module is kept for backwards-compatibility and will be removed in v2.
from .taggers.biberplus import biberplus, extract_biber_features_from_folder, normalize_biber_features  # noqa: F401

__all__ = ["biberplus", "extract_biber_features_from_folder", "normalize_biber_features"]


def _escape_tsv_content(s: str) -> str:
    """Escape special characters so the value is safe inside a TSV field.

    Encoding:
        \\  →  \\\\
        \t  →  \\t
        \n  →  \\n
        \r  →  \\r

    To decode, apply the reverse substitutions in reverse order.
    """
    return (
        s
        .replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _get_tw_word(wdict) -> str:
    """Extract the word text from a biberplus tagged-word dict."""
    if isinstance(wdict, dict):
        return wdict.get("word") or wdict.get("text") or wdict.get("token") or ""
    return ""


def _build_interleaved_rows(original_text: str, tagged_words: list) -> list:
    """Return a list of (type, content, tags) triples that interleave every
    character of *original_text* with Biber tag information.

    Row types
    ---------
    ``word``   : pure-alphabetic token (Latin, including accented letters).
                 ``tags`` = space-joined Biber feature tags, or empty if
                 biberplus assigned none (correct behaviour — Biber tags are
                 register features, not exhaustive POS coverage).
    ``mixed``  : digit-led alphanumeric token kept intact from the source text
                 (e.g. ``18O``, ``250k``, ``40kya``).  biberplus treats these
                 as single tokens; we emit them as one row so the GUI can
                 display them without splitting chemical/scientific notation.
                 ``tags`` = Biber tags for the token (often ``NUM`` or ``NNP``).
    ``number`` : pure-digit sequence (e.g. ``500``).
                 ``tags`` = Biber tags when biberplus returns a standalone
                 numeric token (e.g. ``500`` → ``NUM``); empty otherwise.
    ``gap``    : everything else — whitespace, punctuation, markup (``<…>``),
                 newlines.  ``tags`` is always empty.

    Concatenating all ``content`` values (after TSV-unescaping) exactly
    reconstructs *original_text*.

    Alignment with biberplus tokens
    ---------------------------------
    Biberplus (via NLTK word_tokenize) emits tokens for *every* input unit,
    including punctuation (``','``) and numbers.  We keep the biberplus cursor
    in sync as follows:

    * Pure-punctuation biberplus tokens (no letters, no digits) are **skipped**
      before consuming a token for a ``word``, ``mixed``, or ``number`` row.
    * ``mixed`` parts are matched against biberplus by case-insensitive exact
      comparison.
    * ``word`` parts are matched by exact word OR by the alpha-only component
      of a mixed biberplus token.
    * ``number`` parts consume a biberplus token only when it is purely numeric.
    """
    _LAT = r"A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u024F"

    # Split order matters — more specific patterns must come first:
    #   1. markup tags  <…>
    #   2. digit-led mixed tokens  18O  250k  40kya  (digits then letters)
    #   3. pure digit sequences    500
    #   4. Latin-letter sequences  (word boundaries via look-arounds)
    parts = re.split(
        r"(<[^>]*>"
        r"|\d+[" + _LAT + r"]+"
        r"|\d+"
        r"|(?<![" + _LAT + r"])[" + _LAT + r"]+(?![" + _LAT + r"]))",
        original_text,
    )

    rows = []
    tw_cursor = 0
    gap_buf = ""

    _latin_re  = re.compile(r"[A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u024F]+")
    _ascii_re  = re.compile(r"[A-Za-z]+")
    _digit_re  = re.compile(r"\d+")
    _mixed_re  = re.compile(r"\d+[A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u024F]+")
    _has_alnum = re.compile(r"[A-Za-z0-9]")

    def _skip_punct():
        nonlocal tw_cursor
        while tw_cursor < len(tagged_words):
            if _has_alnum.search(_get_tw_word(tagged_words[tw_cursor])):
                break
            tw_cursor += 1

    def _consume_tags():
        """Return tags from current biberplus entry and advance cursor."""
        wdict = tagged_words[tw_cursor]
        tags  = wdict.get("tags", []) if isinstance(wdict, dict) else []
        return " ".join(tags)

    for part in parts:
        if _mixed_re.fullmatch(part):
            # ── digit-led mixed token (18O, 250k, 40kya) ─────────────────
            if gap_buf:
                rows.append(("gap", gap_buf, ""))
                gap_buf = ""
            _skip_punct()
            if tw_cursor < len(tagged_words):
                tw_word = _get_tw_word(tagged_words[tw_cursor])
                if tw_word.lower() == part.lower():
                    rows.append(("mixed", part, _consume_tags()))
                else:
                    rows.append(("mixed", part, ""))
                tw_cursor += 1
            else:
                rows.append(("mixed", part, ""))

        elif _latin_re.fullmatch(part):
            # ── alphabetic word ───────────────────────────────────────────
            if gap_buf:
                rows.append(("gap", gap_buf, ""))
                gap_buf = ""
            if _ascii_re.fullmatch(part):
                _skip_punct()
                if tw_cursor < len(tagged_words):
                    tw_word = _get_tw_word(tagged_words[tw_cursor])
                    alpha_only = re.sub(r"[^A-Za-z]", "", tw_word)
                    if tw_word.lower() == part.lower() or alpha_only.lower() == part.lower():
                        rows.append(("word", part, _consume_tags()))
                    else:
                        rows.append(("word", part, ""))
                    tw_cursor += 1
                else:
                    rows.append(("word", part, ""))
            else:
                # Accented/Unicode word: biberplus produces no entry for it.
                rows.append(("word", part, ""))

        elif _digit_re.fullmatch(part):
            # ── pure digit sequence ───────────────────────────────────────
            if gap_buf:
                rows.append(("gap", gap_buf, ""))
                gap_buf = ""
            _skip_punct()
            if tw_cursor < len(tagged_words):
                tw_word = _get_tw_word(tagged_words[tw_cursor])
                if _digit_re.fullmatch(tw_word):
                    # Standalone numeric biberplus token → consume and tag.
                    rows.append(("number", part, _consume_tags()))
                    tw_cursor += 1
                else:
                    # Unexpected — emit without tags to avoid drift.
                    rows.append(("number", part, ""))
            else:
                rows.append(("number", part, ""))

        else:
            # Markup (<…>), whitespace, punctuation → accumulate as gap.
            gap_buf += part

    if gap_buf:
        rows.append(("gap", gap_buf, ""))


    return rows


# NOTE: variable name is chosen to avoid shadowing potential local vars.
def extract_biber_features_from_folder(
    folder_path_str: str,
    configdict={"n_processes": 4, "function_words": False},
    usenlp=None,
    save_tagged: bool = False,
    output_dir: str = None,
    copy_originals: bool = False,
):
    """
    Processa todos os arquivos .txt em uma pasta, extrai as caracteristicas Biber
    e salva o resultado em um arquivo CSV.

    Args:
        folder_path_str (str): O caminho para a pasta contendo os arquivos de texto.
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
    if usenlp:
        print("  -> Carregando pipeline spaCy para tokenizacao...")
        try:
            import spacy

            try:
                local_nlp = spacy.load("en_core_web_trf", exclude=["ner"])
                print("    Pipeline carregado: en_core_web_trf")
            except Exception:
                try:
                    local_nlp = spacy.load("en_core_web_sm", exclude=["ner"])
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
        print("  -> Tokenizacao: regex (usenlp=False)")

    if copy_originals and output_dir:
        print(f"  -> Copiando arquivos originais para '{base_out}/originals/{corpus_path.name}/'...")
        try:
            import shutil

            originals_dir = base_out / "originals"
            originals_dir.mkdir(parents=True, exist_ok=True)
            dest = originals_dir / corpus_path.name
            if dest.exists():
                try:
                    shutil.copytree(corpus_path, dest, dirs_exist_ok=True)
                except TypeError:
                    for src in corpus_path.glob("*"):
                        dst = dest / src.name
                        if src.is_dir():
                            try:
                                shutil.copytree(src, dst)
                            except Exception:
                                pass
                        else:
                            try:
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
            tagged_file = tagged_dir / f"{txt_path.stem}_tagged.tsv"
            try:
                rows = _build_interleaved_rows(original_text, tagged_words)
                with tagged_file.open("w", encoding="utf-8", newline="") as outfh:
                    outfh.write(f"# filename: {filename}\n")
                    # Columns: type, content, tags
                    # 'word'   rows: pure-alphabetic token; Biber feature tags or empty
                    # 'mixed'  rows: digit-led alphanumeric token kept intact (18O, 250k);
                    #                tags from biberplus (e.g. NUM, NNP)
                    # 'number' rows: pure-digit sequence; Biber tags or empty
                    # 'gap'    rows: whitespace, punctuation, markup, newlines; tags = empty
                    # Special chars in 'content' are escaped: \n→\\n  \t→\\t  \r→\\r  \\→\\\\
                    # Reconstruct original text: ''.join(unescape(r.content) for r in rows)
                    outfh.write("type\tcontent\ttags\n")
                    for row_type, content, tags in rows:
                        outfh.write(f"{row_type}\t{_escape_tsv_content(content)}\t{tags}\n")
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
    """
    Le um arquivo CSV com contagens brutas de caracteristicas Biber e cria uma nova versao
    com os valores normalizados por 1000 palavras.

    Args:
        csv_path_str (str): O caminho para o arquivo CSV com as contagens brutas.
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
    """Alias de alto nivel para a extracao/tagging BiberPlus."""
    return extract_biber_features_from_folder(
        folder_path_str=folder_path_str,
        configdict=configdict,
        usenlp=usenlp,
        save_tagged=save_tagged,
        output_dir=output_dir,
        copy_originals=copy_originals,
    )
