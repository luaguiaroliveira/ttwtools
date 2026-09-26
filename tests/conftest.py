"""Fixtures comuns: corpus pequeno (5 textos por grupo) copiado para pasta temporária."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent
# Corpora de exemplo do próprio pacote; TTWTOOLS_TEST_CORPORA permite apontar outra pasta
# com a mesma estrutura (ex.: test_corpora/5 do ttwtools-app).
CORPORA = Path(os.environ.get("TTWTOOLS_TEST_CORPORA", PKG_ROOT / "examples" / "test_corpora"))
GROUPS = ("CorIFAessaysNE_5", "essays_bawe_somentetexto_5")


@pytest.fixture
def corpus5(tmp_path) -> dict[str, Path]:
    """Cópia de test_corpora/5: {nome do grupo: pasta com 5 .txt}."""
    missing = [g for g in GROUPS if not (CORPORA / g).is_dir()]
    if missing:
        pytest.skip(f"corpora de teste ausentes em {CORPORA}: {missing}")
    out = {}
    for group in GROUPS:
        dest = tmp_path / "corpora" / group
        shutil.copytree(CORPORA / group, dest)
        out[group] = dest
    return out


@pytest.fixture(scope="session")
def spacy_model():
    spacy = pytest.importorskip("spacy")
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        pytest.skip("modelo en_core_web_sm não instalado")
