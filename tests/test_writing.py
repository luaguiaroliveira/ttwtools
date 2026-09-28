"""Testes da Escrita: leitura de arquivos e comparação de um texto com a referência."""
from __future__ import annotations

import io
import zipfile
from collections import Counter

import pytest

from ttwtools.keyness import FreqTable
from ttwtools.writing import analyze_text, extract_text, text_freqs


def _docx(text: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in text.splitlines())
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def _odt(text: str) -> bytes:
    body = "".join(f"<text:p>{t}</text:p>" for t in text.splitlines())
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<office:document-content '
           'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
           'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
           f"<office:body><office:text>{body}</office:text></office:body></office:document-content>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", xml)
    return buf.getvalue()


def test_extract_txt_e_md():
    assert extract_text("olá mundo".encode(), "a.txt") == "olá mundo"
    assert extract_text("# título\ntexto".encode(), "a.md").startswith("# título")


def test_extract_docx():
    assert extract_text(_docx("Primeira linha\nSegunda linha"), "a.docx") == "Primeira linha\nSegunda linha"


def test_extract_odt():
    assert extract_text(_odt("Olá\nmundo"), "a.odt") == "Olá\nmundo"


def test_formato_desconhecido():
    with pytest.raises(ValueError, match="unsupported_format"):
        extract_text(b"x", "a.rtf")


def test_text_freqs_conta_palavras():
    tf = text_freqs("The cat sat on the mat.", "form")
    assert tf.words == 6                    # só palavras, sem pontuação
    assert tf.counts["the"] == 2
    assert tf.docs["the"] == 1              # texto único


def test_text_freqs_ngram():
    tf = text_freqs("o gato viu o rato", "ngram", n=2)
    assert tf.counts["o gato"] == 1
    assert tf.counts["o rato"] == 1
    assert "gato viu" in tf.counts


def _ref() -> FreqTable:
    counts = Counter({"the": 100, "cat": 5, "dog": 3, "rare": 40})
    docs = Counter({"the": 10, "cat": 8, "dog": 1, "rare": 1})
    return FreqTable(counts, docs, words=1000, n_docs=10, meta={"name": "ref", "unit": "form", "lang": "en"})


def test_analyze_text_badges_dispersao_e_direcao():
    r = analyze_text(None, "the cat cat cat rare", _ref(), unit="form", min_freq=1, measure="log_ratio")
    itens = {row["item"]: row for row in r["rows"]}
    assert itens["cat"]["direction"] == "+"
    assert itens["cat"]["range_reference_pct"] == 80.0
    # "dog" só aparece em 1/10 dos textos da referência → concentrada
    assert "concentrated_reference" in itens["dog"]["flags"]
    assert "single_text" in r["reliability"] and "short_text" in r["reliability"]
    assert all("p_adj" in row for row in r["rows"])


def test_analyze_text_fdr_marca_p_adj():
    r = analyze_text(None, "the the the the cat", _ref(), unit="form", min_freq=1, correction="fdr")
    assert all(row["p_adj"] >= row["p"] - 1e-12 for row in r["rows"])
