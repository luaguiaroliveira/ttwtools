"""
examples.py — exemplos (com marcas) do texto do aluno e da referência, para a Escrita.

Para uma palavra ou um **molde de classes** (ex.: `DT JJ NN`), devolve ocorrências em
contexto, token a token, com a classe de cada token e quais estão no acerto. É o que a tela
usa para mostrar o texto colorido (como no Leitor) e comparar com exemplos do corpus.
"""

from __future__ import annotations

from typing import Mapping

from .constructions import tag_text
from .project import TTWAProject
from .query import _layer_tokens, _select_layers

_KINDS = ("word", "pattern")


def _window(tokens: list[dict], i: int, e: int, width: int, field: str, filename: str | None = None) -> dict:
    lo, hi = max(0, i - width), min(len(tokens), e + width + 1)
    out = [{"w": tokens[j].get("word") or "", "cls": tokens[j].get(field) or "", "hit": i <= j <= e}
           for j in range(lo, hi)]
    return {"filename": filename, "tokens": out}


def _matches(tokens: list[dict], item: str, kind: str, field: str, n: int):
    if kind == "word":
        alvo = item.lower()
        for j, t in enumerate(tokens):
            if (t.get("word") or "").lower() == alvo:
                yield j, j
    else:
        pat = item.split()
        for i in range(len(tokens) - n + 1):
            if [(tokens[j].get(field) or "") for j in range(i, i + n)] == pat:
                yield i, i + n - 1


def text_examples(text: str, item: str, kind: str = "word", field: str = "upos", n: int = 3,
                  limit: int = 5, width: int = 8, lang: str | None = None) -> list[dict]:
    """Exemplos do texto do aluno (tokens com classe e acerto marcado)."""
    toks = tag_text(text, lang=lang)
    out = []
    for i, e in _matches(toks, item, kind, field, n):
        out.append(_window(toks, i, e, width, field))
        if len(out) >= limit:
            break
    return out


def corpus_examples(project: TTWAProject, corpus_name: str, item: str, kind: str = "word",
                    field: str = "upos", n: int = 3, limit: int = 5, width: int = 8,
                    layer: str | None = None) -> list[dict]:
    """Exemplos da referência (tokens direto das camadas, sem reetiquetar)."""
    sel = _select_layers(project, corpus_name, layer, None, "pos")
    out = []
    for doc, rows in _layer_tokens(project, sel):
        toks = [{"word": r["word"], "upos": r["upos"], "xpos": r["xpos"]} for r in rows]
        for i, e in _matches(toks, item, kind, field, n):
            out.append(_window(toks, i, e, width, field, doc["filename"]))
            if len(out) >= limit:
                return out
    return out


def writing_examples(project: TTWAProject, text: str, item: str, reference, kind: str = "word",
                     field: str = "upos", n: int = 3, limit: int = 5, width: int = 8,
                     lang: str | None = None, text_name: str = "Meu texto") -> dict:
    """Exemplos do item no texto e, quando a referência é um corpus, também nele."""
    if kind not in _KINDS:
        raise ValueError(f"kind deve ser um de {_KINDS}")
    ref_corpus = reference if isinstance(reference, str) and not str(reference).endswith((".tsv", ".txt")) else None
    return {"kind": kind, "item": item, "field": field, "n": n, "text_name": text_name,
            "text": text_examples(text, item, kind, field, n, limit, width, lang),
            "corpus": corpus_examples(project, ref_corpus, item, kind, field, n, limit, width) if ref_corpus else []}
