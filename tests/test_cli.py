"""Linha de comando: --version, subcomandos e formatos de saída."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

import ttwtools
from ttwtools import cli


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"ttwtools {ttwtools.__version__}"


def test_python_m_version():
    out = subprocess.run([sys.executable, "-m", "ttwtools", "--version"], capture_output=True, text=True)
    assert out.returncode == 0 and ttwtools.__version__ in out.stdout


@pytest.mark.parametrize("command", list(cli.COMMANDS))
def test_subcommands_not_implemented(command, capsys):
    assert cli.main([command, "--json"]) == cli.EXIT_NOT_IMPLEMENTED
    data = json.loads(capsys.readouterr().out)
    assert data["command"] == command and data["status"] == "not_implemented"


def test_no_command_prints_help(capsys):
    assert cli.main([]) == cli.EXIT_OK
    assert "<comando>" in capsys.readouterr().out


ROWS = [{"palavra": "casa", "freq": 12, "por_mil": 3.14159}, {"palavra": "rua", "freq": 3, "por_mil": 0.5}]


def test_emit_table(capsys):
    cli.emit(ROWS)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["palavra", "freq", "por_mil"]
    assert lines[2].split() == ["casa", "12", "3.142"]


def test_emit_csv(capsys):
    cli.emit(ROWS, "csv")
    assert capsys.readouterr().out.splitlines() == ["palavra,freq,por_mil", "casa,12,3.14159", "rua,3,0.5"]


def test_emit_json(capsys):
    cli.emit(ROWS, "json")
    assert json.loads(capsys.readouterr().out) == ROWS


def test_emit_dict_and_empty(capsys):
    cli.emit({"arquivos": 5})
    assert "arquivos" in capsys.readouterr().out
    cli.emit([])
    assert "nenhum resultado" in capsys.readouterr().out
