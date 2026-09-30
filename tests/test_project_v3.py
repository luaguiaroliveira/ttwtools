"""Esquema v0.3: migração de um .ttwa v2 real, camadas/tokens e .ttwa ↔ .ttwl."""

from __future__ import annotations

import shutil
import sqlite3
import warnings
from pathlib import Path

import pytest

import ttwtools
from ttwtools import layers
from ttwtools.project import SCHEMA_VERSION_CURRENT, TTWAProject

V2_FIXTURE = Path(__file__).parent / "data" / "v2_small.ttwa"   # gerado por ttwtools 0.1.0
GROUPS = ("CorIFAessaysNE_5", "essays_bawe_somentetexto_5")


@pytest.fixture
def v2_copy(tmp_path) -> Path:
    dest = tmp_path / "v2.ttwa"
    shutil.copy(V2_FIXTURE, dest)
    return dest


def _raw_snapshot(path: Path) -> dict:
    """Conteúdo das tabelas v2, lido direto no SQLite (sem migrar)."""
    con = sqlite3.connect(path)
    out = {t: con.execute(f"SELECT * FROM {t} ORDER BY id").fetchall()
           for t in ("corpus_files", "tagged_files", "feature_tables", "kfa_results")}
    out["schema"] = con.execute("SELECT value FROM project_meta WHERE key='schema_version'").fetchone()[0]
    con.close()
    return out


def test_fixture_is_v2(tmp_path):
    copy = tmp_path / "f.ttwa"          # numa cópia: abrir o banco em WAL cria -wal/-shm ao lado do original
    shutil.copy(V2_FIXTURE, copy)
    assert _raw_snapshot(copy)["schema"] == "0.2"


def test_migrate_v2_keeps_everything(v2_copy):
    before = _raw_snapshot(v2_copy)
    with pytest.warns(UserWarning, match="migrado do esquema 0.2"):
        proj = ttwtools.open_project(v2_copy)
    with proj:
        r = proj.migration_report
        assert r["documents"] == 10 and r["layers"] == 30 and r["skipped_legacy"] == 0 and r["tokens"] > 0
        assert str(proj.get_meta("schema_version")) == SCHEMA_VERSION_CURRENT
        assert proj.kind == "ttwa"
        # mesmos resultados de antes
        df = proj.load_feature_table(GROUPS[0], "norm1000", tagger_type="biberplus")
        assert len(df) == 5
        assert proj.load_kfa_result(GROUPS[0], GROUPS[1], tagger_type="biberplus") is not None
    after = _raw_snapshot(v2_copy)
    for table in ("corpus_files", "tagged_files", "feature_tables", "kfa_results"):
        assert after[table] == before[table], table
    # reabrir não migra de novo
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ttwtools.open_project(v2_copy).close()


def test_tokens_match_jsonl(v2_copy):
    with pytest.warns(UserWarning):
        proj = ttwtools.open_project(v2_copy)
    with proj:
        for tool in ("biberplus", "spacy", "mfte"):
            layer = proj.list_layers(GROUPS[0], tool=tool)[0]
            tagged_name = next(f for f in proj.list_tagged_files(GROUPS[0], tool)
                               if f.startswith(Path(layer["filename"]).stem))
            meta, jsonl_tokens = layers.parse_tagged_jsonl(proj.get_tagged_file(GROUPS[0], tagged_name, tool))
            tokens = proj.get_tokens(layer["id"])
            assert len(tokens) == len(jsonl_tokens) == layer["n_tokens"]
            text = proj.get_corpus_file(GROUPS[0], layer["filename"])
            assert layer["text_hash"] == layers.text_hash(text)
            for t, j in zip(tokens, jsonl_tokens):
                assert (t["start_char"], t["end_char"], t["word"]) == (j["start_char"], j["end_char"], j["word"])
                assert t["tags"] == j["tags"]
        spacy_tok = proj.get_tokens(proj.list_layers(GROUPS[0], tool="spacy")[0]["id"])[1]
        assert spacy_tok["upos"] and spacy_tok["xpos"]          # ptb → xpos
        layer = proj.list_layers(GROUPS[0], tool="spacy")[0]
        assert layer["model"] == "en_core_web_sm"
        assert proj.find_layer(layer["text_hash"], "spacy", layer["tool_version"], layer["model"],
                               layer["config_hash"])["id"] == layer["id"]


def test_config_hash_ignores_performance_options():
    base = {"spacy_model": "en_core_web_sm", "extended": True}
    assert layers.config_hash({**base, "device": "cpu"}) == layers.config_hash({**base, "device": "cuda", "n_processes": 8})
    assert layers.config_hash(base) != layers.config_hash({**base, "extended": False})


def test_new_project_indexes_on_save(tmp_path, corpus5):
    group = GROUPS[0]
    with ttwtools.create_project(tmp_path / "n.ttwa") as proj:
        proj.add_corpus_folder(group, corpus5[group])
        first = proj.list_corpus_files(group)[0]
        content = V2_TAGGED_SAMPLE.replace("__FILE__", first)
        proj.save_tagged_file(group, "a_biberplus.jsonl", content, tagger_type="biberplus")
        [layer] = proj.list_layers(group)
        assert layer["filename"] == first and layer["n_tokens"] == 2
        assert layer["text_hash"] == proj.list_documents(group)[0]["content_hash"]
        # salvar de novo a mesma camada substitui, não duplica
        proj.save_tagged_file(group, "a_biberplus.jsonl", content, tagger_type="biberplus")
        assert len(proj.list_layers(group)) == 1


V2_TAGGED_SAMPLE = (
    '{"type": "metadata", "tagger": "biberplus", "tagger_version": "0.4.0", "filename": "__FILE__"}\n'
    '{"start_char": 0, "end_char": 2, "word": "My", "xpos": "", "tags": ["FPP1"]}\n'
    '{"start_char": 3, "end_char": 11, "word": "research", "xpos": "", "tags": ["NN"]}\n'
)


def test_analyses_roundtrip(tmp_path):
    with ttwtools.create_project(tmp_path / "a.ttwa") as proj:
        aid = proj.save_analysis("freq", [{"word": "a", "n": 3}], params={"top": 10}, layer_refs=[1, 2])
        assert proj.list_analyses("freq")[0]["params"] == {"top": 10}
        assert proj.load_analysis(aid)["result"] == [{"word": "a", "n": 3}]


def _migrated(v2_copy) -> TTWAProject:
    with pytest.warns(UserWarning):
        return ttwtools.open_project(v2_copy)


def test_detach_and_embed_roundtrip(v2_copy, tmp_path):
    with _migrated(v2_copy) as full:
        texts = {(c, f): full.get_corpus_file(c, f) for c in GROUPS for f in full.list_corpus_files(c)}
        n_tokens = sum(l["n_tokens"] for l in full.list_layers())
        light = ttwtools.detach_corpus(full, tmp_path / "leve.ttwl")
    with light:
        assert light.kind == "ttwl" and light.is_light
        assert light._con.execute("SELECT COUNT(*) FROM corpus_files").fetchone()[0] == 0
        assert (tmp_path / "leve_corpus" / GROUPS[0]).is_dir()
        assert {(c, f): light.get_corpus_file(c, f) for c, f in texts} == texts
        assert sum(l["n_tokens"] for l in light.list_layers()) == n_tokens
        assert not light.check_corpus()["missing"] and not light.check_corpus()["changed"]
        full2 = ttwtools.embed_corpus(light, tmp_path / "de_volta.ttwa")
    assert (tmp_path / "leve.ttwl").stat().st_size < v2_copy.stat().st_size
    with full2:
        assert full2.kind == "ttwa"
        assert {(c, f): full2.get_corpus_file(c, f) for c, f in texts} == texts
    # abrir pelo tipo gravado no arquivo
    with ttwtools.open_project(tmp_path / "leve.ttwl") as again:
        assert again.is_light


def test_ttwl_missing_and_changed_corpus(v2_copy, tmp_path):
    with _migrated(v2_copy) as full:
        light = full.detach_corpus(tmp_path / "leve.ttwl")
    folder = tmp_path / "leve_corpus"
    moved = tmp_path / "outro_lugar"
    shutil.move(folder, moved)
    with light:
        status = light.check_corpus()
        assert len(status["missing"]) == 10 and not status["ok"]
        assert light.get_corpus_file(GROUPS[0], light.list_documents(GROUPS[0])[0]["filename"]) is None
        # ferramentas que só usam tokens continuam funcionando
        assert light.list_layers(GROUPS[0])
        with pytest.raises(FileNotFoundError):
            light.embed_corpus(tmp_path / "x.ttwa")

        # alterar um texto: relink sem aceitar deixa esse documento de fora
        doc = light.list_documents(GROUPS[0])[0]
        changed_file = moved / GROUPS[0] / doc["filename"]
        changed_file.write_text(changed_file.read_text(encoding="utf-8") + " extra", encoding="utf-8")
        report = light.relink_corpus(moved)
        assert len(report["relinked"]) == 9 and report["changed"] == [(GROUPS[0], doc["filename"])]
        assert light.check_corpus()["missing"] == [(GROUPS[0], doc["filename"])]
        report = light.relink_corpus(moved, accept_changed=True)
        assert not light.check_corpus()["changed"] and not light.check_corpus()["missing"]
        # o hash novo passou a valer: a camada antiga (texto velho) fica marcada pelo text_hash
        new_hash = light.list_documents(GROUPS[0])[0]["content_hash"]
        assert new_hash != doc["content_hash"]
        assert all(l["text_hash"] != new_hash for l in light.list_layers(GROUPS[0]) if l["filename"] == doc["filename"])


def test_ttwl_created_directly(tmp_path, corpus5):
    group = GROUPS[1]
    with ttwtools.create_project(tmp_path / "direto.ttwl") as proj:
        proj.add_corpus_folder(group, corpus5[group])
        assert proj.kind == "ttwl"
        assert proj._con.execute("SELECT COUNT(*) FROM corpus_files").fetchone()[0] == 0
        names = proj.list_corpus_files(group)
        assert len(names) == 5
        assert proj.get_corpus_file(group, names[0]) == (corpus5[group] / names[0]).read_text(encoding="utf-8")
        folder = proj.export_corpus_next_to()
        assert (folder / group / names[0]).is_file()
        assert proj._document_path(group, names[0]) == (folder / group / names[0]).resolve()


def test_add_corpus_text(tmp_path):
    with ttwtools.create_project(tmp_path / "t.ttwa") as proj:
        proj.add_corpus_text("c", "a.txt", "Hello world.")
        assert proj.get_corpus_file("c", "a.txt") == "Hello world."
        assert proj.list_documents("c")[0]["content_hash"] == layers.text_hash("Hello world.")
    with ttwtools.create_project(tmp_path / "t.ttwl") as proj, pytest.raises(ValueError):
        proj.add_corpus_text("c", "a.txt", "x")
