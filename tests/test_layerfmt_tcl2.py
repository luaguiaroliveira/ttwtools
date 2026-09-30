"""layerfmt TCL2 (ids + léxico por corpus): ida e volta, léxico que só cresce e integração com o projeto."""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import pytest

import ttwtools
from ttwtools import layerfmt
from ttwtools.project import LayerStore, save_corpus_as, save_project_as

V2_FIXTURE = Path(__file__).parent / "data" / "v2_small.ttwa"
COLS = "start_char, end_char, word, lemma, upos, xpos, feats, tags, extra"


def test_roundtrip_edge_cases_and_lexicon_is_append_only():
    rows = [
        (0, 3, "Ação", "ação", "NOUN", None, None, '["NOUN"]', None),
        (4, 4, "", None, None, None, '{"Case":"Nom"}', "[]", '{"x":1}'),
        (None, None, "a", "a", "X", "X1", None, None, None),
        (2 ** 30, 2 ** 30 + 5, "z" * 500, "z", "ADJ", "JJ", "f", '["JJ"]', None),
    ]
    lex = layerfmt.Lexicon()
    b1 = layerfmt.encode_tcl2(rows, lex)
    assert layerfmt.is_tcl2(b1) and not layerfmt.is_columnar(b1)
    assert [tuple(r) for r in layerfmt.decode(b1, lex)] == rows
    assert layerfmt.decode(layerfmt.encode_tcl2([], lex), lex) == []
    n = len(lex)
    b2 = layerfmt.encode_tcl2([(0, 1, "novo", "novo", "ADV", "RB", None, None, None)] + rows, lex)
    assert len(lex) > n
    assert [tuple(r) for r in layerfmt.decode(b1, lex)] == rows           # ids antigos continuam valendo
    assert layerfmt.decode(b2, lex)[0][2] == "novo"
    with pytest.raises(ValueError, match="léxico"):
        layerfmt.decode(b1)
    with pytest.raises(ValueError):
        layerfmt.decode(b2, layerfmt.Lexicon())                             # léxico de outro arquivo
    before = len(lex)
    with pytest.raises(ValueError):
        layerfmt.encode_tcl2([(1, 2, 3, "a", "b", "c", "d", "e", "f")], lex)
    assert len(lex) == before                                               # erro não suja o léxico
    ids = layerfmt.decode_ids(b1, (2, 4))
    assert set(ids) == {2, 4} and len(ids[2]) == len(rows)


@pytest.fixture
def real(tmp_path):
    dest = tmp_path / "v2.ttwa"
    shutil.copy(V2_FIXTURE, dest)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = ttwtools.open_project(dest)
    yield p
    p.close()


def _tokens(p):
    return {l["id"]: p.get_tokens(l["id"]) for l in p.list_layers()}


def test_pack_rebuild_and_light_export_in_tcl2(real, tmp_path, monkeypatch):
    monkeypatch.setenv("TTWTOOLS_LAYER_FORMAT", "tcl2")
    before = _tokens(real)
    real.pack_search_tables()
    blobs = [r[0] for r in real._con.execute("SELECT data FROM layer_blobs")]
    assert blobs and all(layerfmt.is_tcl2(b) for b in blobs)
    assert real._con.execute("SELECT COUNT(*) FROM lexicon_parts").fetchone()[0] > 0
    store = LayerStore(real._con)
    lid = next(iter(before))
    assert store.unpack(lid, real._con.execute("SELECT data FROM layer_blobs WHERE layer_id = ?", (lid,)).fetchone()[0])
    real.rebuild_search_tables()
    assert _tokens(real) == before
    # exportar um corpus leve em TCL2 e reabrir; depois voltar para TCL1 sem perder nada
    corpus = real.list_corpus_names()[0]
    keep = {l["id"]: t for l, t in ((l, before[l["id"]]) for l in real.list_layers() if l.get("corpus_name", corpus) == corpus)}
    out = save_corpus_as(real, corpus, tmp_path / "leve.ttwcl", compress=False)
    import sqlite3
    raw = sqlite3.connect(out)
    blobs = [r[0] for r in raw.execute("SELECT data FROM layer_blobs")]
    raw.close()
    assert blobs and all(layerfmt.is_tcl2(b) for b in blobs)                # o arquivo leve está em TCL2
    with ttwtools.open_project(out) as q:
        got = _tokens(q)
    assert {k: got[k] for k in got if k in keep} == {k: keep[k] for k in got if k in keep} and got
    monkeypatch.setenv("TTWTOOLS_LAYER_FORMAT", "tcl1")
    with ttwtools.open_project(out) as q:
        out1 = save_corpus_as(q, corpus, tmp_path / "volta.ttwcl", compress=False)
    with ttwtools.open_project(out1) as q:
        assert _tokens(q) == got
        assert not any(layerfmt.is_tcl2(r[0]) for r in q._con.execute("SELECT data FROM layer_blobs"))


def test_tcl2_file_smaller_than_tcl1(real, tmp_path, monkeypatch):
    monkeypatch.setenv("TTWTOOLS_LAYER_FORMAT", "tcl1")
    a = save_project_as(real.path, tmp_path / "a.ttwa", compress=False, search_tables=False)
    monkeypatch.setenv("TTWTOOLS_LAYER_FORMAT", "tcl2")
    b = save_project_as(real.path, tmp_path / "b.ttwa", compress=False, search_tables=False)
    assert b.stat().st_size < a.stat().st_size * 1.1                        # projeto pequeno: só não pode ser muito pior


def test_tcl2_is_the_default_and_tcl1_can_be_forced(monkeypatch):
    monkeypatch.delenv("TTWTOOLS_LAYER_FORMAT", raising=False)
    assert layerfmt.default_format() == "tcl2"
    monkeypatch.setenv("TTWTOOLS_LAYER_FORMAT", "tcl1")
    assert layerfmt.default_format() == "tcl1"


def test_export_from_tcl1_light_file_converts_to_tcl2(real, tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv("TTWTOOLS_LAYER_FORMAT", "tcl1")
    corpus = real.list_corpus_names()[0]
    old = save_corpus_as(real, corpus, tmp_path / "antigo.ttwcl", compress=False)
    monkeypatch.delenv("TTWTOOLS_LAYER_FORMAT")
    with ttwtools.open_project(old) as q:
        expected = _tokens(q)
        new = save_corpus_as(q, corpus, tmp_path / "novo.ttwcl", compress=False)
    raw = sqlite3.connect(new)
    blobs = [r[0] for r in raw.execute("SELECT data FROM layer_blobs")]
    raw.close()
    assert blobs and all(layerfmt.is_tcl2(b) for b in blobs)
    with ttwtools.open_project(new) as q:
        assert _tokens(q) == expected


def test_saving_derived_results_does_not_mark_the_project_unsaved(tmp_path):
    import pandas as pd
    p = ttwtools.create_project(tmp_path / "t.ttwa")
    p._saved_changes = p._con.total_changes
    p.save_kfa_result("c1", "c2", pd.DataFrame({"Feature": ["a"], "Effect_Size": [0.5]}), 0.2)
    p.save_analysis("describe", {"x": 1}, name="c1")
    p.save_feature_table("c1", pd.DataFrame({"x": [1]}), "norm1000", "spacy")
    assert p._con.execute("SELECT COUNT(*) FROM kfa_results").fetchone()[0] == 1                 # gravou de fato
    assert p._con.total_changes == p._saved_changes                                              # e não sujou
    p._con.execute("INSERT INTO project_meta (key, value) VALUES ('x', '1') ON CONFLICT(key) DO UPDATE SET value='1'")
    assert p._con.total_changes > p._saved_changes                                               # mudança real continua contando
    p.close()


def test_default_feature_for_tag_layers():
    from ttwtools.features import default_feature
    assert [default_feature(t) for t in ("biberplus", "mfte", "mfte_ext", "spacy", "stanza")] == ["tags", "tags", "tags", "upos", "upos"]
