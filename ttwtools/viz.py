"""
viz.py — Dados para os gráficos de comparação (a interface só desenha).

    side = {"corpus": "A", "where": {"grupo": ["x"]}, "label": "A"}
    feature_matrix(proj, [side1, side2], layer="biberplus", features=["VBD", "NN"])
    reduction(proj, [side1, side2], layer="biberplus", method="pca2d")
    heatmap(proj, [side1, side2], layer="biberplus", top=20)

Tudo parte da tabela de atributos por texto (features.feature_table, por 1000 palavras),
sem reetiquetar. Redução: PCA 2D/3D, t-SNE, MDS (scikit-learn) e UMAP (umap-learn,
opcional), sobre os atributos de maior variância, padronizados (z-score).
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from .features import feature_table
from .project import TTWAProject

METHODS = ("pca2d", "pca3d", "tsne", "umap", "mds")
_META = ("filename", "Words", "TTR")


def _f(v) -> float | None:
    v = float(v)
    return None if math.isnan(v) or math.isinf(v) else v


def _tables(project: TTWAProject, sides: list[Mapping], layer: str, feature: str | None) -> list[pd.DataFrame]:
    out = []
    for i, s in enumerate(sides):
        t = feature_table(project, s["corpus"], layer, feature, per1000=True, where=s.get("where"))
        t["__side"] = s.get("label") or f"{s['corpus']} ({i + 1})"      # rótulo de cada lado
        out.append(t)
    return out


def _combined(tables: list[pd.DataFrame]) -> tuple[pd.DataFrame, list[str]]:
    df = pd.concat(tables, ignore_index=True).fillna(0.0)
    feats = [c for c in df.columns if c not in _META and c != "__side"]
    return df, feats


def feature_matrix(project: TTWAProject, sides: list[Mapping], layer: str, features: Iterable[str] | None = None,
                   feature: str | None = None, top: int = 20) -> dict:
    """Valor (por 1000 palavras) de cada atributo em cada texto, com o lado de cada texto.
    Sem `features`, usa os `top` de maior variância."""
    df, feats = _combined(_tables(project, sides, layer, feature))
    chosen = list(features) if features else list(df[feats].var().nlargest(top).index)
    for f in chosen:
        if f not in df.columns:
            df[f] = 0.0
    return {"features": chosen, "sides": [s.get("label") or s["corpus"] for s in sides],
            "rows": [{"filename": r["filename"], "side": r["__side"], "words": int(r["Words"]),
                      "values": {f: _f(r[f]) for f in chosen}} for _, r in df.iterrows()]}


def heatmap(project: TTWAProject, sides: list[Mapping], layer: str, feature: str | None = None, top: int = 20) -> dict:
    """z-score de cada atributo (colunas) em cada texto (linhas), textos agrupados por lado."""
    df, feats = _combined(_tables(project, sides, layer, feature))
    chosen = list(df[feats].var().nlargest(top).index)
    x = df[chosen].astype(float)
    z = (x - x.mean()) / x.std(ddof=0).replace(0, np.nan)
    z = z.fillna(0.0)
    return {"features": chosen, "rows": [{"filename": f, "side": s, "z": [_f(v) for v in zr]}
                                         for f, s, zr in zip(df["filename"], df["__side"], z.values)]}


def reduction(project: TTWAProject, sides: list[Mapping], layer: str, method: str = "pca2d",
              feature: str | None = None, top_features: int = 30, perplexity: float = 30.0,
              n_neighbors: int = 15, min_dist: float = 0.1, metric: str = "euclidean", random_state: int = 42) -> dict:
    """Projeção 2D/3D dos textos. Devolve coords [{filename, side, x, y[, z]}], variância
    explicada (PCA) e cargas dos atributos (PCA 2D)."""
    if method not in METHODS:
        raise ValueError(f"método deve ser um de {METHODS}")
    from sklearn.preprocessing import StandardScaler
    df, feats = _combined(_tables(project, sides, layer, feature))
    if len(df) < 3:
        raise ValueError("são precisos pelo menos 3 textos")
    chosen = list(df[feats].var().nlargest(top_features).index)
    x = StandardScaler().fit_transform(df[chosen].astype(float).values)
    explained = loadings = None
    n = 3 if method == "pca3d" else 2
    if method in ("pca2d", "pca3d"):
        from sklearn.decomposition import PCA
        pca = PCA(n_components=n, random_state=random_state)
        coords = pca.fit_transform(x)
        explained = [_f(v) for v in pca.explained_variance_ratio_]
        if method == "pca2d":
            loadings = [{"feature": f, "pc1": _f(pca.components_[0, i]), "pc2": _f(pca.components_[1, i])}
                        for i, f in enumerate(chosen)]
    elif method == "tsne":
        from sklearn.manifold import TSNE
        coords = TSNE(n_components=2, perplexity=min(perplexity, len(x) - 1), random_state=random_state).fit_transform(x)
    elif method == "umap":
        try:
            import umap
        except ImportError:
            raise ValueError("UMAP precisa do pacote umap-learn: pip install umap-learn") from None
        coords = umap.UMAP(n_components=2, n_neighbors=min(n_neighbors, len(x) - 1), min_dist=min_dist,
                           random_state=random_state).fit_transform(x)
    else:
        from sklearn.manifold import MDS
        from sklearn.metrics import pairwise_distances
        coords = MDS(n_components=2, dissimilarity="precomputed", random_state=random_state,
                     normalized_stress="auto").fit_transform(pairwise_distances(x, metric=metric))
    rows = []
    for i, (fn, side) in enumerate(zip(df["filename"], df["__side"])):
        r = {"filename": fn, "side": side, "x": _f(coords[i, 0]), "y": _f(coords[i, 1])}
        if n == 3:
            r["z"] = _f(coords[i, 2])
        rows.append(r)
    return {"method": method, "features": chosen, "explained_variance": explained, "loadings": loadings, "coords": rows}
