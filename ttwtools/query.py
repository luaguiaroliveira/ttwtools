"""
query.py — Busca, KWIC, frequência, colocados e dispersão sobre a tabela `tokens`.

Consulta (`query`): tokens separados por espaço formam uma sequência (frase).
Cada token aceita:
    casa            forma, sem distinguir maiúsculas
    cas*  *ção      curingas (* e ?) na forma
    /^run(s|ning)$/ expressão regular na forma (sem distinguir maiúsculas)
    lemma=run       lema          pos=NOUN   UPOS ou XPOS     upos=  xpos=
    tag=PASS        etiqueta do tagger (BiberPlus, MFTE)       word=  (forma)
    lemma=run&pos=VERB    condições juntas no mesmo token

Camada: `layer` escolhe a ferramenta (spacy, stanza, conllu...); sem `layer`, usa
a camada mais recente de cada documento. Documentos sem camada nenhuma ganham a
camada `simple` (só formas, sem tagger) na primeira consulta.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from .corpus import filter_documents
from .project import TTWAProject

_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_FIELDS = {"word": "lower(t{i}.word)", "lemma": "lower(t{i}.lemma)", "upos": "t{i}.upos", "xpos": "t{i}.xpos"}


# ---------------------------------------------------------------------------
# Seleção de camadas
# ---------------------------------------------------------------------------

_NEEDS_SQL = {"lemma": "t.lemma IS NOT NULL AND t.lemma <> ''",
              "pos": "(t.upos IS NOT NULL AND t.upos <> '') OR (t.xpos IS NOT NULL AND t.xpos <> '')",
              "tags": "t.tags IS NOT NULL AND t.tags NOT IN ('', '[]')"}


def _needs(query: str | None = None, unit: str | None = None) -> str | None:
    """Campo que a consulta ou a unidade exige da camada (lemma, pos, tags) ou None."""
    if unit == "lemma":
        return "lemma"
    if unit in ("pos", "word_pos"):
        return "pos"
    q = query or ""
    if re.search(r"\blemma=", q):
        return "lemma"
    if re.search(r"\b(pos|upos|xpos)=", q):
        return "pos"
    if re.search(r"\btag=", q):
        return "tags"
    return None


def _select_layers(project: TTWAProject, corpus_name: str, layer: str | None, where: Mapping | None,
                   needs: str | None = None) -> dict[int, dict]:
    """{layer_id: documento} com uma camada por documento; grava em TEMP _sel.
    Sem `layer`, usa a camada mais recente de cada documento; com `needs` (lemma, pos,
    tags), a mais recente que tenha esse campo (ex.: `lemma=` não cai numa camada
    BiberPlus, que não tem lema), e só na falta dela a mais recente."""
    docs = filter_documents(project, corpus_name, where)
    if not docs:
        return {}
    if layer in (None, "simple"):
        # documentos sem camada nenhuma ganham a camada `simple` (só formas)
        ids = [d["id"] for d in docs]
        with_layer = {r[0] for r in project._con.execute(
            f"SELECT DISTINCT doc_id FROM layers WHERE doc_id IN ({','.join('?' * len(ids))})", ids)}
        missing = [d["filename"] for d in docs if d["id"] not in with_layer]
        if layer == "simple":
            missing = [d["filename"] for d in docs]
        if missing:
            from .annotate import tag_corpus
            tag_corpus(project, corpus_name, "simple", filenames=missing)
    sel: dict[int, dict] = {}
    for d in docs:
        row = None
        if not layer and needs in _NEEDS_SQL:
            row = project._con.execute(
                "SELECT l.id FROM layers l WHERE l.doc_id = ? AND EXISTS (SELECT 1 FROM tokens t WHERE t.layer_id = l.id"
                f" AND ({_NEEDS_SQL[needs]})) ORDER BY l.id DESC LIMIT 1", (d["id"],)).fetchone()
        if row is None:
            sql = "SELECT id FROM layers WHERE doc_id = ?" + (" AND tool = ?" if layer else "") + " ORDER BY id DESC LIMIT 1"
            row = project._con.execute(sql, (d["id"], layer) if layer else (d["id"],)).fetchone()
        if row:
            sel[row["id"]] = d
    con = project._con
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _sel (layer_id INTEGER PRIMARY KEY)")
    con.execute("DELETE FROM _sel")
    con.executemany("INSERT INTO _sel VALUES (?)", [(i,) for i in sel])
    return sel


def _ensure_regexp(project: TTWAProject) -> None:
    def regexp(pattern, value):
        return value is not None and re.search(pattern, value, re.IGNORECASE) is not None
    project._con.create_function("REGEXP", 2, regexp, deterministic=True)


# ---------------------------------------------------------------------------
# Consulta → SQL
# ---------------------------------------------------------------------------

def _glob_to_range(pattern: str) -> tuple[str, str] | None:
    """`cas*` → ('cas', 'cat'): prefixo como intervalo (usa o índice)."""
    if pattern.endswith("*") and not re.search(r"[*?\[]", pattern[:-1]) and pattern[:-1]:
        prefix = pattern[:-1]
        return prefix, prefix[:-1] + chr(ord(prefix[-1]) + 1)
    return None


def _token_conditions(spec: str, i: int) -> tuple[list[str], list[Any]]:
    conds, args = [], []
    for part in spec.split("&"):
        key, sep, value = part.partition("=")
        if not sep:
            key, value = "word", part
        key = key.strip().lower()
        value = value.strip()
        if key == "pos":
            conds.append(f"(t{i}.upos = ? OR t{i}.xpos = ?)")
            args += [value, value]
            continue
        if key == "tag":
            # camadas com tags (BiberPlus, MFTE): a tag; sem tags (spaCy, Stanza), cai para UPOS/XPOS
            conds.append(f"(t{i}.tags LIKE ? OR ((t{i}.tags IS NULL OR t{i}.tags IN ('', '[]')) AND (t{i}.upos = ? OR t{i}.xpos = ?)))")
            args += [f'%"{value}"%', value, value]
            continue
        if key not in _FIELDS:
            raise ValueError(f"campo desconhecido '{key}' (use word, lemma, pos, upos, xpos, tag)")
        col = _FIELDS[key].format(i=i)
        if len(value) > 1 and value.startswith("/") and value.endswith("/"):
            raw = {"word": f"t{i}.word", "lemma": f"t{i}.lemma"}.get(key, col)
            conds.append(f"{raw} REGEXP ?")
            args.append(value[1:-1])
            continue
        v = value.lower() if key in ("word", "lemma") else value
        rng = _glob_to_range(v)
        if rng:
            conds.append(f"{col} >= ? AND {col} < ?")
            args += list(rng)
        elif re.search(r"[*?]", v):
            conds.append(f"{col} GLOB ?")
            args.append(v)
        else:
            conds.append(f"{col} = ?")
            args.append(v)
    return conds, args


def _match_sql(query: str) -> tuple[str, list[Any], int]:
    specs = query.split()
    if not specs:
        raise ValueError("consulta vazia")
    froms = ["tokens t0 JOIN _sel s ON s.layer_id = t0.layer_id"]
    where, args = [], []
    for i, spec in enumerate(specs):
        if i:
            froms.append(f"JOIN tokens t{i} ON t{i}.layer_id = t0.layer_id AND t{i}.idx = t0.idx + {i}")
        c, a = _token_conditions(spec, i)
        where += c
        args += a
    last = len(specs) - 1
    sql = (f"SELECT t0.layer_id, t0.doc_id, t0.idx, t0.start_char, t{last}.end_char AS end_char "
           f"FROM {' '.join(froms)} WHERE {' AND '.join(where)}")
    return sql, args, len(specs)


# ---------------------------------------------------------------------------
# search, kwic
# ---------------------------------------------------------------------------

def search(project: TTWAProject, corpus_name: str, query: str, layer: str | None = None,
           where: Mapping | None = None, group_by: str | None = None) -> dict:
    """Quantas vezes a consulta aparece: total, por documento e (com `group_by`,
    nome de metadado) por grupo."""
    sel = _select_layers(project, corpus_name, layer, where, _needs(query))
    _ensure_regexp(project)
    sql, args, _ = _match_sql(query)
    per_doc = Counter()
    for row in project._con.execute(f"SELECT layer_id, COUNT(*) AS n FROM ({sql}) GROUP BY layer_id", args):
        per_doc[sel[row["layer_id"]]["filename"]] += row["n"]
    out = {"query": query, "total": sum(per_doc.values()), "documents": len(per_doc),
           "per_document": [{"filename": f, "freq": n} for f, n in per_doc.most_common()]}
    if group_by:
        groups = Counter()
        for d in sel.values():
            groups[d["meta"].get(group_by, "")] += per_doc.get(d["filename"], 0)
        out["per_group"] = [{"group": g, "freq": n} for g, n in groups.most_common()]
    return out


def _sentence(text: str | None, start: int, end: int) -> str | None:
    if text is None:
        return None
    left = max(text.rfind(ch, 0, start) for ch in ".!?\n")
    rights = [p for p in (text.find(ch, end) for ch in ".!?\n") if p != -1]
    right = min(rights) + 1 if rights else len(text)
    return re.sub(r"\s+", " ", text[left + 1:right]).strip()


def kwic(project: TTWAProject, corpus_name: str, query: str, layer: str | None = None,
         where: Mapping | None = None, context: int = 5, limit: int = 50, offset: int = 0,
         sort: str = "position", with_sentence: bool = True) -> dict:
    """Concordância: cada ocorrência com `context` tokens de cada lado, classe,
    arquivo e posição no texto. Paginada (`limit`/`offset`) no SQL; `sort` =
    position, left (palavra à esquerda) ou right (palavra à direita)."""
    sel = _select_layers(project, corpus_name, layer, where, _needs(query))
    _ensure_regexp(project)
    sql, args, n = _match_sql(query)
    order = {
        "position": "m.doc_id, m.idx",
        "left": "(SELECT lower(word) FROM tokens x WHERE x.layer_id = m.layer_id AND x.idx = m.idx - 1), m.doc_id, m.idx",
        "right": f"(SELECT lower(word) FROM tokens x WHERE x.layer_id = m.layer_id AND x.idx = m.idx + {n}), m.doc_id, m.idx",
    }.get(sort)
    if order is None:
        raise ValueError("sort deve ser position, left ou right")
    total = project._con.execute(f"SELECT COUNT(*) FROM ({sql})", args).fetchone()[0]
    rows = project._con.execute(f"SELECT m.* FROM ({sql}) m ORDER BY {order} LIMIT ? OFFSET ?",
                                (*args, limit, offset)).fetchall()
    texts: dict[int, str | None] = {}
    lines = []
    for r in rows:
        doc = sel[r["layer_id"]]
        ctx = project._con.execute(
            "SELECT idx, word, upos, xpos, lemma, tags FROM tokens WHERE layer_id = ? AND idx BETWEEN ? AND ? ORDER BY idx",
            (r["layer_id"], r["idx"] - context, r["idx"] + n - 1 + context)).fetchall()
        left = [c["word"] for c in ctx if c["idx"] < r["idx"]]
        hit = [c for c in ctx if r["idx"] <= c["idx"] < r["idx"] + n]
        right = [c["word"] for c in ctx if c["idx"] >= r["idx"] + n]
        line = {"filename": doc["filename"], "idx": r["idx"], "start_char": r["start_char"], "end_char": r["end_char"],
                "left": " ".join(left), "match": " ".join(c["word"] for c in hit), "right": " ".join(right),
                "pos": " ".join(c["upos"] or c["xpos"] or _first_tag(c["tags"]) for c in hit).strip() or None,
                "lemma": " ".join(c["lemma"] or "" for c in hit).strip() or None}
        if with_sentence:
            if r["doc_id"] not in texts:
                texts[r["doc_id"]] = project.get_corpus_file(doc["corpus_name"], doc["filename"])
            line["sentence"] = _sentence(texts[r["doc_id"]], r["start_char"], r["end_char"])
        lines.append(line)
    return {"query": query, "total": total, "limit": limit, "offset": offset, "sort": sort, "lines": lines}


def _first_tag(raw: str | None) -> str:
    """Primeira tag do token (camadas só com `tags`, como BiberPlus e MFTE); "" se não houver."""
    try:
        tags = json.loads(raw) if raw else []
    except ValueError:
        return ""
    return str(tags[0]) if tags else ""


def explain(project: TTWAProject, corpus_name: str, query: str, layer: str | None = None) -> list[str]:
    """Plano de execução do SQLite para a consulta (para conferir o uso de índices)."""
    _select_layers(project, corpus_name, layer, None, _needs(query))
    _ensure_regexp(project)
    sql, args, _ = _match_sql(query)
    return [r["detail"] for r in project._con.execute(f"EXPLAIN QUERY PLAN {sql}", args)]


# ---------------------------------------------------------------------------
# Frequência
# ---------------------------------------------------------------------------

UNITS = ("form", "lemma", "word_pos", "pos", "ngram")


def _unit_value(t, unit: str) -> str | None:
    word = (t["word"] or "").lower()
    if unit == "form":
        return word
    if unit == "lemma":
        return (t["lemma"] or word).lower()
    pos = t["upos"] or t["xpos"]
    if unit == "pos":
        return pos
    if unit == "word_pos":
        return f"{word}/{pos}" if pos else word
    raise ValueError(unit)


def _is_word(t) -> bool:
    if t["upos"]:
        return t["upos"] not in ("PUNCT", "SYM", "X", "SPACE")
    return bool(t["word"] and _HAS_LETTER.search(t["word"]))


def _layer_tokens(project: TTWAProject, sel: dict[int, dict]):
    for layer_id, doc in sel.items():
        rows = project._con.execute(
            "SELECT idx, word, lemma, upos, xpos FROM tokens WHERE layer_id = ? ORDER BY idx", (layer_id,)).fetchall()
        yield doc, rows


def frequency(project: TTWAProject, corpus_name: str, unit: str = "form", n: int = 2, by: str = "corpus",
              layer: str | None = None, where: Mapping | None = None, top: int | None = 100,
              words_only: bool = True, stop: Iterable[str] | None = None) -> dict:
    """Lista de frequência. `unit`: form, lemma, word_pos, pos ou ngram (de formas,
    tamanho `n`). `by`: corpus, document ou o nome de um metadado (grupo).
    Devolve freq absoluta e por 1000 palavras."""
    if unit not in UNITS:
        raise ValueError(f"unidade deve ser uma de {UNITS}")
    sel = _select_layers(project, corpus_name, layer, where, _needs(unit=unit))
    stop = {s.lower() for s in (stop or [])}
    counts: dict[str, Counter] = defaultdict(Counter)
    sizes: Counter = Counter()
    for doc, rows in _layer_tokens(project, sel):
        key = "corpus" if by == "corpus" else doc["filename"] if by == "document" else doc["meta"].get(by, "")
        toks = [t for t in rows if _is_word(t)] if words_only and unit != "pos" else list(rows)
        sizes[key] += sum(1 for t in rows if _is_word(t))
        if unit == "ngram":
            forms = [(t["word"] or "").lower() for t in toks]
            items = [" ".join(forms[i:i + n]) for i in range(len(forms) - n + 1)]
        else:
            items = [v for v in (_unit_value(t, unit) for t in toks) if v]
        counts[key].update(i for i in items if i not in stop)
    rows_out = []
    for key, c in counts.items():
        for item, f in (c.most_common(top) if top else c.most_common()):
            rows_out.append({"group": key, "item": item, "freq": f,
                             "per_1000": 1000 * f / sizes[key] if sizes[key] else None})
    return {"unit": unit, "by": by, "sizes": dict(sizes), "rows": rows_out}


# ---------------------------------------------------------------------------
# Colocados
# ---------------------------------------------------------------------------

def collocates(project: TTWAProject, corpus_name: str, node: str, window: tuple[int, int] = (5, 5),
               unit: str = "form", layer: str | None = None, where: Mapping | None = None,
               min_freq: int = 2, top: int = 50, sort: str = "ll") -> dict:
    """Colocados de `node` (um token da sintaxe de consulta) numa janela (esquerda,
    direita) de palavras. Medidas: freq (observada), MI, T-score e log-likelihood
    (tabela 2×2, como no #LancsBox). `position` indica onde o colocado aparece mais."""
    left, right = window
    sel = _select_layers(project, corpus_name, layer, where, _needs(node) or _needs(unit=unit))
    _ensure_regexp(project)
    sql, args, n = _match_sql(node)
    hits: dict[int, set[int]] = defaultdict(set)
    for r in project._con.execute(sql, args):
        hits[r["layer_id"]].add(r["idx"])
    total_words = 0
    coll_freq: Counter = Counter()
    observed: Counter = Counter()
    side: dict[str, Counter] = defaultdict(Counter)
    node_freq = 0
    for layer_id, doc in sel.items():
        rows = project._con.execute("SELECT idx, word, lemma, upos, xpos FROM tokens WHERE layer_id = ? ORDER BY idx",
                                    (layer_id,)).fetchall()
        words = [t for t in rows if _is_word(t)]
        values = [_unit_value(t, unit) for t in words]
        total_words += len(words)
        coll_freq.update(values)
        pos_of = {t["idx"]: k for k, t in enumerate(words)}
        for idx in hits.get(layer_id, ()):
            if idx not in pos_of:
                continue
            k = pos_of[idx]
            node_freq += 1
            for j in range(max(0, k - left), min(len(words), k + n + right)):
                if k <= j < k + n:
                    continue
                observed[values[j]] += 1
                side[values[j]]["L" if j < k else "R"] += 1
    span = left + right
    out = []
    for w, o in observed.items():
        if o < min_freq:
            continue
        fc = coll_freq[w]
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
                    "ll": 2 * ll, "position": "L" if side[w]["L"] > side[w]["R"] else "R" if side[w]["R"] > side[w]["L"] else "L=R",
                    "left": side[w]["L"], "right": side[w]["R"]})
    key = {"ll": "ll", "mi": "mi", "t": "t_score", "freq": "freq"}.get(sort)
    if key is None:
        raise ValueError("sort deve ser ll, mi, t ou freq")
    out.sort(key=lambda r: (r[key] is None, -(r[key] or 0)))
    return {"node": node, "node_freq": node_freq, "corpus_words": total_words, "window": [left, right],
            "unit": unit, "rows": out[:top]}


# ---------------------------------------------------------------------------
# Dispersão
# ---------------------------------------------------------------------------

def dispersion(project: TTWAProject, corpus_name: str, query: str, layer: str | None = None,
               where: Mapping | None = None) -> dict:
    """DP de Gries (2008) e Range da consulta, com as posições relativas de cada
    ocorrência por documento (0 a 1) para o gráfico de "código de barras".

    DP = ½ Σ |oᵢ − eᵢ|, com oᵢ = parte das ocorrências no documento i e eᵢ = parte
    do corpus que o documento i representa. 0 = distribuição uniforme; perto de 1 =
    concentrada. DP_norm = DP / (1 − min eᵢ)."""
    sel = _select_layers(project, corpus_name, layer, where, _needs(query))
    _ensure_regexp(project)
    sql, args, _ = _match_sql(query)
    positions: dict[int, list[int]] = defaultdict(list)
    for r in project._con.execute(sql, args):
        positions[r["layer_id"]].append(r["idx"])
    docs = []
    for layer_id, doc in sel.items():
        size = project._con.execute("SELECT COUNT(*) FROM tokens WHERE layer_id = ?", (layer_id,)).fetchone()[0]
        docs.append({"filename": doc["filename"], "size": size, "freq": len(positions[layer_id]),
                     "positions": sorted(p / size for p in positions[layer_id]) if size else []})
    total_size = sum(d["size"] for d in docs)
    total_freq = sum(d["freq"] for d in docs)
    dp = dp_norm = None
    if total_size and total_freq:
        dp = 0.5 * sum(abs(d["freq"] / total_freq - d["size"] / total_size) for d in docs)
        min_e = min(d["size"] / total_size for d in docs)
        dp_norm = dp / (1 - min_e) if min_e < 1 else 0.0
    return {"query": query, "freq": total_freq, "range": sum(1 for d in docs if d["freq"]),
            "documents": len(docs), "dp": dp, "dp_norm": dp_norm, "per_document": docs}


def read_document(project: TTWAProject, corpus_name: str, filename: str, layer: str | None = None) -> dict:
    """Texto de um documento e os tokens da camada (a mais recente de `layer`, ou de
    qualquer ferramenta), para o leitor com etiquetas. `text` é None se o texto não
    estiver disponível (.ttwl sem a pasta do corpus)."""
    doc = project._con.execute("SELECT id FROM documents WHERE corpus_name = ? AND filename = ?",
                               (corpus_name, filename)).fetchone()
    if doc is None:
        raise KeyError(f"documento não encontrado: {corpus_name}/{filename}")
    sql = "SELECT id, tool, tool_version, model FROM layers WHERE doc_id = ?" + (" AND tool = ?" if layer else "")
    row = project._con.execute(sql + " ORDER BY id DESC LIMIT 1", (doc["id"], layer) if layer else (doc["id"],)).fetchone()
    tokens = []
    if row:
        tokens = [{k: t[k] for k in ("idx", "start_char", "end_char", "word", "lemma", "upos", "xpos", "feats", "tags")}
                  for t in project.get_tokens(row["id"])]
    return {"corpus": corpus_name, "filename": filename, "text": project.get_corpus_file(corpus_name, filename),
            "layer": dict(row) if row else None, "tokens": tokens}


def tag_counts(project: TTWAProject, corpus_name: str, layer: str | None = None, field: str = "tags") -> dict:
    """Quantas vezes cada etiqueta ocorre no corpus todo (leitor: ordenar por ocorrências no corpus).
    `field`: "upos", "xpos" ou "tags" (primeira tag do token, como no leitor). Usa a camada mais
    recente de `layer` (ou de qualquer ferramenta) em cada documento."""
    if field not in ("upos", "xpos", "tags"):
        raise ValueError("field deve ser upos, xpos ou tags")
    counts: dict[str, int] = {}
    docs = project._con.execute("SELECT id FROM documents WHERE corpus_name = ?", (corpus_name,)).fetchall()
    for doc in docs:
        sql = "SELECT id FROM layers WHERE doc_id = ?" + (" AND tool = ?" if layer else "")
        row = project._con.execute(sql + " ORDER BY id DESC LIMIT 1", (doc["id"], layer) if layer else (doc["id"],)).fetchone()
        if not row:
            continue
        for t in project.get_tokens(row["id"]):
            v = (t["tags"][0] if t["tags"] else None) if field == "tags" else t[field]
            if v:
                counts[v] = counts.get(v, 0) + 1
    return {"corpus": corpus_name, "layer": layer, "field": field, "documents": len(docs), "counts": counts}
