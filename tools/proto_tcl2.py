"""Protótipo TCL2 (spike de medição): camadas como inteiros + léxico por corpus. Não muda o app nem o formato gravado.

    python tools/proto_tcl2.py PROJETO [--corpus essays_bawe_somentetexto] [--ferramentas spacy,stanza]
                               [--pasta PASTA_DE_TRABALHO] [--saida relatorio.md] [--max-camadas N] [--sem-sqlite]

PROJETO: .ttwa (gzip de SQLite) ou SQLite puro, de preferência o real e grande. Roda numa CÓPIA feita na pasta
de trabalho (o original nunca é tocado); tudo o que cria é apagado ao fim, mesmo com Ctrl-C. Exige ~4× o
tamanho descompactado em disco livre. Um processo só. Imprime a tabela em Markdown (formato de novodesenho/macintel.md)
e a grava em --saida. `--max-camadas N` roda só N camadas por ferramenta (teste rápido; números não valem).

O que mede (novodesenho/plano.md seção 4, "Especificação do spike"): léxico por corpus e por coluna (ids por frequência
decrescente); camadas como colunas de inteiros (largura fixa × varint, cada coluna com seu zlib); tamanho contra `TCL1`
(`layerfmt.encode`), JSON+zlib e a tabela `tokens` com os 5 índices; codificar e decodificar (só ids × linhas completas);
frequência por `bincount` e matriz documento × tipo contra o laço atual; regex e glob no léxico (viram máscara sobre ids)
contra `REGEXP` por linha e `GLOB` do SQLite; pico de memória; crescimento do léxico ao somar ferramentas.
Limite conhecido: posições nulas (`start_char` ou `end_char` `NULL`) não são tratadas (o spike para com erro).
"""

from __future__ import annotations

import argparse
import fnmatch
import gzip
import json
import os
import platform
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from array import array
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from ttwtools import layerfmt  # noqa: E402

COLS = ["start", "end", "word", "lemma", "upos", "xpos", "feats", "tags", "extra"]
TEXT = list(range(2, 9))
SEL = "SELECT start_char, end_char, word, lemma, upos, xpos, feats, tags, extra FROM tokens WHERE layer_id = ? ORDER BY idx"
MAGIC2 = b"TCL2"
_LEVEL = 6
REGEX = r"^(un|re)[a-z]{3,}(ed|ing)$"
GLOB = "*tion"
pc = time.perf_counter


# ----------------------------------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------------------------------

def _sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def mb(n):
    return f"{n / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def num(x, d=2):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ti(x):
    return f"{x:,}".replace(",", ".")


def peak_mb():
    try:
        import resource
        v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return v / 1e6 if sys.platform == "darwin" else v / 1e3
    except Exception:  # noqa: BLE001
        return float("nan")


def machine_info():
    if sys.platform == "darwin":
        cpu = _sh(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor()
        try:
            mem = int(_sh(["sysctl", "-n", "hw.memsize"])) // 2 ** 20
        except ValueError:
            mem = 0
    else:
        cpu, mem = platform.processor(), 0
        try:
            mem = int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1)) // 1024
        except Exception:  # noqa: BLE001
            pass
    commit = _sh(["git", "-C", str(HERE.parent), "rev-parse", "--short", "HEAD"])
    return [f"- Data: {time.strftime('%Y-%m-%d %H:%M')}", f"- Sistema: {platform.platform()}",
            f"- Processador: {cpu} ({os.cpu_count()} núcleos lógicos)", f"- Memória: {mem:,} MB".replace(",", "."),
            f"- Python {platform.python_version()} · SQLite {sqlite3.sqlite_version} · numpy {np.__version__} · ttwtools (commit {commit})"]


# ----------------------------------------------------------------------------------------------
# codec TCL2 (candidato): colunas de inteiros, cada uma com seu zlib; léxico fora
# ----------------------------------------------------------------------------------------------

def _zig(d: np.ndarray) -> np.ndarray:
    return ((d << 1) ^ (d >> 63)).astype(np.uint64)


def _unzig(u: np.ndarray) -> np.ndarray:
    u = u.astype(np.uint64)
    return ((u >> np.uint64(1)).astype(np.int64)) ^ -((u & np.uint64(1)).astype(np.int64))


def _width(maxv: int) -> int:
    return 1 if maxv < 256 else 2 if maxv < 65536 else 4 if maxv < 2 ** 32 else 8


def varint_encode(a: np.ndarray) -> bytes:
    a = a.astype(np.uint64)
    nb = 1 + (a >= 1 << 7).astype(np.int64) + (a >= 1 << 14) + (a >= 1 << 21) + (a >= 1 << 28) + (a >= 1 << 35)
    ends = np.cumsum(nb)
    starts = ends - nb
    out = np.empty(int(ends[-1]) if len(a) else 0, np.uint8)
    for k in range(6):
        m = nb > k
        if not m.any():
            break
        val = ((a[m] >> np.uint64(7 * k)) & np.uint64(0x7F)).astype(np.uint8)
        out[starts[m] + k] = val | ((nb[m] > k + 1).astype(np.uint8) << 7)
    return out.tobytes()


def varint_decode(raw: bytes) -> np.ndarray:
    b = np.frombuffer(raw, np.uint8)
    ends = np.flatnonzero(b < 128)
    starts = np.concatenate(([0], ends[:-1] + 1))
    ln = ends - starts + 1
    out = np.zeros(len(ends), np.uint64)
    for k in range(int(ln.max()) if len(ln) else 0):
        m = ln > k
        out[m] |= (b[starts[m] + k] & 0x7F).astype(np.uint64) << np.uint64(7 * k)
    return out


class Lexicon:
    """Léxico por corpus: por coluna de texto, valores ordenados por frequência decrescente; id 0 = None."""

    def __init__(self, counters: dict[int, Counter]):
        self.values: dict[int, list] = {}
        self.index: dict[int, dict] = {}
        for c, cnt in counters.items():
            vals = [v for v, _ in sorted(((v, f) for v, f in cnt.items() if v is not None), key=lambda x: (-x[1], x[0]))]
            self.values[c] = [None] + vals
            d = {v: i for i, v in enumerate(vals, 1)}
            d[None] = 0
            self.index[c] = d

    def serialized(self) -> int:
        return sum(len(zlib.compress(json.dumps(self.values[c][1:], ensure_ascii=False, separators=(",", ":")).encode(), _LEVEL))
                   for c in TEXT)


def encode_columns(rows, lex: Lexicon):
    """Linhas → (blob TCL2 com largura fixa, (tamanhos por coluna fixa, por coluna varint), [tempos]). Só ids."""
    n = len(rows)
    t0 = pc()
    cols = list(zip(*rows)) if n else [()] * 9
    s = np.fromiter(cols[0], np.int64, n)          # levanta TypeError se houver None
    e = np.fromiter(cols[1], np.int64, n)
    streams = [_zig(np.diff(s, prepend=0)), _zig(e - s)]
    for c in TEXT:
        g = lex.index[c].__getitem__
        streams.append(np.frombuffer(array("I", map(g, cols[c])), np.uint32))
    t_map = pc() - t0
    t1 = pc()
    fixed, var, parts = [], [], [MAGIC2, struct.pack("<I", n)]
    for a in streams:
        w = _width(int(a.max()) if n else 0)
        z = zlib.compress(a.astype(f"<u{w}").tobytes(), _LEVEL)
        parts += [struct.pack("<BI", w, len(z)), z]
        fixed.append(len(z) + 5)
        var.append(len(zlib.compress(varint_encode(a), _LEVEL)) + 5)
    return b"".join(parts), (fixed, var), [t_map, pc() - t1]


def _chunks(blob: bytes):
    n = struct.unpack_from("<I", blob, 4)[0]
    pos, out = 8, []
    for _ in range(9):
        w, ln = struct.unpack_from("<BI", blob, pos)
        out.append((w, blob[pos + 5:pos + 5 + ln]))
        pos += 5 + ln
    return n, out


def decode_ids(blob: bytes, which=tuple(range(2, 9))) -> dict[int, np.ndarray]:
    """Só os ids das colunas pedidas (2..8 = texto; 0 e 1 devolvem início e fim em caracteres)."""
    n, ch = _chunks(blob)

    def col(i):
        w, z = ch[i]
        return np.frombuffer(zlib.decompress(z), f"<u{w}")

    out = {}
    if 0 in which or 1 in which:
        start = np.cumsum(_unzig(col(0)))
        out[0], out[1] = start, start + _unzig(col(1))
    for c in which:
        if c >= 2:
            out[c] = col(c)
    return out


def decode_rows(blob: bytes, lex: Lexicon):
    ids = decode_ids(blob, tuple(range(0, 9)))
    cols = [ids[0].tolist(), ids[1].tolist()]
    for c in TEXT:
        L = lex.values[c]
        cols.append([L[i] for i in ids[c].tolist()])
    return list(zip(*cols))


# ----------------------------------------------------------------------------------------------
# projeto
# ----------------------------------------------------------------------------------------------

def open_copy(src: Path, work: Path) -> Path:
    dst = work / "copia.sqlite"
    with open(src, "rb") as f:
        gz = f.read(2) == b"\x1f\x8b"
    if gz:
        with gzip.open(src, "rb") as a, open(dst, "wb") as b:
            shutil.copyfileobj(a, b, 1 << 20)
    else:
        shutil.copyfile(src, dst)
    return dst


def layer_list(con, corpus, tools, cap, with_lemma=False):
    out = []
    for t in tools:
        q = ("SELECT l.id, l.doc_id, l.n_tokens FROM layers l JOIN documents d ON d.id = l.doc_id "
             "WHERE l.tool = ? AND d.corpus_name = ?"
             + (" AND EXISTS (SELECT 1 FROM tokens t WHERE t.layer_id = l.id AND t.lemma IS NOT NULL)" if with_lemma else "")
             + " ORDER BY l.id")
        rows = con.execute(q, (t, corpus)).fetchall()
        out += [(t, *r) for r in (rows[:cap] if cap else rows)]
    return out


def read_rows(con, lid, has_tokens):
    if has_tokens:
        return con.execute(SEL, (lid,)).fetchall()
    blob = con.execute("SELECT data FROM layer_blobs WHERE layer_id = ?", (lid,)).fetchone()[0]
    return [tuple(r) for r in layerfmt.decode(bytes(blob))]


def free_gb(p):
    return shutil.disk_usage(p).free / 2 ** 30


# ----------------------------------------------------------------------------------------------
# execução
# ----------------------------------------------------------------------------------------------

def run(args, work: Path, out: list[str]):
    R: dict = {}
    src = Path(args.projeto).expanduser()
    size_src = src.stat().st_size
    print(f"livre: {free_gb(work):.1f} GB; arquivo: {size_src / 1e9:.2f} GB", flush=True)
    if free_gb(work) < args.min_livre_gb:
        raise SystemExit(f"Só {free_gb(work):.1f} GB livres em {work}; exige ≥ {args.min_livre_gb} GB.")
    t = pc()
    copy = open_copy(src, work)
    R["copiar"] = pc() - t
    con = sqlite3.connect(copy)
    has_tokens = con.execute("SELECT count(*) FROM (SELECT 1 FROM tokens LIMIT 1)").fetchone()[0] > 0
    tools = [x.strip() for x in args.ferramentas.split(",")]
    layers = layer_list(con, args.corpus, tools, args.max_camadas, args.so_com_lema)
    if not layers:
        raise SystemExit(f"Nenhuma camada de {tools} no corpus {args.corpus!r}.")
    ntok = sum(x[3] for x in layers)
    R["ntok"], R["nlay"] = ntok, len(layers)
    print(f"{len(layers)} camadas, {ntok:,} tokens; tabela tokens: {'sim' if has_tokens else 'não (usa layer_blobs)'}", flush=True)

    # ---- passo 1: fluxo; TCL1, JSON+zlib, contagens do léxico
    cnt = {tool: {c: Counter() for c in TEXT} for tool in tools}
    t_read = t_e1 = t_d1 = t_json = 0.0
    tcl1 = js = 0
    local_entries = 0
    for k, (tool, lid, did, n) in enumerate(layers):
        t = pc(); rows = read_rows(con, lid, has_tokens); t_read += pc() - t
        t = pc(); b1 = layerfmt.encode(rows); t_e1 += pc() - t
        t = pc(); layerfmt.decode(b1); t_d1 += pc() - t
        tcl1 += len(b1)
        t = pc(); js += len(zlib.compress(json.dumps(rows, ensure_ascii=False).encode(), _LEVEL)); t_json += pc() - t
        for c, col in zip(TEXT, list(zip(*rows))[2:]):
            cnt[tool][c].update(col)
            local_entries += len(set(col))
        if k % 500 == 0:
            print(f"  passo 1: {k}/{len(layers)}", flush=True)
    R.update(tcl1=tcl1, json=js, t_read=t_read, t_e1=t_e1, t_d1=t_d1, mem1=peak_mb())

    # ---- léxico por corpus e por ferramenta
    t = pc()
    merged = {c: sum((cnt[tool][c] for tool in tools), Counter()) for c in TEXT}
    lex = Lexicon(merged)
    R["t_lex"] = pc() - t
    R["lex_size"] = lex.serialized()
    R["lex_n"] = {c: len(lex.values[c]) - 1 for c in TEXT}
    growth = []
    for c in TEXT:
        a = len([v for v in cnt[tools[0]][c] if v is not None])
        b = R["lex_n"][c]
        s = sum(len([v for v in cnt[tool][c] if v is not None]) for tool in tools)
        growth.append((COLS[c], a, b, s))
    R["growth"], R["local_entries"] = growth, local_entries

    # ---- passo 2: TCL2 (ids); guarda blobs; monta a tabela tokens temporária com o mesmo grupo
    sq = None
    if not args.sem_sqlite:
        sq = sqlite3.connect(work / "tokens_tmp.sqlite")
        sq.executescript("""CREATE TABLE tokens (layer_id INTEGER NOT NULL, idx INTEGER NOT NULL, doc_id INTEGER NOT NULL,
            start_char INTEGER, end_char INTEGER, word TEXT, lemma TEXT, upos TEXT, xpos TEXT, feats TEXT, tags TEXT, extra TEXT,
            PRIMARY KEY (layer_id, idx)) WITHOUT ROWID;""")
        sq.execute("PRAGMA journal_mode=OFF"); sq.execute("PRAGMA synchronous=OFF")
    colf, colv = [0] * 9, [0] * 9
    blobs, t_map, t_z, t_ins = [], 0.0, 0.0, 0.0
    for k, (tool, lid, did, n) in enumerate(layers):
        rows = read_rows(con, lid, has_tokens)
        blob, vs, (tm, tz) = encode_columns(rows, lex)
        blobs.append(blob)
        colf = [a + b for a, b in zip(colf, vs[0])]
        colv = [a + b for a, b in zip(colv, vs[1])]
        t_map += tm; t_z += tz
        if sq is not None:
            t = pc()
            sq.executemany("INSERT INTO tokens VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                           ((lid, i, did, *r) for i, r in enumerate(rows)))
            t_ins += pc() - t
        if k % 500 == 0:
            print(f"  passo 2: {k}/{len(layers)}", flush=True)
    tcl2 = sum(len(b) for b in blobs)
    R.update(tcl2=tcl2, tcl2_var=sum(colv), colf=colf, colv=colv, t_map=t_map, t_z=t_z, t_ins=t_ins, mem2=peak_mb())

    # ---- tamanho da tabela tokens (sem e com os 5 índices)
    if sq is not None:
        sq.commit()
        page = lambda: sq.execute("PRAGMA page_count").fetchone()[0] * sq.execute("PRAGMA page_size").fetchone()[0]  # noqa: E731
        R["sql_sem_ind"] = page()
        t = pc()
        for stmt in ("CREATE INDEX idx_tokens_xpos ON tokens (xpos)", "CREATE INDEX idx_tokens_doc ON tokens (doc_id)",
                     "CREATE INDEX idx_tokens_lword ON tokens (lower(word))", "CREATE INDEX idx_tokens_llemma ON tokens (lower(lemma))",
                     "CREATE INDEX idx_tokens_upos ON tokens (upos)"):
            sq.execute(stmt)
        sq.commit()
        R["t_ind"] = pc() - t
        R["sql_com_ind"] = page()

    # ---- decodificar: só ids × linhas completas; verificação de igualdade
    t = pc(); ids_all = [decode_ids(b, (2, 3, 4, 5)) for b in blobs]; R["t_d_ids4"] = pc() - t
    t = pc(); [decode_ids(b, (2,)) for b in blobs]; R["t_d_id1"] = pc() - t
    t = pc(); [decode_ids(b, tuple(range(9))) for b in blobs]; R["t_d_ids9"] = pc() - t
    t = pc(); [decode_rows(b, lex) for b in blobs]; R["t_d_rows"] = pc() - t
    bad = 0
    for k in range(0, len(layers), max(1, len(layers) // 60)):
        if decode_rows(blobs[k], lex) != [tuple(r) for r in read_rows(con, layers[k][1], has_tokens)]:
            bad += 1
    R["verif_ruins"] = bad
    # implementação real (biblioteca padrão): layerfmt.encode_tcl2 / decode, léxico na ordem de chegada
    rl = layerfmt.Lexicon()
    t_re = t_rd = 0.0
    real_size = 0
    real_bad = 0
    for k, (tool, lid, did, n) in enumerate(layers):
        rows = [tuple(r) for r in read_rows(con, lid, has_tokens)]
        t = pc(); b = layerfmt.encode_tcl2(rows, rl); t_re += pc() - t
        real_size += len(b)
        t = pc(); back = layerfmt.decode(b, rl); t_rd += pc() - t
        if k % 50 == 0 and [tuple(r) for r in back] != rows:
            real_bad += 1
    R["real_size"] = real_size
    R["real_lex"] = sum(len(zlib.compress(json.dumps(rl.values[c][1:], ensure_ascii=False, separators=(",", ":")).encode(), _LEVEL)) for c in TEXT)
    R["t_real_e"], R["t_real_d"], R["real_bad"] = t_re, t_rd, real_bad
    ref = np.concatenate([decode_ids(b, (2,))[2] for b in blobs[:50]]).astype(np.uint64)
    vraw = varint_encode(ref)
    t = pc(); back = varint_decode(vraw); R["t_d_varint"], R["varint_tok"] = pc() - t, len(ref)
    R["varint_ok"] = bool(np.array_equal(back, ref))
    R["mem3"] = peak_mb()

    # ---- unidade da frequência: lema, se as camadas tiverem lema; senão a forma
    unit_col = 3 if R["lex_n"][3] > 0 else 2
    R["unit"] = COLS[unit_col]
    uid = [d[unit_col] for d in ids_all]
    word_ids = np.concatenate([d[2] for d in ids_all])
    V = len(lex.values[unit_col])

    # frequência por bincount × laço atual
    t = pc(); allu = np.concatenate(uid); R["t_cat"] = pc() - t
    t = pc(); bc = np.bincount(allu.astype(np.int64), minlength=V); R["t_bincount"] = pc() - t
    # matriz documento × tipo (esparsa) por unique
    t = pc()
    lay_of = np.repeat(np.arange(len(uid), dtype=np.int64), [len(a) for a in uid])
    key = lay_of * V + allu.astype(np.int64)
    uk, uc = np.unique(key, return_counts=True)
    R["t_matrix"], R["matrix_nnz"] = pc() - t, len(uk)
    if sq is not None:
        col = "lemma" if unit_col == 3 else "word"
        per_layer: list[Counter] = []
        t = pc()
        for tool, lid, did, n in layers:
            c = Counter()
            for (v,) in sq.execute(f"SELECT {col} FROM tokens WHERE layer_id = ? ORDER BY idx", (lid,)):
                c[v] += 1
            per_layer.append(c)
        total = Counter()
        for c in per_layer:
            total.update(c)
        R["t_loop"] = pc() - t
        total.pop(None, None)
        vals = lex.values[unit_col]
        same = all(bc[i] == total.get(vals[i], 0) for i in range(1, V)) and int(bc[1:].sum()) == sum(total.values())
        R["freq_igual"] = same

        # regex e glob: léxico × SQLite
        wv = lex.values[2]
        rx = re.compile(REGEX, re.IGNORECASE)
        t = pc(); mask = np.zeros(len(wv), bool)
        for i in range(1, len(wv)):
            if rx.search(wv[i]):
                mask[i] = True
        R["t_rx_lex"] = pc() - t
        t = pc(); n_rx = int(mask[word_ids].sum()); R["t_rx_ids"] = pc() - t
        sq.create_function("REGEXP", 2, lambda p, v: v is not None and re.search(p, v, re.IGNORECASE) is not None, deterministic=True)
        t = pc(); n_rx_sql = sq.execute("SELECT count(*) FROM tokens WHERE word REGEXP ?", (REGEX,)).fetchone()[0]
        R["t_rx_sql"] = pc() - t
        grx = re.compile(fnmatch.translate(GLOB))
        t = pc(); gm = np.zeros(len(wv), bool)
        for i in range(1, len(wv)):
            if grx.match(wv[i].lower()):
                gm[i] = True
        R["t_gl_lex"] = pc() - t
        t = pc(); n_gl = int(gm[word_ids].sum()); R["t_gl_ids"] = pc() - t
        t = pc(); n_gl_sql = sq.execute("SELECT count(*) FROM tokens WHERE lower(word) GLOB ?", (GLOB,)).fetchone()[0]
        R["t_gl_sql"] = pc() - t
        R["rx_n"], R["rx_igual"] = n_rx, n_rx == n_rx_sql
        R["gl_n"], R["gl_igual"] = n_gl, n_gl == n_gl_sql
        R["lex_words"] = len(wv) - 1
        sq.close()
    R["mem4"] = peak_mb()
    con.close()
    return R


def markdown(R, args, hdr):
    n = R["ntok"]
    t1, t2 = R["tcl1"], R["tcl2"]
    L = ["# Protótipo TCL2: medição", "", "## Máquina", ""] + hdr + [
        "", f"Corpus `{args.corpus}`, camadas `{args.ferramentas}`: {R['nlay']} camadas, {ti(n)} tokens"
        + (" **(teste parcial: `--max-camadas`; números não valem)**" if args.max_camadas else "") + ".", "",
        "## 1. Tamanho", "", "| formato | MB | bytes/token | razão ao TCL1 |", "|---|---|---|---|"]

    def row(name, b):
        return f"| {name} | {mb(b)} | {num(b / n)} | {num(b / t1)} |"
    L += [row("JSON + zlib (antigo)", R["json"]), row("`TCL1` (atual, dicionário por documento)", t1),
          row("`TCL2` largura fixa + zlib por coluna, camadas", t2),
          row("`TCL2` largura fixa, camadas + léxico do corpus (1×)", t2 + R["lex_size"]),
          row("`TCL2` varint + zlib por coluna, camadas + léxico", R["tcl2_var"] + R["lex_size"])]
    if "sql_sem_ind" in R:
        L += [row("tabela `tokens` sem índices", R["sql_sem_ind"]), row("tabela `tokens` com os 5 índices (hoje)", R["sql_com_ind"])]
    L += [row("**`TCL2` real** (`layerfmt.encode_tcl2`, biblioteca padrão, léxico em ordem de chegada; camadas + léxico)", R["real_size"] + R["real_lex"])]
    L += ["", "### Onde estão os bytes do `TCL2` (camadas, sem o léxico)", "", "| coluna | fixa (MB) | varint (MB) | bytes/token (fixa) |", "|---|---|---|---|"]
    L += [f"| {COLS[i]} | {num(R['colf'][i] / 1e6)} | {num(R['colv'][i] / 1e6)} | {num(R['colf'][i] / n)} |" for i in range(9)]
    L += ["", f"_Léxico serializado (JSON+zlib): {mb(R['lex_size'])} MB. Entradas de dicionário somadas por camada no `TCL1`: "
          f"{ti(R['local_entries'])}; entradas do léxico por corpus: {ti(sum(R['lex_n'].values()))}._", "",
          "### Léxico por coluna e crescimento ao somar ferramentas", "",
          f"| coluna | só `{args.ferramentas.split(',')[0]}` | união (léxico por corpus) | soma dos léxicos separados |", "|---|---|---|---|"]
    L += [f"| {c} | {ti(a)} | {ti(b)} | {ti(s)} |" for c, a, b, s in R["growth"]]
    tps = lambda t: f"{n / t / 1e6:,.2f}".replace(".", ",") if t else "—"  # noqa: E731
    L += ["", "## 2. Velocidade (Mtokens/s; maior é melhor)", "", "| medida | tempo (s) | Mtok/s |", "|---|---|---|"]
    for name, t in [("ler linhas do SQLite (referência)", R["t_read"]), ("codificar `TCL1`", R["t_e1"]),
                    ("codificar `TCL2`: linhas → ids (dicionários Python)", R["t_map"]),
                    ("codificar `TCL2`: zlib das colunas (largura fixa + varint, ambos)", R["t_z"]),
                    ("decodificar `TCL1` (linhas completas)", R["t_d1"]),
                    ("decodificar `TCL2`: 1 coluna de ids (`word`)", R["t_d_id1"]),
                    ("decodificar `TCL2`: 4 colunas de ids (word, lemma, upos, xpos)", R["t_d_ids4"]),
                    ("decodificar `TCL2`: 9 colunas (só ids e posições)", R["t_d_ids9"]),
                    ("decodificar `TCL2`: linhas completas com strings", R["t_d_rows"]),
                    ("**`TCL2` real**: codificar (`encode_tcl2`, biblioteca padrão)", R["t_real_e"]),
                    ("**`TCL2` real**: decodificar linhas completas (`decode`)", R["t_real_d"])]:
        L.append(f"| {name} | {num(t)} | {tps(t)} |")
    L += ["", f"_`TCL2` real: {R['real_bad']} camadas amostradas com ida e volta diferente (esperado 0)._"]
    L += ["", f"_Verificação: {R['verif_ruins']} camadas amostradas com decodificação diferente da original (esperado 0). "
          f"Varint (vetorizado com numpy; em biblioteca padrão seria laço Python): decodificar `word` de 50 camadas "
          f"({ti(R['varint_tok'])} ids) em {num(R['t_d_varint'], 3)} s, ida e volta {'ok' if R['varint_ok'] else '**FALHOU**'}._"]
    if "t_loop" in R:
        L += ["", f"## 3. Consultas sobre ids × laço atual (unidade: **{R['unit']}**"
              + ("; lemas vazios nessas camadas, medida sobre a forma" if R["unit"] == "word" else "") + ")", "",
              "| medida | `TCL2` (ids) | laço atual (SQLite + `Counter`) | razão |", "|---|---|---|---|",
              f"| frequência do corpus | {num(R['t_bincount'], 3)} s (+ {num(R['t_cat'], 3)} s juntar) | {num(R['t_loop'])} s | {num(R['t_loop'] / max(R['t_bincount'], 1e-9), 0)}× |",
              f"| matriz documento × tipo ({ti(R['matrix_nnz'])} células) | {num(R['t_matrix'], 3)} s | {num(R['t_loop'])} s (mesmo laço) | {num(R['t_loop'] / max(R['t_matrix'], 1e-9), 0)}× |",
              f"| resultado igual ao do laço | {'sim' if R['freq_igual'] else '**NÃO**'} | | |", "",
              f"_Sem incluir o custo de decodificar os ids (seção 2). O laço é o de `query.frequency`: `SELECT` por camada e `Counter`; a função em si não foi chamada (exigiria abrir o projeto)._", "",
              f"### Regex e glob sobre `word` ({ti(R['lex_words'])} formas distintas no léxico)", "",
              "| consulta | léxico (varre) + máscara sobre ids | `TCL2` total | SQLite | razão | ocorrências | igual |", "|---|---|---|---|---|---|---|"]
        for nm, a, b, sql, occ, eq in [(f"regex `{REGEX.replace('|', chr(92) + '|')}` (REGEXP por linha)", "t_rx_lex", "t_rx_ids", "t_rx_sql", "rx_n", "rx_igual"),
                                        (f"glob `{GLOB}` (`lower(word) GLOB`, C nativo)", "t_gl_lex", "t_gl_ids", "t_gl_sql", "gl_n", "gl_igual")]:
            tot = R[a] + R[b]
            L.append(f"| {nm} | {num(R[a], 3)} s + {num(R[b], 3)} s | {num(tot, 3)} s | {num(R[sql])} s | {num(R[sql] / max(tot, 1e-9), 0)}× | {ti(R[occ])} | {'sim' if R[eq] else '**NÃO**'} |")
        L += ["", f"_Montar a tabela `tokens` temporária: inserir {num(R['t_ins'])} s; criar os 5 índices {num(R['t_ind'])} s._"]
    L += ["", "## 4. Memória (pico acumulado do processo, MB)", "", "| depois de | MB |", "|---|---|",
          f"| passo 1 (fluxo: TCL1, JSON, contagens) | {num(R['mem1'], 0)} |", f"| passo 2 (TCL2 e tabela temporária) | {num(R['mem2'], 0)} |",
          f"| decodificações | {num(R['mem3'], 0)} |", f"| consultas | {num(R['mem4'], 0)} |"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("projeto")
    ap.add_argument("--corpus", default="essays_bawe_somentetexto")
    ap.add_argument("--ferramentas", default="spacy,stanza")
    ap.add_argument("--pasta", default=None)
    ap.add_argument("--saida", default=None)
    ap.add_argument("--max-camadas", type=int, default=0)
    ap.add_argument("--so-com-lema", action="store_true", help="só camadas com lema preenchido (exige a tabela tokens)")
    ap.add_argument("--sem-sqlite", action="store_true", help="pula a tabela tokens temporária e as comparações com SQLite")
    ap.add_argument("--min-livre-gb", type=float, default=20)
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="proto_tcl2_", dir=args.pasta))
    try:
        R = run(args, work, [])
        md = markdown(R, args, machine_info())
        print("\n" + md)
        if args.saida:
            Path(args.saida).write_text(md, encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
