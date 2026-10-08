

def test_til_no_caminho_do_projeto(tmp_path, monkeypatch):
    """~ no caminho vira a pasta pessoal (antes: 'unable to open database file')."""
    import ttwtools
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))   # Windows
    ttwtools.create_project("~/novo.ttwa").close()
    assert (tmp_path / "novo.ttwa").exists()
    ttwtools.open_project("~/novo.ttwa").close()


def test_sobrescrever_apaga_restos_do_sqlite(tmp_path):
    import ttwtools
    p = tmp_path / "p.ttwa"
    ttwtools.create_project(p).close()
    (tmp_path / "p.ttwa-journal").write_bytes(b"lixo")
    ttwtools.create_project(p, overwrite=True).close()
    assert not (tmp_path / "p.ttwa-journal").exists()
    ttwtools.open_project(p).close()


def test_migracao_com_progresso_e_retomada(tmp_path, monkeypatch):
    """Interrompida no meio, a migração v0.3 continua de onde parou e dá o mesmo resultado."""
    import shutil
    from pathlib import Path
    import warnings
    import pytest
    import ttwtools
    from ttwtools import project as P
    src = Path(__file__).parent / "data" / "v2_small.ttwa"
    a, b = tmp_path / "a.ttwa", tmp_path / "b.ttwa"
    shutil.copy(src, a)
    shutil.copy(src, b)
    assert ttwtools.needs_migration(a)
    warnings.simplefilter("ignore")

    seen = []
    ref = ttwtools.open_project(a, progress=lambda d, t, m: seen.append((d, t, m)))
    total = seen[-1][1]
    assert seen[-1][2] == "indexes" and any(m == "layers" for _d, _t, m in seen)
    expected = ref._con.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
    ref.close()
    assert not ttwtools.needs_migration(a)

    monkeypatch.setattr(P, "_MIGRATION_BATCH", 1)
    real, calls = P.TTWAProject._index_tagged, {"n": 0}

    def boom(self, *args):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt("fechou a janela")
        return real(self, *args)
    monkeypatch.setattr(P.TTWAProject, "_index_tagged", boom)
    with pytest.raises(KeyboardInterrupt):
        ttwtools.open_project(b)
    monkeypatch.setattr(P.TTWAProject, "_index_tagged", real)
    resumed = []
    proj = ttwtools.open_project(b, progress=lambda d, t, m: resumed.append(d))
    assert resumed[0] > 0 and resumed[-1] == total            # não recomeçou do zero
    assert proj._con.execute("SELECT COUNT(*) FROM tokens").fetchone()[0] == expected
    assert proj.get_meta("migration_v3.last_tagged_id") is None
    names = {r[0] for r in proj._con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {n for n, _ in P._TOKEN_INDEXES} <= names
    proj.close()


def test_salvar_como_inclui_alteracoes_recentes(tmp_path):
    """Com o projeto aberto (WAL), a cópia e o .ttwt levam o que ainda não foi consolidado."""
    import ttwtools
    from ttwtools.project import decompress_from_ttwt
    src = tmp_path / "a.ttwa"
    proj = ttwtools.create_project(src)
    proj.add_corpus_file("c", _txt(tmp_path, "t1.txt", "um texto"))
    proj._con.commit()
    seen = []
    for dest in (tmp_path / "b.ttwa", tmp_path / "c.ttwt"):
        ttwtools.save_project_as(src, dest, progress_cb=lambda d, t: seen.append((d, t)))
    proj.close()
    assert seen and seen[-1][0] == seen[-1][1]
    with ttwtools.open_project(tmp_path / "b.ttwa") as b:
        assert b.list_corpus_names() == ["c"]
    decompress_from_ttwt(tmp_path / "c.ttwt", tmp_path / "d.ttwa")
    with ttwtools.open_project(tmp_path / "d.ttwa") as d:
        assert d.list_corpus_names() == ["c"]
    assert not list(tmp_path.glob("*.part"))


def _txt(folder, name, text):
    f = folder / name
    f.write_text(text, encoding="utf-8")
    return f
