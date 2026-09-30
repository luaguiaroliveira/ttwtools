"""Índice em cache preguiçoso: abrir não monta o índice; a primeira leitura de `tokens` monta, com o mesmo resultado."""

from __future__ import annotations

import shutil
import sqlite3
import warnings
from pathlib import Path

import pytest

import ttwtools
from ttwtools import features, query, storage
from ttwtools.project import save_project_as

V2 = Path(__file__).parent / "data" / "v2_small.ttwa"
C = "CorIFAessaysNE_5"
COLS = "layer_id, idx, doc_id, start_char, end_char, word, lemma, upos, xpos, feats, tags, extra"


def _open(path, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ttwtools.open_project(path, **kw)


@pytest.fixture
def pair(tmp_path):
    """(projeto completo com tabelas, caminho do arquivo salvo SEM tabelas de busca)."""
    full = tmp_path / "full.ttwa"
    shutil.copy(V2, full)
    p = _open(full)
    p._con.commit()
    lean = save_project_as(p.path, tmp_path / "lean.ttwa", search_tables=False, compress=False)
    return p, lean


def _tool(p):
    return p.list_layers(C)[0]["tool"]


def battery(p):
    """Tudo que ainda lê `tokens` (ou que tem de dar o mesmo com e sem índice), em forma comparável."""
    tool = _tool(p)
    layer_ids = sorted(l["id"] for l in p.list_layers(C))
    doc = p.list_documents()[0]["filename"]
    out = {
        "get_tokens": [p.get_tokens(i) for i in layer_ids],
        "search": query.search(p, C, "the"),
        "search_lemma": query.search(p, C, "lemma=the"),
        "search_upos": query.search(p, C, "upos=NOUN"),
        "search_tag": query.search(p, C, "tag=NN"),
        "kwic": query.kwic(p, C, "the", limit=30),
        "kwic2": query.kwic(p, C, "of the", limit=10),
        "freq_form": query.frequency(p, C, unit="form", top=40),
        "freq_lemma": query.frequency(p, C, unit="lemma", top=40),
        "colloc": query.collocates(p, C, "the", top=15),
        "colloc_ex": query.collocate_examples(p, C, "the", None, limit=10),
        "dispersion": query.dispersion(p, C, "the"),
        "read_document": query.read_document(p, C, doc),
        "tag_upos": query.tag_counts(p, C, field="upos"),
        "tag_tags": query.tag_counts(p, C, field="tags"),
        "feature_table": features.feature_table(p, C, tool).sort_values("filename").reset_index(drop=True).to_dict("list"),
    }
    return out


def test_battery_same_with_and_without_index(pair):
    full, lean = pair
    want = battery(full)
    lazy = _open(lean)
    eager = _open(lean, lazy_index=False)
    try:
        assert lazy.index_pending and not eager.index_pending and eager._idx_attached
        assert battery(lazy) == want
        assert battery(eager) == want
        assert not lazy.index_pending          # alguma parte da bateria leu tokens
    finally:
        for q in (lazy, eager, full):
            q.close()


def test_open_does_not_build_and_id_queries_do_not_need_the_index(pair):
    full, lean = pair
    stages = []
    q = _open(lean, progress=lambda d, t, s: stages.append(s))
    try:
        assert [s for s in stages if s != "decompress"] == [] and q.index_pending and not q._idx_attached
        assert not list(storage.cache_dir().glob("idx-*"))
        query.search(q, C, "the")
        query.kwic(q, C, "the", limit=5)
        query.frequency(q, C, unit="lemma", top=5)
        query.collocates(q, C, "the", top=5)
        query.search(q, C, "lemma=the")                  # exigem campo da camada: lido dos ids, não de tokens
        query.search(q, C, "upos=NOUN")
        assert q.index_pending and not list(storage.cache_dir().glob("idx-*"))     # nada montou o índice
    finally:
        q.close()
        full.close()


def test_first_read_of_tokens_builds_once_and_ensure_index_is_explicit(pair):
    full, lean = pair
    q = _open(lean)
    try:
        lid = q.list_layers(C)[0]["id"]
        assert q._con.execute("SELECT COUNT(*) FROM main.tokens").fetchone()[0] == 0     # escrever/ler main não dispara
        assert q._con.execute("SELECT SUM(n_tokens) FROM layers").fetchone()[0] > 0      # coluna n_tokens não dispara
        assert q.index_pending
        seen = []
        q.ensure_index(progress=lambda d, t, s: seen.append(s))                          # explícito, com andamento
        assert not q.index_pending and q._idx_attached and "idx_read" in seen
        assert q.get_tokens(lid) == full.get_tokens(lid)
        q.ensure_index()                                                                 # já pronto: nada
    finally:
        q.close()
        full.close()


def test_unsaved_flag_untouched_and_failure_keeps_pending(pair, monkeypatch):
    full, lean = pair
    q = _open(lean)
    try:
        from ttwtools import searchindex
        real = searchindex.ensure

        def boom(*a, **k):
            raise storage.InsufficientDiskSpace("sem espaço") if False else OSError("x")
        monkeypatch.setattr(q, "attach_search_index", lambda progress=None: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            q.get_tokens(q.list_layers(C)[0]["id"])
        assert q.index_pending                                   # cancelado: tenta de novo na próxima leitura
        monkeypatch.undo()
        assert q.get_tokens(q.list_layers(C)[0]["id"])
        assert not q.index_pending and not q.unsaved
    finally:
        q.close()
        full.close()


def test_new_layer_in_lazy_mode_joins_the_cached_tokens(pair):
    full, lean = pair
    q = _open(lean)
    try:
        doc = q.list_documents()[0]
        toks = [{"word": "zzz", "lemma": "zzz", "upos": "X", "start_char": 0, "end_char": 3}]
        new = q.save_layer(doc["id"], "fake", "1", "m", {}, toks)
        q._con.commit()
        n = q._con.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]         # dispara: view = main ∪ cache
        assert n == full._con.execute("SELECT COUNT(*) FROM tokens").fetchone()[0] + 1
        assert q._con.execute("SELECT word FROM tokens WHERE layer_id = ?", (new,)).fetchall()[0][0] == "zzz"
    finally:
        q.close()
        full.close()


def test_save_as_from_lazy_project_keeps_all_tokens(pair, tmp_path):
    full, lean = pair
    q = _open(lean)
    try:
        out = save_project_as(q.path, tmp_path / "mat.ttwa", search_tables=True)
    finally:
        q.close()
    r = _open(out)
    try:
        a = [tuple(x) for x in r._con.execute(f"SELECT {COLS} FROM tokens ORDER BY layer_id, idx")]
        b = [tuple(x) for x in full._con.execute(f"SELECT {COLS} FROM tokens ORDER BY layer_id, idx")]
        assert a == b
    finally:
        r.close()
        full.close()


def test_on_demand_build_reports_progress_through_index_progress(pair):
    full, lean = pair
    q = _open(lean)
    seen = []
    q.index_progress = lambda d, t, s: seen.append(s)
    try:
        q.get_tokens(q.list_layers(C)[0]["id"])
        assert seen[0] == "idx_read" and "idx_words" in seen
    finally:
        q.close()
        full.close()
