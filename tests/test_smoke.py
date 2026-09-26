"""Fumaça do que já existe: projeto .ttwa, JSONL etiquetado e KFA."""

from __future__ import annotations

import pandas as pd
import pytest

import ttwtools
from ttwtools.tagged_io import read_tagged_jsonl, write_tagged_jsonl


def test_lazy_exports():
    for name in ttwtools.__all__:
        assert getattr(ttwtools, name) is not None


def test_project_create_save_reopen(tmp_path, corpus5):
    path = tmp_path / "p.ttwa"
    group = "CorIFAessaysNE_5"
    with ttwtools.create_project(path, name="teste") as proj:
        proj.add_corpus_folder(group, corpus5[group])
        assert proj.list_corpus_names() == [group]
        files = proj.list_corpus_files(group)
    assert len(files) == 5
    with ttwtools.open_project(path) as proj:
        assert proj.list_corpus_files(group) == files
        text = proj.get_corpus_file(group, files[0])
        assert text == (corpus5[group] / files[0]).read_text(encoding="utf-8")


def test_tagged_jsonl_roundtrip(tmp_path):
    meta = {"tagger": "spacy_upos", "tagger_version": "3.8", "filename": "a.txt"}
    tokens = [
        {"type": "token", "text": "Olá", "start": 0, "end": 3, "tags": ["INTJ"]},
        {"type": "token", "text": "mundo", "start": 4, "end": 9, "tags": ["NOUN"]},
    ]
    path = tmp_path / "sub" / "a.jsonl"
    write_tagged_jsonl(meta, tokens, path)
    meta2, tokens2 = read_tagged_jsonl(path)
    assert meta2 == {"type": "metadata", **meta}
    assert tokens2 == tokens


def test_tagged_jsonl_rejects_legacy_tsv(tmp_path):
    path = tmp_path / "old.tsv"
    path.write_text("# filename: x.txt\nword\tNN\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_tagged_jsonl(path)


def test_biberplus_then_kfa(tmp_path, corpus5, spacy_model):
    norm = {}
    for group, folder in corpus5.items():
        out = tmp_path / f"out_{group}"
        ttwtools.biberplus(str(folder), configdict={"n_processes": 1, "function_words": False},
                           output_dir=str(out))
        raw = next(out.glob("*_rawcount.csv"))
        ttwtools.normalize_biber_features(str(raw))
        norm[group] = next(out.glob("*_norm1000.csv"))
        df = pd.read_csv(norm[group])
        assert len(df) == 5 and (df["Words"] > 0).all()

    result = ttwtools.kfa(str(norm["CorIFAessaysNE_5"]), str(norm["essays_bawe_somentetexto_5"]))
    assert result is not None and len(result) > 0
