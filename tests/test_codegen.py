"""'Copiar como código': o comando gerado dá o mesmo resultado que a função."""

from __future__ import annotations

import json
import shlex

import pytest

import ttwtools
from ttwtools import cli
from ttwtools.codegen import cli_command, python_code


@pytest.fixture
def proj(tmp_path):
    path = tmp_path / "meu projeto.ttwa"
    with ttwtools.create_project(path) as p:
        p.add_corpus_text("c", "a.txt", "The black cat sat. The cat ran. A dog sat.")
        p.add_corpus_text("c", "b.txt", "Black dogs and black cats.")
        ttwtools.tag_corpus(p, "c", "simple")
    return path


CASES = [
    ("kwic", {"corpus": "c", "query": "cat", "context": 2, "limit": 5}, lambda p: ttwtools.kwic(p, "c", "cat", context=2, limit=5)),
    ("search", {"corpus": "c", "query": "black"}, lambda p: ttwtools.search(p, "c", "black")),
    ("frequency", {"corpus": "c", "unit": "form", "top": 3}, lambda p: ttwtools.frequency(p, "c", "form", top=3)),
    ("collocates", {"corpus": "c", "node": "cat", "left": 1, "right": 1, "min_freq": 1},
     lambda p: ttwtools.collocates(p, "c", "cat", window=(1, 1), min_freq=1)),
    ("dispersion", {"corpus": "c", "query": "sat"}, lambda p: ttwtools.dispersion(p, "c", "sat")),
]


@pytest.mark.parametrize("analysis,params,fn", CASES)
def test_cli_command_reproduces_function(proj, analysis, params, fn, capsys):
    cmd = cli_command(analysis, str(proj), params)
    assert cmd.startswith(f"ttwtools {'freq' if analysis == 'frequency' else analysis} ")
    assert "'" in cmd                                           # caminho com espaço vem entre aspas
    assert cli.main(shlex.split(cmd)[1:] + ["--json"]) == 0
    from_cli = json.loads(capsys.readouterr().out)
    with ttwtools.open_project(proj) as p:
        expected = json.loads(json.dumps(fn(p), default=str))
    assert from_cli == expected


@pytest.mark.parametrize("analysis,params,fn", CASES)
def test_python_code_runs(proj, analysis, params, fn):
    code = python_code(analysis, str(proj), params)
    ns: dict = {}
    exec(code, ns)
    with ttwtools.open_project(proj) as p:
        assert json.loads(json.dumps(ns["result"], default=str)) == json.loads(json.dumps(fn(p), default=str))


def test_tag_and_where_and_windows_quoting():
    cmd = cli_command("tag", "p.ttwa", {"corpus": "c", "tagger": "spacy", "preset": "rapido",
                                          "options": {"model": "en_core_web_sm", "components": ["pos"]},
                                          "where": {"grupo": ["A", "B"]}})
    assert cmd == ("ttwtools tag p.ttwa --corpus c --tagger spacy --preset rapido --set model=en_core_web_sm "
                   "--set 'components=[\"pos\"]' --where grupo=A --where grupo=B")
    win = cli_command("kwic", "C:\\meus dados\\p.ttwa", {"corpus": "c", "query": "cat"}, windows=True)
    assert win == 'ttwtools kwic "C:\\meus dados\\p.ttwa" cat --corpus c'
    with pytest.raises(ValueError):
        cli_command("nada", "p", {})
