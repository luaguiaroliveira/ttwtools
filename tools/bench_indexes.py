"""Benchmark dos índices da tabela `tokens` (A4 do plano de armazenamento).

Gera um projeto SINTÉTICO (Zipf; padrão 2 milhões de tokens, nunca o projeto real), cria cada conjunto
de índices numa cópia e mede tamanho do arquivo, tempo de criação e tempo de KWIC, frequência,
colocados e dispersão (mediana de 3 execuções). Apaga tudo ao fim.

    python tools/bench_indexes.py [--tokens 2000000] [--dir PASTA_TEMPORARIA] [--json]
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

import ttwtools
from ttwtools import query
from ttwtools.project import TTWAProject, _TOKEN_INDEXES

LEGACY = [("idx_tokens_word", "CREATE INDEX idx_tokens_word ON tokens (word)"),
          ("idx_tokens_lemma", "CREATE INDEX idx_tokens_lemma ON tokens (lemma)")]
INDEXES = LEGACY + [(n, s.replace("IF NOT EXISTS ", "")) for n, s in _TOKEN_INDEXES]
ALL = [n for n, _ in INDEXES]
SETS = {
    "antigo (7)": ALL,
    "reduzido (5, adotado)": ["idx_tokens_lword", "idx_tokens_llemma", "idx_tokens_doc", "idx_tokens_upos", "idx_tokens_xpos"],
    "mínimo (3)": ["idx_tokens_lword", "idx_tokens_llemma", "idx_tokens_doc"],
    "nenhum": [],
}
UPOS = ["NOUN", "VERB", "ADJ", "ADV", "ADP", "DET", "PRON", "AUX", "PUNCT", "CCONJ", "SCONJ", "NUM", "PROPN", "PART", "INTJ", "X", "SYM"]


def build(path: Path, n_tokens: int, doc_len: int = 10_000, vocab: int = 20_000, seed: int = 1) -> None:
    rnd = random.Random(seed)
    words = [f"w{i}" for i in range(vocab)]
    weights = [1 / (i + 1) for i in range(vocab)]
    proj = ttwtools.create_project(path)
    n_docs = max(1, n_tokens // doc_len)
    for d in range(n_docs):
        doc = proj._upsert_document("c", f"d{d:04d}.txt", f"texto {d}")
        toks, pos = [], 0
        for w in rnd.choices(range(vocab), weights, k=doc_len):
            word = words[w]
            toks.append({"word": word.capitalize() if rnd.random() < 0.1 else word, "lemma": word,
                         "upos": UPOS[w % len(UPOS)], "xpos": f"X{w % 40}", "start_char": pos, "end_char": pos + len(word)})
            pos += len(word) + 1
        proj.save_layer(doc, "spacy", "1", "m", {}, toks)
        if d % 20 == 0:
            proj._con.commit()
    proj._con.commit()
    proj.close()


def _drop_all(con: sqlite3.Connection) -> None:
    for n in ALL:
        con.execute(f"DROP INDEX IF EXISTS {n}")
    con.commit()


def _median(fn, runs: int = 3) -> float:
    ts = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t)
    return statistics.median(ts)


def measure(base: Path, work: Path, name: str, wanted: list[str]) -> dict:
    db = work / "v.ttwa"
    shutil.copyfile(base, db)
    con = sqlite3.connect(db)
    _drop_all(con)
    sql = dict(INDEXES)
    t = time.perf_counter()
    for n in wanted:
        con.execute(sql[n])
    con.commit()
    create = time.perf_counter() - t
    con.execute("VACUUM")
    con.close()
    proj = TTWAProject(db)
    proj._con = sqlite3.connect(db)          # sem _connect: ele recriaria os índices do esquema
    proj._con.row_factory = sqlite3.Row
    q = lambda f, *a, **k: (lambda: f(proj, "c", *a, **k))  # noqa: E731
    out = {"conjunto": name, "tamanho_mb": round(db.stat().st_size / 1e6, 1), "criar_s": round(create, 2),
           "kwic_forma_s": _median(q(query.kwic, "w5", limit=50)),
           "kwic_raro_s": _median(q(query.kwic, "w9000", limit=50)),
           "kwic_lema_pos_s": _median(q(query.kwic, "lemma=w40 & upos=ADV", limit=50)),
           "kwic_pos_s": _median(q(query.kwic, "pos=X7", limit=50)),
           "busca_s": _median(q(query.search, "w5")),
           "frequencia_s": _median(q(query.frequency, unit="lemma", top=100)),
           "colocados_s": _median(q(query.collocates, "w5", top=30)),
           "dispersao_s": _median(q(query.dispersion, "w5"))}
    proj._con.close()
    db.unlink()
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tokens", type=int, default=2_000_000)
    ap.add_argument("--dir", help="pasta temporária (padrão: do sistema); apagada ao fim")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="ttw_bench_", dir=args.dir))
    try:
        base = work / "base.ttwa"
        t = time.perf_counter()
        build(base, args.tokens)
        print(f"projeto sintético: {args.tokens} tokens em {time.perf_counter() - t:.0f} s", file=sys.stderr)
        con = sqlite3.connect(base)
        _drop_all(con)
        con.execute("VACUUM")
        con.close()
        rows = [measure(base, work, n, w) for n, w in SETS.items()]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        cols = list(rows[0])
        print(" | ".join(cols))
        for r in rows:
            print(" | ".join(str(r[c]) for c in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
