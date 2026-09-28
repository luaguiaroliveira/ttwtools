"""Testes das construções (n-gramas de classes) da Escrita."""
from __future__ import annotations

from collections import Counter

import pytest

from ttwtools.keyness import FreqTable
from ttwtools.constructions import _pattern_items, analyze_patterns, tag_text


def test_pattern_items_ignora_pontuacao():
    rows = [{"word": "The", "upos": "DET"}, {"word": "new", "upos": "ADJ"},
            {"word": "policy", "upos": "NOUN"}, {"word": ".", "upos": "PUNCT"},
            {"word": "works", "upos": "VERB"}]
    items, words = _pattern_items(rows, "upos", 2)
    assert words == 4
    assert items == ["DET ADJ", "ADJ NOUN", "NOUN VERB"]


def test_tag_text_upos_xpos():
    pytest.importorskip("spacy")
    toks = tag_text("The new policy works well.")
    assert any(t["upos"] == "NOUN" for t in toks)
    assert all("word" in t and "upos" in t for t in toks)


def test_analyze_patterns_com_referencia_manual():
    pytest.importorskip("spacy")
    counts = Counter({"DET ADJ NOUN": 50, "NOUN ADP DET": 30, "VERB ADP DET": 20})
    ref = FreqTable(counts, Counter({k: 10 for k in counts}), words=1000, n_docs=10,
                    meta={"name": "ref", "tool": "spacy", "model": "en_core_web_sm", "lang": "en",
                          "unit": "upos", "pattern_n": 3})
    r = analyze_patterns(None, "The new policy depends on the old system.", ref,
                         field="upos", n=3, min_freq=1, correction="none")
    assert r["kind"] == "patterns"
    assert r["rows"]
    assert all(len(row["item"].split()) == 3 for row in r["rows"])
    assert all("p_adj" in row and "z_reference" in row for row in r["rows"])
