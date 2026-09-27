

def test_til_no_caminho_do_projeto(tmp_path, monkeypatch):
    """~ no caminho vira a pasta pessoal (antes: 'unable to open database file')."""
    import ttwtools
    monkeypatch.setenv("HOME", str(tmp_path))
    ttwtools.create_project("~/novo.ttwa").close()
    assert (tmp_path / "novo.ttwa").exists()
    ttwtools.open_project("~/novo.ttwa").close()
