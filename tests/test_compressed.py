"""Projetos salvos compactados por padrão: cópia de trabalho, save(), close() e .ttwl com a pasta ao lado."""
from pathlib import Path

import pytest
import ttwtools
from ttwtools.project import compression_of, save_project_as

CORPUS = Path(__file__).resolve().parents[1] / "examples" / "test_corpora" / "CorIFAessaysNE_5"


def _plain(tmp_path, name="base.ttwa"):
    p = ttwtools.create_project(tmp_path / name)
    ttwtools.import_corpus(p, CORPUS, "c")
    p.close()
    return tmp_path / name


def test_salvar_compactado_por_padrao_e_sem_compressao(tmp_path):
    base = _plain(tmp_path)
    assert compression_of(base) is None
    small = save_project_as(base, tmp_path / "z.ttwa")
    big = save_project_as(base, tmp_path / "raw.ttwa", compress=False)
    assert compression_of(small) == "gzip" and compression_of(big) is None
    assert small.stat().st_size < big.stat().st_size


def test_copia_de_trabalho_save_e_close(tmp_path):
    z = save_project_as(_plain(tmp_path), tmp_path / "z.ttwa")
    proj = ttwtools.open_project(z)
    assert proj.is_working_copy and proj.home == z.resolve() and not proj.unsaved
    ttwtools.import_corpus(proj, None, "colado", text="Um texto novo.")
    assert proj.unsaved
    proj.save()
    assert not proj.unsaved and compression_of(z) == "gzip"
    ttwtools.import_corpus(proj, None, "outro", text="Mais um.")
    work = proj.path
    proj.close()                                   # alterações não salvas: grava ao fechar
    assert not work.exists()
    with ttwtools.open_project(z) as again:
        assert set(again.list_corpus_names()) == {"c", "colado", "outro"}
    with ttwtools.open_project(z) as ro:
        ro.list_corpus_names()
    proj = ttwtools.open_project(z)
    ttwtools.import_corpus(proj, None, "descartado", text="x")
    proj.close(save=False)                         # fechar sem salvar
    with ttwtools.open_project(z) as again:
        assert "descartado" not in again.list_corpus_names()


def test_ttwl_compactado_acha_os_textos_ao_lado(tmp_path):
    base = _plain(tmp_path)
    with ttwtools.open_project(base) as full:
        light = full.detach_corpus(tmp_path / "leve.ttwl")
        light.close()
    z = save_project_as(tmp_path / "leve.ttwl", tmp_path / "leve.ttwl")
    assert compression_of(z) == "gzip"
    with ttwtools.open_project(z) as proj:
        assert proj.is_light and proj.is_working_copy
        docs = [d["filename"] for d in proj.list_documents("c")] if hasattr(proj, "list_documents") else None
        status = proj.check_corpus()
        assert not status["missing"] and not status["changed"]


BAWE = Path(__file__).resolve().parents[1] / "examples" / "test_corpora" / "essays_bawe_somentetexto_5"


def _two(tmp_path):
    import pytest
    p = ttwtools.create_project(tmp_path / "dois.ttwa")
    ttwtools.import_corpus(p, CORPUS, "c", filename_fields=["a"])
    ttwtools.import_corpus(p, BAWE, "d")
    pytest.importorskip("spacy")
    ttwtools.tag_corpus(p, "c", "spacy", preset="rapido")
    ttwtools.add_step(p, "d", {"kind": "stats"})
    return p


def test_ttwc_leva_um_corpus_com_camadas(tmp_path):
    import pytest
    p = _two(tmp_path)
    out = ttwtools.save_corpus_as(p, "c", tmp_path / "so_c.ttwc")
    p.close()
    assert compression_of(out) == "gzip"
    with ttwtools.open_project(out) as c:
        assert c.list_corpus_names() == ["c"] and c.single_corpus and not c.is_light
        assert c.get_corpus_file("c", c.list_corpus_files("c")[0])
        assert [layer["tool"] for layer in ttwtools.layer_summary(c, "c")] == ["spacy"]
        assert ttwtools.pending_steps(c, "d") == []
        with pytest.raises(ValueError, match="um corpus só"):
            ttwtools.import_corpus(c, None, "outro", text="x")
    with ttwtools.open_project(tmp_path / "dois.ttwa") as orig:          # a origem não muda
        assert set(orig.list_corpus_names()) == {"c", "d"}


def test_ttwcl_textos_ao_lado_e_a_partir_de_ttwl(tmp_path):
    p = _two(tmp_path)
    out = ttwtools.save_corpus_as(p, "d", tmp_path / "sub" / "so_d.ttwcl", compress=False)
    light = p.detach_corpus(tmp_path / "leve.ttwl")
    p.close()
    assert (tmp_path / "sub" / "so_d_corpus" / "d").is_dir() and compression_of(out) is None
    with ttwtools.open_project(out) as d:
        assert d.is_light and d.single_corpus and d.list_corpus_names() == ["d"]
        st = d.check_corpus()
        assert not st["missing"] and not st["changed"] and len(d.list_corpus_files("d")) == 5
    # de um .ttwl para um .ttwc: os textos entram no arquivo
    out2 = ttwtools.save_corpus_as(light, "c", tmp_path / "outra" / "c.ttwc")
    light.close()
    with ttwtools.open_project(out2) as c:
        assert not c.is_light and len(c.list_corpus_files("c")) == 5


def test_ttwc_novo_recusa_segundo_corpus(tmp_path):
    import pytest
    p = ttwtools.create_project(tmp_path / "novo.ttwc")
    ttwtools.import_corpus(p, CORPUS, "c")
    with pytest.raises(ValueError):
        ttwtools.import_corpus(p, BAWE, "d")
    p.close()


def test_salvar_sem_tabelas_de_busca_e_recriar(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("spacy")
    monkeypatch.setenv("TTWTOOLS_INDEX_CACHE", "0")      # o caminho antigo: recriar as tabelas dentro do projeto
    from ttwtools.project import needs_migration
    p = ttwtools.create_project(tmp_path / "t.ttwa")
    ttwtools.import_corpus(p, CORPUS, "c")
    ttwtools.tag_corpus(p, "c", "spacy", preset="rapido")
    cols = "layer_id, idx, doc_id, start_char, end_char, word, lemma, upos, xpos, feats, tags, extra"
    before = p._con.execute(f"SELECT {cols} FROM tokens ORDER BY layer_id, idx").fetchall()
    p._con.commit()
    full = save_project_as(p.path, tmp_path / "com.ttwa", compress=False)
    small = save_project_as(p.path, tmp_path / "sem.ttwa", compress=False, search_tables=False)
    small_z = save_project_as(p.path, tmp_path / "sem_z.ttwa", search_tables=False)
    p.close()
    assert small.stat().st_size < full.stat().st_size and not needs_migration(small) and not needs_migration(full)   # abrir não monta o índice
    seen = []
    with ttwtools.open_project(small_z, progress=lambda d, t, m: seen.append(m), lazy_index=False) as q:
        assert "search" in seen and "indexes" in seen and q.has_search_tables and not q.unsaved
        after = q._con.execute(f"SELECT {cols} FROM tokens ORDER BY layer_id, idx").fetchall()
        assert [tuple(r) for r in after] == [tuple(r) for r in before]
        assert q._con.execute("SELECT COUNT(*) FROM layer_blobs").fetchone()[0] == 0
        assert ttwtools.kwic(q, "c", "the", limit=1)["total"] > 0


def test_ttwal_pacote_leve_com_varios_corpora(tmp_path):
    p = _two(tmp_path)
    out = ttwtools.save_corpora_as(p, ["c", "d"], tmp_path / "pac" / "dois.ttwal")
    only_d = ttwtools.save_corpora_as(p, ["d"], tmp_path / "pac" / "so_d.ttwal", compress=False)
    with pytest.raises(ValueError, match="ao menos um"):
        ttwtools.save_corpora_as(p, [], tmp_path / "x.ttwal")
    with pytest.raises(ValueError, match="não existe"):
        ttwtools.save_corpora_as(p, ["c", "nada"], tmp_path / "y.ttwal")
    with pytest.raises(ValueError, match="use a extensão"):
        ttwtools.save_corpora_as(p, ["c"], tmp_path / "z.ttwc")
    p.close()
    assert (tmp_path / "pac" / "dois_corpus" / "c").is_dir() and (tmp_path / "pac" / "dois_corpus" / "d").is_dir()
    with ttwtools.open_project(out) as pk:
        assert pk.is_light and not pk.single_corpus and set(pk.list_corpus_names()) == {"c", "d"}
        st = pk.check_corpus()
        assert not st["missing"] and not st["changed"]
        assert [layer["tool"] for layer in ttwtools.layer_summary(pk, "c")] == ["spacy"]
        ttwtools.import_corpus(pk, None, "novo", text="ainda dá para acrescentar")           # não é de um corpus só
    with ttwtools.open_project(only_d) as pd:
        assert pd.list_corpus_names() == ["d"] and pd.is_light and not pd.single_corpus
    with ttwtools.open_project(tmp_path / "dois.ttwa") as orig:
        assert set(orig.list_corpus_names()) == {"c", "d"}


def test_cli_save_as_ttwal_com_selecao(tmp_path, capsys):
    p = _two(tmp_path)
    p.close()
    from ttwtools import cli
    src = str(tmp_path / "dois.ttwa")
    assert cli.main(["save-as", src, str(tmp_path / "todos.ttwal"), "--json"]) == 0            # sem --corpus: todos
    assert cli.main(["save-as", src, str(tmp_path / "um.ttwal"), "--corpus", "c", "--json"]) == 0
    with ttwtools.open_project(tmp_path / "todos.ttwal") as a, ttwtools.open_project(tmp_path / "um.ttwal") as b:
        assert set(a.list_corpus_names()) == {"c", "d"} and b.list_corpus_names() == ["c"]


def test_exportar_corpus_reporta_etapas_e_nao_deixa_lixo_temporario(tmp_path):
    import tempfile
    p = _two(tmp_path)
    stages = []
    before = set(Path(tempfile.gettempdir()).glob("ttw_export_*"))
    ttwtools.save_corpora_as(p, ["c", "d"], tmp_path / "x.ttwal", progress=lambda d, t, m: stages.append((d, t, m)))
    p.close()
    copy = [s for s in stages if s[2] == "copy"]
    assert copy and copy[-1][0] == copy[-1][1] and copy[-1][1] >= 2          # uma etapa por camada copiada
    assert set(Path(tempfile.gettempdir()).glob("ttw_export_*")) == before   # a pasta temporária foi apagada


def test_purge_orphan_workdirs_pelo_dono(tmp_path, monkeypatch):
    import os
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    dead, alive, old, new = (tmp_path / n for n in ("ttw_work_dead", "ttw_work_alive", "ttw_work_old", "ttw_work_new"))
    for d in (dead, alive, old, new):
        d.mkdir()
    (dead / "owner.pid").write_text("999999")                  # processo que não existe
    (alive / "owner.pid").write_text(str(os.getpid()))
    os.utime(old, (1, 1))                                      # sem marca e antiga: abandonada
    assert ttwtools.purge_orphan_workdirs() == 2
    assert not dead.exists() and not old.exists() and alive.exists() and new.exists()


def test_formatos_leves_saem_sem_tabelas_de_busca_por_padrao(tmp_path):
    p = _two(tmp_path)
    cheio = ttwtools.save_corpus_as(p, "c", tmp_path / "c.ttwc")                                   # .ttwc: com tabelas
    leve = ttwtools.save_corpus_as(p, "c", tmp_path / "leve" / "c.ttwcl")                         # .ttwcl: leve de verdade
    forcado = ttwtools.save_corpus_as(p, "c", tmp_path / "forcado" / "c.ttwcl", search_tables=True)
    pacote = ttwtools.save_corpora_as(p, ["c", "d"], tmp_path / "pac" / "dois.ttwal")
    p.close()
    assert leve.stat().st_size < cheio.stat().st_size and pacote.stat().st_size < cheio.stat().st_size * 2
    for path, com_tabelas in ((cheio, True), (leve, False), (forcado, True), (pacote, False)):
        with ttwtools.open_project(path, migrate=False) as q:
            assert q.has_search_tables is com_tabelas
    with ttwtools.open_project(leve) as q:                                                         # abrir recria as tabelas
        if not q.has_search_tables:
            q.rebuild_search_tables()
        assert ttwtools.search(q, "c", "the", layer="spacy")["total"] > 0
