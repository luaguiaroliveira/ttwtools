"""
graf.py — Leitura do XML standoff GrAF (ISO 24612) do OANC e do MASC.

Cada documento tem um cabeçalho (`X.anc` ou `X.hdr`) que aponta o texto primário
(`X.txt`) e os arquivos de anotação (`X-penn.xml`, `X-hepple.xml`, `X-s.xml`,
`X-seg.xml`...). Nos arquivos de anotação:

    <region xml:id="seg-r0" anchors="0 3"/>                 posições no texto
    <node xml:id="penn-n0"><link targets="seg-r0"/></node>  nó ligado a regiões
    <a label="tok" ref="penn-n0"><fs>                       anotação do nó
        <f name="msd" value="DT"/><f name="base" value="the"/><f name="string" value="The"/></fs></a>

As regiões podem estar em outro arquivo (OANC: tokens em -hepple ligados a
regiões de -seg), então todos os arquivos do documento são lidos juntos. Cada
token é conferido contra o texto: `text[início:fim]` deve bater com `string`
quando houver; as divergências são contadas no resultado.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..project import TTWAProject
from .common import add_document_with_layer

TOKEN_FILES = ("penn", "hepple", "tok", "tokens")          # preferência de camada de tokens
TOKEN_LABELS = {"tok", "token", "w"}
SENT_FILES = ("s", "sentences")
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

# PTB → UPOS (tabela usual da conversão para Universal Dependencies)
PTB_UPOS = {
    "CC": "CCONJ", "CD": "NUM", "DT": "DET", "EX": "PRON", "FW": "X", "IN": "ADP", "JJ": "ADJ", "JJR": "ADJ",
    "JJS": "ADJ", "LS": "X", "MD": "AUX", "NN": "NOUN", "NNS": "NOUN", "NNP": "PROPN", "NNPS": "PROPN",
    "PDT": "DET", "POS": "PART", "PRP": "PRON", "PRP$": "PRON", "RB": "ADV", "RBR": "ADV", "RBS": "ADV",
    "RP": "ADP", "SYM": "SYM", "TO": "PART", "UH": "INTJ", "VB": "VERB", "VBD": "VERB", "VBG": "VERB",
    "VBN": "VERB", "VBP": "VERB", "VBZ": "VERB", "WDT": "PRON", "WP": "PRON", "WP$": "PRON", "WRB": "ADV",
    ".": "PUNCT", ",": "PUNCT", ":": "PUNCT", "``": "PUNCT", "''": "PUNCT", "-LRB-": "PUNCT", "-RRB-": "PUNCT",
    "(": "PUNCT", ")": "PUNCT", "#": "SYM", "$": "SYM", "HYPH": "PUNCT", "NFP": "PUNCT",
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _features(a: ET.Element) -> dict[str, str]:
    out = {}
    for f in a.iter():
        if _local(f.tag) == "f" and f.get("name"):
            out[f.get("name")] = f.get("value") if f.get("value") is not None else (f.text or "").strip()
    return out


def read_header(path: str | Path) -> dict:
    """Cabeçalho `.anc`/`.hdr`: {"text": caminho do .txt, "annotations": {f.id: caminho}, "meta": {...}}."""
    path = Path(path).expanduser()
    root = ET.parse(path).getroot()
    text, annotations, meta = None, {}, {}
    for el in root.iter():
        name = _local(el.tag)
        if name == "primaryData" and el.get("loc"):
            text = path.parent / el.get("loc")
        elif name == "annotation" and el.get("loc"):
            annotations[el.get("f.id") or Path(el.get("loc")).stem.rsplit("-", 1)[-1]] = path.parent / el.get("loc")
        elif name == "title" and (el.text or "").strip() and "title" not in meta:
            meta["title"] = " ".join(el.text.split())
        elif name in ("author", "domain", "subdomain", "genre", "subject") and (el.text or "").strip():
            meta.setdefault(name, " ".join(el.text.split()))
        elif name == "catRef" and el.get("target"):
            meta.setdefault("category", el.get("target"))
    if text is None:                      # sem primaryData: X.txt ao lado
        text = path.with_suffix(".txt")
    return {"text": Path(text), "annotations": annotations, "meta": meta}


def _discover(folder: Path) -> list[dict]:
    headers = sorted([*folder.rglob("*.anc"), *folder.rglob("*.hdr")])
    if headers:
        return [read_header(h) for h in headers]
    docs = []                              # sem cabeçalho: X.txt + X-*.xml
    for txt in sorted(folder.rglob("*.txt")):
        ann = {p.stem[len(txt.stem) + 1:]: p for p in txt.parent.glob(f"{txt.stem}-*.xml")}
        if ann:
            docs.append({"text": txt, "annotations": ann, "meta": {}})
    return docs


def parse_graf(text: str, annotations: dict[str, Path], token_file: str | None = None) -> dict:
    """Tokens e frases de um documento GrAF. Devolve {"tokens", "token_file", "mismatches", "sentences"}."""
    regions: dict[str, tuple[int, int]] = {}
    nodes: dict[str, list[str]] = {}
    anns: dict[str, list[tuple[str, dict]]] = {}          # arquivo → [(nó, traços)] das anotações
    labels: dict[str, list[str]] = {}
    for fid, path in annotations.items():
        if not Path(path).is_file():
            continue
        items, labs = [], []
        for el in ET.parse(path).getroot().iter():
            name = _local(el.tag)
            if name == "region" and el.get("anchors"):
                nums = [int(x) for x in re.findall(r"-?\d+", el.get("anchors"))]
                if len(nums) >= 2:
                    regions[el.get(XML_ID)] = (nums[0], nums[-1])
            elif name == "node":
                targets = [t for link in el if _local(link.tag) == "link" for t in (link.get("targets") or "").split()]
                nodes[el.get(XML_ID)] = targets
            elif name == "a" and el.get("ref"):
                items.append((el.get("ref"), _features(el)))
                labs.append(el.get("label") or "")
        anns[fid] = items
        labels[fid] = labs

    def span(node_id: str) -> tuple[int, int] | None:
        spans = [regions[r] for r in nodes.get(node_id, []) if r in regions]
        return (min(s for s, _ in spans), max(e for _, e in spans)) if spans else None

    chosen = token_file or next((f for f in TOKEN_FILES if f in anns), None) or next(
        (f for f, labs in labels.items() if any(lab in TOKEN_LABELS for lab in labs)), None)
    if chosen is None:
        raise ValueError(f"nenhum arquivo de tokens entre {sorted(anns)} (esperado: {', '.join(TOKEN_FILES)})")
    tokens, mismatches = [], 0
    for (node, feats), label in zip(anns[chosen], labels[chosen]):
        if label and label not in TOKEN_LABELS:
            continue
        sp = span(node)
        if sp is None:
            continue
        start, end = sp
        word = text[start:end]
        if feats.get("string") is not None and feats["string"] != word:
            mismatches += 1
        xpos = feats.get("msd") or feats.get("pos") or feats.get("cat")
        tokens.append({"start_char": start, "end_char": end, "word": word, "lemma": feats.get("base") or feats.get("lemma"),
                       "xpos": xpos, "upos": PTB_UPOS.get(xpos or ""), "tags": [xpos] if xpos else []})
    tokens.sort(key=lambda t: (t["start_char"], t["end_char"]))
    sents = []
    sfile = next((f for f in SENT_FILES if f in anns), None)
    if sfile:
        sents = sorted(sp for node, _f in anns[sfile] if (sp := span(node)))
    k = 0
    for tok in tokens:                     # frase de cada token: pelas regiões de -s, senão uma só
        while k + 1 < len(sents) and tok["start_char"] >= sents[k + 1][0]:
            k += 1
        tok["sent"] = k
    return {"tokens": tokens, "token_file": chosen, "mismatches": mismatches, "sentences": len(sents) or 1}


def import_graf(project: TTWAProject, source: str | Path, corpus_name: str, token_file: str | None = None,
                encoding: str = "utf-8") -> dict:
    """Importa uma pasta do OANC/MASC (ou um cabeçalho .anc/.hdr) para `corpus_name`,
    com uma camada `graf` (forma, lema, PTB e UPOS) por documento."""
    src = Path(source).expanduser()
    docs = [read_header(src)] if src.is_file() else _discover(src)
    if not docs:
        raise ValueError(f"nenhum documento GrAF (cabeçalho .anc/.hdr ou .txt com -*.xml) em '{src}'")
    files, n_tokens, mismatches, skipped = [], 0, 0, []
    for d in docs:
        if not d["text"].is_file():
            skipped.append(str(d["text"]))
            continue
        text = d["text"].read_text(encoding=encoding)
        try:
            parsed = parse_graf(text, d["annotations"], token_file)
        except ValueError:
            skipped.append(d["text"].name)
            continue
        meta = dict(d["meta"])
        try:
            meta.setdefault("folder", str(d["text"].parent.relative_to(src)) if src.is_dir() else "")
        except ValueError:
            pass
        meta = {k: v for k, v in meta.items() if v not in ("", ".", None)}
        fname, _ = add_document_with_layer(project, corpus_name, d["text"].name, text, parsed["tokens"], tool="graf",
                                           config={"source": "graf", "token_file": parsed["token_file"]}, meta=meta)
        files.append(fname)
        n_tokens += len(parsed["tokens"])
        mismatches += parsed["mismatches"]
    return {"corpus": corpus_name, "imported": len(files), "files": files, "tokens": n_tokens,
            "offset_mismatches": mismatches, "skipped": skipped}
