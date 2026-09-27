"""
tables.py — Tabela de tokens de uma camada em CSV, JSONL ou Parquet.

CSV/Parquet: uma linha por token (corpus, arquivo, índice, posições, word,
lemma, upos, xpos, feats, tags). JSONL: um arquivo no formato canônico do
`tagged_io` por documento, dentro da pasta de saída. Parquet precisa do
`pyarrow`, que não é dependência do pacote: `pip install pyarrow`.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..project import TTWAProject
from ..tagged_io import write_tagged_jsonl
from .common import document_layers, iter_layer_tokens

FIELDS = ("corpus", "filename", "idx", "start_char", "end_char", "word", "lemma", "upos", "xpos", "feats", "tags")


def _rows(project, corpus_name, tool, where):
    for doc, layer, tokens in iter_layer_tokens(project, document_layers(project, corpus_name, tool, where)):
        for t in tokens:
            yield {"corpus": corpus_name, "filename": doc["filename"], "idx": t["idx"],
                   "start_char": t["start_char"], "end_char": t["end_char"], "word": t["word"],
                   "lemma": t["lemma"], "upos": t["upos"], "xpos": t["xpos"], "feats": t["feats"],
                   "tags": "|".join(t["tags"])}


def export_tokens(project: TTWAProject, corpus_name: str, out: str | Path, fmt: str = "csv",
                  tool: str | None = None, where: dict | None = None) -> dict:
    """Exporta os tokens de uma camada como tabela: CSV, JSONL ou Parquet (se houver pyarrow)."""
    out = Path(out).expanduser()
    if fmt == "csv":
        n = 0
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
            w.writeheader()
            for row in _rows(project, corpus_name, tool, where):
                w.writerow(row)
                n += 1
        return {"tokens": n, "out": str(out)}
    if fmt == "parquet":
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            raise RuntimeError("Parquet precisa do pacote pyarrow: pip install pyarrow") from None
        import pandas as pd
        df = pd.DataFrame(list(_rows(project, corpus_name, tool, where)), columns=list(FIELDS))
        df.to_parquet(out, index=False)
        return {"tokens": len(df), "out": str(out)}
    if fmt == "jsonl":
        out.mkdir(parents=True, exist_ok=True)
        n_docs = n_tok = 0
        for doc, layer, tokens in iter_layer_tokens(project, document_layers(project, corpus_name, tool, where)):
            meta = {"tagger": layer["tool"], "tagger_version": layer["tool_version"], "filename": doc["filename"],
                    "model": layer["model"]}
            canon = []
            for t in tokens:
                tok = {k: t[k] for k in ("start_char", "end_char", "word") }
                for k in ("lemma", "upos", "xpos", "feats"):
                    if t[k] is not None:
                        tok[k] = t[k]
                tok["tags"] = t["tags"]
                tok.update(t["extra"])
                canon.append(tok)
            write_tagged_jsonl(meta, canon, out / f"{Path(doc['filename']).stem}_{layer['tool']}.jsonl")
            n_docs += 1
            n_tok += len(canon)
        return {"documents": n_docs, "tokens": n_tok, "out": str(out)}
    raise ValueError(f"formato '{fmt}' desconhecido (csv, jsonl, parquet)")
