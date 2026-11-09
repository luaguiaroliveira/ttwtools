"""Lista "a executar": camadas escolhidas agora e executadas depois (ttwtools.pipeline)."""
from pathlib import Path

import pytest

import ttwtools

CORPUS = Path(__file__).resolve().parents[1] / "examples" / "test_corpora" / "CorIFAessaysNE_5"


@pytest.fixture
def proj(tmp_path):
    p = ttwtools.create_project(tmp_path / "p.ttwa")
    ttwtools.import_corpus(p, CORPUS, "c")
    yield p
    p.close()


def test_montar_guardar_e_remover(proj, tmp_path):
    assert ttwtools.pending_steps(proj, "c") == []
    ttwtools.add_step(proj, "c", {"kind": "stats"})
    ttwtools.add_step(proj, "c", {"kind": "tag", "tagger": "biberplus"})
    ttwtools.add_step(proj, "c", {"kind": "stats"})                      # repetido não entra
    assert [s["kind"] for s in ttwtools.pending_steps(proj, "c")] == ["tag", "stats"]    # ordem de execução
    proj.close()
    with ttwtools.open_project(tmp_path / "p.ttwa") as again:           # fica guardada no projeto
        assert len(ttwtools.pending_steps(again, "c")) == 2
        assert ttwtools.remove_step(again, "c", 1) == [{"kind": "tag", "tagger": "biberplus", "options": {}}]
    with pytest.raises(ValueError):
        ttwtools.add_step(ttwtools.open_project(tmp_path / "p.ttwa"), "c", {"kind": "nada"})


def test_corpus_inexistente(proj):
    with pytest.raises(ValueError):
        ttwtools.add_step(proj, "outro", {"kind": "stats"})


def test_executar_etiqueta_antes_das_estatisticas(proj):
    pytest.importorskip("spacy")
    ttwtools.add_step(proj, "c", {"kind": "stats"})
    ttwtools.add_step(proj, "c", {"kind": "tag", "tagger": "spacy", "preset": "rapido"})
    calls = []
    r = ttwtools.run_steps(proj, "c", progress=lambda d, t, m: calls.append(m))
    assert [d["step"]["kind"] for d in r["done"]] == ["tag", "stats"] and r["remaining"] == []
    assert "spacy" in r["done"][1]["report"]["layers"]
    assert ttwtools.describe(proj, "c", layer="spacy", cache_only=True) is not None
    assert ttwtools.pending_steps(proj, "c") == []


def test_andamento_por_passo(proj):
    pytest.importorskip("spacy")
    ttwtools.add_step(proj, "c", {"kind": "tag", "tagger": "spacy", "preset": "rapido"})
    ttwtools.add_step(proj, "c", {"kind": "stats"})
    seen = []
    ttwtools.run_steps(proj, "c", on_step=lambda i, st: seen.append((i, st["status"], st["done"], st["total"])))
    assert (0, "running", 5, 5) in seen and (0, "done", 1, 1) in seen
    assert seen[-1] == (1, "done", 1, 1) and any(s[0] == 1 and s[1] == "running" and s[3] for s in seen)


@pytest.fixture
def doiscorpora(proj):
    ttwtools.import_corpus(proj, CORPUS, "d")
    return proj


def test_lista_de_todos_os_corpora(doiscorpora):
    assert ttwtools.pending_steps_all(doiscorpora) == {}
    ttwtools.add_step(doiscorpora, "c", {"kind": "stats"})
    assert list(ttwtools.pending_steps_all(doiscorpora)) == ["c"]           # só os que têm passos
    r = ttwtools.add_step_all(doiscorpora, {"kind": "tag", "tagger": "biberplus"})
    assert set(r) == {"c", "d"}
    assert [s["kind"] for s in r["d"]] == ["tag"]
    assert [s["kind"] for s in r["c"]] == ["tag", "stats"]                  # na ordem em que roda
    assert list(ttwtools.pending_steps_all(doiscorpora, ["d"])) == ["d"]
    with pytest.raises(ValueError):
        ttwtools.add_step_all(doiscorpora, {"kind": "stats"}, ["d", "outro"])


def test_executar_todos_os_corpora(doiscorpora):
    ttwtools.add_step_all(doiscorpora, {"kind": "stats"})
    seen, progress = [], []
    r = ttwtools.run_all(doiscorpora, on_step=lambda i, st: seen.append((i, st["corpus"], st["status"])),
                         progress=lambda d, t, m: progress.append((d, t, m)))
    assert [(d["corpus"], d["step"]["kind"]) for d in r["done"]] == [("c", "stats"), ("d", "stats")]
    assert r["remaining"] == {} and ttwtools.pending_steps_all(doiscorpora) == {}
    assert progress[-1][:2] == (2, 2)
    assert {(i, c) for i, c, _ in seen} == {(0, "c"), (1, "d")}
    assert all(m.startswith(("c: ", "d: ")) for _, _, m in progress)       # a mensagem diz o corpus
