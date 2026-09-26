"""Partes comuns: escolher a camada de cada documento, frases, gravar documento com camada."""

from __future__ import annotations

import re
from typing import Any, Iterable

from ..corpus import _add_text, _unique_filename, filter_documents, set_document_meta
from ..project import TTWAProject

_SENT_END = re.compile(r"^[.!?]+$|^[.!?][\"'”’)\]]*$")


def document_layers(project: TTWAProject, corpus_name: str, tool: str | None = None,
                    where: dict | None = None) -> list[tuple[dict, dict]]:
    """[(documento, camada)] com uma camada por documento: a mais recente da
    ferramenta pedida (ou de qualquer uma). Documentos sem camada ficam de fora."""
    out = []
    for doc in filter_documents(project, corpus_name, where):
        sql = "SELECT id, tool, tool_version, model, config, created_at FROM layers WHERE doc_id = ?"
        args: list[Any] = [doc["id"]]
        if tool:
            sql += " AND tool = ?"
            args.append(tool)
        row = project._con.execute(sql + " ORDER BY id DESC LIMIT 1", args).fetchone()
        if row:
            out.append((doc, dict(row)))
    return out


def sentences_of(tokens: list[dict]) -> list[list[dict]]:
    """Divide os tokens em frases: pelo índice de frase gravado pela camada
    (`sent`, em `extra`), ou, na falta dele, por pontuação final (. ! ?)."""
    if not tokens:
        return []
    if all("sent" in t["extra"] for t in tokens):
        groups: dict[Any, list[dict]] = {}
        for t in tokens:
            groups.setdefault(t["extra"]["sent"], []).append(t)
        return list(groups.values())
    out, cur = [], []
    for t in tokens:
        cur.append(t)
        if t["word"] and _SENT_END.match(t["word"]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def add_document_with_layer(project: TTWAProject, corpus_name: str, filename: str, text: str,
                            tokens: list[dict], tool: str, tool_version: str = "", model: str = "",
                            config: dict | None = None, meta: dict | None = None) -> tuple[str, int]:
    """Grava o texto (`.ttwa` dentro; `.ttwl` numa pasta ao lado), a camada e os metadados."""
    filename = _unique_filename(project, corpus_name, filename)
    _add_text(project, corpus_name, filename, text)
    doc_id = project._con.execute(
        "SELECT id FROM documents WHERE corpus_name = ? AND filename = ?", (corpus_name, filename)
    ).fetchone()["id"]
    layer_id = project.save_layer(doc_id, tool, tool_version, model, config or {}, tokens)
    project._con.commit()
    if meta:
        set_document_meta(project, corpus_name, filename, meta)
    return filename, layer_id


def iter_layer_tokens(project: TTWAProject, pairs: Iterable[tuple[dict, dict]]):
    for doc, layer in pairs:
        yield doc, layer, project.get_tokens(layer["id"])
