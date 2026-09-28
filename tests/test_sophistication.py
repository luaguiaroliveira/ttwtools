"""Testes da riqueza lexical (Fase C)."""
from __future__ import annotations

from ttwtools.sophistication import lexical_profile, mtld


def test_lexical_profile_basico():
    text = "the cat sat on the mat. the dog ate the bone. " * 20
    p = lexical_profile(text)
    assert p["words"] > 100
    assert 0 < p["ttr"] <= 1
    assert p["sentences"] == 40
    assert p["mtld"] is None or p["mtld"] > 0
    assert 0 <= p["long_pct"] <= 100


def test_mtld_texto_curto_none():
    assert mtld(["a", "b", "c"]) is None


def test_mtld_texto_variado_maior_que_repetitivo():
    repet = ["palavra"] * 200
    variado = [f"w{i % 50}" for i in range(200)]      # 50 tipos repetidos
    m_rep, m_var = mtld(repet), mtld(variado)
    assert m_rep is not None and m_var is not None
    assert m_var > m_rep
