"""
tei.py — Leitura de TEI XML (P5) e do XML do BNC.

Um documento por `<TEI>` (ou `<bncDoc>`; um `<teiCorpus>` vira vários). O texto
sai de `<text>`/`<wtext>`/`<stext>`, com parágrafos (`p`, `head`, `l`, `u`, `div`)
separados por linha em branco; `note` e `fw` ficam de fora. Quando o texto já vem
anotado palavra a palavra (`<w>`, `<c>`/`<pc>` para pontuação), cria-se uma camada
`tei` com forma, lema (`lemma` ou `hw`) e etiqueta (`pos`, `c5`, `msd`, `type` ou
`ana`); `<s>` define as frases. Metadados: título, autor, data e classificação
(`catRef`, `classCode`, tipo do `wtext`).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..project import TTWAProject
from .common import add_document_with_layer

DOC_TAGS = {"TEI", "bncDoc", "TEI.2"}
TEXT_TAGS = {"text", "wtext", "stext"}
TOKEN_TAGS = {"w", "c", "pc"}
BLOCK_TAGS = {"p", "head", "l", "u", "div", "div1", "div2", "div3", "lg", "sp", "list", "item", "table", "row"}
SKIP_TAGS = {"note", "fw", "teiHeader", "header"}
LEMMA_ATTRS = ("lemma", "hw")
TAG_ATTRS = ("c5", "pos", "msd", "type", "ana")          # c5 (BNC) antes do pos simplificado


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _attr(el: ET.Element, names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for n in names:
        if el.get(n):
            return el.get(n).lstrip("#"), n
    return None, None


def _header_meta(doc: ET.Element) -> dict:
    meta: dict[str, str] = {}
    header = next((el for el in doc.iter() if _local(el.tag) in ("teiHeader", "header")), None)
    for el in header.iter() if header is not None else []:
        name, txt = _local(el.tag), " ".join("".join(el.itertext()).split())
        if name == "title" and txt and "title" not in meta:
            meta["title"] = txt
        elif name == "author" and txt and "author" not in meta:
            meta["author"] = txt
        elif name == "date" and "date" not in meta and (el.get("when") or txt):
            meta["date"] = el.get("when") or txt
        elif name == "catRef" and el.get("target"):
            meta.setdefault("category", " ".join(t.lstrip("#") for t in el.get("target").split()))
        elif name == "classCode" and txt:
            meta.setdefault("class", txt)
    for el in doc.iter():
        if _local(el.tag) == "wtext" and el.get("type"):
            meta.setdefault("type", el.get("type"))
            break
    return meta


class _Builder:
    """Monta o texto e as posições dos tokens percorrendo o XML."""

    def __init__(self):
        self.parts: list[str] = []
        self.pos = 0
        self.tokens: list[dict] = []
        self.sent = 0
        self.tag_attr: str | None = None

    def _last(self, n: int = 1) -> str:
        return "".join(self.parts[-3:])[-n:] if self.parts else ""

    def add(self, s: str) -> None:
        if s and (not self.parts or self._last().isspace()):
            s = s.lstrip()                       # sem espaço no começo de linha
        if s:
            self.parts.append(s)
            self.pos += len(s)

    def space(self) -> None:
        if self.parts and not self._last().isspace():
            self.add_raw(" ")

    def add_raw(self, s: str) -> None:
        self.parts.append(s)
        self.pos += len(s)

    def block(self) -> None:
        """Fim de parágrafo: tira espaços do fim e garante uma linha em branco."""
        while self.parts and self.parts[-1].endswith(" "):
            last = self.parts.pop()
            self.pos -= len(last)
            if last.rstrip(" "):
                self.add_raw(last.rstrip(" "))
                break
        if self.parts and not self._last(2).endswith("\n\n"):
            self.add_raw("\n" if self._last() == "\n" else "\n\n")

    def walk(self, el: ET.Element) -> None:
        name = _local(el.tag)
        if name in SKIP_TAGS:
            self._tail(el)
            return
        if name in TOKEN_TAGS:
            raw = "".join(el.itertext())
            word = raw.strip()
            if word:
                lemma, _ = _attr(el, LEMMA_ATTRS)
                tag, attr = _attr(el, TAG_ATTRS)
                self.tag_attr = self.tag_attr or attr
                if raw[:1].isspace():
                    self.space()
                self.tokens.append({"start_char": self.pos, "end_char": self.pos + len(word), "word": word,
                                    "lemma": lemma, "xpos": tag, "upos": el.get("upos"),
                                    "tags": [tag] if tag else [], "sent": self.sent})
                self.add_raw(word)
                if raw[-1:].isspace():           # BNC: o espaço seguinte vem dentro do <w>
                    self.space()
            self._tail(el)
            return
        if name in BLOCK_TAGS:
            self.block()
        if el.text and el.text.strip():
            self.add(re.sub(r"\s+", " ", el.text))
        for child in el:
            self.walk(child)
        if name == "s":
            self.sent += 1
        if name in BLOCK_TAGS:
            self.block()
        self._tail(el)

    def _tail(self, el: ET.Element) -> None:
        if not el.tail:
            return
        if el.tail.strip():
            self.add(re.sub(r"\s+", " ", el.tail))
        elif _local(el.tag) in TOKEN_TAGS or _local(el.tag) in ("hi", "name", "s"):
            self.space()


def parse_tei(source: str | Path) -> list[dict]:
    """Documentos de um arquivo TEI: [{"id", "text", "tokens", "meta", "tag_attr"}]."""
    root = ET.parse(source).getroot()
    docs = [el for el in root.iter() if _local(el.tag) in DOC_TAGS] or [root]
    out = []
    for i, doc in enumerate(docs):
        text_el = next((el for el in doc.iter() if _local(el.tag) in TEXT_TAGS), None)
        if text_el is None:
            continue
        b = _Builder()
        b.walk(text_el)
        text = "".join(b.parts).rstrip()
        tokens = [t for t in b.tokens if t["end_char"] <= len(text)]
        doc_id = doc.get("{http://www.w3.org/XML/1998/namespace}id") or doc.get("id") or \
            f"{Path(source).stem}{'-' + str(i + 1) if len(docs) > 1 else ''}"
        out.append({"id": doc_id, "text": text, "tokens": tokens, "meta": _header_meta(doc), "tag_attr": b.tag_attr})
    return out


def import_tei(project: TTWAProject, source: str | Path, corpus_name: str, glob: str = "*.xml") -> dict:
    """Importa um arquivo TEI ou uma pasta de arquivos TEI. Texto anotado (`<w>`) ganha uma camada `tei`."""
    from ..corpus import _add_text, _unique_filename, set_document_meta
    src = Path(source)
    paths = sorted(src.rglob(glob)) if src.is_dir() else [src]
    files, n_tokens, with_layer = [], 0, 0
    for path in paths:
        for d in parse_tei(path):
            name = d["id"] if d["id"].endswith(".txt") else f"{d['id']}.txt"
            if d["tokens"]:
                fname, _ = add_document_with_layer(project, corpus_name, name, d["text"], d["tokens"], tool="tei",
                                                   config={"source": "tei", "tag_attr": d["tag_attr"]}, meta=d["meta"])
                with_layer += 1
            else:
                fname = _unique_filename(project, corpus_name, name)
                _add_text(project, corpus_name, fname, d["text"])
                if d["meta"]:
                    set_document_meta(project, corpus_name, fname, d["meta"])
            files.append(fname)
            n_tokens += len(d["tokens"])
    return {"corpus": corpus_name, "imported": len(files), "files": files, "tokens": n_tokens, "with_layer": with_layer}
