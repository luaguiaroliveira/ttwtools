"""Testes dos exemplos com marcas (Escrita)."""
from __future__ import annotations

import pytest

from ttwtools.examples import text_examples


def test_text_examples_word():
    pytest.importorskip("spacy")
    ex = text_examples("The cat sat on the mat.", "cat", kind="word", width=2)
    assert len(ex) == 1
    assert any(t["hit"] and t["w"].lower() == "cat" for t in ex[0]["tokens"])


def test_text_examples_pattern():
    pytest.importorskip("spacy")
    ex = text_examples("The new policy works well.", "DET ADJ NOUN", kind="pattern", field="upos", n=3)
    assert len(ex) >= 1
    hits = [t["cls"] for t in ex[0]["tokens"] if t["hit"]]
    assert hits == ["DET", "ADJ", "NOUN"]
