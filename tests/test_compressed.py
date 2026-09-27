"""Projetos salvos compactados por padrão: cópia de trabalho, save(), close() e .ttwl com a pasta ao lado."""
from pathlib import Path

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


def test_salvar_sem_tabelas_de_busca_e_recriar(tmp_path):
    import pytest
    pytest.importorskip("spacy")
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
    assert small.stat().st_size < full.stat().st_size and needs_migration(small) and not needs_migration(full)
    seen = []
    with ttwtools.open_project(small_z, progress=lambda d, t, m: seen.append(m)) as q:
        assert "search" in seen and "indexes" in seen and q.has_search_tables and not q.unsaved
        after = q._con.execute(f"SELECT {cols} FROM tokens ORDER BY layer_id, idx").fetchall()
        assert [tuple(r) for r in after] == [tuple(r) for r in before]
        assert q._con.execute("SELECT COUNT(*) FROM layer_blobs").fetchone()[0] == 0
        assert ttwtools.kwic(q, "c", "the", limit=1)["total"] > 0
