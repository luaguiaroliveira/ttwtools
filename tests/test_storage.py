"""Espaço livre: a operação é recusada antes de criar qualquer arquivo."""

from __future__ import annotations

import gzip
import shutil
import tempfile
from collections import namedtuple
from pathlib import Path

import pytest

import ttwtools
from ttwtools import storage
from ttwtools.corpus import import_corpus
from ttwtools.project import save_corpus_as, save_project_as, TTWAProject
from ttwtools.storage import InsufficientDiskSpace

Usage = namedtuple("Usage", "total used free")


def _residue() -> set:
    return {p.name for p in Path(tempfile.gettempdir()).glob("ttw_*")}


@pytest.fixture
def project(tmp_path, corpus5):
    p = ttwtools.create_project(tmp_path / "p.ttwa")
    import_corpus(p, corpus5["CorIFAessaysNE_5"], "a")
    yield p
    p.close()


@pytest.fixture
def full_disk(monkeypatch):
    """Disco com 1 KB livre."""
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: Usage(10**9, 10**9 - 1000, 1000))


def test_ensure_free_space_message_and_params(full_disk, tmp_path):
    with pytest.raises(InsufficientDiskSpace) as e:
        storage.ensure_free_space(tmp_path / "ainda" / "nao" / "existe", 5_000_000, "export")
    assert e.value.params == {"what": "export", "needed_mb": 5, "free_mb": 0, "path": str(tmp_path / "ainda" / "nao" / "existe")}
    assert "exportar" in str(e.value) and e.value.code == "insufficient_disk_space"
    storage.ensure_free_space(tmp_path, 900, "save")            # cabe: não levanta


def test_estimate_open_reads_gzip_header(tmp_path):
    raw = tmp_path / "x.bin"
    raw.write_bytes(b"a" * 5_000_000)
    z = tmp_path / "x.gz"
    with gzip.open(z, "wb") as fh:
        fh.write(raw.read_bytes())
    assert storage.gzip_uncompressed_size(z) == 5_000_000
    assert storage.estimate_open(z) == storage.with_margin(5_000_000)
    assert storage.gzip_uncompressed_size(raw) is None
    assert storage.estimate_open(raw) == storage.with_margin(3 * 5_000_000)     # sem cabeçalho: 3×


@pytest.mark.parametrize("search_tables", [True, False])
def test_save_refused_before_creating_anything(project, tmp_path, full_disk, search_tables):
    project._con.commit()
    dest = tmp_path / "novo" / "sub" / "out.ttwa"
    residue = _residue()
    with pytest.raises(InsufficientDiskSpace):
        save_project_as(project.path, dest, search_tables=search_tables)
    assert not dest.parent.exists() and _residue() == residue


def test_export_subset_refused(project, tmp_path, full_disk):
    dest = tmp_path / "saida" / "a.ttwc"
    residue = _residue()
    with pytest.raises(InsufficientDiskSpace):
        save_corpus_as(project, "a", dest)
    assert not dest.parent.exists() and _residue() == residue


def test_open_compressed_refused_without_leftovers(project, tmp_path, monkeypatch):
    project._con.commit()
    packed = save_project_as(project.path, tmp_path / "p.ttwt")
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: Usage(10**9, 10**9 - 1000, 1000))
    residue = _residue()
    with pytest.raises(InsufficientDiskSpace) as e:
        TTWAProject.open(packed)
    assert e.value.what == "open" and _residue() == residue      # a pasta de trabalho não fica


def test_import_refused_and_nothing_imported(project, tmp_path, corpus5, full_disk):
    before = project.list_corpus_names()
    with pytest.raises(InsufficientDiskSpace):
        import_corpus(project, corpus5["essays_bawe_somentetexto_5"], "b")
    assert project.list_corpus_names() == before


def test_enough_space_works_and_leaves_no_residue(project, tmp_path):
    project._con.commit()
    residue = _residue()
    out = save_project_as(project.path, tmp_path / "ok.ttwt")
    with TTWAProject.open(out) as p:
        assert p.list_corpus_names() == ["a"]
    assert _residue() == residue
