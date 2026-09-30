"""idquery: consultas por ids (TCL2) devem dar exatamente o resultado do caminho SQL (`tokens`)."""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import pytest

import ttwtools
from ttwtools import idquery, query

V2_FIXTURE = Path(__file__).parent / "data" / "v2_small.ttwa"

SEARCH = ["the", "the*", "*ing", "?he", "/^th/", "/^(un|re)[a-z]+(ed|ing)$/", "lemma=be", "lemma=be&pos=VERB", "pos=NOUN",
          "pos=NN", "tag=NN", "tag=PIN", "upos=VERB&xpos=VBD", "of the", "in the *", "the /^[a-z]+ed$/", "zzzzqq", "Ação",
          "word=the", "lemma=the*", "[ab]*"]


@pytest.fixture(scope="module")
def paired(tmp_path_factory):
    """(resultados do SQL, função que roda as mesmas chamadas depois de empacotar em TCL2)."""
    tmp = tmp_path_factory.mktemp("idq")
    dest = tmp / "v2.ttwa"
    shutil.copy(V2_FIXTURE, dest)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = ttwtools.open_project(dest)
    corpus = p.list_corpus_names()[0]
    tools = sorted({l["tool"] for l in p.list_layers()})
    calls = []
    for layer in [None] + tools:
        for q in SEARCH:
            calls.append(("search", (p_ := None), dict(corpus=corpus, query=q, layer=layer)))
            for sort in ("position", "left", "right"):
                calls.append(("kwic", None, dict(corpus=corpus, query=q, layer=layer, sort=sort, limit=7, offset=2, context=3)))
        for unit in ("form", "lemma", "pos", "word_pos", "ngram"):
            for by in ("corpus", "document"):
                calls.append(("frequency", None, dict(corpus=corpus, unit=unit, n=2, by=by, layer=layer, top=15)))
        calls.append(("frequency", None, dict(corpus=corpus, unit="ngram", n=3, layer=layer, top=None, words_only=False)))
        calls.append(("frequency", None, dict(corpus=corpus, unit="form", layer=layer, top=20, stop=["the", "of"])))
        for node in ("the", "lemma=be", "of the", "pos=NOUN", "th*", "/^(the|a)$/"):
            for unit in ("form", "lemma", "pos", "word_pos"):
                calls.append(("collocates", None, dict(corpus=corpus, node=node, unit=unit, layer=layer, min_freq=1, top=40)))
        for node in ("the", "lemma=be", "of the"):
            for coll in ("of", "to", "a", "be"):
                calls.append(("collocate_examples", None, dict(corpus=corpus, node=node, collocate=coll, layer=layer, limit=6, offset=1)))
    def run(proj):
        out = []
        for kind, _, kw in calls:
            kw = dict(kw)
            corpus = kw.pop("corpus")
            fn = getattr(query, kind)
            try:
                out.append(fn(proj, corpus, **kw))
            except Exception as e:  # noqa: BLE001
                out.append(("ERR", type(e).__name__))
        return out
    sql = run(p)
    p.pack_search_tables()
    p._con.commit()
    yield calls, sql, run, p
    p.close()


def test_ids_path_is_used_and_matches_sql(paired, monkeypatch):
    calls, sql, run, p = paired
    used = {"n": 0}
    orig = idquery.available

    def spy(project, sel):
        r = orig(project, sel)
        used["n"] += r is not None
        return r
    monkeypatch.setattr(idquery, "available", spy)
    ids = run(p)
    assert used["n"] > len(calls) // 2                       # o caminho por ids foi de fato usado
    bad = [(c[0], c[2], a, b) for c, a, b in zip(calls, sql, ids) if a != b]
    assert not bad, bad[:3]


def test_ids_path_off_switch(paired, monkeypatch):
    calls, sql, run, p = paired
    monkeypatch.setenv("TTWTOOLS_ID_QUERIES", "0")
    assert idquery.available(p, {1: {"corpus_name": "x"}}) is None


def test_collocate_examples_match_the_collocates_table(tmp_path):
    """Os exemplos de um colocado somam exatamente a frequência que a tabela de colocados mostra."""
    dest = tmp_path / "v2.ttwa"
    shutil.copy(V2_FIXTURE, dest)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = ttwtools.open_project(dest)
    corpus = p.list_corpus_names()[0]
    tab = query.collocates(p, corpus, "the", (5, 5), "form", "spacy", None, 1, 30)
    assert tab["rows"]
    for r in tab["rows"][:8]:
        ex = query.collocate_examples(p, corpus, "the", r["collocate"], (5, 5), "form", "spacy", None, limit=100000)
        n_hits = sum(c["hit"] for l in ex["lines"] for c in l["left"] + l["right"])
        assert not ex["capped"] and ex["total"] == len(ex["lines"]) and n_hits == r["freq"], (r["collocate"], n_hits, r["freq"])
        assert all(l["node"] and all(c["w"].lower() == "the" for c in l["node"]) for l in ex["lines"])
        assert all(c["hit"] is False or c["w"].lower() == r["collocate"] for l in ex["lines"] for c in l["left"] + l["right"])
    p.close()
