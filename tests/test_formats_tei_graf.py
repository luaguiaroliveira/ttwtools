"""Importadores TEI (P5 e BNC) e GrAF (OANC/MASC) — passo 5.2."""

from __future__ import annotations

import json

import ttwtools
from ttwtools import cli
from ttwtools.formats import import_graf, import_tei, parse_graf, parse_tei

BNC = """<bncDoc xml:id="A00"><teiHeader><fileDesc><titleStmt><title>Sample</title></titleStmt></fileDesc>
<profileDesc><textClass><classCode scheme="DLEE">W ac:polit</classCode></textClass></profileDesc></teiHeader>
<wtext type="ACPROSE"><div><head><s n="1"><w c5="AJ0" hw="new" pos="ADJ">New </w><w c5="NN1" hw="law" pos="SUBST">law</w></s></head>
<p><s n="2"><w c5="AT0" hw="the" pos="ART">The </w><w c5="NN1" hw="cat" pos="SUBST">cat</w><w c5="VBZ" hw="be" pos="VERB">'s </w>
<w c5="AJ0" hw="happy" pos="ADJ">happy</w><c c5="PUN">.</c></s></p></div></wtext></bncDoc>"""

P5 = """<teiCorpus xmlns="http://www.tei-c.org/ns/1.0">
<TEI xml:id="d1"><teiHeader><fileDesc><titleStmt><title>One</title><author>Ann</author></titleStmt></fileDesc></teiHeader>
<text><body><p>Plain <hi>text</hi> here.<note>not this</note> More.</p><p>Second   paragraph.</p></body></text></TEI>
<TEI xml:id="d2"><teiHeader><fileDesc><titleStmt><title>Two</title></titleStmt></fileDesc></teiHeader>
<text><body><p><s><w lemma="dog" pos="NOUN">Dogs</w> <w lemma="bark" pos="VERB">bark</w><pc>.</pc></s></p></body></text></TEI>
</teiCorpus>"""

TEXT = "The cats sat. They ran!\n"
HEADER = """<cesHeader xmlns="http://www.xces.org/schema/2003"><fileDesc><titleStmt><title>Doc A</title></titleStmt></fileDesc>
<profileDesc><textClass><domain>fiction</domain></textClass><primaryData loc="a.txt"/>
<annotations><annotation f.id="seg" loc="a-seg.xml"/><annotation f.id="penn" loc="a-penn.xml"/>
<annotation f.id="s" loc="a-s.xml"/></annotations></profileDesc></cesHeader>"""
G = 'xmlns="http://www.xces.org/ns/GrAF/1.0/"'
SPANS = [(0, 3, "the", "DT", "The"), (4, 8, "cat", "NNS", "cats"), (9, 12, "sit", "VBD", "sat"), (12, 13, ".", ".", "."),
         (14, 18, "they", "PRP", "They"), (19, 22, "run", "VBD", "ran"), (22, 23, "!", ".", "!")]


def _graf(folder, broken=False):
    (folder / "a.anc").write_text(HEADER)
    (folder / "a.txt").write_text(TEXT)
    regions = "".join(f'<region xml:id="seg-r{i}" anchors="{s} {e}"/>' for i, (s, e, *_r) in enumerate(SPANS))
    (folder / "a-seg.xml").write_text(f"<graph {G}>{regions}</graph>")
    toks = "".join(f'<node xml:id="penn-n{i}"><link targets="seg-r{i}"/></node><a label="tok" ref="penn-n{i}"><fs>'
                   f'<f name="base" value="{b}"/><f name="msd" value="{m}"/>'
                   f'<f name="string" value="{"X" if broken and i == 1 else w}"/></fs></a>'
                   for i, (_s, _e, b, m, w) in enumerate(SPANS))
    (folder / "a-penn.xml").write_text(f"<graph {G}>{toks}</graph>")
    sents = ('<region xml:id="s-r0" anchors="0 13"/><region xml:id="s-r1" anchors="14 23"/>'
             '<node xml:id="s-n0"><link targets="s-r0"/></node><a label="s" ref="s-n0"/>'
             '<node xml:id="s-n1"><link targets="s-r1"/></node><a label="s" ref="s-n1"/>')
    (folder / "a-s.xml").write_text(f"<graph {G}>{sents}</graph>")


def test_parse_bnc(tmp_path):
    (tmp_path / "bnc.xml").write_text(BNC)
    [doc] = parse_tei(tmp_path / "bnc.xml")
    assert doc["text"] == "New law\n\nThe cat's happy."
    assert doc["meta"] == {"title": "Sample", "class": "W ac:polit", "type": "ACPROSE"} and doc["tag_attr"] == "c5"
    for t in doc["tokens"]:
        assert doc["text"][t["start_char"]:t["end_char"]] == t["word"]
    assert [(t["word"], t["lemma"], t["xpos"], t["sent"]) for t in doc["tokens"][2:5]] == \
        [("The", "the", "AT0", 1), ("cat", "cat", "NN1", 1), ("'s", "be", "VBZ", 1)]


def test_import_tei_corpus(tmp_path):
    (tmp_path / "p5.xml").write_text(P5)
    with ttwtools.create_project(tmp_path / "t.ttwa") as p:
        r = import_tei(p, tmp_path / "p5.xml", "tei")
        assert r["imported"] == 2 and r["with_layer"] == 1 and r["tokens"] == 3
        docs = {d["filename"]: d for d in ttwtools.corpus.filter_documents(p, "tei")}
        assert docs["d1.txt"]["meta"] == {"title": "One", "author": "Ann"}
        assert ttwtools.query.read_document(p, "tei", "d1.txt")["text"] == "Plain text here. More.\n\nSecond paragraph."
        assert ttwtools.search(p, "tei", "lemma=bark")["total"] == 1


def test_graf_offsets_and_sentences(tmp_path):
    _graf(tmp_path)
    with ttwtools.create_project(tmp_path / "g.ttwa") as p:
        r = import_graf(p, tmp_path, "masc")
        assert r == {"corpus": "masc", "imported": 1, "files": ["a.txt"], "tokens": 7, "offset_mismatches": 0,
                     "skipped": []}
        [doc] = ttwtools.corpus.filter_documents(p, "masc")
        assert doc["meta"]["title"] == "Doc A" and doc["meta"]["domain"] == "fiction"
        kw = ttwtools.kwic(p, "masc", "lemma=run")
        assert kw["total"] == 1 and "ran" in json.dumps(kw["lines"][0])
        assert ttwtools.search(p, "masc", "pos=NOUN")["total"] == 1       # UPOS a partir do PTB


def test_graf_mismatch_counted_and_cli(tmp_path, capsys):
    _graf(tmp_path, broken=True)
    parsed = parse_graf(TEXT, {"seg": tmp_path / "a-seg.xml", "penn": tmp_path / "a-penn.xml", "s": tmp_path / "a-s.xml"})
    assert parsed["mismatches"] == 1 and [t["sent"] for t in parsed["tokens"]] == [0, 0, 0, 0, 1, 1, 1]
    assert cli.main(["import", str(tmp_path / "c.ttwa"), str(tmp_path / "a.anc"), "--name", "m", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["tokens"] == 7
