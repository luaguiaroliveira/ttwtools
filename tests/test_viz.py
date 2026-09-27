"""Dados dos gráficos de comparação (galeria da KFA)."""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import pytest

import ttwtools
from ttwtools.viz import feature_matrix, heatmap, reduction

V2 = Path(__file__).parent / "data" / "v2_small.ttwa"
SIDES = [{"corpus": "CorIFAessaysNE_5", "label": "CorIFA"}, {"corpus": "essays_bawe_somentetexto_5", "label": "BAWE"}]


@pytest.fixture
def proj(tmp_path):
    shutil.copy(V2, tmp_path / "v.ttwa")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = ttwtools.open_project(tmp_path / "v.ttwa")
    yield p
    p.close()


def test_feature_matrix(proj):
    m = feature_matrix(proj, SIDES, "mfte", top=5)
    assert len(m["features"]) == 5 and len(m["rows"]) == 10
    assert {r["side"] for r in m["rows"]} == {"CorIFA", "BAWE"}
    assert set(m["rows"][0]["values"]) == set(m["features"])
    assert feature_matrix(proj, SIDES, "mfte", features=["NN", "nao_existe"])["rows"][0]["values"]["nao_existe"] == 0.0


def test_heatmap_zscores(proj):
    h = heatmap(proj, SIDES, "spacy", top=6)
    import numpy as np
    col = np.array([r["z"][0] for r in h["rows"]])
    assert len(h["features"]) == 6 and abs(col.mean()) < 1e-9


@pytest.mark.parametrize("method", ["pca2d", "pca3d", "tsne", "mds"])
def test_reduction(proj, method):
    r = reduction(proj, SIDES, "mfte", method=method, perplexity=3)
    assert len(r["coords"]) == 10 and all(c["x"] is not None for c in r["coords"])
    assert ("z" in r["coords"][0]) == (method == "pca3d")
    if method == "pca2d":
        assert r["loadings"] and 0 < sum(r["explained_variance"]) <= 1


def test_groups_same_corpus(proj):
    from ttwtools.corpus import set_document_meta
    for i, f in enumerate(proj.list_corpus_files("CorIFAessaysNE_5")):
        set_document_meta(proj, "CorIFAessaysNE_5", f, {"g": "A" if i < 3 else "B"})
    sides = [{"corpus": "CorIFAessaysNE_5", "where": {"g": "A"}, "label": "A"},
             {"corpus": "CorIFAessaysNE_5", "where": {"g": "B"}, "label": "B"}]
    assert {c["side"] for c in reduction(proj, sides, "spacy")["coords"]} == {"A", "B"}
    with pytest.raises(ValueError):
        reduction(proj, SIDES, "mfte", method="nada")
