"""
nltk_tagged.py — Leitura de texto anotado no formato `palavra/TAG`, usado pelo
Brown e pelo LOB (como distribuídos no NLTK):

    The/at Fulton/np-tl County/nn-tl Grand/jj-tl Jury/nn-tl said/vbd ...

Cada linha não vazia é uma frase; a etiqueta é o que vem depois da ÚLTIMA barra
(`1/2/cd` → palavra `1/2`). O texto é reconstruído com espaço entre as palavras,
sem espaço antes de pontuação; a etiqueta vai para `xpos` (tagset do corpus).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..project import TTWAProject
from .common import add_document_with_layer

_NO_SPACE_BEFORE = re.compile(r"^[.,;:!?%)\]}’”']+$|^'s$|^n't$", re.IGNORECASE)
_NO_SPACE_AFTER = re.compile(r"^[(\[{‘“$]+$")


def parse_nltk_tagged(source: str | Path, lowercase_tags: bool = False) -> dict:
    """Lê um arquivo `palavra/TAG` → {"text", "tokens"} (uma frase por linha)."""
    content = Path(source).read_text(encoding="utf-8", errors="ignore") if (
        isinstance(source, Path) or ("\n" not in str(source) and Path(str(source)).is_file())) else str(source)
    parts: list[str] = []
    tokens: list[dict] = []
    pos = 0
    sent_idx = 0
    for line in content.splitlines():
        items = line.split()
        if not items:
            continue
        if parts:
            parts.append("\n")
            pos += 1
        prev = None
        for item in items:
            word, sep, tag = item.rpartition("/")
            if not sep or not word:
                word, tag = item, ""
            tag = tag.lower() if lowercase_tags else tag
            if prev is not None and not _NO_SPACE_BEFORE.match(word) and not _NO_SPACE_AFTER.match(prev):
                parts.append(" ")
                pos += 1
            parts.append(word)
            tokens.append({"start_char": pos, "end_char": pos + len(word), "word": word, "xpos": tag or None,
                           "tags": [tag] if tag else [], "sent": sent_idx})
            pos += len(word)
            prev = word
        sent_idx += 1
    return {"text": "".join(parts), "tokens": tokens}


def import_nltk_tagged(project: TTWAProject, source: str | Path, corpus_name: str, glob: str = "*",
                       tagset: str = "") -> dict:
    """Importa um arquivo ou uma pasta de arquivos `palavra/TAG` (um documento por arquivo)."""
    src = Path(source).expanduser()
    files = sorted(p for p in src.glob(glob) if p.is_file() and not p.name.startswith(".")) if src.is_dir() else [src]
    out = []
    n_tokens = 0
    for f in files:
        d = parse_nltk_tagged(f)
        if not d["tokens"]:
            continue
        name = f.name if f.suffix == ".txt" else f"{f.name}.txt"
        fname, _ = add_document_with_layer(project, corpus_name, name, d["text"], d["tokens"], tool="nltk_tagged",
                                           config={"source": "nltk_tagged", "tagset": tagset})
        out.append(fname)
        n_tokens += len(d["tokens"])
    return {"corpus": corpus_name, "imported": len(out), "files": out, "tokens": n_tokens}
