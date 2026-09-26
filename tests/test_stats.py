"""Estatísticas descritivas com valores calculados à mão (passo 1.7)."""

from __future__ import annotations

import json
import math

import pytest

import ttwtools
from ttwtools import cli
from ttwtools.stats import cttr, describe, mattr, stopwords, sttr, ttr

# a.txt: "The cat saw the dog. The dog ran!"  → the cat saw the dog the dog ran (8 palavras)
#        types {the, cat, saw, dog, ran} = 5; frases 2
# b.txt: "A cat, 2 cats." → a cat cats (número fora) = 3 palavras, 3 types; 1 frase
TEXTS = {"a.txt": "The cat saw the dog. The dog ran!", "b.txt": "A cat, 2 cats."}


@pytest.fixture
def proj(tmp_path):
    with ttwtools.create_project(tmp_path / "p.ttwa") as p:
        for name, text in TEXTS.items():
            p.add_corpus_text("c", name, text)
        yield p


def test_measures_by_hand():
    words = "the cat saw the dog the dog ran".split()
    assert ttr(words) == 5 / 8
    assert cttr(words) == pytest.approx(5 / math.sqrt(16))
    assert sttr([words], 4) == pytest.approx(((3 / 4) + (3 / 4)) / 2)   # the cat saw the | dog the dog ran
    assert sttr([words], 10) is None
    # janelas de 4: [the cat saw the]=3 [cat saw the dog]=4 [saw the dog the]=3 [the dog the dog]=2 [dog the dog ran]=3
    assert mattr([words], 4) == pytest.approx((3 + 4 + 3 + 2 + 3) / 4 / 5)


def test_describe_text(proj):
    r = describe(proj, "c", sttr_block=4, mattr_window=4, top=3)
    t = r["text"]
    assert r["cached"] is False and t["estimated"] is True
    assert (t["documents"], t["tokens"], t["types"]) == (2, 11, 7)      # the cat saw dog ran a cats
    assert t["hapax"] == 4                                               # saw ran a cats
    assert t["ttr"] == pytest.approx(7 / 11)
    assert t["sentences"] == 3 and t["mean_sentence_length"] == pytest.approx(11 / 3)
    assert t["mean_word_length"] == pytest.approx(sum(map(len, "the cat saw the dog the dog ran a cat cats".split())) / 11)
    assert t["document_tokens"] == {"min": 3, "median": 5.5, "max": 8, "mean": 5.5, "stdev": pytest.approx(math.sqrt(12.5))}
    assert t["top_words"] == [{"word": "the", "freq": 3}, {"word": "cat", "freq": 2}, {"word": "dog", "freq": 2}]
    assert t["zipf"][:3] == [3, 2, 2]
    assert t["sttr"] == pytest.approx(3 / 4)                             # só a.txt tem blocos de 4: 3/4 e 3/4


def test_second_call_comes_from_cache_until_text_changes(proj):
    first = describe(proj, "c")
    second = describe(proj, "c")
    assert second["cached"] is True and second["text"] == first["text"]
    proj.add_corpus_text("c", "b.txt", "Completely different words now.")
    assert describe(proj, "c")["cached"] is False
    assert describe(proj, "c", top=5)["cached"] is False                 # parâmetro diferente


def test_hide_stopwords(proj):
    r = describe(proj, "c", hide_stopwords=True, top=10)
    words = [w["word"] for w in r["text"]["top_words"]]
    assert "the" not in words and "a" not in words and words[0] in ("cat", "dog")
    assert r["text"]["tokens"] == 11                                    # contagens não mudam
    assert "cat" in stopwords("en", add=["cat"]) and stopwords("en", replace=["x"]) == {"x"}
    with pytest.raises(ValueError):
        stopwords("xx")
    assert "que" in stopwords("pt")


def test_describe_layer(proj, spacy_model):
    ttwtools.tag_corpus(proj, "c", "spacy")
    r = describe(proj, "c", layer="spacy")
    lay = r["layer"]
    assert lay["upos"]["NOUN"] >= 4 and lay["upos"]["PUNCT"] >= 4
    # palavras (sem PUNCT/SYM): a.txt 8, b.txt "A cat 2 cats" = 4
    assert lay["words"] == 12
    assert lay["lexical_density"] == pytest.approx(
        sum(v for k, v in lay["upos"].items() if k in {"NOUN", "PROPN", "VERB", "ADJ", "ADV"}) / 12)
    assert lay["sentences"] == 3
    assert {"lemma": "cat", "freq": 3} in lay["top_lemmas"]["NOUN"]
    assert any(f["feature"] == "UPOS:NOUN" for f in lay["per_document"])
    assert describe(proj, "c", layer="spacy")["cached"] is True
    assert ttwtools.tag_corpus(proj, "c", "spacy", {"components": ["pos"]})["reused"] == 2   # atendido: cache vale
    assert describe(proj, "c", layer="spacy")["cached"] is True
    ttwtools.tag_corpus(proj, "c", "spacy", force=True)                  # camada refeita → recalcula
    assert describe(proj, "c", layer="spacy")["cached"] is False


def test_cli_describe(tmp_path, capsys):
    folder = tmp_path / "txt"
    folder.mkdir()
    for name, text in TEXTS.items():
        (folder / name).write_text(text, encoding="utf-8")
    assert cli.main(["describe", str(folder), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["text"]["tokens"] == 11
    assert cli.main(["describe", str(folder)]) == 0
    assert "estimativas" in capsys.readouterr().out
