

def test_til_no_caminho_do_projeto(tmp_path, monkeypatch):
    """~ no caminho vira a pasta pessoal (antes: 'unable to open database file')."""
    import ttwtools
    monkeypatch.setenv("HOME", str(tmp_path))
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
