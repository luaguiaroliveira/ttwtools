"""Português (passo 5.3): modelos, idioma do corpus, palavras funcionais e fluxo completo."""

from __future__ import annotations

import pytest

import ttwtools
from ttwtools.formats import parse_conllu
from ttwtools.stats import guess_language, stopwords
from ttwtools.taggers import language_defaults, validate_options

PT = {"a.txt": "Os meninos não foram à escola ontem, mas estudaram muito em casa. A casa é grande.",
      "b.txt": "As meninas foram ao parque. Elas correram e brincaram no parque durante a tarde."}


def test_language_defaults():
    assert language_defaults("spacy", "pt")["model"].startswith("pt_core_news_")
    assert language_defaults("spacy", "pt", {"model": "en_core_web_md"}) == {"model": "pt_core_news_md"}
    assert language_defaults("spacy", "pt", {"model": "en_core_web_trf"}) == {"model": "pt_core_news_lg"}
    assert language_defaults("stanza", "pt") == {"lang": "pt"}
    assert language_defaults("spacy", "en") == {} and language_defaults("spacy", None) == {}
    assert language_defaults("biberplus", "pt") == {}          # só inglês


def test_stanza_package_by_language():
    validate_options("stanza", {"lang": "pt", "package": "bosque"})
    with pytest.raises(ValueError, match="idioma 'pt'"):
        validate_options("stanza", {"lang": "pt", "package": "gum"})
    with pytest.raises(ValueError, match="idioma 'en'"):
        validate_options("stanza", {"package": "bosque"})


def test_guess_language_and_stopwords(tmp_path):
    with ttwtools.create_project(tmp_path / "p.ttwa") as p:
        for name, text in PT.items():
            p.add_corpus_text("pt", name, text)
        p.add_corpus_text("en", "e.txt", "The boys did not go to school, but they studied at home.")
        assert guess_language(p, "pt") == "pt" and guess_language(p, "en") == "en"
        top = [w["word"] for w in ttwtools.describe(p, "pt", hide_stopwords=True)["text"]["top_words"]]
    assert "não" not in top and "foram" not in top and "parque" in top
    assert {"não", "foram", "está"} <= stopwords("pt")


def test_conllu_newdoc_id_underscore(tmp_path):
    f = tmp_path / "b.conllu"
    f.write_text("# newdoc_id = CF1\n# text = Olá.\n1\tOlá\tolá\tINTJ\t_\t_\t0\troot\t_\tSpaceAfter=No\n"
                 "2\t.\t.\tPUNCT\t_\t_\t1\tpunct\t_\t_\n\n# newdoc_id = CP2\n# text = Sim\n1\tSim\tsim\tADV\t_\t_\t0\troot\t_\t_\n\n")
    assert [d["id"] for d in parse_conllu(f)] == ["CF1", "CP2"]


def test_fluxo_completo_em_portugues(tmp_path):
    spacy = pytest.importorskip("spacy")
    from ttwtools import models
    models.activate()
    try:
        spacy.load("pt_core_news_sm")
    except OSError:
        pytest.skip("modelo pt_core_news_sm não instalado (ttwtools catalog download-model pt_core_news_sm)")
    with ttwtools.create_project(tmp_path / "pt.ttwa") as p:
        for name, text in PT.items():
            p.add_corpus_text("pt", name, text)
        r = ttwtools.tag_corpus(p, "pt", "spacy", options=language_defaults("spacy", guess_language(p, "pt")))
        assert r["tagged"] == 2
        assert ttwtools.search(p, "pt", "lemma=menino")["total"] == 1
        assert ttwtools.search(p, "pt", "pos=NOUN")["total"] >= 5
        assert ttwtools.kwic(p, "pt", "lemma=parque")["total"] == 2
