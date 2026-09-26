"""
vrt.py — Escrita em VRT ("vertical text"), o formato de entrada do CWB, do
Sketch Engine e do CQPweb.

    <text id="arquivo.txt" corpus="nome" grupo="A">
    <s>
    The	DT	DET	the	-
    ...
    </s>
    </text>

Atributos posicionais (nesta ordem): word, xpos, upos, lemma, tags (tags do
tagger separadas por `|`, ou `-`). Os metadados do documento viram atributos
de `<text>`. Os nomes dos atributos ficam no cabeçalho, em comentário.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from ..project import TTWAProject
from .common import document_layers, iter_layer_tokens, sentences_of

P_ATTRS = ("word", "xpos", "upos", "lemma", "tags")
_ATTR_NAME = re.compile(r"[^A-Za-z0-9_]")


def _cell(value) -> str:
    if value in (None, "", []):
        return "-"
    if isinstance(value, list):
        value = "|".join(value)
    return escape(str(value).replace("\t", " ").replace("\n", " "))


def export_vrt(project: TTWAProject, corpus_name: str, out: str | Path, tool: str | None = None,
               where: dict | None = None) -> dict:
    """Escreve o corpus em VRT a partir da camada (mais recente de `tool`) de cada documento."""
    lines = [f"<!-- ttwtools VRT: p-attributes = {' '.join(P_ATTRS)} -->"]
    n_docs = n_tok = 0
    for doc, layer, tokens in iter_layer_tokens(project, document_layers(project, corpus_name, tool, where)):
        attrs = {"id": doc["filename"], "corpus": corpus_name, "layer": layer["tool"], **doc.get("meta", {})}
        attr_txt = " ".join(f"{_ATTR_NAME.sub('_', k)}={quoteattr(str(v))}" for k, v in attrs.items())
        lines.append(f"<text {attr_txt}>")
        for sent in sentences_of(tokens):
            lines.append("<s>")
            for t in sent:
                lines.append("\t".join(_cell(t.get(a)) for a in P_ATTRS))
                n_tok += 1
            lines.append("</s>")
        lines.append("</text>")
        n_docs += 1
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"documents": n_docs, "tokens": n_tok, "out": str(out), "p_attributes": list(P_ATTRS)}
