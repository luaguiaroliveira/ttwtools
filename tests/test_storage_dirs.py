"""Pastas de trabalho e cache num lugar só: dono, limite LRU, limpeza e nada de resíduo."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

import ttwtools
from ttwtools import storage
from ttwtools.cli import main as cli_main
from ttwtools.corpus import import_corpus
from ttwtools.project import TTWAProject, compact_project, save_corpus_as, save_project_as


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """Pasta temporária, de cache e de dados só deste teste."""
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    monkeypatch.setenv("TTWTOOLS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("TTWTOOLS_DATA_DIR", str(tmp_path / "data"))
    return tmp


def test_workdir_kinds_have_owner(dirs):
    for kind, prefix in storage.WORKDIR_PREFIXES.items():
        d = storage.workdir(kind)
        assert d.name.startswith(prefix) and (d / "owner.pid").read_text() == str(os.getpid())
    listed = storage.list_workdirs()
    assert {w["kind"] for w in listed} == {"work", "export", "pack"} and all(w["mine"] and w["alive"] for w in listed)
    assert storage.release_own_workdirs() == 3 and not storage.list_workdirs()


def test_killed_process_leaves_workdir_and_restart_purges_it(dirs):
    """Matar o processo no meio de uma exportação e reiniciar apaga os restos."""
    code = ("import os, sys; from ttwtools import storage\n"
            "d = storage.workdir('export'); (d / 'work.ttwc').write_bytes(b'x' * 5_000_000)\n"
            "print(d, flush=True); os._exit(9)")          # morre sem limpar, como um kill -9
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env={**os.environ, "TMPDIR": str(dirs)})
    left = Path(r.stdout.strip())
    assert r.returncode == 9 and left.exists()
    w = next(w for w in storage.list_workdirs() if w["path"] == str(left))
    assert w["alive"] is False and w["bytes"] >= 5_000_000 and not w["mine"]
    assert storage.disk_usage()["orphans_bytes"] >= 5_000_000
    assert storage.purge_orphans() == 1 and not left.exists()      # ao iniciar
    assert storage.last_purge["bytes"] >= 5_000_000


def test_cache_lru_limit_and_clear(dirs, monkeypatch):
    assert storage.cache_dir() == Path(os.environ["TTWTOOLS_CACHE_DIR"])
    for i, key in enumerate(("velho", "meio", "novo")):
        d = storage.cache_entry(key)
        (d / "dados.bin").write_bytes(b"x" * 1000)
        os.utime(d / ".last_used", (1000 + i, 1000 + i))
    assert [e["key"] for e in storage.cache_entries()] == ["velho", "meio", "novo"]     # do menos ao mais usado
    storage.touch_cache("velho")                                                          # usado agora: passa a ser o mais novo
    assert [e["key"] for e in storage.cache_entries()][-1] == "velho"
    assert storage.enforce_cache_limit(limit=2500) == ["meio"]                            # sai o menos usado
    monkeypatch.setattr(storage, "cache_limit", lambda: 0)
    assert sorted(storage.enforce_cache_limit()) == ["novo", "velho"]
    (storage.cache_entry("x") / "d.bin").write_bytes(b"y" * 500)
    assert storage.clear_cache("x") >= 500 and not storage.cache_entries()


def test_cache_limit_from_settings(dirs):
    from ttwtools.corpus_catalog import set_setting
    assert storage.cache_limit() == storage.DEFAULT_CACHE_LIMIT_MB * 1024 * 1024
    set_setting("cache_limit_mb", 10)
    assert storage.cache_limit() == 10 * 1024 * 1024


def test_cleanup_start_and_exit(dirs):
    orphan = dirs / "ttw_work_old"
    orphan.mkdir()
    (orphan / "owner.pid").write_text("999999")
    mine = storage.workdir("pack")
    assert storage.cleanup()["orphans"] == 1 and mine.exists()          # ao iniciar: só as abandonadas
    assert storage.cleanup(exit=True)["own"] == 1 and not mine.exists()   # ao sair: as deste processo


def test_cli_cache_list_and_clear(dirs, capsys):
    storage.cache_entry("indice")
    (dirs / "ttw_work_dead").mkdir()
    (dirs / "ttw_work_dead" / "owner.pid").write_text("999999")
    assert cli_main(["cache", "list", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert {r["nome"] for r in rows} == {"indice", "ttw_work_dead"}
    assert next(r for r in rows if r["nome"] == "ttw_work_dead")["estado"] == "abandonada"
    assert cli_main(["cache", "clear", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["pastas_de_trabalho_apagadas"] == 1
    assert not storage.cache_entries() and not (dirs / "ttw_work_dead").exists()


# --- nenhum resíduo depois de abrir, salvar, exportar, cancelar e falhar -------------------------

@pytest.fixture
def project(tmp_path, corpus5):
    p = ttwtools.create_project(tmp_path / "p.ttwa")
    import_corpus(p, corpus5["CorIFAessaysNE_5"], "a")
    p._con.commit()
    yield p
    p.close()


def test_no_residue_open_save_export(project, tmp_path, no_temp_residue):
    packed = save_project_as(project.path, tmp_path / "p.ttwt")                            # salvar
    lean = save_project_as(project.path, tmp_path / "lean.ttwt", search_tables=False)      # salvar sem tabelas (pack)
    save_corpus_as(project, "a", tmp_path / "a.ttwcl")                                      # exportar
    for f in (packed, lean):                                                                # abrir (cópia de trabalho) e fechar
        with TTWAProject.open(f) as p:
            assert p.list_corpus_names() == ["a"]
    p = TTWAProject.open(packed)                                                            # e sem fechar explicitamente: close() limpa
    p.close()


def test_no_residue_on_cancel_and_failure(project, tmp_path, no_temp_residue):
    packed = save_project_as(project.path, tmp_path / "p.ttwt")

    class Cancel(Exception):
        pass

    def cancel(done, total, stage="x"):
        raise Cancel()

    with pytest.raises(Cancel):                       # cancelar ao abrir
        TTWAProject.open(packed, progress=cancel)
    with pytest.raises(Cancel):                       # cancelar ao exportar
        save_corpus_as(project, "a", tmp_path / "a.ttwc", progress_cb=cancel)
    with pytest.raises(Cancel):                       # cancelar ao salvar sem tabelas de busca
        save_project_as(project.path, tmp_path / "x.ttwt", search_tables=False, progress_cb=cancel)
    bad = tmp_path / "bad.ttwt"
    bad.write_bytes(b"\x1f\x8b" + b"lixo" * 100)      # gzip corrompido
    with pytest.raises(Exception):
        TTWAProject.open(bad)
    assert not list(tmp_path.glob("*.part"))
