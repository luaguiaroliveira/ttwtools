"""
conllu.py — CoNLL-U (Universal Dependencies) de e para camadas.

Leitura: cada `# newdoc` (ou o arquivo inteiro) vira um documento; o texto é
reconstruído a partir de `# text =` ou das formas com `SpaceAfter=No`, e cada
palavra vira um token com posição no texto. HEAD, DEPREL, DEPS, MISC, o ID e a
frase ficam em `extra`, para a volta a CoNLL-U não perder nada. Tokens de várias
palavras (`1-2`) guardam a forma de superfície em `extra.mwt`; nós vazios (`1.1`)
são ignorados.

Escrita: qualquer camada vira CoNLL-U. Sem dependências na camada, HEAD/DEPREL
saem como `_`; sem frases gravadas, as frases vêm da pontuação final.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..project import TTWAProject
from .common import add_document_with_layer, document_layers, iter_layer_tokens, sentences_of

COLUMNS = ("id", "form", "lemma", "upos", "xpos", "feats", "head", "deprel", "deps", "misc")


def _misc_dict(misc: str) -> dict[str, str]:
    if not misc or misc == "_":
        return {}
    out = {}
    for item in misc.split("|"):
        k, _, v = item.partition("=")
        out[k] = v
    return out


def parse_conllu(source: str | Path, default_doc: str = "doc") -> list[dict]:
    """Lê CoNLL-U e devolve documentos: {"id", "text", "tokens", "meta"}.

    `source` é um caminho ou o próprio conteúdo. Cada token segue o formato
    canônico (start_char, end_char, word, lemma, upos, xpos, feats) + campos
    CoNLL-U em chaves próprias (head, deprel, deps, misc, conllu_id, sent, mwt)."""
    text_in = Path(source).read_text(encoding="utf-8") if isinstance(source, Path) or (
        isinstance(source, str) and "\n" not in source and Path(source).is_file()) else str(source)
    docs: list[dict] = []
    doc: dict | None = None
    sent_lines: list[list[str]] = []
    sent_comments: dict[str, str] = {}

    def new_doc(doc_id: str) -> dict:
        d = {"id": doc_id, "parts": [], "tokens": [], "meta": {}, "n_sent": 0}
        docs.append(d)
        return d

    def flush_sentence():
        nonlocal doc, sent_lines, sent_comments
        if not sent_lines:
            sent_comments = {}
            return
        if doc is None:
            doc = new_doc(default_doc)
        _add_sentence(doc, sent_lines, sent_comments)
        sent_lines, sent_comments = [], {}

    for raw in text_in.splitlines():
        line = raw.rstrip("\r")
        if not line.strip():
            flush_sentence()
            continue
        if line.startswith("#"):
            key, sep, value = line[1:].strip().partition("=")
            key, value = key.strip(), value.strip()
            if key in ("newdoc id", "newdoc_id", "newdoc"):          # newdoc_id: Bosque e outros
                flush_sentence()
                doc = new_doc(value or f"{default_doc}_{len(docs) + 1}")
            elif key == "newpar" or key.startswith("newpar"):
                sent_comments["newpar"] = "1"
            elif sep:
                sent_comments[key] = value
            continue
        cols = line.split("\t")
        if len(cols) != 10:
            raise ValueError(f"linha CoNLL-U com {len(cols)} colunas (esperado 10): {line[:80]!r}")
        sent_lines.append(cols)
    flush_sentence()

    out = []
    for d in docs:
        out.append({"id": d["id"], "text": "".join(d["parts"]), "tokens": d["tokens"], "meta": d["meta"]})
    return out


def _add_sentence(doc: dict, lines: list[list[str]], comments: dict[str, str]) -> None:
    # formas de superfície e se há espaço depois (tokens de várias palavras contam como um)
    surface: list[tuple[str, bool, list[list[str]]]] = []
    i = 0
    while i < len(lines):
        cols = lines[i]
        tid = cols[0]
        if "." in tid:                      # nó vazio
            i += 1
            continue
        misc = _misc_dict(cols[9])
        if "-" in tid:                      # token de várias palavras
            a, b = (int(x) for x in tid.split("-"))
            words = []
            i += 1
            while i < len(lines) and "-" not in lines[i][0] and "." not in lines[i][0] and int(lines[i][0]) <= b:
                words.append(lines[i])
                i += 1
            surface.append((cols[1], misc.get("SpaceAfter") != "No", words, cols))
            continue
        surface.append((cols[1], misc.get("SpaceAfter") != "No", [cols], None))
        i += 1

    sent_text = comments.get("text")
    if sent_text is None:
        sent_text = "".join(form + (" " if space else "") for form, space, _, _ in surface).rstrip(" ")
    base = sum(len(p) for p in doc["parts"])
    if doc["parts"]:
        sep = "\n\n" if comments.get("newpar") else " "
        doc["parts"].append(sep)
        base += len(sep)
    doc["parts"].append(sent_text)

    pos = 0
    sent_idx = doc["n_sent"]
    for form, _space, words, mwt_cols in surface:
        found = sent_text.find(form, pos)
        start = found if found >= 0 else pos
        end = start + len(form) if found >= 0 else start
        pos = end
        for k, cols in enumerate(words):
            tok: dict[str, Any] = {
                "start_char": base + start, "end_char": base + end,
                "word": cols[1] if not mwt_cols else cols[1],
                "lemma": None if cols[2] == "_" else cols[2],
                "upos": None if cols[3] == "_" else cols[3],
                "xpos": None if cols[4] == "_" else cols[4],
                "feats": None if cols[5] == "_" else cols[5],
                "tags": [],
                "conllu_id": cols[0], "head": cols[6], "deprel": cols[7], "deps": cols[8], "misc": cols[9],
                "sent": sent_idx,
            }
            if mwt_cols is not None:
                tok["mwt"] = {"id": mwt_cols[0], "form": mwt_cols[1], "misc": mwt_cols[9], "first": k == 0}
            doc["tokens"].append(tok)
    doc["n_sent"] += 1
    sent_meta = {k: v for k, v in comments.items() if k not in ("text", "newpar")}
    if sent_meta:
        doc["meta"].setdefault("sent_comments", []).append(sent_meta)


def import_conllu(project: TTWAProject, path: str | Path, corpus_name: str) -> dict:
    """Importa um arquivo CoNLL-U: um documento por `# newdoc` e uma camada `conllu`."""
    path = Path(path)
    docs = parse_conllu(path, default_doc=path.stem)
    files = []
    for d in docs:
        filename = d["id"] if d["id"].endswith(".txt") else f"{d['id']}.txt"
        fname, _ = add_document_with_layer(
            project, corpus_name, filename, d["text"], d["tokens"], tool="conllu",
            config={"source": "conllu", "file": path.name},
        )
        files.append(fname)
    return {"corpus": corpus_name, "imported": len(files), "files": files,
            "tokens": sum(len(d["tokens"]) for d in docs)}


def _val(v) -> str:
    return "_" if v in (None, "") else str(v)


def write_conllu(docs: list[tuple[dict, list[dict]]]) -> str:
    """[(documento, tokens da camada)] → texto CoNLL-U."""
    lines: list[str] = []
    for doc, tokens in docs:
        lines.append(f"# newdoc id = {doc['filename']}")
        text = doc.get("text")
        for s_idx, sent in enumerate(sentences_of(tokens), 1):
            lines.append(f"# sent_id = {doc['filename']}-{s_idx}")
            if text is not None and sent:
                lines.append(f"# text = {text[sent[0]['start_char']:sent[-1]['end_char']].replace(chr(10), ' ')}")
            n = 0
            for t in sent:
                ex = t["extra"]
                mwt = ex.get("mwt")
                if mwt and mwt.get("first"):
                    lines.append("\t".join([mwt["id"], mwt["form"], "_", "_", "_", "_", "_", "_", "_", _val(mwt.get("misc"))]))
                n += 1
                tid = ex.get("conllu_id") or str(n)
                misc = ex.get("misc")
                if misc is None and text is not None and not mwt:
                    nxt_start = next((u["start_char"] for u in sent if u["start_char"] > t["start_char"]), None)
                    if nxt_start is not None and nxt_start == t["end_char"]:
                        misc = "SpaceAfter=No"
                lines.append("\t".join([
                    tid, _val(t["word"]), _val(t["lemma"]), _val(t["upos"]), _val(t["xpos"]), _val(t["feats"]),
                    _val(ex.get("head")), _val(ex.get("deprel")), _val(ex.get("deps")), _val(misc),
                ]))
            lines.append("")
    return "\n".join(lines) + ("\n" if lines else "")


def export_conllu(project: TTWAProject, corpus_name: str, out: str | Path, tool: str | None = None,
                  where: dict | None = None) -> dict:
    """Escreve CoNLL-U de uma camada (a mais recente de `tool`) de cada documento."""
    items = []
    for doc, layer, tokens in iter_layer_tokens(project, document_layers(project, corpus_name, tool, where)):
        doc = {**doc, "text": project.get_corpus_file(corpus_name, doc["filename"])}
        items.append((doc, tokens))
    Path(out).write_text(write_conllu(items), encoding="utf-8")
    return {"documents": len(items), "tokens": sum(len(t) for _, t in items), "out": str(out)}
