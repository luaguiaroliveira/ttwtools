"""Pacotes de corpus, catálogo e instalação (passos 4.1 e 4.2)."""

from __future__ import annotations

import json
import zipfile

import pytest

import ttwtools
from ttwtools import cli
from ttwtools import corpus_catalog as cc

FICHA = {"id": "demo", "name": "Demo", "version": "1.0", "lang": "en", "variety": "en-GB", "period": "2000s",
         "genres": ["ensaio"], "source": {"url": "https://example.org", "citation": "Demo corpus"},
         "license": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/",
                     "redistributable": True, "verified_on": "2026-09-26"}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TTWTOOLS_DATA_DIR", str(tmp_path / "dados"))
    proj = tmp_path / "demo.ttwa"
    with ttwtools.create_project(proj) as p:
        for i in range(3):
            p.add_corpus_text("demo", f"t{i}.txt", f"The cat number {i} sat on the mat. Dogs ran.")
        ttwtools.tag_corpus(p, "demo", "simple")
    entry = cc.make_package(proj, tmp_path / "pub", FICHA)
    catalog = tmp_path / "pub" / "catalogo.json"
    cc.write_catalog([entry], catalog)
    return {"tmp": tmp_path, "entry": entry, "catalog": str(catalog)}


def test_package_contents_and_ficha(env):
    entry = env["entry"]
    assert entry["url"] == "demo-1.0.zip" and len(entry["sha256"]) == 64
    with zipfile.ZipFile(env["tmp"] / "pub" / entry["url"]) as z:
        names = set(z.namelist())
        ficha = json.loads(z.read("ficha.json"))
    assert {"ficha.json", "corpus.ttwa", "referencia-form.tsv"} <= names
    assert ficha["size"] == {"documents": 3, "words": 27}      # 9 palavras por texto (números fora) and ficha["layers"][0]["tool"] == "simple"
    assert set(ficha["files"]) == names - {"ficha.json"}


def test_license_rule():
    bad = dict(FICHA, license={"name": "restrita", "redistributable": False})
    errors = cc.validate_ficha(bad)
    assert any("verified_on" in e for e in errors) and any("redistribuir" in e for e in errors)
    catalog = {"format": cc.CATALOG_FORMAT, "packages": [{"id": "x", "version": "1", "kind": "recipe", "ficha": dict(bad, id="x", version="1")}]}
    assert cc.validate_catalog(catalog) == []                    # receita pode ter licença restrita
    catalog["packages"][0]["kind"] = "package"
    assert cc.validate_catalog(catalog)
    with pytest.raises(ValueError):
        cc.write_catalog(catalog["packages"], "/tmp/x.json")


def test_install_open_remove_and_updates(env):
    item = cc.install("demo", catalog=cc.load_catalog(env["catalog"]))
    assert item["project"] and item["reference_lists"]
    with ttwtools.open_project(item["project"]) as p:
        assert ttwtools.search(p, "demo", "cat")["total"] == 3
    assert [i["id"] for i in cc.installed()] == ["demo"]
    newer = dict(env["entry"], version="1.1", ficha=dict(env["entry"]["ficha"], version="1.1"))
    cc.write_catalog([env["entry"], newer], env["catalog"])
    assert cc.updates(cc.load_catalog(env["catalog"])) == [{"id": "demo", "installed": "1.0", "latest": "1.1"}]
    assert cc.remove("demo") == 1 and cc.installed() == []


def test_hash_mismatch_is_refused(env):
    cat = cc.load_catalog(env["catalog"])
    cat["packages"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        cc.install("demo", catalog=cat)
    assert cc.installed() == []


def test_keywords_against_installed_reference_list(env, tmp_path):
    item = cc.install("demo", catalog=cc.load_catalog(env["catalog"]))
    ref = next(p for p in item["reference_lists"] if p.endswith("form.tsv"))
    with ttwtools.create_project(tmp_path / "meu.ttwa") as p:
        p.add_corpus_text("meu", "a.txt", "Zebras zebras zebras and a cat.")
        r = ttwtools.keywords(p, "meu", ref, min_freq=1)
    assert r["rows"][0]["item"] == "zebras" and r["reference"] == "Demo 1.0"


def test_cli_catalog(env, capsys):
    assert cli.main(["catalog", "list", "--url", env["catalog"], "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == "demo"
    assert cli.main(["catalog", "install", "demo", "--url", env["catalog"], "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["versão"] == "1.0"
    assert cli.main(["catalog", "validate", env["catalog"]]) == 0
    assert cli.main(["catalog", "remove", "demo", "--json"]) == 0
