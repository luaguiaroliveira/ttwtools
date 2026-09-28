"""
writing.py — comparar **um texto individual** com um corpus de referência (menu "Escrita").

O texto é UMA unidade, não uma amostra aleatória de unidades independentes: a saída é
descritiva/exploratória, não uma inferência sobre uma população (Kilgarriff 2001).

    extract_text(blob, "redacao.docx") → str
    analyze_text(proj, texto, reference="corpus_referencia", unit="form")

Medidas e correção vêm de `keyness` (LL de Dunning 1993; log ratio de Hardie 2014; %DIFF de
Gabrielatos & Marchi 2012; FDR de Benjamini-Hochberg). Além do p corrigido, cada item ganha
a **dispersão na referência** (em quantos textos aparece) e badges de confiabilidade.
Formatos: txt, md, docx e odt (stdlib); pdf depende de `pypdf` (opcional).
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Mapping
from xml.etree import ElementTree as ET

from .corpus import TokenizerConfig, get_tokenizer_config, tokenize
from .i18n import t
from .keyness import (MIN_WORDS, FreqTable, _catalog_reference, comparability, corpus_freqs,
                      keyword_rows, read_reference_list)
from .project import TTWAProject

READABLE = (".txt", ".md", ".markdown", ".text", ".docx", ".odt", ".pdf")
MIN_WORDS_TEXT = 200       # abaixo disto: "exploratório"
MIN_WORDS_HARD = 50        # abaixo disto: praticamente sem valor
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

_DOCX_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_ODT_T = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


# ---------------------------------------------------------------------------
# Leitura de arquivos
# ---------------------------------------------------------------------------

def _docx_text(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    paras = []
    for p in root.iter(f"{_DOCX_W}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{_DOCX_W}t":
                parts.append(node.text or "")
            elif node.tag == f"{_DOCX_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_DOCX_W}br", f"{_DOCX_W}cr"):
                parts.append("\n")
        paras.append("".join(parts))
    return "\n".join(paras)


def _odt_text(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        root = ET.fromstring(z.read("content.xml"))
    paras = []
    for p in root.iter(f"{_ODT_T}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{_ODT_T}s":
                parts.append(" " * int(node.get(f"{_ODT_T}c", "1")))
            elif node.tag == f"{_ODT_T}tab":
                parts.append("\t")
            elif node.tag == f"{_ODT_T}line-break":
                parts.append("\n")
            elif node.text:
                parts.append(node.text)
        paras.append("".join(parts))
    return "\n".join(paras)


def _pdf_text(blob: bytes) -> str:
    try:
        from pypdf import PdfReader                      # opcional (pip install pypdf)
    except ImportError as exc:
        raise ValueError("pdf_unavailable") from exc
    reader = PdfReader(io.BytesIO(blob))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def extract_text(blob: bytes, filename: str) -> str:
    """Texto puro de um upload: txt/md, docx, odt ou pdf (este se `pypdf` estiver instalado)."""
    suffix = Path(filename).suffix.lower()
    if suffix in (".txt", ".text", ".md", ".markdown", ""):
        return blob.decode("utf-8", errors="replace").lstrip("\ufeff")
    if suffix == ".docx":
        return _docx_text(blob)
    if suffix == ".odt":
        return _odt_text(blob)
    if suffix == ".pdf":
        return _pdf_text(blob)
    raise ValueError(f"unsupported_format:{suffix or '?'}")


# ---------------------------------------------------------------------------
# Frequências do texto individual
# ---------------------------------------------------------------------------

def text_freqs(text: str, unit: str = "form", n: int = 2, tokenizer: TokenizerConfig | None = None,
               name: str = "Meu texto") -> FreqTable:
    """FreqTable do texto (docs = 1 em cada item, pois é um único texto)."""
    if unit not in ("form", "ngram"):
        raise ValueError("a Escrita aceita, por enquanto, as unidades form e ngram")
    toks = tokenize(text, tokenizer)
    words = sum(1 for t in toks if _LETTER.search(t))
    if unit == "ngram":
        low = [t.lower() for t in toks]
        items = [" ".join(low[i:i + n]) for i in range(len(low) - n + 1)]
    else:
        items = [t.lower() for t in toks]
    counts = Counter(i for i in items if i)
    docs = Counter({k: 1 for k in counts})
    return FreqTable(counts, docs, words, 1, {"name": name, "unit": unit, "lang": None})


# ---------------------------------------------------------------------------
# Análise
# ---------------------------------------------------------------------------

def _reliability_flags(row: Mapping, ref: FreqTable) -> list[str]:
    flags = []
    if row["freq_target"] < 3:
        flags.append("rare_in_text")
    if ref.docs is not None and ref.n_docs:
        pct = 100 * ref.docs.get(row["item"], 0) / ref.n_docs
        if pct < 20:
            flags.append("concentrated_reference")
    if not row.get("significant"):
        flags.append("not_significant")
    return flags


def analyze_text(project: TTWAProject, text: str, reference, unit: str = "form", n: int = 2,
                 measure: str = "log_ratio", min_freq: int = 2, min_range: int = 1,
                 correction: str = "fdr", alpha: float = 0.05, top: int | None = 100,
                 both_directions: bool = True, lang: str | None = None, text_name: str = "Meu texto",
                 filename: str | None = None) -> dict:
    """Palavras-chave de um texto único contra `reference` (corpus do projeto, lista .tsv
    ou `catalog:<id>`), com dispersão na referência e badges de confiabilidade."""
    reference = _catalog_reference(reference, unit)
    if isinstance(reference, FreqTable):
        ref, ref_id = reference, reference.meta.get("name", "tabela")
        tokenizer = None
    elif str(reference).endswith((".tsv", ".txt")) and Path(str(reference)).is_file():
        ref = read_reference_list(reference)
        ref_id = f"{ref.meta.get('name', Path(str(reference)).stem)} {ref.meta.get('version', '')}".strip()
        tokenizer = None
    elif str(reference).startswith("rest:"):
        raise ValueError("a Escrita não usa 'rest:' (o alvo já é um texto só)")
    else:
        ref = corpus_freqs(project, str(reference), unit, n)
        ref_id = str(reference)
        tokenizer = get_tokenizer_config(project, str(reference))

    target = text_freqs(text, unit, n, tokenizer, text_name)
    warnings = comparability(target, ref, unit, lang)      # `lang` = idioma das mensagens, não do corpus
    reliability = ["single_text"]
    if target.words < MIN_WORDS_TEXT:
        reliability.append("short_text")
        warnings.append({"code": "writing_short_text", "severity": "warning",
                         "message": t("writing.warn.short_text", lang, words=target.words),
                         "params": {"words": target.words}})
    if target.words < MIN_WORDS_HARD:
        reliability.append("very_short_text")
    if ref.docs is None:
        warnings.append({"code": "writing_no_reference_docs", "severity": "info",
                         "message": t("writing.warn.no_reference_docs", lang), "params": {}})

    rows = keyword_rows(target, ref, unit, measure, min_freq, min_range, correction, alpha, both_directions)
    for r in rows:
        r["range_reference_pct"] = (100 * ref.docs.get(r["item"], 0) / ref.n_docs) if (ref.docs is not None and ref.n_docs) else None
        r["flags"] = _reliability_flags(r, ref)
    if top:
        pos = [r for r in rows if r["direction"] == "+"][:top]
        neg = [r for r in rows if r["direction"] == "-"][:top]
        rows = pos + neg
    return {"kind": "writing", "text_name": text_name, "filename": filename,
            "target_words": target.words, "reference": ref_id, "reference_words": ref.words,
            "reference_documents": ref.n_docs,
            "reference_card": {k: v for k, v in ref.meta.items() if k != "missing_field"},
            "unit": unit, "measure": measure, "correction": correction, "alpha": alpha,
            "reliability": reliability, "warnings": warnings, "rows": rows}


def analyze_file(project: TTWAProject, blob: bytes, filename: str, reference, **kwargs) -> dict:
    """Lê o arquivo e chama `analyze_text` (atalho usado pela rota e pela CLI)."""
    text = extract_text(blob, filename)
    return analyze_text(project, text, reference, filename=filename, **kwargs)
