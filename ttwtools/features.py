"""
features.py — Tabelas de traços a partir das camadas e KFA entre corpora ou grupos.

    feature_table(proj, "corpus", layer="biberplus")          # contagens por texto
    feature_table(proj, "corpus", layer="spacy", feature="xpos", per1000=True)
    kfa_layers(proj, "A", "B", layer="biberplus")             # d de Cohen por traço

As contagens vêm dos tokens da camada (sem reetiquetar). "Words" segue a regra de
cada tagger no fluxo antigo, para a KFA dar o mesmo resultado: BiberPlus conta
palavras só de letras ([A-Za-z]+) no texto; os demais contam tokens com letra.
"""

from __future__ import annotations

import re
import tempfile
import threading
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Callable, Mapping

import pandas as pd

from .project import TTWAProject
from .query import _select_layers

_WORD_RE = re.compile(r"\b[A-Za-z]+\b")
_TABLES: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()     # tabelas já contadas (memória; ver feature_table)
_TABLES_MAX = 12
_TABLES_LOCK = threading.Lock()
_HAS_ALPHA = re.compile(r"[A-Za-z]")
FEATURES = ("tags", "upos", "xpos")


def default_feature(tool: str) -> str:
    """Traço padrão da camada: `tags` no BiberPlus e no MFTE (`mfte`, `mfte_ext`), `upos` nos demais."""
    return "tags" if tool in ("biberplus", "mfte", "mfte_ext") else "upos"


def feature_table(project: TTWAProject, corpus_name: str, layer: str, feature: str | None = None,
                  per1000: bool = False, where: Mapping | None = None,
                  progress: "Callable[[int, int], None] | None" = None, sel: Mapping | None = None) -> pd.DataFrame:
    """Uma linha por documento: filename, Words, TTR e uma coluna por traço
    (contagem bruta ou por 1000 palavras). `progress(feitos, total)` a cada documento;
    `sel` (opcional): camadas já escolhidas por `_select_layers`."""
    feature = feature or default_feature(layer)
    if feature not in FEATURES:
        raise ValueError(f"feature deve ser uma de {FEATURES}")
    sel = sel if sel is not None else _select_layers(project, corpus_name, layer, where)
    # Contar é a parte cara. Uma camada (id) nunca muda, então a chave é o conteúdo das camadas escolhidas:
    # o detalhe de uma feature, a galeria e a KFA repetida reaproveitam a tabela (só em memória, por sessão).
    key = _table_key(project, sel, layer, feature, per1000)
    with _TABLES_LOCK:
        if key in _TABLES:
            _TABLES.move_to_end(key)
            return _TABLES[key].copy()
    records = []
    for n_done, (layer_id, doc) in enumerate(sel.items(), 1):
        if progress:
            progress(n_done - 1, len(sel))
        toks = project._con.execute("SELECT word, upos, xpos, tags FROM tokens WHERE layer_id = ? ORDER BY idx",
                                    (layer_id,)).fetchall()
        counts: Counter = Counter()
        for t in toks:
            if feature == "tags":
                import json
                counts.update(json.loads(t["tags"] or "[]"))
            elif t[feature] and t[feature] not in ("_", "SP", "_SP"):
                counts[t[feature]] += 1
        if layer == "biberplus":
            text = project.get_corpus_file(corpus_name, doc["filename"]) or ""
            words = _WORD_RE.findall(re.sub(r"<[^>]*>", "", text))
        else:
            words = [t["word"] for t in toks if t["word"] and _HAS_ALPHA.search(t["word"])]
        n = len(words)
        types = set(words) if layer == "biberplus" else {w.lower() for w in words}   # regra antiga de cada tagger
        rec = {"filename": doc["filename"], "Words": n, "TTR": len(types) / n if n else 0.0}
        for tag, c in counts.items():
            rec[tag] = (c * 1000 / n if n else 0.0) if per1000 else c
        records.append(rec)
    df = pd.DataFrame(records)
    if not df.empty:
        meta = ["filename", "Words", "TTR"]
        df = df[meta + sorted(c for c in df.columns if c not in meta)].fillna(0)
    with _TABLES_LOCK:
        _TABLES[key] = df.copy()
        while len(_TABLES) > _TABLES_MAX:
            _TABLES.popitem(last=False)
    return df


def _table_key(project: TTWAProject, sel: Mapping, layer: str, feature: str, per1000: bool) -> tuple:
    """Identidade do conteúdo contado: camadas (id, hash do texto, configuração, tokens) mais o que muda a conta."""
    ids = sorted(sel)
    marks = ",".join("?" * len(ids))
    rows = project._con.execute(
        f"SELECT id, text_hash, config_hash, n_tokens FROM layers WHERE id IN ({marks}) ORDER BY id", ids).fetchall() if ids else []
    return (layer, feature, per1000, tuple(tuple(r) for r in rows))


def kfa_layers(project: TTWAProject, corpus1: str, corpus2: str, layer: str, feature: str | None = None,
               metric: str = "kfa", min_effect: float = 0.0, join: str = "union",
               where1: Mapping | None = None, where2: Mapping | None = None, save: bool = True,
               progress: "Callable[[int, int, str], None] | None" = None, reuse: bool = True) -> dict:
    """KFA (d de Cohen por traço, por 1000 palavras) entre dois corpora — ou dois
    grupos do mesmo corpus, com `where1`/`where2`. `metric`: kfa (Biber & Egbert)
    ou kfa2 (desvio combinado ponderado).

    Com `save`, o resultado fica nas análises do projeto junto das camadas usadas; pedir de novo a
    mesma KFA sobre as mesmas camadas devolve o resultado guardado (`reuse=True`; `cached` no
    resultado) em vez de contar tudo outra vez. `progress(feitos, total, etapa)`: `kfa_count` (um
    documento de cada vez, nos dois lados) e `kfa_calc`."""
    from .analysis import analyze_key_features
    params = {"corpus1": corpus1, "corpus2": corpus2, "where1": dict(where1 or {}), "where2": dict(where2 or {}),
              "layer": layer, "feature": feature or default_feature(layer), "metric": metric,
              "min_effect": min_effect, "join": join}
    sel1 = _select_layers(project, corpus1, layer, where1)
    sel2 = _select_layers(project, corpus2, layer, where2)
    refs = sorted(set(sel1) | set(sel2))
    if save and reuse:
        hit = project.find_analysis("kfa", params, refs)
        if hit is not None:
            return {**hit["result"], "cached": True}
    total = len(sel1) + len(sel2)

    def side(offset):
        return (lambda d, t: progress(offset + d, total, "kfa_count")) if progress else None
    t1 = feature_table(project, corpus1, layer, feature, per1000=True, where=where1, progress=side(0), sel=sel1)
    t2 = feature_table(project, corpus2, layer, feature, per1000=True, where=where2, progress=side(len(sel1)), sel=sel2)
    if progress:
        progress(total, total, "kfa_calc")
    if len(t1) < 2 or len(t2) < 2:
        raise ValueError("cada lado precisa de pelo menos 2 documentos com a camada")
    meta = {"filename", "Words", "TTR"}
    if not ({*t1.columns} | {*t2.columns}) - meta:
        raise ValueError(f"a camada '{layer}' não tem o traço '{feature or default_feature(layer)}' nesses corpora "
                         "(escolha outra camada no topo ou outro traço)")
    with tempfile.TemporaryDirectory() as tmp:
        p1, p2 = Path(tmp) / "c1_norm1000.csv", Path(tmp) / "c2_norm1000.csv"
        t1.to_csv(p1, index=False)
        t2.to_csv(p2, index=False)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):     # a função antiga imprime o progresso
            df = analyze_key_features(str(p1), str(p2), min_effect_size=min_effect, join=join, metric=metric)
    rows = df.to_dict(orient="records") if not df.empty else []
    result = {**params, "n1": len(t1), "n2": len(t2), "rows": rows}
    if save:
        project.replace_analysis("kfa", result, name=f"{corpus1} × {corpus2} [{layer}]", params=params, layer_refs=refs)
    return result


def feature_values(project: TTWAProject, corpus_name: str, layer: str, feature_name: str,
                   feature: str | None = None, where: Mapping | None = None) -> list[dict]:
    """Valor por 1000 palavras de um traço em cada documento (detalhe do traço)."""
    t = feature_table(project, corpus_name, layer, feature, per1000=True, where=where)
    if t.empty:
        return []
    col = t[feature_name] if feature_name in t.columns else pd.Series(0.0, index=t.index)
    return [{"filename": f, "value": float(v), "words": int(w)} for f, v, w in zip(t["filename"], col, t["Words"])]
