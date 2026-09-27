"""A referência gerada (docs/referencia.md) cobre todos os nomes públicos do pacote."""

from pathlib import Path

import ttwtools

REF = Path(__file__).resolve().parent.parent / "docs" / "referencia.md"


def test_reference_covers_public_names():
    text = REF.read_text(encoding="utf-8")
    missing = [name for name in ttwtools._EXPORTS if f"### `{name}`" not in text]
    assert not missing, f"rode python docs/gerar_referencia.py (faltam: {missing})"
    assert "sem descrição" not in text
