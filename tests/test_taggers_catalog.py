"""Descritores de opções, tagsets, disponibilidade e validação (passo 1.5)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import ttwtools
from ttwtools import cli, i18n, layers
from ttwtools.annotate import build_request, tag_corpus
from ttwtools.taggers import catalog

DATA = Path(ttwtools.__file__).parent / "data"


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in i18n.TEXT_FIELDS and isinstance(v, str):
                yield v
            else:
                yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_every_text_key_has_pt_and_en():
    files = list((DATA / "taggers").glob("*.json")) + list((DATA / "tagsets").glob("*.json"))
    assert len(files) == 8
    missing = {lang: sorted({k for f in files for k in _keys(json.loads(f.read_text()))} - set(i18n.messages(lang)))
               for lang in i18n.LANGS}
    assert missing == {"pt": [], "en": []}


def test_descriptor_fields():
    for tagger in catalog.TAGGERS:
        d = catalog.options(tagger, lang=False)
        assert set(d["presets"]) == set(catalog.PRESETS)
        for o in d["options"]:
            assert {"id", "grupo", "tipo", "padrao", "afeta_resultado", "nome", "explicacao"} <= set(o)
            assert o["grupo"] in ("modelo", "extrair", "desempenho", "avancado")
            if o["tipo"] in ("escolha", "lista"):
                assert set(o["padrao"] if o["tipo"] == "lista" else [o["padrao"]]) <= set(o["valores"])
        for values in d["presets"].values():
            catalog.validate_options(tagger, values)


def test_translations_differ_by_language():
    pt = catalog.options("spacy_upos", lang="pt")["options"][0]["explicacao"]
    en = catalog.options("spacy_upos", lang="en")["options"][0]["explicacao"]
    assert pt != en and "Modelo" in pt and "model" in en


def test_validate_options():
    catalog.validate_options("spacy", {"model": "en_core_web_sm", "components": ["pos"], "batch_size": 8})
    for bad in ({"modelo": "x"}, {"model": "nao_existe"}, {"components": ["pos", "dep"]}, {"components": []},
                {"batch_size": 0}, {"batch_size": "8"}):
        with pytest.raises(ValueError, match="opções inválidas"):
            catalog.validate_options("spacy", bad)
    with pytest.raises(ValueError):
        catalog.validate_options("mfte", {"extended": "sim"})
    with pytest.raises(ValueError, match="tagger desconhecido"):
        catalog.validate_options("nltk", {})


def test_build_request_presets_aliases_and_hash():
    fast = build_request("spacy", preset="rapido")
    assert fast["config"]["components"] == ["pos", "tag"]
    assert build_request("spacy", {"components": ["lemma", "pos"]}, preset="rapido")["config"]["components"] == ["lemma", "pos"]
    assert build_request("spacy_upos")["tool"] == "spacy"
    assert build_request("mfte_ext")["config"]["extended"] is True
    r1 = build_request("stanza", {"pos_batch_size": 10, "device": "cpu", "package": "default"})
    r2 = build_request("stanza_xpos", {"device": "cuda", "pos_batch_size": 999})
    assert r1["performance"] == {"pos_batch_size": 10, "device": "cpu"}
    assert layers.config_hash(r1["config"]) == layers.config_hash(r2["config"])       # estável, desempenho fora
    assert layers.config_hash(r1["config"]) != layers.config_hash(build_request("stanza", {"package": "gum"})["config"])
    with pytest.raises(ValueError, match="predefinição"):
        build_request("spacy", preset="turbo")


def test_tagsets():
    assert catalog.list_tagsets() == ["biber", "mfte", "ptb", "upos"]
    biber = catalog.get_tagset("biberplus")
    original = {d["tag"] for d in json.loads((DATA.parent / "tags_biber.json").read_text())}
    assert {t["tag"] for t in biber["tags"]} == original
    assert catalog.get_tagset("stanza_xpos", lang=False)["tagset"] == "ptb"
    assert catalog.get_tagset("spacy_upos")["tagset"] == "upos"
    noun = next(t for t in catalog.get_tagset("upos", lang="en")["tags"] if t["tag"] == "NOUN")
    assert noun["definition"] == "noun" and noun["example"]
    assert all(t["group"] == "modal" for t in catalog.get_tagset("mfte", group="modal")["tags"])


def test_available_reports_reason_when_torch_broken(monkeypatch):
    monkeypatch.setattr(catalog, "_torch_status", lambda: (False, ("torch_numpy", {"error": "RuntimeError: Numpy is not available"})))
    info = {a["id"]: a for a in catalog.available("pt")}
    assert info["stanza"]["disponivel"] is False and "numpy<2" in info["stanza"]["motivo"]
    assert info["mfte"]["disponivel"] is False
    assert info["spacy"]["disponivel"] == (importlib.util.find_spec("spacy") is not None)


def test_available_missing_module(monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "biberplus" else real(name, *a))
    info = {a["id"]: a for a in catalog.available("en")}
    assert info["biberplus"]["disponivel"] is False
    assert "biberplus" in info["biberplus"]["motivo"] and info["biberplus"]["comando"] == "pip install biberplus"


@pytest.fixture
def proj(tmp_path):
    with ttwtools.create_project(tmp_path / "p.ttwa") as p:
        p.add_corpus_text("c", "a.txt", "The cats were running quickly.")
        yield p


def test_spacy_options_change_behaviour(proj, spacy_model):
    tag_corpus(proj, "c", "spacy", preset="rapido")
    [layer] = proj.list_layers("c", tool="spacy")
    tok = next(t for t in proj.get_tokens(layer["id"]) if t["word"] == "cats")
    assert tok["upos"] == "NOUN" and tok["xpos"] == "NNS" and tok["lemma"] is None and tok["feats"] is None
    tag_corpus(proj, "c", "spacy", {"components": ["pos", "lemma"]})
    lemma_layer = next(l for l in proj.list_layers("c", tool="spacy") if "lemma" in l["config"]["components"])
    tok = next(t for t in proj.get_tokens(lemma_layer["id"]) if t["word"] == "cats")
    assert tok["lemma"] == "cat" and tok["xpos"] is None


def test_missing_spacy_model_gives_command(proj, spacy_model):
    if importlib.util.find_spec("en_core_web_md"):
        pytest.skip("en_core_web_md instalado")
    with pytest.raises(catalog.TaggerUnavailable) as exc:
        tag_corpus(proj, "c", "spacy", {"model": "en_core_web_md"})
    assert exc.value.command == "python -m spacy download en_core_web_md"


def test_missing_stanza_package_does_not_download(proj):
    pytest.importorskip("stanza")
    if not catalog._torch_status()[0]:
        pytest.skip("torch indisponível")
    if catalog.stanza_package_installed("en", "lines"):
        pytest.skip("pacote 'lines' já baixado")
    with pytest.raises(catalog.TaggerUnavailable) as exc:
        tag_corpus(proj, "c", "stanza", {"package": "lines"})
    assert "stanza.download('en', package='lines'" in exc.value.command
    assert not catalog.stanza_package_installed("en", "lines")


def test_cli_tagger_options_tagset_and_set(tmp_path, capsys, spacy_model):
    assert cli.main(["tagger-options", "spacy_upos", "--lang", "pt"]) == 0
    out = capsys.readouterr().out
    assert "muda o resultado" in out and "só muda a velocidade" in out and "Modelo estatístico" in out
    assert cli.main(["tagset", "biber", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["tags"]) == 95
    project = str(tmp_path / "cli.ttwa")
    with ttwtools.create_project(project) as p:
        p.add_corpus_text("c", "a.txt", "The cats sat.")
    assert cli.main(["tag", project, "--corpus", "c", "--tagger", "spacy", "--preset", "rapido",
                     "--set", 'components=["pos"]', "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["tagged"] == 1
    with ttwtools.open_project(project) as p:
        assert p.list_layers("c")[0]["config"]["components"] == ["pos"]


def test_run_with_project_and_legacy_folder(tmp_path, proj, spacy_model):
    report = ttwtools.taggers.run("spacy_upos", "c", project=proj, preset="rapido")
    assert report["tagged"] == 1
    folder = tmp_path / "txt"
    folder.mkdir()
    (folder / "a.txt").write_text("The cats sat.", encoding="utf-8")
    ttwtools.taggers.run("spacy_upos", str(folder), {"model": "en_core_web_sm"}, output_dir=str(tmp_path / "out"))
    assert list((tmp_path / "out").glob("*_rawcount.csv"))


def test_mfte_tagset_has_official_docs():
    tags = {t["tag"]: t for t in catalog.get_tagset("mfte", lang="en")["tags"]}
    jjat = tags["JJAT"]["doc"]
    assert jjat["feature"] == "Attributive adjectives" and jjat["operationalisation"] and jjat["unit"] == "Nouns"
    assert catalog.get_tagset("mfte")["doc_version"] == "1.6"
    assert sum("doc" in t for t in tags.values()) >= 150
