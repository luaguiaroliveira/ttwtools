"""Formatos: CoNLL-U (ida e volta), VRT, palavra/TAG (Brown) e tabelas de tokens."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import ttwtools
from ttwtools import cli
from ttwtools.formats import (export_conllu, export_tokens, export_vrt, import_conllu, import_nltk_tagged,
                              parse_conllu, parse_nltk_tagged)

SAMPLE = Path(__file__).parent / "data" / "sample.conllu"


def _token_lines(text: str) -> list[list[str]]:
    """Linhas de token (sem nós vazios), com as 10 colunas."""
    return [l.split("\t") for l in text.splitlines() if l and not l.startswith("#") and "." not in l.split("\t")[0]]


@pytest.fixture
def proj(tmp_path):
    with ttwtools.create_project(tmp_path / "p.ttwa") as p:
        yield p


def test_parse_conllu_text_and_offsets():
    docs = parse_conllu(SAMPLE)
    assert [d["id"] for d in docs] == ["doc1", "doc2"]
    d1 = docs[0]
    assert d1["text"] == "I don't like cats. Sue went, and so did Bob."
    assert docs[1]["text"] == "Hello!"
    for t in d1["tokens"]:
        surface = d1["text"][t["start_char"]:t["end_char"]]
        assert surface == (t["mwt"]["form"] if "mwt" in t else t["word"])
    do, nt = d1["tokens"][1], d1["tokens"][2]
    assert (do["word"], nt["word"], do["start_char"], nt["end_char"]) == ("do", "n't", 2, 7)
    assert len(d1["tokens"]) == 14              # nó vazio 6.1 ignorado
    assert d1["tokens"][4]["feats"] == "Number=Plur" and d1["tokens"][4]["lemma"] == "cat"


def test_conllu_roundtrip_keeps_all_columns(proj, tmp_path):
    report = import_conllu(proj, SAMPLE, "ud")
    assert report["imported"] == 2 and report["tokens"] == 16
    assert proj.get_corpus_file("ud", "doc1.txt") == "I don't like cats. Sue went, and so did Bob."
    [layer] = proj.list_layers("ud", tool="conllu")[:1]
    assert layer["n_tokens"] in (14, 2)
    out = tmp_path / "volta.conllu"
    export_conllu(proj, "ud", out, tool="conllu")
    original, back = SAMPLE.read_text(), out.read_text()
    assert _token_lines(back) == _token_lines(original)
    texts = lambda s: [l for l in s.splitlines() if l.startswith("# text")]
    assert texts(back)[:2] == texts(original)[:2]


def test_conllu_from_tagger_layer(proj, tmp_path, spacy_model):
    proj.add_corpus_text("c", "a.txt", "The cats sat. They left!")
    ttwtools.tag_corpus(proj, "c", "spacy")
    out = tmp_path / "spacy.conllu"
    export_conllu(proj, "c", out, tool="spacy")
    text = out.read_text()
    assert text.count("# sent_id") == 2 and "# text = The cats sat." in text
    cats = next(l for l in _token_lines(text) if l[1] == "cats")
    assert cats[2:5] == ["cat", "NOUN", "NNS"] and cats[6] == "_"
    sat = next(l for l in _token_lines(text) if l[1] == "sat")
    assert sat[9] == "SpaceAfter=No"


def test_vrt(proj, tmp_path):
    import_conllu(proj, SAMPLE, "ud")
    from ttwtools.corpus import set_document_meta
    set_document_meta(proj, "ud", "doc1.txt", {"grupo": "A", "ano 2": "2020"})
    out = tmp_path / "c.vrt"
    report = export_vrt(proj, "ud", out)
    lines = out.read_text().splitlines()
    assert report["documents"] == 2
    assert lines[1] == '<text id="doc1.txt" corpus="ud" layer="conllu" ano_2="2020" grupo="A">'
    assert lines.count("<s>") == 3 and lines.count("</text>") == 2
    assert "cats\tNNS\tNOUN\tcat\t-" in lines


def test_nltk_tagged(proj, tmp_path):
    brown = tmp_path / "brown"
    brown.mkdir()
    (brown / "ca01").write_text("\n\n\tThe/at Fulton/np-tl jury/nn said/vbd ``/`` 1/2/cd ''/'' ./.\n\n\tIt/pps ended/vbd ./.\n")
    d = parse_nltk_tagged(brown / "ca01")
    assert d["text"] == "The Fulton jury said `` 1/2''.\nIt ended."
    assert [t["xpos"] for t in d["tokens"]][:6] == ["at", "np-tl", "nn", "vbd", "``", "cd"]
    assert all(d["text"][t["start_char"]:t["end_char"]] == t["word"] for t in d["tokens"])
    report = import_nltk_tagged(proj, brown, "brown", tagset="brown")
    assert report["imported"] == 1 and report["files"] == ["ca01.txt"]
    [layer] = proj.list_layers("brown")
    assert layer["tool"] == "nltk_tagged" and layer["config"]["tagset"] == "brown"


def test_token_tables(proj, tmp_path):
    import_conllu(proj, SAMPLE, "ud")
    export_tokens(proj, "ud", tmp_path / "t.csv")
    rows = list(csv.DictReader((tmp_path / "t.csv").open()))
    assert len(rows) == 16 and rows[4]["word"] == "cats" and rows[4]["lemma"] == "cat"
    export_tokens(proj, "ud", tmp_path / "jsonl", fmt="jsonl")
    meta, tokens = ttwtools.tagged_io.read_tagged_jsonl(tmp_path / "jsonl" / "doc1_conllu.jsonl")
    assert meta["tagger"] == "conllu" and tokens[1]["deprel"] == "aux"
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="pyarrow"):
            export_tokens(proj, "ud", tmp_path / "t.parquet", fmt="parquet")


def test_cli_import_export(tmp_path, capsys):
    project = str(tmp_path / "cli.ttwa")
    assert cli.main(["import", project, str(SAMPLE), "--name", "ud", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["tokens"] == 16
    out = tmp_path / "o.conllu"
    assert cli.main(["export", project, "--corpus", "ud", "--to", "conllu", "--out", str(out), "--json"]) == 0
    capsys.readouterr()
    assert _token_lines(out.read_text()) == _token_lines(SAMPLE.read_text())
    assert cli.main(["export", project, "--corpus", "ud", "--to", "vrt", "--out", str(tmp_path / "o.vrt")]) == 0
