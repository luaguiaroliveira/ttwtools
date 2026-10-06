"""Ajuda e traduções (passo 1.10)."""

from __future__ import annotations

import pytest

from ttwtools import cli, help as h, i18n

FIRST = ["cohens_d", "normalizacao_por_mil", "kwic", "tagset_biber", "keyness", "dispersao"]


def test_first_topics_exist_in_both_languages():
    for lang in i18n.LANGS:
        ids = {x["id"] for x in h.topics(lang)}
        assert set(FIRST) <= ids
        for topic in FIRST:
            d = h.get(topic, lang)
            assert d["lang"] == lang and not d["fallback"]
            assert d["title"] and d["summary"] and ("Como ler" in d["body"] or "How to read" in d["body"])
            assert ("Cuidados" in d["body"] or "Caveats" in d["body"])
            for rel in d["related"]:
                h.get(rel, lang)                           # relacionados existem


def test_every_topic_has_pt_and_en_or_falls_back(tmp_path, monkeypatch):
    for lang in i18n.LANGS:
        for item in h.topics(lang):
            assert h.get(item["id"], lang)["body"]
    # tópico só em inglês: cai no inglês sem erro
    only_en = tmp_path / "en" / "metricas"
    only_en.mkdir(parents=True)
    (only_en / "novo.md").write_text("---\ntitulo: New\nresumo: s\n---\nbody", encoding="utf-8")
    monkeypatch.setattr(h, "_DIR", tmp_path)
    h._index.cache_clear()
    try:
        d = h.get("novo", "pt")
        assert d["fallback"] and d["lang"] == "en" and d["title"] == "New"
        with pytest.raises(KeyError):
            h.get("nao_existe", "pt")
    finally:
        h._index.cache_clear()


def test_i18n_fallback_and_format():
    assert i18n.t("help.not_found", "pt", topic="x") == "Tópico de ajuda 'x' não encontrado."
    assert i18n.t("chave.inexistente", "pt") == "chave.inexistente"
    assert i18n.t("tagger.affects.yes", "en") == "changes the result"


def test_tour_and_search():
    assert "primeiro_corpus" in h.tours()
    tour = h.tour("primeiro_corpus", "pt")
    assert tour["title"] == "Primeiro corpus" and tour["steps"][0]["target"] == "#importar-corpus"
    assert all(s["text"] for s in tour["steps"])
    assert {x["id"] for x in h.search("desvio", "pt")} >= {"cohens_d"}


def test_cli_help(capsys):
    assert cli.main(["help", "cohens_d", "--lang", "pt"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("d de Cohen") and "Como ler" in out
    assert cli.main(["help", "--lang", "en"]) == 0
    assert "keyness" in capsys.readouterr().out
    assert cli.main(["help", "nada"]) == cli.EXIT_ERROR


def test_check_reports_problems(tmp_path, monkeypatch):
    for lang in i18n.LANGS:
        (tmp_path / lang / "metricas").mkdir(parents=True)
    (tmp_path / "pt" / "metricas" / "a.md").write_text(
        "---\ntitulo: A\nresumo: s\nrelacionados: nada\n---\n[ok]{marca azul} [ruim]{rodopio} [x]{azul} ==aberto", encoding="utf-8")
    monkeypatch.setattr(h, "_DIR", tmp_path)
    h._index.cache_clear()
    try:
        out = "\n".join(h.check())
    finally:
        h._index.cache_clear()
    assert "en/a: sem tradução" in out and "relacionado inexistente 'nada'" in out
    assert "rodopio" in out and "falta o tipo" in out and "'==' sem par" in out
    assert "[ok]" not in out


def test_shipped_help_texts_are_clean():
    assert h.check() == []


def test_help_assets_come_from_the_package():
    assert h.asset_path("kfa_big_picture.png").is_file()
    assert h.asset_path("nada.png") is None
    assert h.asset_path("../kfa.md") is None and h.asset_path("sub/x.png") is None and h.asset_path("") is None
