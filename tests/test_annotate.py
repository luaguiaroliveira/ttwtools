"""Camadas e cache: etiquetar duas vezes não reprocessa; opção de desempenho não
invalida; modelo invalida; suficiência por componentes; retomada."""

from __future__ import annotations

import json
import re

import pytest

import ttwtools
from ttwtools import cli
from ttwtools.annotate import build_request, find_layer, tag_corpus
from ttwtools.backends import BACKENDS, Backend, register_backend
from ttwtools.corpus import filter_documents, import_corpus
from ttwtools.layers import layer_satisfies


class FakeBackend(Backend):
    """Tagger de mentira: uma etiqueta por palavra, e conta quantas vezes foi chamado."""
    name = "fake"
    defaults = {"model": "m1", "upper": False}
    components = ("pos", "lemma")
    default_components = ("pos",)

    def __init__(self):
        self.calls = 0
        self.fail_on: str | None = None

    def tool_version(self):
        return "1.0"

    def model(self, options):
        return options["model"]

    def tag(self, text, options, components):
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("falha simulada")
        self.calls += 1
        out = []
        for m in re.finditer(r"\w+", text):
            tok = {"start_char": m.start(), "end_char": m.end(), "word": m.group(), "upos": "X", "tags": []}
            if "lemma" in components:
                tok["lemma"] = m.group().lower()
            out.append(tok)
        return out


@pytest.fixture
def fake():
    backend = FakeBackend()
    register_backend(backend)
    yield backend
    BACKENDS.pop("fake", None)


@pytest.fixture
def proj(tmp_path):
    with ttwtools.create_project(tmp_path / "p.ttwa") as p:
        for i, text in enumerate(["The cat sat.", "A dog ran fast.", "Birds fly high."], 1):
            p.add_corpus_text("c", f"t{i}.txt", text)
        yield p


def test_second_run_does_not_call_tagger(proj, fake):
    r1 = tag_corpus(proj, "c", "fake")
    assert (r1["tagged"], r1["reused"], fake.calls) == (3, 0, 3)
    r2 = tag_corpus(proj, "c", "fake")
    assert (r2["tagged"], r2["reused"], fake.calls) == (0, 3, 3)
    assert r2["layer_ids"] == r1["layer_ids"]
    layer = proj.list_layers("c", tool="fake")[0]
    assert layer["config"]["components"] == ["pos"] and layer["config"]["model"] == "m1"
    assert [t["word"] for t in proj.get_tokens(layer["id"])] == ["The", "cat", "sat"]


def test_performance_option_does_not_invalidate(proj, fake):
    tag_corpus(proj, "c", "fake", {"batch_size": 8, "n_processes": 1})
    r = tag_corpus(proj, "c", "fake", {"batch_size": 256, "n_processes": 4})
    assert r["reused"] == 3 and fake.calls == 3


def test_model_or_result_option_invalidates(proj, fake):
    tag_corpus(proj, "c", "fake")
    assert tag_corpus(proj, "c", "fake", {"model": "m2"})["tagged"] == 3
    assert tag_corpus(proj, "c", "fake", {"upper": True})["tagged"] == 3
    assert fake.calls == 9
    assert len(proj.list_layers("c", tool="fake")) == 9


def test_components_sufficiency(proj, fake):
    tag_corpus(proj, "c", "fake", components=["pos", "lemma"])
    assert tag_corpus(proj, "c", "fake", components=["pos"])["reused"] == 3      # mais atende menos
    assert fake.calls == 3
    with ttwtools.create_project(proj.path.with_name("q.ttwa")) as q:
        q.add_corpus_text("c", "t.txt", "Only pos here.")
        tag_corpus(q, "c", "fake", components=["pos"])
        assert tag_corpus(q, "c", "fake", components=["pos", "lemma"])["tagged"] == 1   # menos não atende mais


def test_layer_satisfies_rule():
    layer = {"model": "m", "components": ["lemma", "pos"], "batch_size": 8}
    assert layer_satisfies(layer, {"model": "m", "components": ["pos"], "batch_size": 64})
    assert not layer_satisfies(layer, {"model": "m", "components": ["pos", "morph"]})
    assert not layer_satisfies(layer, {"model": "n", "components": ["pos"]})


def test_resume_after_interruption(proj, fake):
    fake.fail_on = "dog"
    with pytest.raises(RuntimeError):
        tag_corpus(proj, "c", "fake")
    assert fake.calls == 1                        # t1 gravado antes da falha
    fake.fail_on = None
    r = tag_corpus(proj, "c", "fake")
    assert (r["reused"], r["tagged"]) == (1, 2)


def test_same_text_in_other_corpus_is_cloned(proj, fake):
    tag_corpus(proj, "c", "fake")
    proj.add_corpus_text("d", "copia.txt", "The cat sat.")
    r = tag_corpus(proj, "d", "fake")
    assert (r["cloned"], r["tagged"], fake.calls) == (1, 0, 3)
    [layer] = proj.list_layers("d")
    assert [t["word"] for t in proj.get_tokens(layer["id"])] == ["The", "cat", "sat"]


def test_changed_text_is_retagged(tmp_path, fake):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("One two.", encoding="utf-8")
    with ttwtools.create_project(tmp_path / "l.ttwl") as p:
        import_corpus(p, src, "c")
        tag_corpus(p, "c", "fake")
        (src / "a.txt").write_text("One two three.", encoding="utf-8")
        p.relink_corpus(src, accept_changed=True)
        assert tag_corpus(p, "c", "fake")["tagged"] == 1


def test_where_filter_and_missing_text(tmp_path, fake):
    src = tmp_path / "src"
    src.mkdir()
    for n in ("A_1.txt", "B_1.txt"):
        (src / n).write_text(f"Some words in {n}.", encoding="utf-8")   # textos diferentes: sem cópia
    with ttwtools.create_project(tmp_path / "l.ttwl") as p:
        import_corpus(p, src, "c", filename_fields=["grupo", "n"])
        assert tag_corpus(p, "c", "fake", where={"grupo": "A"})["tagged"] == 1
        (src / "B_1.txt").unlink()
        r = tag_corpus(p, "c", "fake")
        assert r["reused"] == 1 and r["missing_text"] == ["B_1.txt"]


def test_unknown_option_and_component(fake):
    with pytest.raises(ValueError, match="opções desconhecidas"):
        build_request("fake", {"nope": 1})
    with pytest.raises(ValueError, match="componentes indisponíveis"):
        build_request("fake", components=["morph"])
    with pytest.raises(ValueError, match="tagger desconhecido"):
        build_request("nao_existe")


def test_cli_tag(tmp_path, fake, capsys):
    project = str(tmp_path / "cli.ttwa")
    with ttwtools.create_project(project) as p:
        p.add_corpus_text("c", "a.txt", "Hello there.")
    assert cli.main(["tag", project, "--corpus", "c", "--tagger", "fake", "--option", "upper=true", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["tagged"] == 1
    assert cli.main(["tag", project, "--corpus", "c", "--tagger", "fake", "--option", "upper=true", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["reused"] == 1


def test_spacy_backend_gives_lemma_upos_feats(proj, spacy_model, monkeypatch):
    spacy_backend = BACKENDS["spacy"]
    calls = {"n": 0}
    original = type(spacy_backend).tag

    def counting(self, *a, **k):
        calls["n"] += 1
        return original(self, *a, **k)

    monkeypatch.setattr(type(spacy_backend), "tag", counting)
    assert tag_corpus(proj, "c", "spacy")["tagged"] == 3
    layer = proj.list_layers("c", tool="spacy")[0]
    assert layer["model"] == "en_core_web_sm" and layer["config"]["model_version"]
    toks = proj.get_tokens(layer["id"])
    cat = next(t for t in toks if t["word"] == "cat")
    assert cat["upos"] == "NOUN" and cat["xpos"] == "NN" and cat["lemma"] == "cat" and "Number=Sing" in cat["feats"]
    text = proj.get_corpus_file("c", layer["filename"])
    assert all(text[t["start_char"]:t["end_char"]] == t["word"] for t in toks)
    # só POS: atendido pela camada completa, sem chamar o spaCy
    assert tag_corpus(proj, "c", "spacy", components=["pos"])["reused"] == 3
    assert calls["n"] == 3


def test_biberplus_backend(proj, spacy_model):
    r = tag_corpus(proj, "c", "biberplus", {"n_processes": 1})
    assert r["tagged"] == 3
    layer = proj.list_layers("c", tool="biberplus")[0]
    toks = proj.get_tokens(layer["id"])
    assert toks and all(isinstance(t["tags"], list) for t in toks) and any(t["tags"] for t in toks)


def test_plan_tagging(proj, fake):
    from ttwtools.annotate import plan_tagging
    p = plan_tagging(proj, "c", "fake")
    assert (p["documents"], p["reusable"], p["to_tag"]) == (3, 0, 3)
    tag_corpus(proj, "c", "fake", where=None, filenames=["t1.txt"])
    proj.add_corpus_text("d", "copia.txt", "The cat sat.")
    p = plan_tagging(proj, "c", "fake")
    assert (p["reusable"], p["to_tag"]) == (1, 2)
    assert plan_tagging(proj, "d", "fake")["clonable"] == 1
    assert fake.calls == 1                              # o plano não chama o tagger


def test_value_availability():
    from ttwtools.taggers import value_availability
    import importlib.util
    av = value_availability("spacy_upos")["model"]
    assert av["en_core_web_sm"]["installed"] == (importlib.util.find_spec("en_core_web_sm") is not None)
    assert av["en_core_web_lg"]["command"] == "python -m spacy download en_core_web_lg"
