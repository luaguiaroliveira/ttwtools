"""Palavras-chave e referência (passo 1.9)."""

from __future__ import annotations

import json
import math

import pytest
from scipy.special import xlogy

import ttwtools
from ttwtools import cli
from ttwtools.corpus import set_document_meta
from ttwtools.keywords import (FreqTable, _adjust, chi2_p, keywords, log_likelihood, log_odds, log_ratio,
                               make_reference_list, pct_diff, read_reference_list)
from collections import Counter


def _ll_independent(a, b, c, d):
    # mesmo LL por outro caminho: soma O·ln(O/E) com xlogy, E pelas proporções de tamanho
    e = [(a + b) * c / (c + d), (a + b) * d / (c + d)]
    return 2 * float(xlogy(a, a / e[0]) + xlogy(b, b / e[1]))


@pytest.mark.parametrize("a,b,c,d", [(100, 50, 10_000, 10_000), (5, 0, 1000, 50_000), (0, 30, 2000, 30_000),
                                     (1234, 5678, 1_000_000, 4_000_000)])
def test_log_likelihood_matches_independent(a, b, c, d):
    assert log_likelihood(a, b, c, d) == pytest.approx(_ll_independent(a, b, c, d))


def test_known_values():
    assert log_likelihood(100, 50, 10_000, 10_000) == pytest.approx(16.99, abs=0.01)      # exemplo clássico
    assert log_ratio(100, 50, 10_000, 10_000) == pytest.approx(1.0)
    assert log_ratio(4, 0, 100, 100) == pytest.approx(math.log2(4 / 0.5))                 # zero → 0,5
    assert pct_diff(100, 50, 10_000, 10_000) == pytest.approx(100.0)
    lo, z = log_odds(100, 50, 10_000, 10_000)
    assert lo == pytest.approx(math.log(100.5 / 9900.5) - math.log(50.5 / 9950.5)) and z > 3
    assert chi2_p(3.841) == pytest.approx(0.05, abs=1e-3) and chi2_p(6.635) == pytest.approx(0.01, abs=1e-3)
    assert _adjust([0.01, 0.04, 0.03], "bonferroni") == pytest.approx([0.03, 0.12, 0.09])
    assert _adjust([0.01, 0.04, 0.03], "fdr") == pytest.approx([0.03, 0.04, 0.04])


@pytest.fixture
def proj(tmp_path):
    with ttwtools.create_project(tmp_path / "p.ttwa") as p:
        # alvo: fala muito de "cat"; referência: "dog"
        for i in range(3):
            p.add_corpus_text("alvo", f"a{i}.txt", "the cat and the cat saw a cat near the house " * 5)
            p.add_corpus_text("ref", f"r{i}.txt", "the dog and the dog saw a bird near the house " * 20)
        for i, g in enumerate(["A", "A", "B"]):
            set_document_meta(p, "alvo", f"a{i}.txt", {"grupo": g})
        yield p


def test_keywords_corpus_vs_corpus(proj):
    r = keywords(proj, "alvo", "ref", min_freq=2)
    top = r["rows"][0]
    assert top["item"] == "cat" and top["direction"] == "+"
    assert (top["freq_target"], top["freq_reference"], r["target_words"], r["reference_words"]) == (45, 0, 165, 660)
    assert top["ll"] == pytest.approx(_ll_independent(45, 0, 165, 660))
    assert top["significant"] and top["range_target"] == 3
    neg = [x for x in r["rows"] if x["direction"] == "-"]
    assert {x["item"] for x in neg} >= {"dog", "bird"}
    assert "the" not in {x["item"] for x in r["rows"] if x["significant"]}          # mesma proporção nos dois
    codes = {w["code"] for w in r["warnings"]}
    assert "small_target" in codes and "language_mismatch" not in codes
    assert proj.list_analyses("keywords")[-1]["params"]["reference"] == "ref"


def test_min_range_and_measure_order(proj):
    proj.add_corpus_text("alvo", "a9.txt", "zebra zebra zebra zebra zebra zebra")
    r = keywords(proj, "alvo", "ref", min_freq=2, min_range=2)
    assert "zebra" not in {x["item"] for x in r["rows"]}                           # só num texto
    r = keywords(proj, "alvo", "ref", min_freq=2, measure="log_ratio")
    pos = [x["log_ratio"] for x in r["rows"] if x["direction"] == "+"]
    assert pos == sorted(pos, reverse=True)


def test_rest_of_groups(proj):
    proj.add_corpus_text("alvo", "a3.txt", "gato gato gato house")
    set_document_meta(proj, "alvo", "a3.txt", {"grupo": "B"})
    r = keywords(proj, "alvo", "rest:grupo", where={"grupo": "B"}, min_freq=2)
    assert r["rows"][0]["item"] == "gato" and r["reference"] == "alvo (demais grupos)"
    with pytest.raises(ValueError, match="rest"):
        keywords(proj, "alvo", "rest:grupo")


def test_reference_list_roundtrip_and_card(proj, tmp_path):
    out = make_reference_list(proj, "ref", tmp_path / "ref.tsv", card={"name": "Ref", "lang": "en", "version": "1.0",
                                                                         "license": "CC BY"})
    table = read_reference_list(out)
    assert table.words == 660 and table.counts["dog"] == 120 and table.docs["dog"] == 3
    assert table.meta["license"] == "CC BY" and table.meta["tool"] == "simple"
    r = keywords(proj, "alvo", out, min_freq=2)
    assert r["rows"][0]["item"] == "cat" and r["reference"] == "Ref 1.0"
    direct = keywords(proj, "alvo", "ref", min_freq=2, save=False)
    assert [x["item"] for x in r["rows"]] == [x["item"] for x in direct["rows"]]


def test_comparability_warnings(proj, spacy_model):
    ttwtools.tag_corpus(proj, "alvo", "spacy")
    other = FreqTable(Counter({"cat": 1, "dog": 50}), None, 100_000, 10,
                      {"name": "outra", "lang": "pt", "tool": "stanza", "tool_version": "1.0"})
    r = keywords(proj, "alvo", other, unit="lemma", layer="spacy", min_freq=1, lang="en")
    codes = {w["code"]: w for w in r["warnings"]}
    assert codes["language_mismatch"]["severity"] == "error" and "'en'" in codes["language_mismatch"]["message"]
    assert "tool_mismatch" in codes and "no_reference_docs" in codes
    same = keywords(proj, "alvo", "alvo", min_freq=1, save=False)
    assert "same_data" in {w["code"] for w in same["warnings"]}


def test_cli_keywords(proj, tmp_path, capsys):
    path = str(proj.path)
    proj._con.commit()
    assert cli.main(["reference-list", path, "--corpus", "ref", "--out", str(tmp_path / "r.tsv"), "--lang", "en"]) == 0
    capsys.readouterr()
    assert cli.main(["keywords", path, "--corpus", "alvo", "--reference", str(tmp_path / "r.tsv"),
                     "--min-freq", "2", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rows"][0]["item"] == "cat"
    assert cli.main(["keywords", path, "--corpus", "alvo", "--reference", "ref", "--min-freq", "2", "--lang", "pt"]) == 0
    assert "Alvo pequeno" in capsys.readouterr().out
