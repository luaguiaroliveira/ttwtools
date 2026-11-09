"""Importação de corpus, metadados por documento, tokenização simples e filtros."""

from __future__ import annotations

import json

import pytest

import ttwtools
from ttwtools import cli
from ttwtools.corpus import (
    TokenizerConfig, filter_documents, get_document_meta, get_tokenizer_config, import_corpus,
    list_groups, meta_from_filename, metadata_keys, parse_where, tokenize,
)

TEXTS = {
    "grupoA_texto01.txt": "The cat sat on the mat. It's 3 o'clock!",
    "grupoA_texto02.txt": "Dogs don't like cats, do they?",
    "grupoB_texto01.txt": "In 2026, 3,5 million people read books.",
}


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "textos"
    d.mkdir()
    for name, text in TEXTS.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


@pytest.fixture
def proj(tmp_path):
    with ttwtools.create_project(tmp_path / "p.ttwa") as p:
        yield p


def test_meta_from_filename():
    assert meta_from_filename("grupoA_texto01.txt", ["grupo", "texto"]) == {"grupo": "grupoA", "texto": "texto01"}
    assert meta_from_filename("a-b-c-d.txt", ["x", "resto"], "-") == {"x": "a", "resto": "b-c-d"}
    assert meta_from_filename("sozinho.txt", ["grupo", "texto"]) == {"grupo": "sozinho"}


def test_import_folder_with_filename_groups_and_filter(proj, folder):
    report = import_corpus(proj, folder, "ensaios", filename_fields=["grupo", "texto"])
    assert report["imported"] == 3 and report["metadata_applied"] == 3
    assert get_document_meta(proj, "ensaios", "grupoB_texto01.txt") == {"grupo": "grupoB", "texto": "texto01"}
    assert list_groups(proj, "ensaios", "grupo") == {"grupoA": 2, "grupoB": 1}
    only_a = filter_documents(proj, "ensaios", {"grupo": "grupoA"})
    assert [d["filename"] for d in only_a] == ["grupoA_texto01.txt", "grupoA_texto02.txt"]
    assert only_a[0]["meta"]["texto"] == "texto01"
    both = filter_documents(proj, "ensaios", {"grupo": ["grupoA", "grupoB"], "texto": "texto01"})
    assert [d["filename"] for d in both] == ["grupoA_texto01.txt", "grupoB_texto01.txt"]
    assert metadata_keys(proj, "ensaios") == ["grupo", "texto"]


def test_import_with_metadata_csv(proj, folder, tmp_path):
    meta = tmp_path / "meta.csv"
    meta.write_text("filename;nivel;ano\ngrupoA_texto01;B2;2016\ngrupoB_texto01.txt;C1;2017\nnao_existe.txt;A1;2000\n",
                    encoding="utf-8-sig")
    report = import_corpus(proj, folder, "ensaios", metadata_csv=meta)
    assert report["metadata_applied"] == 2 and report["unmatched"] == ["nao_existe.txt"]
    assert get_document_meta(proj, "ensaios", "grupoA_texto01.txt") == {"ano": "2016", "nivel": "B2"}
    assert [d["filename"] for d in filter_documents(proj, "ensaios", {"nivel": "C1"})] == ["grupoB_texto01.txt"]


def _um_corpus_por_pasta(parent, spec):
    for group, names in spec.items():
        (parent / group).mkdir(parents=True)
        for n in names:
            (parent / group / n).write_text(f"Texto de {n}.", encoding="utf-8")


def test_subfolders_preview(proj, tmp_path):
    parent = tmp_path / "pasta"
    _um_corpus_por_pasta(parent, {"turmaB": ["b_01.txt"], "turmaA": ["a_01.txt", "a_02.txt"], "vazia": []})
    (parent / ".oculta").mkdir()
    (parent / ".oculta" / "x.txt").write_text("x", encoding="utf-8")
    (parent / "solto.txt").write_text("solto", encoding="utf-8")
    assert [(f["name"], f["files"]) for f in ttwtools.subfolders(parent)] == [("turmaA", 2), ("turmaB", 1)]
    assert ttwtools.subfolders(parent)[0]["path"] == str(parent / "turmaA")
    assert ttwtools.subfolders(tmp_path / "nao_existe") == []


def test_import_each_subfolder(proj, tmp_path):
    parent = tmp_path / "corpora"
    _um_corpus_por_pasta(parent, {"turmaA": ["x_01.txt", "x_02.txt"], "turmaB": ["y_01.txt"]})
    r = ttwtools.import_subfolders(proj, parent, filename_fields=["grupo", "texto"])
    assert [c["corpus"] for c in r["corpora"]] == ["turmaA", "turmaB"]
    assert r["imported"] == 3 and r["folders"] == ["turmaA", "turmaB"]
    assert {c["name"] for c in ttwtools.list_corpora(proj)} == {"turmaA", "turmaB"}
    assert get_document_meta(proj, "turmaA", "x_01.txt") == {"grupo": "x", "texto": "01"}
    with pytest.raises(ValueError, match="subpasta sem"):
        ttwtools.import_subfolders(proj, parent, names=["turmaA", "nada"])
    with pytest.raises(ValueError, match="Nenhuma subpasta"):
        ttwtools.import_subfolders(proj, tmp_path / "pasta_sem_subpastas")


def test_import_csv_corpus(proj, tmp_path):
    src = tmp_path / "corpus.csv"
    src.write_text('filename,text,autor\nd1.txt,"Hello, world.",Ana\n,"Sem nome, com vírgula.",Bia\n', encoding="utf-8")
    report = import_corpus(proj, src, "csv")
    assert report["files"] == ["d1.txt", "csv_0002.txt"]
    assert proj.get_corpus_file("csv", "d1.txt") == "Hello, world."
    assert get_document_meta(proj, "csv", "csv_0002.txt") == {"autor": "Bia"}


def test_import_pasted_text_does_not_overwrite(proj):
    import_corpus(proj, None, "colado", text="Primeiro texto.")
    report = import_corpus(proj, None, "colado", text="Segundo texto.")
    assert report["files"] == ["texto_colado_2.txt"]
    assert proj.get_corpus_file("colado", "texto_colado.txt") == "Primeiro texto."


def test_import_into_ttwl(tmp_path, folder):
    with ttwtools.create_project(tmp_path / "leve.ttwl") as p:
        import_corpus(p, folder, "ensaios", filename_fields=["grupo", "texto"])
        import_corpus(p, None, "ensaios", text="Colado no leve.")
        assert p._con.execute("SELECT COUNT(*) FROM corpus_files").fetchone()[0] == 0
        assert p.get_corpus_file("ensaios", "texto_colado.txt") == "Colado no leve."
        assert (tmp_path / "leve_corpus" / "ensaios" / "texto_colado.txt").is_file()
        assert len(filter_documents(p, "ensaios", {"grupo": "grupoA"})) == 2


def test_tokenize_options():
    text = "It's 3 o'clock, isn't it? Don't panic!"
    assert tokenize(text) == ["It's", "3", "o'clock", "isn't", "it", "Don't", "panic"]
    assert tokenize(text, TokenizerConfig(keep_numbers=False, lowercase=True)) == \
        ["it's", "o'clock", "isn't", "it", "don't", "panic"]
    assert tokenize(text, TokenizerConfig(contractions="split", keep_punct=True)) == \
        ["It", "'s", "3", "o'clock", ",", "is", "n't", "it", "?", "Do", "n't", "panic", "!"]
    assert tokenize("Custa 3,5 mil em 2026.", TokenizerConfig(keep_punct=True)) == ["Custa", "3,5", "mil", "em", "2026", "."]
    with pytest.raises(ValueError):
        TokenizerConfig(contractions="expand")


def test_tokenizer_config_saved_per_corpus(proj, folder):
    cfg = TokenizerConfig(lowercase=True, contractions="split")
    import_corpus(proj, folder, "ensaios", tokenizer=cfg)
    assert get_tokenizer_config(proj, "ensaios") == cfg
    assert get_tokenizer_config(proj, "outro") == TokenizerConfig()


def test_parse_where():
    assert parse_where(["grupo=A", "grupo=B", "ano = 2020"]) == {"grupo": ["A", "B"], "ano": ["2020"]}
    with pytest.raises(ValueError):
        parse_where(["semigual"])


def test_cli_import_and_documents(tmp_path, folder, capsys):
    project = str(tmp_path / "cli.ttwa")
    assert cli.main(["import", project, str(folder), "--name", "ens", "--fields", "grupo,texto", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["imported"] == 3
    assert cli.main(["documents", project, "--where", "grupo=grupoB", "--csv"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "corpus,arquivo,caracteres,grupo,texto"
    assert lines[1].startswith("ens,grupoB_texto01.txt,")
    assert cli.main(["documents", project, "--corpus", "ens"]) == 0
    assert "grupoA_texto02.txt" in capsys.readouterr().out


def test_list_corpora_and_layer_summary(proj, folder):
    import_corpus(proj, folder, "ensaios", filename_fields=["grupo", "texto"])
    from ttwtools.annotate import tag_corpus
    from ttwtools.corpus import list_corpora
    tag_corpus(proj, "ensaios", "simple", where={"grupo": "grupoA"})
    [c] = list_corpora(proj)
    assert (c["name"], c["documents"], c["metadata_keys"]) == ("ensaios", 3, ["grupo", "texto"])
    assert c["chars"] == sum(len(t) for t in TEXTS.values())
    [layer] = c["layers"]
    assert layer["tool"] == "simple" and layer["documents"] == 2 and layer["coverage"] == pytest.approx(2 / 3)
    assert layer["tokens"] > 0 and "components" in layer["config"]


def test_preview_filenames_e_pedaco_ignorado(tmp_path):
    from ttwtools.corpus import meta_from_filename, preview_filenames
    for n in ("ana_B1_2024.txt", "joao_C1_2023.txt", "sem_ano.txt"):
        (tmp_path / n).write_text("x", encoding="utf-8")
    pv = preview_filenames(tmp_path, "_", ["aluno", "", "ano"])
    assert pv["total"] == 3 and pv["parts"] == 3 and pv["irregular"] == ["sem_ano.txt"]
    ana = next(e for e in pv["examples"] if e["file"].startswith("ana"))
    assert ana["parts"] == ["ana", "B1", "2024"] and ana["meta"] == {"aluno": "ana", "ano": "2024"}
    assert meta_from_filename("ana_B1_2024.txt", ["aluno", "nivel", ""]) == {"aluno": "ana", "nivel": "B1"}
    assert preview_filenames(tmp_path / "nao_existe")["total"] == 0
