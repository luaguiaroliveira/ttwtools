"""Tabelas de traços das camadas e KFA (passo 3.7): mesmo resultado do fluxo antigo."""

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
