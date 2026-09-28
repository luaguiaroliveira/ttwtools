"""Testes do perfil de colocação da Escrita."""
from __future__ import annotations

import ttwtools

from ttwtools.collocations import collocate_profile, text_collocates


def test_text_collocates_janela():
    r = text_collocates("the cat sat on the mat", "cat", window=(2, 2))
    assert r["node_freq"] == 1
    assert r["observed"]["the"] == 1
    assert r["observed"]["sat"] == 1
    assert "mat" not in r["observed"]        # fora da janela de 2


def test_text_collocates_expressao():
    r = text_collocates("a strong argument for the case", "strong argument", window=(1, 1))
    assert r["node_freq"] == 1
    assert r["observed"]["a"] == 1 and r["observed"]["for"] == 1


def test_collocate_profile(tmp_path):
    with ttwtools.create_project(tmp_path / "p.ttwa") as p:
        p.add_corpus_text("ref", "a.txt", "the strong argument and the strong claim " * 10)
        r = collocate_profile(p, "a strong argument", "strong", "ref", min_freq=1, top=10)
    assert r["kind"] == "collocations"
    assert r["node_freq_text"] == 1
    itens = {row["collocate"]: row for row in r["rows"]}
    assert "argument" in itens
    assert itens["argument"]["freq_text"] == 1
    assert "log_ratio" in itens["argument"]
