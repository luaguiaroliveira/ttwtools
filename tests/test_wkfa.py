"""`kfa2` passou a se chamar `wkfa`: nome novo, alias antigo e migração de projetos salvos."""

from __future__ import annotations

import numpy as np

from ttwtools import project as P
from ttwtools.analysis import METRICS, normalize_metric
from ttwtools.experimental import _d


def test_wkfa_is_the_name_and_kfa2_is_a_legacy_alias():
    assert METRICS == ("kfa", "wkfa")
    assert normalize_metric("kfa2") == "wkfa" and normalize_metric("wkfa") == "wkfa" and normalize_metric("kfa") == "kfa"


def test_d_weighted_matches_legacy_name():
    a, b = np.array([[1.0], [2.0], [4.0]]), np.array([[3.0], [5.0], [9.0], [11.0]])
    assert np.allclose(_d(a, b, "wkfa"), _d(a, b, "kfa2"))
    assert not np.allclose(_d(a, b, "wkfa"), _d(a, b, "kfa"))


def test_saved_projects_with_kfa2_are_migrated(tmp_path):
    path = tmp_path / "t.db"
    con = P._connect(path)
    row = "INSERT INTO kfa_results (corpus1_name,corpus2_name,min_effect,join_method,tagger_type,analysis_name,metric,features_meta,data,created_at) VALUES (?,?,0,'union','biberplus','default',?,'[]','{}','2026')"
    con.execute(row, ("a", "b", "kfa2"))
    con.execute(row, ("c", "d", "kfa"))
    con.commit()
    con.close()
    con = P._connect(path)
    assert sorted(r[0] for r in con.execute("SELECT metric FROM kfa_results")) == ["kfa", "wkfa"]
