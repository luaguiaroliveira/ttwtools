"""Lista de arquivos recentes."""

from __future__ import annotations

from ttwtools import cli, recent


def test_add_list_remove_clear(tmp_path, monkeypatch):
    monkeypatch.setenv("TTWTOOLS_HOME", str(tmp_path / "cfg"))
    a, b = tmp_path / "a.ttwa", tmp_path / "b.ttwcl"
    a.write_text("x"); b.write_text("x")
    recent.add(a); recent.add(b); recent.add(a); recent.add(tmp_path / "outro.txt")
    rows = recent.listing()
    assert [r["name"] for r in rows] == ["a.ttwa", "b.ttwcl"] and rows[0]["exists"]
    b.unlink()
    assert not recent.listing()[1]["exists"]
    recent.remove(str(b))
    assert [r["name"] for r in recent.listing()] == ["a.ttwa"]
    recent.clear()
    assert recent.listing() == []


def test_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("TTWTOOLS_HOME", str(tmp_path))
    for i in range(recent.MAX_RECENT + 5):
        recent.add(tmp_path / f"p{i}.ttwa")
    assert len(recent.listing()) == recent.MAX_RECENT


def test_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TTWTOOLS_HOME", str(tmp_path))
    recent.add(tmp_path / "z.ttwc")
    assert cli.main(["recent", "--json"]) == 0
    assert "z.ttwc" in capsys.readouterr().out
