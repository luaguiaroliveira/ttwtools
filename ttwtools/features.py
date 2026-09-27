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
from collections import Counter
from pathlib import Path
from typing import Mapping

import pandas as pd

from .project import TTWAProject
from .query import _select_layers

_WORD_RE = re.compile(r"\b[A-Za-z]+\b")
_HAS_ALPHA = re.compile(r"[A-Za-z]")
FEATURES = ("tags", "upos", "xpos")


def default_feature(tool: str) -> str:
    return "tags" if tool in ("biberplus", "mfte") else "upos"


def feature_table(project: TTWAProject, corpus_name: str, layer: str, feature: str | None = None,
                  per1000: bool = False, where: Mapping | None = None) -> pd.DataFrame:
    """Uma linha por documento: filename, Words, TTR e uma coluna por traço
    (contagem bruta ou por 1000 palavras)."""
    feature = feature or default_feature(layer)
    if feature not in FEATURES:
        raise ValueError(f"feature deve ser uma de {FEATURES}")
    sel = _select_layers(project, corpus_name, layer, where)
    records = []
    for layer_id, doc in sel.items():
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
    return df


def kfa_layers(project: TTWAProject, corpus1: str, corpus2: str, layer: str, feature: str | None = None,
               metric: str = "kfa", min_effect: float = 0.0, join: str = "union",
               where1: Mapping | None = None, where2: Mapping | None = None, save: bool = True) -> dict:
    """KFA (d de Cohen por traço, por 1000 palavras) entre dois corpora — ou dois
    grupos do mesmo corpus, com `where1`/`where2`. `metric`: kfa (Biber & Egbert)
    ou kfa2 (desvio combinado ponderado)."""
    from .analysis import analyze_key_features
    t1 = feature_table(project, corpus1, layer, feature, per1000=True, where=where1)
    t2 = feature_table(project, corpus2, layer, feature, per1000=True, where=where2)
    if len(t1) < 2 or len(t2) < 2:
        raise ValueError("cada lado precisa de pelo menos 2 documentos com a camada")
    with tempfile.TemporaryDirectory() as tmp:
        p1, p2 = Path(tmp) / "c1_norm1000.csv", Path(tmp) / "c2_norm1000.csv"
        t1.to_csv(p1, index=False)
        t2.to_csv(p2, index=False)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):     # a função antiga imprime o progresso
            df = analyze_key_features(str(p1), str(p2), min_effect_size=min_effect, join=join, metric=metric)
    rows = df.to_dict(orient="records") if not df.empty else []
    result = {"corpus1": corpus1, "corpus2": corpus2, "where1": dict(where1 or {}), "where2": dict(where2 or {}),
              "layer": layer, "feature": feature or default_feature(layer), "metric": metric,
              "min_effect": min_effect, "join": join, "n1": len(t1), "n2": len(t2), "rows": rows}
    if save:
        project.save_analysis("kfa", result, name=f"{corpus1} × {corpus2} [{layer}]",
                              params={k: result[k] for k in ("corpus1", "corpus2", "where1", "where2", "layer",
                                                              "feature", "metric", "min_effect", "join")})
    return result


def feature_values(project: TTWAProject, corpus_name: str, layer: str, feature_name: str,
                   feature: str | None = None, where: Mapping | None = None) -> list[dict]:
    """Valor por 1000 palavras de um traço em cada documento (detalhe do traço)."""
    t = feature_table(project, corpus_name, layer, feature, per1000=True, where=where)
    if t.empty:
        return []
    col = t[feature_name] if feature_name in t.columns else pd.Series(0.0, index=t.index)
    return [{"filename": f, "value": float(v), "words": int(w)} for f, v, w in zip(t["filename"], col, t["Words"])]
