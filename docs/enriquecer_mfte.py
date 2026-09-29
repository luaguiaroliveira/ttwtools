"""Acrescenta ao tagset do MFTE a documentação oficial (List_Features_MFTE_python_<versão>.xlsx,
do repositório do MFTE): nome do traço, categoria, exemplos, operacionalização, unidade de
normalização e autoria. Texto em inglês, como na fonte; a definição curta em pt/en segue nas
chaves de tradução. Uso: python docs/enriquecer_mfte.py CAMINHO/List_Features_MFTE_python_1.6.xlsx 1.6
(o .xlsx é lido sem dependências: é um zip de XML)."""
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
Q = "{%s}" % NS["m"]
SHEETS = ("SimpleTagset", "ExtendedTagset", "ExtendedCompositeTags", "FeaturesWithNoTags", "FeaturesNotCounted")
COLS = {"A": "category", "B": "feature", "C": "code", "D": "examples", "E": "operationalisation", "F": "unit", "G": "by"}


def read_sheets(path: str) -> dict[str, list[dict]]:
    z = zipfile.ZipFile(path)
    strings = ["".join(t.text or "" for t in si.iter(Q + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)]
    names = [s.get("name") for s in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS)]
    out = {}
    for i, name in enumerate(names, 1):
        rows = []
        for r in ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml")).iter(Q + "row"):
            row = {}
            for c in r.findall("m:c", NS):
                col = re.match(r"[A-Z]+", c.get("r")).group()
                v = c.find("m:v", NS)
                if v is not None:
                    val = strings[int(v.text)] if c.get("t") == "s" else v.text
                else:
                    node = c.find("m:is", NS)
                    val = "".join(t.text or "" for t in node.iter(Q + "t")) if node is not None else None
                if val and col in COLS:
                    row[COLS[col]] = val.strip()
            if row:
                rows.append(row)
        out[name] = rows
    return out


def main(xlsx: str, version: str) -> None:
    sheets = read_sheets(xlsx)
    docs = {}
    for name in SHEETS:
        for r in sheets.get(name, []):
            code = r.get("code")
            if code and r.get("feature") and code != "Code/ Tag":
                docs.setdefault(code, {k: v for k, v in r.items() if k != "code"})
    path = Path(__file__).resolve().parent.parent / "ttwtools/data/tagsets/mfte.tagset.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    hit = 0
    for t in data["tags"]:
        d = docs.get(t["tag"])
        if d:
            t["doc"] = d
            hit += 1
        else:
            t.pop("doc", None)
    data["doc_version"] = version
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    missing = sorted(t["tag"] for t in data["tags"] if "doc" not in t)
    print(f"{hit} de {len(data['tags'])} tags com documentação (MFTE {version}); sem correspondência: {missing}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "?")
