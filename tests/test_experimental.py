"""Laboratório: comparar N grupos (passo 5.1)."""

from __future__ import annotations

import json

import pytest

import ttwtools
from ttwtools import cli
from ttwtools import experimental as ex

TEXTS = {
    "a": "The cat sat on the mat. The dog ran to the park. A bird sang in the tree.",
    "b": "She quickly and quietly walked home. He slowly and carefully read. They happily sang.",
    "c": "Run! Stop! Go now! Why? Because I said so! Wait here! Look there!",
}


@pytest.fixture
def proj(tmp_path, spacy_model):
    path = tmp_path / "g.ttwa"
    with ttwtools.create_project(path) as p:
        for g, text in TEXTS.items():
            for i in range(6):
                p.add_corpus_text("c", f"{g}_{i}.txt", " ".join([text] * (i + 2)) + f" Extra{i} word{i}.")
        ttwtools.corpus.apply_metadata(p, "c", {f"{g}_{i}.txt": {"grupo": g} for g in TEXTS for i in range(6)})
        ttwtools.tag_corpus(p, "c", "spacy", options={"model": "en_core_web_sm"})
    return path


def test_groups_by_metadata(proj):
    with ttwtools.open_project(proj) as p:
        groups = ex.groups_by_metadata(p, "c", "grupo")
    assert [g["label"] for g in groups] == ["a", "b", "c"] and groups[0]["where"] == {"grupo": ["a"]}


@pytest.mark.parametrize("method", ex.METHODS)
def test_every_method_runs(proj, method):
    with ttwtools.open_project(proj) as p:
        r = ex.compare_groups(p, ex.groups_by_metadata(p, "c", "grupo"), "spacy", method=method, feature="upos")
        assert p.list_analyses()[-1]["type"] == "lab"
    assert r["method"] == method and [g["n"] for g in r["groups"]] == [6, 6, 6]
    assert r["warnings"][0]["code"] == "experimental"
    json.dumps(r)                                   # tudo serializável (sem NaN do numpy)
    if method == "one_vs_rest":
        assert len(r["results"]) == 3 and r["heatmap"]["features"]
    if method == "pairwise":
        assert r["distance"][0][0] == 0.0 and r["distance"][0][1] == r["distance"][1][0] > 0
    if method == "anova":
        assert all(0 <= x["p_adj"] <= 1 for x in r["results"])
    if method == "dendrogram":
        assert sorted(r["order"]) == ["a", "b", "c"]
    if method == "nearest":
        assert r["target"] == "a" and {x["label"] for x in r["results"]} == {"b", "c"}


def test_warnings_and_errors(proj):
    with ttwtools.open_project(proj) as p:
        small = [{"corpus": "c", "where": {"grupo": ["a"]}, "label": "a"},
                 {"corpus": "c", "where": {"grupo": ["b", "c"]}, "label": "bc"}]
        r = ex.compare_groups(p, small, "spacy", save=False, lang="en")
        assert "unequal" not in {w["code"] for w in r["warnings"]}
        with pytest.raises(ValueError, match="2 grupos"):
            ex.compare_groups(p, small[:1], "spacy")
        with pytest.raises(ValueError, match="atributos"):
            ex.compare_groups(p, small, "spacy", feature="tags")
        with pytest.raises(ValueError, match="rótulos"):
            ex.compare_groups(p, [small[0], small[0]], "spacy")


def test_cli_group_by(proj, capsys):
    assert cli.main(["compare", str(proj), "--corpus", "c", "--layer", "spacy", "--feature", "upos",
                     "--group-by", "grupo", "--method", "pairwise", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["pairs"]) == 3
    assert cli.main(["compare", str(proj), "--corpus", "c", "--layer", "spacy", "--group", "x=c:grupo=a",
                     "--group", "c:grupo=b,c", "--method", "nearest", "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["target"] == "x" and r["results"][0]["label"] == "c:grupo=b,c"
