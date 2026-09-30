"""compact_project: remove `tagged_files` legados só quando há camada equivalente."""

from __future__ import annotations

import json
import shutil
import tempfile
import warnings
from pathlib import Path

import pytest

import ttwtools
from ttwtools import layers
from ttwtools.cli import main as cli_main
from ttwtools.project import compact_project

V2_FIXTURE = Path(__file__).parent / "data" / "v2_small.ttwa"   # v0.2: tagged_files, sem camadas


@pytest.fixture
def proj(tmp_path):
    dest = tmp_path / "v2.ttwa"
    shutil.copy(V2_FIXTURE, dest)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = ttwtools.open_project(dest)     # migra para v0.3: tagged_files + camadas
    yield p
    p.close()


def _n_tagged(p) -> int:
    return p._con.execute("SELECT COUNT(*) FROM tagged_files").fetchone()[0]


def _all_tokens(p) -> dict:
    return {(l["corpus_name"], l["filename"], l["tool"]): p.get_tokens(l["id"]) for l in p.list_layers()}


def _residue() -> set:
    return {x.name for x in Path(tempfile.gettempdir()).glob("ttw_*")}


def test_dry_run_changes_nothing(proj):
    n = _n_tagged(proj)
    size = proj.path.stat().st_size
    r = compact_project(proj)                       # dry_run é o padrão
    assert r["dry_run"] and r["n_removed"] == n == 30 and r["n_kept"] == 0 and r["bytes_freed"] > 0
    assert _n_tagged(proj) == n and proj.path.stat().st_size == size


def test_removes_equivalent_and_keeps_results(proj):
    before = _all_tokens(proj)
    layers_before = proj.list_layers()
    residue = _residue()
    seen = []
    r = compact_project(proj, dry_run=False, progress=lambda d, t, s: seen.append(s))
    assert r["n_removed"] == 30 and _n_tagged(proj) == 0
    assert r["size_after"] < r["size_before"] and {"check", "vacuum"} <= set(seen)
    assert _all_tokens(proj) == before and proj.list_layers() == layers_before
    assert proj.load_feature_table("CorIFAessaysNE_5", "norm1000", tagger_type="biberplus") is not None
    assert _residue() == residue                    # não deixa lixo temporário
    assert compact_project(proj, dry_run=False)["n_removed"] == 0     # idempotente


def test_keeps_what_it_cannot_prove(proj):
    con = proj._con
    rows = con.execute("SELECT id FROM tagged_files ORDER BY id").fetchall()
    ids = [r[0] for r in rows]
    # 1) token diferente na camada; 2) camada apagada; 3) TSV antigo; 4) documento inexistente
    row = con.execute("SELECT corpus_name, filename, tagger_type, content, encoding FROM tagged_files WHERE id = ?",
                      (ids[0],)).fetchone()
    meta = layers.parse_tagged_jsonl(ttwtools.project._decode_content(row["content"], row["encoding"]))[0]
    info = layers.layer_info(meta)
    lid = con.execute("SELECT id FROM layers WHERE tool = ? AND config_hash = ? AND doc_id = (SELECT id FROM documents"
                      " WHERE corpus_name = ? AND filename = ?)",
                      (row["tagger_type"], info["config_hash"], row["corpus_name"], meta.get("filename") or row["filename"])).fetchone()[0]
    con.execute("UPDATE tokens SET word = 'ALTERADO' WHERE layer_id = ? AND idx = 0", (lid,))
    other = con.execute("SELECT id, doc_id FROM layers WHERE id != ? LIMIT 1", (lid,)).fetchone()
    con.execute("DELETE FROM layers WHERE id = ?", (other["id"],))
    con.execute("INSERT INTO tagged_files (corpus_name, filename, tagger_type, encoding, content)"
                " VALUES ('c', 'velho.tsv', 'biberplus', 'plain', 'a\tb\n')")
    bogus = json.dumps({"type": "metadata", "tagger": "spacy", "tagger_version": "1", "filename": "nao_existe.txt"})
    con.execute("INSERT INTO tagged_files (corpus_name, filename, tagger_type, encoding, content)"
                " VALUES ('c', 'x.jsonl', 'spacy', 'plain', ?)", (bogus + "\n",))
    con.commit()
    r = compact_project(proj, dry_run=False)
    reasons = sorted(k["reason"] for k in r["kept"])
    assert reasons.count("tokens_differ") == 1 and reasons.count("not_jsonl") == 1
    assert reasons.count("no_document") == 1 and reasons.count("no_layer") >= 1
    assert r["n_removed"] == 30 - reasons.count("tokens_differ") - reasons.count("no_layer")
    assert _n_tagged(proj) == r["n_kept"]


def test_works_from_packed_layers(proj):
    proj.pack_search_tables()                       # tokens só em layer_blobs
    assert proj._con.execute("SELECT COUNT(*) FROM tokens").fetchone()[0] == 0
    r = compact_project(proj, dry_run=False)
    assert r["n_removed"] == 30 and _n_tagged(proj) == 0
    proj.rebuild_search_tables()
    assert proj._con.execute("SELECT COUNT(*) FROM tokens").fetchone()[0] > 0


def test_cli_compact(tmp_path, capsys):
    dest = tmp_path / "v2.ttwa"
    shutil.copy(V2_FIXTURE, dest)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert cli_main(["compact", str(dest), "--dry-run", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["simulação"] is True and out["removidos"] == 30
    assert cli_main(["compact", str(dest), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["removidos"] == 30 and out["tamanho_depois_mb"] <= out["tamanho_antes_mb"]
    with ttwtools.open_project(dest) as p:
        assert _n_tagged(p) == 0


def test_unified_upos_xpos_files_are_equivalent(proj):
    """Um arquivo com `tags` = [upos] (ou [xpos]) do mesmo token é redundante; outra diferença não é."""
    rows = [(1, 2, "casa", "casa", "NOUN", "NN", None, '["NN"]', None)]
    same = lambda tags: [(1, 2, "casa", "casa", "NOUN", "NN", None, tags, None)]
    from ttwtools.project import _same_token_rows
    assert _same_token_rows(same('["NOUN"]'), rows) and _same_token_rows(same('["NN"]'), rows)
    assert not _same_token_rows(same('["VERB"]'), rows)
    assert not _same_token_rows([(1, 2, "casa", "casa", "NOUN", "NN", None, '["NOUN"]', '{"a":1}')], rows)
    assert not _same_token_rows(rows + rows, rows)
