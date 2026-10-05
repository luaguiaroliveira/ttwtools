"""Busca, KWIC, frequência, colocados e dispersão (passo 1.8)."""

from __future__ import annotations

import csv
import io
import json
import math

import pytest

import ttwtools
from ttwtools import cli
from ttwtools.corpus import set_document_meta
from ttwtools.query import collocates, dispersion, explain, frequency, kwic, search, tag_counts

TEXTS = {
    "a.txt": "The black cat sat on the mat. The cat slept.",       # 12 tokens, 10 palavras
    "b.txt": "A dog chased the black cat.",                        # 7 tokens, 6 palavras
    "c.txt": "Dogs bark. Dogs run.",                               # 6 tokens, 4 palavras
}


@pytest.fixture
def proj(tmp_path):
    with ttwtools.create_project(tmp_path / "p.ttwa") as p:
        for name, text in TEXTS.items():
            p.add_corpus_text("c", name, text)
        set_document_meta(p, "c", "a.txt", {"grupo": "A"})
        set_document_meta(p, "c", "b.txt", {"grupo": "B"})
        set_document_meta(p, "c", "c.txt", {"grupo": "B"})
        yield p


def test_search_without_tagger_creates_simple_layer(proj):
    r = search(proj, "c", "cat")
    assert r["total"] == 3 and r["documents"] == 2
    assert {l["tool"] for l in proj.list_layers("c")} == {"simple"}
    assert search(proj, "c", "CAT")["total"] == 3                      # sem distinguir maiúsculas
    assert search(proj, "c", "black cat")["total"] == 2               # frase
    assert search(proj, "c", "dog*")["total"] == 3                    # prefixo: dog, dogs, dogs
    assert search(proj, "c", "/^d.gs?$/")["total"] == 3               # regex
    assert search(proj, "c", "*at")["total"] == 5                     # cat×3, sat, mat
    g = search(proj, "c", "cat", group_by="grupo")
    assert g["per_group"] == [{"group": "A", "freq": 2}, {"group": "B", "freq": 1}]
    assert search(proj, "c", "cat", where={"grupo": "B"})["total"] == 1


def test_index_is_used(proj):
    plan = " | ".join(explain(proj, "c", "cat"))
    assert "idx_tokens_lword" in plan
    assert "idx_tokens_lword" in " | ".join(explain(proj, "c", "ca*"))


def test_kwic_pagination_and_sort(proj):
    r = kwic(proj, "c", "cat", context=2)
    assert r["total"] == 3
    first = r["lines"][0]
    assert (first["filename"], first["left"], first["match"], first["right"]) == ("a.txt", "The black", "cat", "sat on")
    assert first["sentence"] == "The black cat sat on the mat."
    assert proj.get_corpus_file("c", "a.txt")[first["start_char"]:first["end_char"]] == "cat"
    page2 = kwic(proj, "c", "cat", limit=1, offset=1)
    assert page2["total"] == 3 and len(page2["lines"]) == 1 and page2["lines"][0]["idx"] == r["lines"][1]["idx"]
    by_right = [l["right"].split()[0] for l in kwic(proj, "c", "cat", sort="right", context=1)["lines"]]
    assert by_right == sorted(by_right, key=str.lower)                # . sat slept


def test_kwic_cli_matches_function(proj, capsys):
    path = str(proj.path)
    expected = kwic(proj, "c", "the", limit=2, offset=1, context=3)
    proj._con.commit()
    assert cli.main(["kwic", path, "the", "--corpus", "c", "--limit", "2", "--offset", "1", "--context", "3", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == expected


def test_frequency_units(proj):
    r = frequency(proj, "c", "form")
    top = {row["item"]: row["freq"] for row in r["rows"]}
    assert top["the"] == 4 and top["cat"] == 3 and "." not in top
    assert r["sizes"] == {"corpus": 20}
    bigrams = {r["item"]: r for r in frequency(proj, "c", "ngram", n=2, top=None)["rows"]}
    assert bigrams["black cat"]["freq"] == 2 and bigrams["the black"]["freq"] == 2
    assert bigrams["black cat"]["per_1000"] == pytest.approx(2000 / 20)
    by_doc = frequency(proj, "c", "form", by="document", top=1)["rows"]
    assert {r["group"] for r in by_doc} == {"a.txt", "b.txt", "c.txt"}
    by_group = {(r["group"], r["item"]): r["freq"] for r in frequency(proj, "c", "form", by="grupo", top=None)["rows"]}
    assert by_group[("B", "dogs")] == 2 and by_group[("A", "cat")] == 2
    no_stop = frequency(proj, "c", "form", stop=["the", "a", "on"])["rows"]
    assert no_stop[0]["item"] == "cat"


def test_frequency_with_tagger_layer(proj, spacy_model):
    ttwtools.tag_corpus(proj, "c", "spacy")
    lemmas = {r["item"]: r["freq"] for r in frequency(proj, "c", "lemma", layer="spacy", top=None)["rows"]}
    assert lemmas["cat"] == 3 and lemmas["dog"] >= 2      # "Dogs" no início pode virar PROPN
    pos = {r["item"]: r["freq"] for r in frequency(proj, "c", "pos", layer="spacy", top=None)["rows"]}
    assert pos["NOUN"] >= 6
    assert search(proj, "c", "lemma=dog&pos=NOUN", layer="spacy")["total"] == lemmas["dog"]
    wp = {r["item"] for r in frequency(proj, "c", "word_pos", layer="spacy", top=None)["rows"]}
    assert "cat/NOUN" in wp


def test_collocates_by_hand(proj):
    # nó "cat", janela 1E/1D, só palavras: a: black[cat]sat, the[cat]slept · b: black[cat](fim)
    r = collocates(proj, "c", "cat", window=(1, 1), min_freq=1, sort="freq")
    rows = {x["collocate"]: x for x in r["rows"]}
    assert r["node_freq"] == 3 and r["corpus_words"] == 20
    assert rows["black"]["freq"] == 2 and rows["black"]["position"] == "L"
    assert rows["sat"]["freq"] == 1 and rows["sat"]["position"] == "R"
    e = 3 * 2 * 2 / 20                                                # f(nó) × f(black) × span / N
    assert rows["black"]["expected"] == pytest.approx(e)
    assert rows["black"]["mi"] == pytest.approx(math.log2(2 / e))
    assert rows["black"]["t_score"] == pytest.approx((2 - e) / math.sqrt(2))
    assert rows["black"]["ll"] > 0
    assert collocates(proj, "c", "cat", window=(1, 1))["rows"][0]["collocate"] == "black"   # min_freq=2


def test_dispersion_dp_by_hand(proj):
    r = dispersion(proj, "c", "cat")
    # tamanhos (tokens): a 12, b 7, c 6 → e = 12/25, 7/25, 6/25; o = 2/3, 1/3, 0
    e = [12 / 25, 7 / 25, 6 / 25]
    o = [2 / 3, 1 / 3, 0]
    dp = 0.5 * sum(abs(oi - ei) for oi, ei in zip(o, e))
    assert (r["freq"], r["range"], r["documents"]) == (3, 2, 3)
    assert r["dp"] == pytest.approx(dp) and r["dp_norm"] == pytest.approx(dp / (1 - 6 / 25))
    a = next(d for d in r["per_document"] if d["filename"] == "a.txt")
    assert a["positions"] == [pytest.approx(2 / 12), pytest.approx(9 / 12)]


def test_tag_counts_upos_matches_frequency(proj, spacy_model, capsys):
    ttwtools.tag_corpus(proj, "c", "spacy")
    pos = {r["item"]: r["freq"] for r in frequency(proj, "c", "pos", layer="spacy", top=None)["rows"]}
    r = tag_counts(proj, "c", "spacy", "upos")
    assert r["counts"] == pos and r["documents"] == 3
    with pytest.raises(ValueError):
        tag_counts(proj, "c", "spacy", "nada")
    proj._con.commit()
    assert cli.main(["tag-counts", str(proj.path), "--corpus", "c", "--layer", "spacy", "--field", "upos", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"] == pos


def test_kwic_layer_with_only_tags_shows_first_tag(proj):
    ttwtools.tag_corpus(proj, "c", "biberplus")
    lines = ttwtools.kwic(proj, "c", "cat", layer="biberplus")["lines"]
    assert lines and all(l["pos"] for l in lines)     # sem upos/xpos: cai para a primeira tag


def test_tag_query_falls_back_to_upos_xpos_without_tags(proj, spacy_model):
    ttwtools.tag_corpus(proj, "c", "spacy")
    noun = search(proj, "c", "pos=NOUN", layer="spacy")["total"]
    assert noun > 0 and search(proj, "c", "tag=NOUN", layer="spacy")["total"] == noun
    ttwtools.tag_corpus(proj, "c", "biberplus")
    assert search(proj, "c", "tag=NOUN", layer="biberplus")["total"] == 0        # BiberPlus tem tags próprias: sem cair para UPOS


def test_query_alternatives_or(proj):
    # `|` = ou, no mesmo campo: forma, curinga e regex (o `|` do regex não é separador)
    assert search(proj, "c", "cat|dog*")["total"] == 6        # cat×3 + (dog, Dogs×2)
    assert search(proj, "c", "cat|dog")["total"] == 4         # dog exato = 1
    assert search(proj, "c", "word=cat|mat")["total"] == 4    # cat×3 + mat
    assert search(proj, "c", "/^d.gs?$/")["total"] == 3       # regex inteira


def test_query_alternatives_with_tagger(proj, spacy_model):
    ttwtools.tag_corpus(proj, "c", "spacy")
    noun = search(proj, "c", "pos=NOUN", layer="spacy")["total"]
    verb = search(proj, "c", "pos=VERB", layer="spacy")["total"]
    both = search(proj, "c", "pos=NOUN|VERB", layer="spacy")["total"]
    assert both == noun + verb
    assert search(proj, "c", "tag=NOUN|VERB", layer="spacy")["total"] == both
    assert search(proj, "c", "cat&pos=NOUN|VERB", layer="spacy")["total"] == search(proj, "c", "cat&pos=NOUN", layer="spacy")["total"]


def test_cli_other_commands(proj, capsys):
    path = str(proj.path)
    proj._con.commit()
    assert cli.main(["search", path, "cat", "--corpus", "c", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 3
    assert cli.main(["freq", path, "--corpus", "c", "--top", "2", "--csv"]) == 0
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert rows[0]["item"] == "the" and rows[0]["freq"] == "4"
    assert cli.main(["collocates", path, "cat", "--corpus", "c", "--left", "1", "--right", "1", "--min-freq", "1"]) == 0
    assert "black" in capsys.readouterr().out
    assert cli.main(["dispersion", path, "dog*", "--corpus", "c"]) == 0
    assert "range 2/3" in capsys.readouterr().out


def test_read_document(proj):
    from ttwtools.query import read_document
    d = read_document(proj, "c", "a.txt")
    assert d["text"] == TEXTS["a.txt"] and d["layer"] is None and d["tokens"] == []
    search(proj, "c", "cat")                                    # cria a camada simple
    d = read_document(proj, "c", "a.txt")
    assert d["layer"]["tool"] == "simple" and d["tokens"][2]["word"] == "cat"
    assert d["text"][d["tokens"][2]["start_char"]:d["tokens"][2]["end_char"]] == "cat"
    with pytest.raises(KeyError):
        read_document(proj, "c", "nao.txt")


def test_default_layer_has_needed_field(tmp_path, spacy_model):
    """Sem `layer`, `lemma=`/`pos=` usam a camada mais recente QUE TENHA o campo (não uma sem lema)."""
    import ttwtools
    with ttwtools.create_project(tmp_path / "l.ttwa") as p:
        p.add_corpus_text("c", "a.txt", "They make things. She made a cake and makes tea.")
        ttwtools.tag_corpus(p, "c", "spacy", options={"model": "en_core_web_sm"})
        ttwtools.tag_corpus(p, "c", "simple", force=True)       # camada mais recente, sem lema nem classe
        assert ttwtools.search(p, "c", "lemma=make")["total"] == 3
        assert ttwtools.search(p, "c", "pos=VERB")["total"] >= 3
        assert ttwtools.frequency(p, "c", unit="lemma")["rows"][0]["item"] in ("make", ".")
        assert ttwtools.search(p, "c", "make")["total"] == 1      # forma: vale a camada mais recente
