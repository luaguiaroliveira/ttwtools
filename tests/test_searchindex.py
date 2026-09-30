"""B3: índice de busca em cache (ATTACH + view), construído uma vez, com etapas e sem mexer no arquivo."""

from __future__ import annotations

import shutil
import sqlite3
import warnings
from collections import namedtuple
from pathlib import Path

import pytest

import ttwtools
from ttwtools import query, searchindex, storage
from ttwtools.project import TTWAProject, save_corpus_as, save_project_as

V2 = Path(__file__).parent / "data" / "v2_small.ttwa"
COLS = "layer_id, idx, doc_id, start_char, end_char, word, lemma, upos, xpos, feats, tags, extra"
Usage = namedtuple("Usage", "total used free")


@pytest.fixture
def lean(tmp_path):
    """(arquivo salvo SEM tabelas de busca, tokens de referência lidos do projeto completo)."""
    full = tmp_path / "full.ttwa"
    shutil.copy(V2, full)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = ttwtools.open_project(full)
    before = [tuple(r) for r in p._con.execute(f"SELECT {COLS} FROM tokens ORDER BY layer_id, idx")]
    p._con.commit()
    out = save_project_as(p.path, tmp_path / "lean.ttwa", search_tables=False, compress=False)
    p.close()
    return out, before


def _tokens(p):
    return [tuple(r) for r in p._con.execute(f"SELECT {COLS} FROM tokens ORDER BY layer_id, idx")]


def test_ddl_matches_project_tokens_table(tmp_path):
    p = ttwtools.create_project(tmp_path / "p.ttwa")
    db = sqlite3.connect(":memory:")
    db.execute(searchindex._DDL)
    mine = [tuple(r[1:4]) for r in db.execute("PRAGMA table_info(tokens)")]
    theirs = [tuple(r[1:4]) for r in p._con.execute("PRAGMA main.table_info(tokens)")]
    assert mine == theirs and [r[1] for r in db.execute("PRAGMA table_info(tokens)")] == searchindex._COLS.split(", ")
    p.close()


def test_open_uses_cached_index_and_leaves_project_small(lean):
    path, before = lean
    stages = []
    with ttwtools.open_project(path, progress=lambda d, t, s: stages.append(s)) as q:
        assert q._idx_attached and not q.has_search_tables and not q.unsaved
        assert q._con.execute("SELECT COUNT(*) FROM main.tokens").fetchone()[0] == 0         # nada dentro do projeto
        assert q._con.execute("SELECT COUNT(*) FROM layer_blobs").fetchone()[0] > 0           # blobs continuam
        assert _tokens(q) == before                                                          # mesmos tokens, via view
        assert query.kwic(q, "CorIFAessaysNE_5", "the", limit=1)["total"] > 0
    stages = [s for s in stages if s != "decompress"]
    order = [s for i, s in enumerate(stages) if s not in stages[:i]]
    assert order[0] == "idx_read" and sorted(order[1:]) == sorted(["idx_words", "idx_lemmas", "idx_doc", "idx_upos", "idx_xpos"])
    entries = list(storage.cache_dir().glob("idx-*/tokens.sqlite"))
    assert entries and all((e.parent / "entry.json").is_file() for e in entries)


def test_second_open_does_not_build_and_copies_share_the_cache(lean, tmp_path):
    path, before = lean
    ttwtools.open_project(path).close()
    n = len(list(storage.cache_dir().glob("idx-*")))
    copy = tmp_path / "copia.ttwa"
    shutil.copy(path, copy)                                    # mesma linhagem: mesmos ids e blobs
    stages = []
    with ttwtools.open_project(copy, progress=lambda d, t, s: stages.append(s)) as q:
        assert [s for s in stages if s != "decompress"] == [] and _tokens(q) == before      # nenhuma construção
    assert len(list(storage.cache_dir().glob("idx-*"))) == n


def test_queries_match_a_fully_materialized_project(lean, tmp_path):
    path, _ = lean
    a = ttwtools.open_project(path)
    mat = save_project_as(a.path, tmp_path / "mat.ttwa", search_tables=True)        # materializa (vem do modo cache)
    b = ttwtools.open_project(mat)
    try:
        assert a._idx_attached and not b._idx_attached and b.has_search_tables
        c = "CorIFAessaysNE_5"
        for fn in (lambda p: query.search(p, c, "the")["total"], lambda p: query.kwic(p, c, "the", limit=20),
                   lambda p: query.frequency(p, c, unit="lemma", top=30), lambda p: query.collocates(p, c, "the", top=10),
                   lambda p: query.dispersion(p, c, "the"), lambda p: query.kwic(p, c, "the of", limit=5)):
            assert fn(a) == fn(b)
    finally:
        a.close()
        b.close()


def test_live_layers_and_saving_in_cache_mode(lean, tmp_path):
    path, before = lean
    with ttwtools.open_project(path) as q:
        doc = q.list_documents()[0]
        toks = [{"word": "zzz", "lemma": "zzz", "upos": "X", "start_char": 0, "end_char": 3}]
        new = q.save_layer(doc["id"], "fake", "1", "m", {}, toks)              # camada nova: vai para main.tokens
        q._con.commit()
        assert q._con.execute("SELECT COUNT(*) FROM main.tokens").fetchone()[0] == 1
        assert len(_tokens(q)) == len(before) + 1                               # a view junta main e cache
        again = save_project_as(q.path, tmp_path / "again.ttwa", search_tables=False)   # empacota só a nova
        full = save_project_as(q.path, tmp_path / "again_full.ttwa", search_tables=True)  # materializa tudo
    with ttwtools.open_project(again) as r:
        assert len(_tokens(r)) == len(before) + 1 and r._idx_attached
    with ttwtools.open_project(full) as r:
        assert not r._idx_attached and r.has_search_tables and len(_tokens(r)) == len(before) + 1
        assert r._con.execute("SELECT COUNT(*) FROM layer_blobs").fetchone()[0] == 0


def test_export_with_tables_from_cache_mode(lean, tmp_path):
    path, _ = lean
    with ttwtools.open_project(path) as q:
        c = save_corpus_as(q, "CorIFAessaysNE_5", tmp_path / "c.ttwc")                # com tabelas de busca
        leve = save_corpus_as(q, "CorIFAessaysNE_5", tmp_path / "c.ttwcl")            # leve
        want = [r for r in _tokens(q) if r[0] in {l["id"] for l in q.list_layers("CorIFAessaysNE_5")}]
    with ttwtools.open_project(c) as r:
        assert r.has_search_tables and not r._idx_attached and _tokens(r) == want
        assert r._con.execute("SELECT COUNT(*) FROM layer_blobs").fetchone()[0] == 0
    with ttwtools.open_project(leve) as r:
        assert _tokens(r) == want


def test_disabled_falls_back_to_rebuild(lean, monkeypatch):
    path, before = lean
    monkeypatch.setenv("TTWTOOLS_INDEX_CACHE", "0")
    with ttwtools.open_project(path) as q:
        assert not q._idx_attached and q.has_search_tables and _tokens(q) == before


def test_cache_removed_rebuilds_and_cancel_leaves_nothing(lean):
    path, before = lean
    ttwtools.open_project(path).close()
    storage.clear_cache()
    searchindex._memo.clear()

    class Cancel(Exception):
        pass

    def stop(d, t, s):
        if s == "idx_words":
            raise Cancel()

    with pytest.raises(Cancel):                                 # cancelar no meio da construção
        ttwtools.open_project(path, progress=stop)
    assert not list(storage.cache_dir().glob("idx-*/tokens.sqlite*"))      # nem pronto nem .part
    with ttwtools.open_project(path) as q:                      # e reconstrói sem problema
        assert _tokens(q) == before


def test_full_disk_refuses_before_building(lean, monkeypatch):
    path, _ = lean
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: Usage(10**9, 10**9 - 1000, 1000))
    with pytest.raises(storage.InsufficientDiskSpace) as e:
        ttwtools.open_project(path)
    assert e.value.what == "index" and not list(storage.cache_dir().glob("idx-*/tokens.sqlite*"))


def test_status_and_clear(lean):
    path, _ = lean
    with ttwtools.open_project(path) as q:
        st = searchindex.status(q)
        assert st["entries"] and all(e["ready"] and e["bytes"] > 0 for e in st["entries"]) and st["missing_tokens"] == 0
        assert searchindex.clear(q) > 0
        assert not searchindex.status(q)["entries"][0]["ready"]


def test_plan_entries_groups_to_respect_the_attach_limit():
    layers = [{"id": i, "doc_id": i, "corpus": f"c{i % 5}", "tool": f"t{i % 3}", "version": "1", "model": "", "config": "x",
               "tokens": 10} for i in range(60)]
    assert len(searchindex.plan_entries(layers, 20)) == 15          # corpus × ferramenta
    assert len(searchindex.plan_entries(layers, 8)) == 3            # por ferramenta
    assert len(searchindex.plan_entries(layers, 2)) == 1            # tudo junto
    assert sum(len(g) for g in searchindex.plan_entries(layers, 8)) == 60


def test_lru_keeps_entries_in_use(tmp_path):
    for k in ("a", "b"):
        (storage.cache_entry(k) / "x.bin").write_bytes(b"x" * 1000)
    import os
    os.utime(storage.cache_dir() / "a" / ".last_used", (1, 1))
    assert storage.enforce_cache_limit(limit=0, keep=("a",)) == ["b"]


def test_compressed_file_with_cache_mode_and_cli(tmp_path, capsys):
    import json
    from ttwtools.cli import main as cli_main
    full = tmp_path / "full.ttwa"
    shutil.copy(V2, full)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = ttwtools.open_project(full)
    n = p._con.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
    p._con.commit()
    z = save_project_as(p.path, tmp_path / "z.ttwa", search_tables=False)              # compactado (padrão)
    p.close()
    assert cli_main(["index", "status", str(z), "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st and all(e["pronto"] == "não" for e in st)                                   # status não constrói
    assert cli_main(["index", "build", str(z), "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert all(e["pronto"] == "sim" and e["mb"] > 0 for e in st)
    with ttwtools.open_project(z) as q:                                                   # cópia de trabalho + cache
        assert q.is_working_copy and q._idx_attached and not q.unsaved
        assert q._con.execute("SELECT COUNT(*) FROM tokens").fetchone()[0] == n
    assert cli_main(["index", "clear", str(z), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["mb_liberados"] > 0
