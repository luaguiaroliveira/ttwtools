"""layerfmt (TCL1): ida e volta token a token, blobs antigos e integração com layer_blobs."""

from __future__ import annotations

import json
import shutil
import warnings
import zlib
from pathlib import Path

import pytest

import ttwtools
from ttwtools import layerfmt
from ttwtools.project import _layer_rows, _pack_rows, save_project_as

V2_FIXTURE = Path(__file__).parent / "data" / "v2_small.ttwa"


def test_roundtrip_edge_cases():
    rows = [
        (0, 3, "Ação", "ação", "NOUN", None, None, '["NOUN"]', None),
        (4, 4, "", None, None, None, '{"Case":"Nom"}', "[]", '{"x":1}'),      # token vazio, tudo None, unicode
        (None, None, "a", "a", "X", "X1", None, None, None),                 # sem posições
        (2 ** 30, 2 ** 30 + 5, "z" * 500, "z", "ADJ", "JJ", "f", "[\"JJ\"]", None),
    ]
    assert [tuple(r) for r in layerfmt.decode(layerfmt.encode(rows))] == rows
    assert layerfmt.decode(layerfmt.encode([])) == []
    blob = layerfmt.encode(rows)
    assert layerfmt.is_columnar(blob) and blob[:4] == b"TCL1"


def test_large_dictionary_uses_wide_indexes():
    rows = [(i, i + 1, f"w{i}", None, None, None, None, None, None) for i in range(70_000)]   # > 65 535 formas
    assert [tuple(r) for r in layerfmt.decode(layerfmt.encode(rows))] == rows


def test_decode_accepts_the_old_json_blob():
    rows = [[0, 3, "The", "the", "DET", "DT", None, '["DET"]', None]]
    old = zlib.compress(json.dumps(rows).encode("utf-8"), 6)
    assert not layerfmt.is_columnar(old) and layerfmt.decode(old) == rows


def test_pack_rows_falls_back_to_json_for_odd_rows():
    odd = [(0, 3, 12345, None, None, None, None, None, None)]          # word não textual
    blob = _pack_rows(odd)
    assert not layerfmt.is_columnar(blob) and layerfmt.decode(blob) == [list(odd[0])]
    with pytest.raises(ValueError):
        layerfmt.encode(odd)
    with pytest.raises(ValueError):
        layerfmt.encode([(1, 2, "a")])                                   # colunas a menos


@pytest.fixture
def real(tmp_path):
    """Projeto v2 real pequeno, migrado: camadas de BiberPlus, spaCy e MFTE."""
    dest = tmp_path / "v2.ttwa"
    shutil.copy(V2_FIXTURE, dest)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = ttwtools.open_project(dest)
    yield p
    p.close()


def test_real_layers_roundtrip_token_by_token(real):
    tools = {l["tool"] for l in real.list_layers()}
    assert {"biberplus", "spacy", "mfte"} <= tools
    cols = "start_char, end_char, word, lemma, upos, xpos, feats, tags, extra"
    n = 0
    for l in real.list_layers():
        rows = [tuple(r) for r in real._con.execute(f"SELECT {cols} FROM tokens WHERE layer_id = ? ORDER BY idx", (l["id"],))]
        assert [tuple(r) for r in layerfmt.decode(layerfmt.encode(rows))] == rows, (l["tool"], l["filename"])
        n += len(rows)
    assert n > 10_000


@pytest.mark.parametrize("fmt", ["tcl1", "tcl2"])
def test_pack_and_rebuild_use_the_new_format_and_keep_everything(real, tmp_path, monkeypatch, fmt):
    monkeypatch.setenv("TTWTOOLS_LAYER_FORMAT", fmt)          # o padrão é tcl2; tcl1 ainda grava e lê
    before = {l["id"]: real.get_tokens(l["id"]) for l in real.list_layers()}
    real.pack_search_tables()
    blobs = [r[0] for r in real._con.execute("SELECT data FROM layer_blobs")]
    assert blobs and all((layerfmt.is_tcl2(b) if fmt == "tcl2" else layerfmt.is_columnar(b)) for b in blobs)
    assert _layer_rows(real._con, next(iter(before))) is not None                 # lê de layer_blobs
    real.rebuild_search_tables()
    assert {l["id"]: real.get_tokens(l["id"]) for l in real.list_layers()} == before


def test_old_json_blobs_in_a_file_are_still_readable(real):
    """Arquivo salvo sem tabelas de busca por versão anterior: blobs JSON+zlib; abrir recria os tokens."""
    before = {l["id"]: real.get_tokens(l["id"]) for l in real.list_layers()}
    cols = "start_char, end_char, word, lemma, upos, xpos, feats, tags, extra"
    for lid in before:
        rows = real._con.execute(f"SELECT {cols} FROM tokens WHERE layer_id = ? ORDER BY idx", (lid,)).fetchall()
        real._con.execute("INSERT INTO layer_blobs (layer_id, data) VALUES (?, ?)", (lid, zlib.compress(
            json.dumps([list(r) for r in rows], ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)))
    real._con.execute("DELETE FROM tokens")
    real._set_meta("search_tables", False)
    real._con.commit()
    real.rebuild_search_tables()
    assert {l["id"]: real.get_tokens(l["id"]) for l in real.list_layers()} == before


def test_columnar_is_smaller_than_json(real):
    cols = "start_char, end_char, word, lemma, upos, xpos, feats, tags, extra"
    lid = max(real.list_layers(), key=lambda l: l["n_tokens"])["id"]
    rows = real._con.execute(f"SELECT {cols} FROM tokens WHERE layer_id = ? ORDER BY idx", (lid,)).fetchall()
    old = zlib.compress(json.dumps([list(r) for r in rows], ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
    assert len(layerfmt.encode(rows)) < len(old)
