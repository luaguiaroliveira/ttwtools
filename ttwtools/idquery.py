"""idquery.py — Consultas sobre os ids das camadas `TCL2` (sem passar pela tabela `tokens`).

Num arquivo salvo sem tabelas de busca, as camadas vivem em `layer_blobs` (`TCL2`: colunas de inteiros e um
léxico por corpus). Aqui `search`, `kwic`, `frequency` e `collocates` de `query.py` ganham um caminho por
ids: cada condição da consulta (forma, lema, curinga, regex, classe, etiqueta) é avaliada **uma vez no
léxico** e vira uma máscara sobre os ids; contagens são `numpy.bincount`/`unique`. Os resultados são os
mesmos do caminho SQL (inclusive desempates e ordem); onde não houver como garantir isso, `query.py` cai no SQL.

`available(project, sel)` diz se o caminho vale para as camadas escolhidas: todas empacotadas em `TCL2`, sem
linhas em `main.tokens`. `TTWTOOLS_ID_QUERIES=0` desliga (para comparar). numpy é só cálculo: o formato não o usa.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, OrderedDict, defaultdict
from typing import Any, Iterable, Mapping

import numpy as np

from . import layerfmt

_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_EXCLUDED_UPOS = ("PUNCT", "SYM", "X", "SPACE")
_ASCII_LOWER = {c: c + 32 for c in range(ord("A"), ord("Z") + 1)}
WORD, LEMMA, UPOS, XPOS, FEATS, TAGS, EXTRA = range(2, 9)
_CACHE_LIMIT = 1_500_000_000          # bytes de ids decodificados mantidos em memória por projeto


class Unsupported(Exception):
    """A consulta não tem equivalente por ids (o chamador usa o SQL)."""


def enabled() -> bool:
    return os.environ.get("TTWTOOLS_ID_QUERIES", "1").strip().lower() not in ("0", "false", "no")


def _sql_lower(s: str) -> str:
    """`lower()` do SQLite: só A–Z."""
    return s.translate(_ASCII_LOWER)


def _glob_regex(pattern: str) -> "re.Pattern":
    """GLOB do SQLite (`*`, `?`, `[...]`, `[^...]`, sensível a maiúsculas) como regex."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            out.append(".*")
        elif c == "?":
            out.append(".")
        elif c == "[":
            j = i + 1
            if j < len(pattern) and pattern[j] == "^":
                j += 1
            if j < len(pattern) and pattern[j] == "]":
                j += 1
            while j < len(pattern) and pattern[j] != "]":
                j += 1
            if j >= len(pattern):
                raise Unsupported("colchete sem fechar")
            body = pattern[i + 1:j]
            neg = body.startswith("^")
            body = body[1:] if neg else body
            out.append("[" + ("^" if neg else "") + body.replace("\\", "\\\\") + "]")
            i = j
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("".join(out), re.DOTALL)


def _like_regex(pattern: str) -> "re.Pattern":
    """LIKE do SQLite (`%`, `_`; sem distinguir A–Z/a–z) como regex."""
    out = []
    for c in pattern:
        out.append(".*" if c == "%" else "." if c == "_" else re.escape(c))
    return re.compile("(?a)" + "".join(out), re.DOTALL | re.IGNORECASE)


class Selection:
    """Camadas escolhidas, com os ids de cada coluna concatenados (uma camada depois da outra)."""

    def __init__(self, store: "IdStore", sel: dict[int, dict]):
        self.store = store
        self.sel = sel
        self.layer_ids = list(sel)
        self.docs = [sel[i] for i in self.layer_ids]
        self.lex = store.lexicon(self.docs[0]["corpus_name"]) if self.docs else layerfmt.Lexicon()
        self._flat: dict[int, np.ndarray] = {}
        counts = [store.length(i) for i in self.layer_ids]
        self.counts = np.array(counts, dtype=np.int64)
        self.offsets = np.concatenate(([0], np.cumsum(self.counts)))
        self.total = int(self.offsets[-1])
        self.lay = np.repeat(np.arange(len(counts), dtype=np.int32), self.counts)
        self.idx = (np.arange(self.total, dtype=np.int64) - self.offsets[:-1][self.lay]).astype(np.int32) if self.total else np.zeros(0, np.int32)

    def col(self, c: int) -> np.ndarray:
        a = self._flat.get(c)
        if a is None:
            parts = [self.store.column(i, c) for i in self.layer_ids]
            a = self._flat[c] = np.concatenate(parts) if parts else np.zeros(0, np.uint32)
        return a

    def values(self, c: int) -> list:
        return self.lex.values[c]


class IdStore:
    """Ids decodificados por camada (cache limitado) e léxicos do projeto."""

    def __init__(self, project):
        self.project = project
        self.con = project._con
        from .project import LayerStore
        self.layers = LayerStore(self.con)
        self._cols: "OrderedDict[tuple[int, int], np.ndarray]" = OrderedDict()
        self._bytes = 0
        self._len: dict[int, int] = {}
        self._rows: "OrderedDict[int, list]" = OrderedDict()
        self._derived: dict = {}

    # -- acesso -----------------------------------------------------------
    def lexicon(self, corpus: str) -> "layerfmt.Lexicon":
        return self.layers.lexicon(corpus)

    def blob(self, layer_id: int) -> bytes:
        r = self.con.execute("SELECT data FROM layer_blobs WHERE layer_id = ?", (layer_id,)).fetchone()
        return bytes(r[0])

    def length(self, layer_id: int) -> int:
        n = self._len.get(layer_id)
        if n is None:
            n = self._len[layer_id] = layerfmt.blob_length(self.blob(layer_id))
        return n

    def column(self, layer_id: int, c: int) -> np.ndarray:
        key = (layer_id, c)
        a = self._cols.get(key)
        if a is None:
            arr = layerfmt.decode_ids(self.blob(layer_id), (c,))[c]
            a = np.frombuffer(arr, dtype=arr.typecode).astype(np.uint32, copy=False) if len(arr) else np.zeros(0, np.uint32)
            self._cols[key] = a
            self._bytes += a.nbytes
            while self._bytes > _CACHE_LIMIT and len(self._cols) > 1:
                _, old = self._cols.popitem(last=False)
                self._bytes -= old.nbytes
        else:
            self._cols.move_to_end(key)
        return a

    def rows(self, layer_id: int) -> list:
        r = self._rows.get(layer_id)
        if r is None:
            r = self._rows[layer_id] = self.layers.unpack(layer_id, self.blob(layer_id))
            while len(self._rows) > 64:
                self._rows.popitem(last=False)
        return r

    def derived(self, key, build):
        """Vetores derivados do léxico (máscaras, rótulos), guardados enquanto o léxico tem o mesmo tamanho."""
        d = self._derived.get(key)
        if d is None:
            d = self._derived[key] = build()
        return d


def available(project, sel: dict[int, dict]) -> "IdStore | None":
    """O `IdStore` do projeto se todas as camadas escolhidas estão só em `layer_blobs` no formato `TCL2`."""
    if not enabled() or not sel or getattr(project, "_con", None) is None:
        return None
    con = project._con
    ids = list(sel)
    marks = ",".join("?" * len(ids))
    try:
        if len({d["corpus_name"] for d in sel.values()}) != 1:
            return None
        blobs = {r[0]: bytes(r[1][:4]) for r in con.execute(
            f"SELECT layer_id, substr(data, 1, 4) FROM layer_blobs WHERE layer_id IN ({marks})", ids)}
        if len(blobs) != len(ids) or any(b != layerfmt.MAGIC2 for b in blobs.values()):
            return None
        if con.execute(f"SELECT 1 FROM main.tokens WHERE layer_id IN ({marks}) LIMIT 1", ids).fetchone():
            return None
    except Exception:  # noqa: BLE001 — qualquer dúvida: SQL
        return None
    store = getattr(project, "_idstore", None)
    if store is None or store.con is not con:
        store = project._idstore = IdStore(project)
    return store


def layer_has(store: "IdStore", layer_id: int, needs: str) -> bool:
    """A camada tem o campo `needs` (lemma, pos, tags) em algum token? Mesma regra do SQL de `query._select`."""
    def present(c: int, bad: tuple) -> bool:
        vals = store.layers.lexicon(_corpus_of(store, layer_id)).values[c]
        ok = np.fromiter((v is not None and v not in bad for v in vals), dtype=bool, count=len(vals))
        return bool(len(ok) and ok[store.column(layer_id, c)].any())
    if needs == "lemma":
        return present(LEMMA, ("",))
    if needs == "pos":
        return present(UPOS, ("",)) or present(XPOS, ("",))
    if needs == "tags":
        return present(TAGS, ("", "[]"))
    raise Unsupported(needs)


def _corpus_of(store: "IdStore", layer_id: int) -> str:
    return store.con.execute("SELECT d.corpus_name FROM layers l JOIN documents d ON d.id = l.doc_id WHERE l.id = ?",
                             (layer_id,)).fetchone()[0]


# ---------------------------------------------------------------------------
# Consulta → máscaras sobre o léxico
# ---------------------------------------------------------------------------

def _mask(values: list, pred) -> np.ndarray:
    return np.fromiter((pred(v) for v in values), dtype=bool, count=len(values))


def _cond_mask(s: Selection, spec: str) -> np.ndarray:
    """Máscara, sobre os tokens escolhidos, das condições de um token da consulta (`a&b` = todas)."""
    total = None
    for part in spec.split("&"):
        key, sep, value = part.partition("=")
        if not sep:
            key, value = "word", part
        key = key.strip().lower()
        value = value.strip()
        m = _one_condition(s, key, value)
        total = m if total is None else (total & m)
    return total


def _one_condition(s: Selection, key: str, value: str) -> np.ndarray:
    if key == "pos":
        u, x = s.values(UPOS), s.values(XPOS)
        return (_mask(u, lambda v: v is not None and v == value)[s.col(UPOS)]
                | _mask(x, lambda v: v is not None and v == value)[s.col(XPOS)])
    if key == "tag":
        like = _like_regex(f'%"{value}"%')
        t = s.values(TAGS)
        tag_like = _mask(t, lambda v: v is not None and like.fullmatch(v) is not None)[s.col(TAGS)]
        tag_none = _mask(t, lambda v: v is None or v in ("", "[]"))[s.col(TAGS)]
        pos = (_mask(s.values(UPOS), lambda v: v is not None and v == value)[s.col(UPOS)]
               | _mask(s.values(XPOS), lambda v: v is not None and v == value)[s.col(XPOS)])
        return tag_like | (tag_none & pos)
    cols = {"word": WORD, "lemma": LEMMA, "upos": UPOS, "xpos": XPOS}
    if key not in cols:
        raise ValueError(f"campo desconhecido '{key}' (use word, lemma, pos, upos, xpos, tag)")
    c = cols[key]
    vals, ids = s.values(c), s.col(c)
    if len(value) > 1 and value.startswith("/") and value.endswith("/"):
        rx = re.compile(value[1:-1], re.IGNORECASE)
        return _mask(vals, lambda v: v is not None and rx.search(v) is not None)[ids]
    lowered = key in ("word", "lemma")
    v = value.lower() if lowered else value

    def norm(x):
        return _sql_lower(x) if lowered else x
    rng = None
    if v.endswith("*") and not re.search(r"[*?\[]", v[:-1]) and v[:-1]:
        prefix = v[:-1]
        rng = (prefix, prefix[:-1] + chr(ord(prefix[-1]) + 1))
    if rng:
        return _mask(vals, lambda x: x is not None and rng[0] <= norm(x) < rng[1])[ids]
    if re.search(r"[*?]", v):
        gx = _glob_regex(v)
        return _mask(vals, lambda x: x is not None and gx.fullmatch(norm(x)) is not None)[ids]
    return _mask(vals, lambda x: x is not None and norm(x) == v)[ids]


def find(s: Selection, query: str) -> tuple[np.ndarray, int]:
    """Posições (no vetor concatenado) do primeiro token de cada ocorrência e o tamanho da sequência."""
    specs = query.split()
    if not specs:
        raise ValueError("consulta vazia")
    n = len(specs)
    if s.total < n:
        return np.zeros(0, np.int64), n
    m = _cond_mask(s, specs[0])
    ok = m[: s.total - (n - 1)].copy() if n > 1 else m.copy()
    for i in range(1, n):
        mi = _cond_mask(s, specs[i])
        ok &= mi[i: s.total - (n - 1) + i]
        ok &= s.lay[i: s.total - (n - 1) + i] == s.lay[: s.total - (n - 1)]
    return np.flatnonzero(ok), n


# ---------------------------------------------------------------------------
# search, kwic
# ---------------------------------------------------------------------------

def search(store: IdStore, sel: dict[int, dict], query: str, group_by: str | None) -> dict:
    s = Selection(store, sel)
    pos, _ = find(s, query)
    counts = np.bincount(s.lay[pos], minlength=len(s.layer_ids)) if len(pos) else np.zeros(len(s.layer_ids), np.int64)
    order = sorted(range(len(s.layer_ids)), key=lambda k: s.layer_ids[k])          # como o GROUP BY layer_id
    per_doc: Counter = Counter()
    for k in order:
        if counts[k]:
            per_doc[s.docs[k]["filename"]] += int(counts[k])
    out = {"query": query, "total": sum(per_doc.values()), "documents": len(per_doc),
           "per_document": [{"filename": f, "freq": n} for f, n in per_doc.most_common()]}
    if group_by:
        groups: Counter = Counter()
        for d in s.docs:
            groups[d["meta"].get(group_by, "")] += per_doc.get(d["filename"], 0)
        out["per_group"] = [{"group": g, "freq": n} for g, n in groups.most_common()]
    return out


def kwic(project, store: IdStore, sel: dict[int, dict], query: str, context: int, limit: int, offset: int,
         sort: str, with_sentence: bool) -> dict:
    from .query import _first_tag, _sentence
    s = Selection(store, sel)
    pos, n = find(s, query)
    total = int(len(pos))
    lay, idx = s.lay[pos], s.idx[pos].astype(np.int64)
    doc_id = np.array([d["id"] for d in s.docs], dtype=np.int64)[lay] if total else np.zeros(0, np.int64)
    if sort == "position":
        order = np.lexsort((idx, doc_id))
    elif sort in ("left", "right"):
        words = s.values(WORD)
        low = [None if w is None else _sql_lower(w) for w in words]
        rank_of = {w: r for r, w in enumerate(sorted({w for w in low if w is not None}))}
        rank = np.array([-1 if w is None else rank_of[w] for w in low], dtype=np.int64)
        wid = s.col(WORD)
        shift = -1 if sort == "left" else n
        nb = pos + shift
        valid = (nb >= 0) & (nb < s.total)
        nbc = np.where(valid, nb, 0)
        valid &= s.lay[nbc] == lay
        key = np.where(valid, rank[wid[nbc]], -1)
        order = np.lexsort((idx, doc_id, key))
    else:
        raise ValueError("sort deve ser position, left ou right")
    page = order[offset: offset + limit]
    texts: dict[int, str | None] = {}
    lines = []
    for p in page:
        k = int(lay[p])
        doc = s.docs[k]
        rows = store.rows(s.layer_ids[k])
        i0 = int(idx[p])
        lo, hi = max(0, i0 - context), min(len(rows) - 1, i0 + n - 1 + context)
        ctx = [(j, rows[j]) for j in range(lo, hi + 1)]          # (idx, start, end, word, lemma, upos, xpos, feats, tags, extra)
        left = [r[2] for j, r in ctx if j < i0]
        hit = [r for j, r in ctx if i0 <= j < i0 + n]
        right = [r[2] for j, r in ctx if j >= i0 + n]
        start_char, end_char = rows[i0][0], rows[i0 + n - 1][1]
        line = {"filename": doc["filename"], "idx": i0, "start_char": start_char, "end_char": end_char,
                "left": " ".join(left), "match": " ".join(r[2] for r in hit), "right": " ".join(right),
                "pos": " ".join(r[4] or r[5] or _first_tag(r[7]) for r in hit).strip() or None,
                "lemma": " ".join(r[3] or "" for r in hit).strip() or None}
        if with_sentence:
            if doc["id"] not in texts:
                texts[doc["id"]] = project.get_corpus_file(doc["corpus_name"], doc["filename"])
            line["sentence"] = _sentence(texts[doc["id"]], start_char, end_char)
        lines.append(line)
    return {"query": query, "total": total, "limit": limit, "offset": offset, "sort": sort, "lines": lines}


# ---------------------------------------------------------------------------
# Unidades (frequência e colocados)
# ---------------------------------------------------------------------------

def _per_layer(s: Selection, flags: np.ndarray) -> np.ndarray:
    """Soma de `flags` (um por token) em cada camada; camadas vazias dão 0."""
    cs = np.concatenate(([0], np.cumsum(flags.astype(np.int64))))
    return cs[s.offsets[1:]] - cs[s.offsets[:-1]]


def _is_word(s: Selection) -> np.ndarray:
    def build():
        u = s.values(UPOS)
        w = s.values(WORD)
        upos_truthy = _mask(u, lambda v: bool(v))
        upos_ok = _mask(u, lambda v: bool(v) and v not in _EXCLUDED_UPOS)
        word_ok = _mask(w, lambda v: bool(v) and _HAS_LETTER.search(v) is not None)
        return upos_truthy, upos_ok, word_ok
    upos_truthy, upos_ok, word_ok = build()
    uid, wid = s.col(UPOS), s.col(WORD)
    return np.where(upos_truthy[uid], upos_ok[uid], word_ok[wid])


class _Vocab:
    def __init__(self):
        self.ids: dict[str, int] = {}
        self.strings: list[str] = []

    def add(self, v: str) -> int:
        i = self.ids.get(v)
        if i is None:
            i = self.ids[v] = len(self.strings)
            self.strings.append(v)
        return i


def _unit_keys(s: Selection, unit: str, vocab: _Vocab) -> np.ndarray:
    """Um inteiro por token identificando o valor da unidade (-1 = sem valor). Valores iguais têm chave igual."""
    wv, lv, uv, xv = s.values(WORD), s.values(LEMMA), s.values(UPOS), s.values(XPOS)
    wid, lid, uid, xid = s.col(WORD), s.col(LEMMA), s.col(UPOS), s.col(XPOS)
    word_low = np.array([vocab.add((w or "").lower()) for w in wv], dtype=np.int64)     # '' para None, como `_unit_value`
    if unit == "form":
        return word_low[wid]
    if unit == "lemma":
        lem = np.array([vocab.add(v.lower()) if v else -1 for v in lv], dtype=np.int64)
        lem_truthy = np.array([bool(v) for v in lv], dtype=bool)
        return np.where(lem_truthy[lid], lem[lid], word_low[wid])
    upos_s = np.array([vocab.add(v) if v else -1 for v in uv], dtype=np.int64)
    xpos_s = np.array([vocab.add(v) if v else -1 for v in xv], dtype=np.int64)
    pos = np.where(upos_s[uid] >= 0, upos_s[uid], xpos_s[xid])
    if unit == "pos":
        return pos
    if unit == "word_pos":
        base = len(vocab.strings) + 1
        return _pair_key(word_low[wid], pos, base, vocab, joiner="/")
    raise Unsupported(unit)


def _pair_key(a: np.ndarray, b: np.ndarray, base: int, vocab: _Vocab, joiner: str) -> np.ndarray:
    """Chave de `f"{a}/{b}"` (ou só `a` quando b == -1), registrando as cadeias no vocabulário."""
    key = a * base + (b + 1)
    uniq = np.unique(key)
    mapping = {}
    for k in uniq.tolist():
        av, bv = divmod(k, base)
        text = vocab.strings[av] if bv == 0 else f"{vocab.strings[av]}{joiner}{vocab.strings[bv - 1]}"
        mapping[k] = vocab.add(text)
    return _map_keys(key, uniq, mapping)


def _map_keys(key: np.ndarray, uniq: np.ndarray, mapping: dict) -> np.ndarray:
    targets = np.array([mapping[k] for k in uniq.tolist()], dtype=np.int64)
    return targets[np.searchsorted(uniq, key)]


def _group_key(doc: dict, by: str) -> str:
    return "corpus" if by == "corpus" else doc["filename"] if by == "document" else doc["meta"].get(by, "")


def frequency(store: IdStore, sel: dict[int, dict], unit: str, n: int, by: str, top: int | None, words_only: bool,
              stop: "set[str]") -> dict:
    s = Selection(store, sel)
    isw = _is_word(s)
    vocab = _Vocab()
    order_layers = list(range(len(s.layer_ids)))
    gkeys = [_group_key(d, by) for d in s.docs]
    sizes: Counter = Counter()
    per_layer_words = _per_layer(s, isw)
    for k in order_layers:
        sizes[gkeys[k]] += int(per_layer_words[k])
    if unit == "ngram":
        if n < 1 or n > 3:
            raise Unsupported("n-grama grande")
        keyed = _unit_keys(s, "form", vocab)
    else:
        keyed = _unit_keys(s, unit, vocab)
    keep = isw if (words_only and unit != "pos") else np.ones(s.total, dtype=bool)
    counts: dict[str, "list[tuple[int, int, int]]"] = {}
    groups_layers: "dict[str, list[int]]" = {}
    for k in order_layers:
        groups_layers.setdefault(gkeys[k], []).append(k)
    for g, layers in groups_layers.items():
        if unit == "ngram":
            keys = _ngram_keys(s, keyed, keep, layers, n, len(vocab.strings) + 1)
        else:
            sl = np.concatenate([np.arange(s.offsets[k], s.offsets[k + 1]) for k in layers]) if layers else np.zeros(0, np.int64)
            sl = sl[keep[sl]]
            keys = keyed[sl]
            nonempty = np.array([bool(x) for x in vocab.strings] + [False], dtype=bool)
            keys = keys[(keys >= 0) & nonempty[np.where(keys >= 0, keys, len(vocab.strings))]]
        uniq, first_idx, cnt = np.unique(keys, return_index=True, return_counts=True)
        counts[g] = list(zip(uniq.tolist(), first_idx.tolist(), cnt.tolist()))
    rows_out = []
    for g, items in counts.items():
        strings = [(vocab.strings[k] if unit != "ngram" else _ngram_text(k, n, vocab), first, c) for k, first, c in items]
        merged: dict[str, list[int]] = {}
        for text, first, c in strings:                        # chaves diferentes com o mesmo texto: soma
            if text in stop:
                continue
            m = merged.get(text)
            if m is None:
                merged[text] = [first, c]
            else:
                m[0] = min(m[0], first)
                m[1] += c
        ranked = sorted(merged.items(), key=lambda kv: (-kv[1][1], kv[1][0]))     # como Counter.most_common (estável na 1ª aparição)
        for text, (first, c) in (ranked[:top] if top else ranked):
            rows_out.append({"group": g, "item": text, "freq": c,
                             "per_1000": 1000 * c / sizes[g] if sizes[g] else None})
    return {"unit": unit, "by": by, "sizes": dict(sizes), "rows": rows_out}


def _ngram_keys(s: Selection, keyed: np.ndarray, keep: np.ndarray, layers: list[int], n: int, base: int) -> np.ndarray:
    parts = []
    for k in layers:
        seg = keyed[s.offsets[k]: s.offsets[k + 1]][keep[s.offsets[k]: s.offsets[k + 1]]]
        m = len(seg) - n + 1
        if m > 0:
            acc = seg[:m].copy()
            for j in range(1, n):
                acc = acc * base + seg[j: j + m]
            parts.append(acc)
    return np.concatenate(parts) if parts else np.zeros(0, np.int64)


def _ngram_text(key: int, n: int, vocab: _Vocab) -> str:
    base = len(vocab.strings) + 1
    ids = []
    for _ in range(n):
        key, r = divmod(key, base)
        ids.append(r)
    return " ".join(vocab.strings[i] for i in reversed(ids))


# ---------------------------------------------------------------------------
# Colocados
# ---------------------------------------------------------------------------

def collocates(store: IdStore, sel: dict[int, dict], node: str, window: tuple[int, int], unit: str, min_freq: int,
               top: int, sort: str) -> dict:
    s = Selection(store, sel)
    pos, n = find(s, node)
    lay, idx = s.lay[pos], s.idx[pos].astype(np.int64)
    left, right = window
    isw = _is_word(s)
    vocab = _Vocab()
    if unit not in ("form", "lemma", "pos", "word_pos"):
        raise Unsupported(unit)
    keyed = _unit_keys(s, unit, vocab)
    NONE = len(vocab.strings) + 5                      # valor None (sem chave) conta como um valor
    keyed = np.where(keyed >= 0, keyed, NONE)
    # posição de cada token entre as palavras da camada
    cs = np.concatenate(([0], np.cumsum(isw.astype(np.int64))))
    word_rank = cs[:-1]                                # nº de palavras antes do token, no vetor todo
    layer_first_word = cs[s.offsets[:-1]]
    words_flat = np.flatnonzero(isw)                   # posições (no vetor todo) das palavras, em ordem
    n_words_layer = _per_layer(s, isw)
    total_words = int(isw.sum())
    coll_freq = np.bincount(keyed[isw], minlength=NONE + 1) if total_words else np.zeros(NONE + 1, np.int64)
    # acertos: um por (camada, idx) — conjunto — e só os que são palavras
    order_events_keys, order_events_side, order_events_node = [], [], []
    node_vocab = _Vocab()
    wv_all, wid_all = s.values(WORD), s.col(WORD)
    node_freq = 0
    hits_by_layer: "dict[int, set[int]]" = defaultdict(set)
    for L, i in zip(lay.tolist(), idx.tolist()):
        hits_by_layer[L].add(i)
    d_left = np.arange(-left, 0)
    d_right = np.arange(n, n + right)
    offs = np.concatenate([d_left, d_right]) if left or right else np.zeros(0, np.int64)
    for L in sorted(hits_by_layer):                        # a ordem das camadas de `sel`
        idxs = list(hits_by_layer[L])                      # ordem de iteração de um conjunto, como no caminho SQL
        base = int(s.offsets[L])
        arr = np.array(idxs, dtype=np.int64)
        flat_pos = base + arr
        is_hit_word = isw[flat_pos]
        arr, flat_pos = arr[is_hit_word], flat_pos[is_hit_word]
        if not len(arr):
            continue
        k = word_rank[flat_pos] - layer_first_word[L]      # posição do acerto entre as palavras da camada
        node_freq += len(k)
        nw = int(n_words_layer[L])
        first_word = int(layer_first_word[L])
        j = k[:, None] + offs[None, :]
        valid = (j >= 0) & (j < nw)
        gj = np.where(valid, first_word + j, 0)
        vals = keyed[words_flat[gj]]
        order_events_keys.append(vals[valid])
        order_events_side.append(np.broadcast_to(offs < 0, j.shape)[valid])
        # forma do nó de cada acerto: palavras k..k+n-1 da camada, em minúsculas (como no caminho SQL)
        nid = np.array([node_vocab.add(" ".join((wv_all[wid_all[words_flat[first_word + i]]] or "").lower()
                                                 for i in range(int(kk), min(nw, int(kk) + n)))) for kk in k], dtype=np.int64)
        order_events_node.append(np.broadcast_to(nid[:, None], j.shape)[valid])
    if order_events_keys:
        ev_keys = np.concatenate(order_events_keys)
        ev_left = np.concatenate(order_events_side)
        ev_node = np.concatenate(order_events_node)
    else:
        ev_keys, ev_left, ev_node = np.zeros(0, np.int64), np.zeros(0, bool), np.zeros(0, np.int64)
    # forma do nó mais frequente por colocado (empate: a que apareceu primeiro, como Counter.most_common)
    best_form: dict = {}
    if len(ev_keys):
        nn = len(node_vocab.strings) + 1
        combo = ev_keys.astype(np.int64) * nn + ev_node
        cu, cfirst, ccnt = np.unique(combo, return_index=True, return_counts=True)
        ckey, cnode = cu // nn, cu % nn
        order = np.lexsort((cfirst, -ccnt, ckey))
        ukeys, ufirst, ucount = np.unique(ckey[order], return_index=True, return_counts=True)
        for key_, at, c_ in zip(ukeys.tolist(), ufirst.tolist(), ucount.tolist()):
            best_form[key_] = (node_vocab.strings[int(cnode[order][at])], c_)
    # `hits` no SQL vinha de um conjunto por camada, e as camadas em ordem de `sel`: reproduz a 1ª aparição
    uniq, first, cnt = np.unique(ev_keys, return_index=True, return_counts=True)
    lcount = np.bincount(np.searchsorted(uniq, ev_keys[ev_left]), minlength=len(uniq)) if len(uniq) else np.zeros(0, np.int64)
    span = left + right
    out = []
    for u_i in np.argsort(first, kind="stable").tolist():         # ordem de 1ª aparição = ordem de inserção do Counter
        key = int(uniq[u_i])
        o = int(cnt[u_i])
        if o < min_freq:
            continue
        w = None if key == NONE else vocab.strings[key]
        fc = int(coll_freq[key])
        lc = int(lcount[u_i])
        rc = o - lc
        e = node_freq * fc * span / total_words if total_words else 0
        o12 = max(node_freq * span - o, 0)
        o21 = max(fc - o, 0)
        o22 = max(total_words - o - o12 - o21, 0)
        n_all = o + o12 + o21 + o22
        ll = 0.0
        for obs, r_tot, c_tot in ((o, o + o12, o + o21), (o12, o + o12, o12 + o22),
                                  (o21, o21 + o22, o + o21), (o22, o21 + o22, o12 + o22)):
            exp = r_tot * c_tot / n_all if n_all else 0
            if obs > 0 and exp > 0:
                ll += obs * math.log(obs / exp)
        out.append({"collocate": w, "freq": o, "coll_total": fc, "expected": e,
                    "mi": math.log2(o / e) if e else None, "t_score": (o - e) / math.sqrt(o) if o else None,
                    "ll": 2 * ll, "position": "L" if lc > rc else "R" if rc > lc else "L=R",
                    "left": lc, "right": rc, "node_form": best_form[key][0], "node_forms": best_form[key][1]})
    k = {"ll": "ll", "mi": "mi", "t": "t_score", "freq": "freq"}.get(sort)
    if k is None:
        raise ValueError("sort deve ser ll, mi, t ou freq")
    out.sort(key=lambda r: (r[k] is None, -(r[k] or 0)))
    return {"node": node, "node_freq": node_freq, "corpus_words": total_words, "window": [left, right],
            "unit": unit, "rows": out[:top]}


def hits(store: IdStore, sel: dict[int, dict], node: str) -> "tuple[list[tuple[int, int, int]], int]":
    """Ocorrências da consulta como (camada, documento, idx), em ordem de documento e posição, e o tamanho da sequência."""
    s = Selection(store, sel)
    pos, n = find(s, node)
    lay, idx = s.lay[pos], s.idx[pos].astype(np.int64)
    doc_id = np.array([d["id"] for d in s.docs], dtype=np.int64)[lay] if len(pos) else np.zeros(0, np.int64)
    order = np.lexsort((idx, doc_id))
    ids = np.array(s.layer_ids, dtype=np.int64)
    return [(int(ids[lay[i]]), int(doc_id[i]), int(idx[i])) for i in order], n
