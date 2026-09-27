"""
experimental.py — Laboratório: comparar N grupos (novomodelo.md §14). API EXPERIMENTAL:
nomes, parâmetros e resultados podem mudar entre versões.

Um grupo é um lado como em viz: {"corpus": "A", "where": {"nível": ["B1"]}, "label": "B1"}.
Toda comparação parte da tabela textos × traços (por 1000 palavras) de uma camada.

    groups = groups_by_metadata(proj, "alunos", "nível")
    compare_groups(proj, groups, layer="biberplus", method="one_vs_rest")
    compare_groups(proj, groups, layer="spacy", method="pairwise")
    compare_groups(proj, [meu_texto] + referencias, layer="biberplus", method="nearest")

Métodos:
    one_vs_rest  d de Cohen de cada grupo contra todos os demais juntos, por traço
    pairwise     d de Cohen para cada par; matriz N×N de distância (média de |d|)
    anova        Kruskal-Wallis por traço, epsilon² e p corrigido (FDR ou Bonferroni)
    profile      PCA dos textos, coloridos pelo grupo (viz.reduction)
    dendrogram   agrupamento hierárquico (Ward) dos perfis médios dos grupos (z-score)
    nearest      o 1º grupo ("meu texto") contra os demais (referências): distância
                 pelo z médio e os traços que mais afastam da referência mais próxima
"""

from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .i18n import t
from .project import TTWAProject

METHODS = ("one_vs_rest", "pairwise", "anova", "profile", "dendrogram", "nearest")
_META = ("filename", "Words", "TTR", "__group")
SMALL_GROUP = 5


def _f(v) -> float | None:
    v = float(v)
    return None if math.isnan(v) or math.isinf(v) else v


def groups_by_metadata(project: TTWAProject, corpus_name: str, key: str,
                       values: list[str] | None = None) -> list[dict]:
    """Um grupo por valor do metadado `key` (ou só os `values` pedidos)."""
    from .corpus import list_groups
    found = sorted(v for v in list_groups(project, corpus_name, key) if v not in (None, ""))
    return [{"corpus": corpus_name, "where": {key: [v]}, "label": v} for v in (values or found)]


def _table(project: TTWAProject, groups: list[Mapping], layer: str, feature: str | None) -> tuple[pd.DataFrame, list[str]]:
    from .features import feature_table
    parts = []
    for i, g in enumerate(groups):
        tab = feature_table(project, g["corpus"], layer, feature, per1000=True, where=g.get("where"))
        tab["__group"] = g.get("label") or f"{g['corpus']} ({i + 1})"
        parts.append(tab)
    df = pd.concat(parts, ignore_index=True).fillna(0.0)
    feats = [c for c in df.columns if c not in _META]
    return df, feats


def _d(a: np.ndarray, b: np.ndarray, metric: str) -> np.ndarray:
    """d de Cohen por coluna (a − b). kfa: SD = sqrt((s1²+s2²)/2); kfa2: SD combinado ponderado."""
    m1, m2 = a.mean(axis=0), b.mean(axis=0)
    v1, v2 = a.var(axis=0, ddof=1), b.var(axis=0, ddof=1)
    if metric == "kfa2":
        n1, n2 = len(a), len(b)
        sd = np.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    else:
        sd = np.sqrt((v1 + v2) / 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(sd > 0, (m1 - m2) / sd, np.nan)


def _top(feats: list[str], d: np.ndarray, extra: dict[str, np.ndarray], top: int) -> list[dict]:
    order = [i for i in np.argsort(-np.abs(np.nan_to_num(d))) if not np.isnan(d[i])][:top]
    return [{"feature": feats[i], "d": _f(d[i]), **{k: _f(v[i]) for k, v in extra.items()}} for i in order]


def _adjust(p: np.ndarray, correction: str) -> np.ndarray:
    if correction == "bonferroni":
        return np.minimum(p * len(p), 1.0)
    if correction == "fdr":
        order = np.argsort(p)
        ranked = p[order] * len(p) / (np.arange(len(p)) + 1)
        adj = np.minimum.accumulate(ranked[::-1])[::-1]
        out = np.empty_like(adj)
        out[order] = np.minimum(adj, 1.0)
        return out
    return p


def _warnings(sizes: dict[str, int], method: str, n_features: int, lang: str | None) -> list[dict]:
    out = [{"code": "experimental", "severity": "info", "message": t("lab.warn.experimental", lang)}]
    small = [g for g, n in sizes.items() if n < SMALL_GROUP]
    if small:
        out.append({"code": "small_group", "severity": "warning",
                    "message": t("lab.warn.small_group", lang, groups=", ".join(small), n=SMALL_GROUP)})
    ns = [n for n in sizes.values() if n]
    if ns and max(ns) >= 3 * min(ns):
        out.append({"code": "unequal", "severity": "warning", "message": t("lab.warn.unequal", lang,
                                                                           min=min(ns), max=max(ns))})
    if method in ("one_vs_rest", "pairwise", "anova") and n_features > 1:
        k = len(sizes) * (len(sizes) - 1) // 2 if method == "pairwise" else len(sizes) if method == "one_vs_rest" else 1
        out.append({"code": "multiple", "severity": "info",
                    "message": t("lab.warn.multiple", lang, tests=k * n_features)})
    return out


def compare_groups(project: TTWAProject, groups: list[Mapping], layer: str, method: str = "one_vs_rest",
                   feature: str | None = None, metric: str = "kfa", top: int = 10, correction: str = "fdr",
                   lang: str | None = None, save: bool = True) -> dict[str, Any]:
    """Compara N grupos de textos pelos traços da camada `layer` (ver o cabeçalho do módulo).
    Devolve {"method", "groups": [{label, n}], "warnings", ...resultado do método}."""
    if method not in METHODS:
        raise ValueError(f"método deve ser um de {METHODS}")
    if len(groups) < 2:
        raise ValueError("são precisos pelo menos 2 grupos")
    df, feats = _table(project, groups, layer, feature)
    labels = list(dict.fromkeys(df["__group"]))
    names = [g.get("label") or f"{g['corpus']} ({i + 1})" for i, g in enumerate(groups)]
    if len(set(names)) < len(names):
        raise ValueError("os grupos precisam de rótulos diferentes")
    sizes = {name: int((df["__group"] == name).sum()) for name in names}
    if len(labels) < 2:
        raise ValueError("menos de 2 grupos têm textos com a camada")
    if not feats:
        raise ValueError(f"a camada '{layer}' não tem traços do tipo '{feature or 'padrão'}' (sem etiquetas)")
    X = df[feats].to_numpy(dtype=float)
    grp = df["__group"].to_numpy()
    out: dict[str, Any] = {"method": method, "layer": layer, "feature": feature, "metric": metric,
                           "groups": [{"label": k, "n": v} for k, v in sizes.items()],
                           "warnings": _warnings(sizes, method, len(feats), lang)}

    if method == "one_vs_rest":
        rows, matrix = [], {}
        for g in labels:
            a, b = X[grp == g], X[grp != g]
            if len(a) < 2 or len(b) < 2:
                continue
            d = _d(a, b, metric)
            matrix[g] = d
            rows.append({"label": g, "features": _top(feats, d, {"mean_group": a.mean(0), "mean_rest": b.mean(0)}, top)})
        chosen = sorted({f["feature"] for r in rows for f in r["features"]})
        idx = [feats.index(f) for f in chosen]
        out.update(results=rows, heatmap={"features": chosen, "groups": list(matrix),
                                          "d": [[_f(matrix[g][i]) for i in idx] for g in matrix]})

    elif method == "pairwise":
        n = len(labels)
        dist = [[0.0] * n for _ in range(n)]
        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                a, b = X[grp == labels[i]], X[grp == labels[j]]
                if len(a) < 2 or len(b) < 2:
                    dist[i][j] = dist[j][i] = None
                    continue
                d = _d(a, b, metric)
                dist[i][j] = dist[j][i] = _f(np.nanmean(np.abs(d))) if not np.all(np.isnan(d)) else None
                pairs.append({"a": labels[i], "b": labels[j], "mean_abs_d": dist[i][j],
                              "large": int(np.sum(np.abs(np.nan_to_num(d)) >= 0.8)),
                              "features": _top(feats, d, {"mean_a": a.mean(0), "mean_b": b.mean(0)}, top)})
        out.update(labels=labels, distance=dist, pairs=pairs)

    elif method == "anova":
        from scipy.stats import kruskal
        samples = [X[grp == g] for g in labels]
        N = len(X)
        res = []
        for k, f in enumerate(feats):
            cols = [s[:, k] for s in samples if len(s)]
            if len({v for c in cols for v in c}) < 2:
                continue
            h, p = kruskal(*cols)
            res.append({"feature": f, "H": _f(h), "p": float(p), "epsilon2": _f(h / (N - 1)) if N > 1 else None,
                        "means": {g: _f(s[:, k].mean()) for g, s in zip(labels, samples)}})
        if res:
            adj = _adjust(np.array([r["p"] for r in res]), correction)
            for r, pa in zip(res, adj):
                r["p_adj"] = float(pa)
        res.sort(key=lambda r: -(r["epsilon2"] or 0))
        out.update(correction=correction, results=res[:max(top, 1) * 5])

    elif method == "profile":
        from .viz import reduction
        out.update(reduction=reduction(project, [dict(g, label=g.get("label")) for g in groups], layer,
                                       method="pca2d", feature=feature))

    elif method == "dendrogram":
        from scipy.cluster.hierarchy import dendrogram, linkage
        means = np.array([X[grp == g].mean(0) for g in labels])
        sd = X.std(0, ddof=1)
        keep = sd > 0
        Z = (means[:, keep] - X[:, keep].mean(0)) / sd[keep]
        link = linkage(Z, method="ward") if len(labels) > 2 else linkage(Z, method="single")
        dn = dendrogram(link, labels=labels, no_plot=True)
        out.update(labels=labels, order=dn["ivl"], icoord=dn["icoord"], dcoord=dn["dcoord"],
                   linkage=[[_f(v) for v in row] for row in link])

    elif method == "nearest":
        target, refs = labels[0], labels[1:]
        t_mean = X[grp == target].mean(0)
        res = []
        for r in refs:
            R = X[grp == r]
            if len(R) < 2:
                continue
            sd = R.std(0, ddof=1)
            with np.errstate(divide="ignore", invalid="ignore"):
                z = np.where(sd > 0, (t_mean - R.mean(0)) / sd, np.nan)
            dist = np.sqrt(np.nanmean(z ** 2)) if not np.all(np.isnan(z)) else np.nan
            res.append({"label": r, "n": len(R), "distance": _f(dist),
                        "features": [{"feature": f["feature"], "z": f["d"], "value": f["value"], "mean_ref": f["mean_ref"]}
                                     for f in _top(feats, z, {"value": t_mean, "mean_ref": R.mean(0)}, top)]})
        res.sort(key=lambda r: r["distance"] if r["distance"] is not None else math.inf)
        out.update(target=target, results=res)

    if save:
        project.save_analysis("lab", out, name=f"{method}: {' × '.join(labels)} [{layer}]",
                              params={"groups": [dict(g) for g in groups], "layer": layer, "method": method,
                                      "feature": feature, "metric": metric, "correction": correction})
    return out
