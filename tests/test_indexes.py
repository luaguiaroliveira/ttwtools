"""A4: conjunto reduzido de índices de `tokens`; arquivos antigos abrem e perdem os índices sem uso."""

from __future__ import annotations

import sqlite3

import ttwtools
from ttwtools import query
from ttwtools.corpus import import_corpus
from ttwtools.project import _OBSOLETE_INDEXES, _TOKEN_INDEXES

NEW = {"idx_tokens_lword", "idx_tokens_llemma", "idx_tokens_doc", "idx_tokens_upos", "idx_tokens_xpos"}


def _indexes(path) -> set:
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tokens'")}
    finally:
        con.close()


def test_index_set_is_the_reduced_one():
    assert {n for n, _ in _TOKEN_INDEXES} == NEW
    assert set(_OBSOLETE_INDEXES) == {"idx_tokens_word", "idx_tokens_lemma"}


def test_old_file_loses_unused_indexes_and_results_do_not_change(tmp_path, corpus5):
    path = tmp_path / "p.ttwa"
    p = ttwtools.create_project(path)
    import_corpus(p, corpus5["CorIFAessaysNE_5"], "a")
    p._con.execute("CREATE INDEX idx_tokens_word ON tokens (word)")          # como um arquivo de versão anterior
    p._con.execute("CREATE INDEX idx_tokens_lemma ON tokens (lemma)")
    p._con.commit()
    p.close()
    assert {"idx_tokens_word", "idx_tokens_lemma"} <= _indexes(path)
    with ttwtools.open_project(path) as p:
        assert _indexes(path) == NEW                          # apagados ao abrir
        assert p.list_corpus_names() == ["a"]
        assert query.search(p, 'a', 'the')['total'] > 0            # as buscas seguem funcionando
    with ttwtools.open_project(path) as p:                   # reabrir: nada a fazer, nada muda
        assert _indexes(path) == NEW
