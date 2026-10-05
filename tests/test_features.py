"""Tabelas de atributos das camadas e KFA (passo 3.7): mesmo resultado do fluxo antigo."""

from __future__ import annotations

import json
import shlex
import shutil
import warnings

import pandas as pd
import pytest

import ttwtools
from ttwtools import cli
from ttwtools.codegen import cli_command
from ttwtools.features import feature_table, feature_values, kfa_layers

from pathlib import Path

V2_FIXTURE = Path(__file__).parent / "data" / "v2_small.ttwa"


@pytest.fixture
def v2(tmp_path):
    shutil.copy(V2_FIXTURE, tmp_path / "v.ttwa")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = ttwtools.open_project(tmp_path / "v.ttwa")
    yield p
    p.close()


@pytest.mark.parametrize("tool,legacy", [("mfte", "mfte"), ("spacy", "spacy_upos")])
def test_table_from_migrated_layers_equals_legacy(v2, tool, legacy):
    new = feature_table(v2, "CorIFAessaysNE_5", tool).set_index("filename").sort_index()
    old = v2.load_feature_table("CorIFAessaysNE_5", "rawcount", tagger_type=legacy).set_index("filename").sort_index()
    cols = [c for c in old.columns if c not in ("field", "section")]
    pd.testing.assert_frame_equal(new[cols], old[cols].fillna(0), check_dtype=False, atol=1e-9)


def test_fresh_biberplus_layer_equals_legacy_and_kfa(v2, tmp_path, spacy_model):
    with ttwtools.create_project(tmp_path / "n.ttwa") as q:
        for g in ("CorIFAessaysNE_5", "essays_bawe_somentetexto_5"):
            ttwtools.import_corpus(q, V2_FIXTURE.parent.parent.parent / "examples" / "test_corpora" / g, g)
            ttwtools.tag_corpus(q, g, "biberplus", {"n_processes": 1})
        new = feature_table(q, "CorIFAessaysNE_5", "biberplus").set_index("filename").sort_index()
        old = v2.load_feature_table("CorIFAessaysNE_5", "rawcount", tagger_type="biberplus").set_index("filename").sort_index()
        cols = [c for c in old.columns if c not in ("field", "section")]
        pd.testing.assert_frame_equal(new[cols], old[cols].fillna(0), check_dtype=False, atol=1e-9)
        r = kfa_layers(q, "CorIFAessaysNE_5", "essays_bawe_somentetexto_5", "biberplus", metric="kfa2")
        legacy = v2.load_kfa_result("CorIFAessaysNE_5", "essays_bawe_somentetexto_5", tagger_type="biberplus")
        mine = pd.DataFrame(r["rows"]).set_index("Feature")["Effect_Size"]
        theirs = legacy.set_index("Feature")["Effect_Size"]
        assert set(mine.index) == set(theirs.index)
        assert (mine - theirs.loc[mine.index]).abs().max() < 1e-9
        assert q.list_analyses("kfa")


def test_groups_values_and_cli(v2, capsys):
    from ttwtools.corpus import set_document_meta
    files = v2.list_corpus_files("CorIFAessaysNE_5")
    for i, f in enumerate(files):
        set_document_meta(v2, "CorIFAessaysNE_5", f, {"g": "A" if i < 3 else "B"})
    r = kfa_layers(v2, "CorIFAessaysNE_5", "CorIFAessaysNE_5", "spacy", where1={"g": "A"}, where2={"g": "B"}, save=False)
    assert (r["n1"], r["n2"]) == (3, 2) and r["rows"]
    vals = feature_values(v2, "CorIFAessaysNE_5", "spacy", "NOUN")
    assert len(vals) == 5 and all(v["value"] > 0 for v in vals)
    raw = feature_table(v2, "CorIFAessaysNE_5", "spacy", per1000=False).set_index("filename")
    for v in vals:
        assert v["count"] == int(raw.loc[v["filename"], "NOUN"])
        assert v["words"] == int(raw.loc[v["filename"], "Words"])
        assert v["value"] == (v["count"] * 1000 / v["words"] if v["words"] else 0.0)
    v2._con.commit()
    params = {"corpus": "CorIFAessaysNE_5", "corpus2": "essays_bawe_somentetexto_5", "layer": "mfte", "min_effect": 0.5}
    cmd = cli_command("kfa", str(v2.path), params)
    assert cli.main(shlex.split(cmd)[1:] + ["--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    direct = kfa_layers(v2, **{"corpus1": "CorIFAessaysNE_5", "corpus2": "essays_bawe_somentetexto_5", "layer": "mfte",
                               "min_effect": 0.5}, save=False)
    assert [x["Feature"] for x in out["rows"]] == [x["Feature"] for x in direct["rows"]]
    with pytest.raises(ValueError):
        kfa_layers(v2, "CorIFAessaysNE_5", "CorIFAessaysNE_5", "spacy", where1={"g": "B"}, where2={"g": "nada"})


def test_feature_table_is_reused_and_invalidated_by_new_layers(tmp_path):
    """A 2ª chamada não recontar (memória); uma camada nova muda a chave e recalcula."""
    import shutil
    import warnings
    from pathlib import Path
    import ttwtools
    from ttwtools import features
    features._TABLES.clear()
    path = tmp_path / "p.ttwa"
    shutil.copy(Path(__file__).parent / "data" / "v2_small.ttwa", path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = ttwtools.open_project(path)

    a = features.feature_table(p, "CorIFAessaysNE_5", "spacy", per1000=True)
    n = len(features._TABLES)
    seen = []
    b = features.feature_table(p, "CorIFAessaysNE_5", "spacy", per1000=True, progress=lambda d, t: seen.append(d))
    assert b.equals(a) and b is not a and seen == []            # veio da memória (sem andamento) e é cópia
    b.loc[0, "Words"] = -1                                       # mexer na cópia não estraga o cache
    assert features.feature_table(p, "CorIFAessaysNE_5", "spacy", per1000=True).equals(a)
    assert len(features._TABLES) == n
    c = features.feature_table(p, "CorIFAessaysNE_5", "spacy", per1000=False)      # outra forma: outra entrada
    assert not c.equals(a) and len(features._TABLES) == n + 1
    doc = p.list_documents("CorIFAessaysNE_5")[0]
    p.save_layer(doc["id"], "spacy", "9", "outro", {"x": 1}, [{"word": "zzz", "lemma": "zzz", "upos": "X", "start_char": 0, "end_char": 3}])
    p._con.commit()
    seen = []
    features.feature_table(p, "CorIFAessaysNE_5", "spacy", per1000=True, progress=lambda d, t: seen.append(d))
    assert seen                                                  # camada nova: contou de novo
    p.close()


def test_kfa_reports_raw_counts_per_side(v2):
    """A KFA devolve, por atributo, a contagem bruta (total no corpus) de cada lado, além da média por 1000."""
    r = kfa_layers(v2, "CorIFAessaysNE_5", "essays_bawe_somentetexto_5", "mfte", metric="kfa2")
    raw = feature_table(v2, "CorIFAessaysNE_5", "mfte", per1000=False).drop(columns=["filename", "Words", "TTR"]).sum()
    assert r["rows"] and all("Count_Corpus1" in row and "Count_Corpus2" in row for row in r["rows"])
    for row in r["rows"]:
        assert row["Count_Corpus1"] == int(raw.get(row["Feature"], 0))


def test_min_effect_only_filters_and_never_recomputes(v2):
    full = kfa_layers(v2, "CorIFAessaysNE_5", "essays_bawe_somentetexto_5", "mfte", min_effect=0.0)
    assert not full.get("cached") and full["rows"]
    cut = kfa_layers(v2, "CorIFAessaysNE_5", "essays_bawe_somentetexto_5", "mfte", min_effect=0.5)
    assert cut["cached"] and cut["min_effect"] == 0.5                      # reaproveitou a análise completa
    assert cut["rows"] == [r for r in full["rows"] if abs(r["Effect_Size"]) >= 0.5]
    assert len(cut["rows"]) < len(full["rows"])
    again = kfa_layers(v2, "CorIFAessaysNE_5", "essays_bawe_somentetexto_5", "mfte", min_effect=0.1)
    assert again["rows"] == [r for r in full["rows"] if abs(r["Effect_Size"]) >= 0.1]
