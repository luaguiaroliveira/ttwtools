"""Mede, na sua máquina, as opções de armazenamento do TTWtools e grava um relatório em Markdown.

    python tools/bench_storage.py [PROJETO] [--saida relatorio.md] [--pasta PASTA_DE_TRABALHO]
                                  [--tokens 1000000] [--tolerancia-min 5]

Sem PROJETO roda só as medições sintéticas (~2 min). Com PROJETO (.ttwa/.ttwt, de preferência o real
e grande) roda também o ciclo completo numa CÓPIA: o original nunca é tocado. Tudo que o script cria
(cópias, cache, pastas temporárias) fica na pasta de trabalho e é apagado ao fim, mesmo com Ctrl-C.
O relatório é regravado a cada etapa: se interromper, o que já foi medido fica salvo.

Um processo só; nada roda em segundo plano. Guia passo a passo: novodesenho/verificacao/macos-intel-armazenamento.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _mb(n: float) -> str:
    return f"{n / 1e6:,.0f} MB".replace(",", ".")


def _sec(x: float) -> str:
    return f"{x:.1f} s" if x < 100 else f"{x / 60:.1f} min"


class Report:
    """Relatório em Markdown, regravado a cada etapa."""

    def __init__(self, path: Path):
        self.path = path
        self.env: list[str] = []
        self.sections: list[tuple[str, list[str]]] = []
        self.data: dict = {}          # números para a recomendação

    def section(self, title: str) -> list[str]:
        lines: list[str] = []
        self.sections.append((title, lines))
        return lines

    def write(self, footer: str = "") -> None:
        out = ["# Relatório de armazenamento do TTWtools", "", "## Máquina", ""] + [f"- {l}" for l in self.env] + [""]
        for title, lines in self.sections:
            out += [f"## {title}", ""] + lines + [""]
        if footer:
            out += [footer]
        self.path.write_text("\n".join(out) + "\n", encoding="utf-8")


def machine_info() -> list[str]:
    cpu = _sh(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor() or platform.machine()
    mem = _sh(["sysctl", "-n", "hw.memsize"])
    import sqlite3
    import ttwtools
    rev = _sh(["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"])
    return [
        f"Data: {dt.datetime.now():%Y-%m-%d %H:%M}",
        f"Sistema: {platform.platform()}",
        f"Processador: {cpu} ({os.cpu_count()} núcleos lógicos)",
        f"Memória: {_mb(int(mem)) if mem.isdigit() else '?'} · troca (swap): {_sh(['sysctl', '-n', 'vm.swapusage']) or '?'}",
        f"Pressão de memória: {(_sh(['memory_pressure']).splitlines() or ['?'])[-1]}",
        f"Python {platform.python_version()} · SQLite {sqlite3.sqlite_version} · ttwtools {getattr(ttwtools, '__version__', '?')}"
        + (f" (commit {rev})" if rev else ""),
    ]


def ticker():
    """Callback de progresso que imprime no terminal no máximo a cada 3 s (etapa e andamento)."""
    last = [0.0]

    def cb(done, total, stage="") -> None:
        now = time.perf_counter()
        if now - last[0] < 3 and done != total:
            return
        last[0] = now
        if stage == "decompress":
            txt = f"descompactando {done / 1e6:,.0f} / {total / 1e6:,.0f} MB".replace(",", ".")
        else:
            txt = f"{stage}: {done:,} / {total:,}".replace(",", ".")
        print(f"\n      {txt}", end="", flush=True)
    return cb


def describe(src: Path) -> list[str]:
    """Que tipo de arquivo é (compactado, banco direto, esquema, tabelas de busca) e o que abrir vai fazer."""
    import sqlite3
    from ttwtools.project import compression_of, needs_migration
    out = []
    kind = compression_of(src)
    out.append(f"formato: **{'compactado (' + kind + ')' if kind else 'banco direto (SQLite)'}**, {_mb(src.stat().st_size)}")
    if kind:
        out.append("abrir = **descompactar** para uma cópia de trabalho (o tamanho cresce na pasta `tmp/ttw_work_*`)")
        return out
    try:
        con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        try:
            v = con.execute("SELECT value FROM project_meta WHERE key='schema_version'").fetchone()
        finally:
            con.close()
        out.append(f"esquema: **{v[0] if v else 'antigo (sem versão)'}**")
    except sqlite3.Error:
        pass
    if needs_migration(src):
        out.append("**abrir vai MIGRAR o arquivo** (esquema antigo, ou salvo sem tabelas): pode levar muitos minutos; "
                   "para medir o ciclo normal use um projeto já migrado")
    return out


def med(fn, n: int = 3) -> float:
    xs = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        xs.append(time.perf_counter() - t)
    return statistics.median(xs)


def step(rep: Report, lines: list[str], label: str, fn):
    """Roda uma etapa, mostra no terminal, registra erro sem parar o resto."""
    print(f"  · {label} ...", end="", flush=True)
    t = time.perf_counter()
    try:
        out = fn()
        print(f" {_sec(time.perf_counter() - t)}", flush=True)
        return out
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f" ERRO: {exc}", flush=True)
        lines.append(f"- **{label}: ERRO** — `{type(exc).__name__}: {exc}`")
        lines.append("```\n" + traceback.format_exc(limit=3) + "```")
        rep.write()
        return None


# ---------------------------------------------------------------------------
# 1. Micro-medições (velocidade bruta da máquina)
# ---------------------------------------------------------------------------

def micro(rep: Report) -> None:
    from ttwtools import layerfmt
    lines = rep.section("1. Velocidade bruta da máquina")
    rnd = random.Random(1)
    words = [f"w{i}" for i in range(20000)]
    rows, pos = [], 0
    for w in rnd.choices(range(20000), [1 / (i + 1) for i in range(20000)], k=300_000):
        rows.append((pos, pos + 4, words[w], words[w], "NOUN", f"X{w % 40}", None, None, None))
        pos += 5
    enc = med(lambda: layerfmt.encode(rows), 2)
    blob = layerfmt.encode(rows)
    dec = med(lambda: layerfmt.decode(blob), 2)
    data = os.urandom(1 << 20) * 20                       # 20 MB
    import hashlib
    sha = med(lambda: hashlib.sha256(data).digest(), 2)
    gz = med(lambda: zlib.compress(blob * 30, 1), 1)
    lines += ["| medida | resultado |", "|---|---|",
              f"| codificar camadas (`TCL1`) | {len(rows) / enc / 1e3:,.0f} mil tokens/s |".replace(",", "."),
              f"| decodificar camadas | {len(rows) / dec / 1e3:,.0f} mil tokens/s |".replace(",", "."),
              f"| SHA-256 (chave do cache) | {len(data) / sha / 1e6:,.0f} MB/s |".replace(",", "."),
              f"| zlib nível 1 (salvar compactado) | {len(blob) * 30 / gz / 1e6:,.0f} MB/s |".replace(",", "."), "",
              "_Referência (Apple Silicon M-series): codificar ~890 mil tokens/s, decodificar ~3.300 mil tokens/s._"]
    rep.data["decode_tok_s"] = len(rows) / dec
    rep.write()


# ---------------------------------------------------------------------------
# 2. Índices sintéticos
# ---------------------------------------------------------------------------

def synthetic(rep: Report, work: Path, n_tokens: int) -> None:
    import bench_indexes as B
    lines = rep.section(f"2. Índice de busca em projeto sintético ({n_tokens:,} tokens)".replace(",", "."))
    base = work / "sint.ttwa"
    step(rep, lines, "gerar o projeto sintético", lambda: B.build(base, n_tokens))
    if not base.exists():
        return
    import sqlite3
    con = sqlite3.connect(base)
    B._drop_all(con)
    con.execute("VACUUM")
    con.close()
    rows = []
    for name in ("antigo (7)", "reduzido (5, adotado)"):
        r = step(rep, lines, f"índices {name}", lambda name=name: B.measure(base, work, name, B.SETS[name]))
        if r:
            rows.append(r)
    if rows:
        cols = list(rows[0])
        lines += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
        lines += ["", "_Tempos em segundos. Referência (M-series, 2 milhões de tokens): criar os índices 2,7 s; KWIC 0,03 s; frequência 1,8 s._"]
    base.unlink(missing_ok=True)
    rep.write()


# ---------------------------------------------------------------------------
# 3. Projeto real: as opções lado a lado
# ---------------------------------------------------------------------------

def queries(p, corpus: str) -> dict:
    from ttwtools import query
    return {
        "KWIC (the)": med(lambda: query.kwic(p, corpus, "the", limit=50)),
        "KWIC lema+classe": med(lambda: query.kwic(p, corpus, "lemma=be & pos=VERB", limit=50)),
        "busca (contagem)": med(lambda: query.search(p, corpus, "the")),
        "frequência de lemas": med(lambda: query.frequency(p, corpus, unit="lemma", top=100), 1),
        "colocados": med(lambda: query.collocates(p, corpus, "the", top=30), 1),
        "dispersão": med(lambda: query.dispersion(p, corpus, "the")),
    }


def _both(tick, stages):
    def cb(d, t, s=""):
        if s not in stages:
            stages.append(s)
        tick(d, t, s)
    return cb


def real_project(rep: Report, work: Path, src: Path) -> None:
    import ttwtools
    from ttwtools import searchindex, storage
    lines = rep.section(f"3. Projeto real: `{src.name}` ({_mb(src.stat().st_size)})")
    need = src.stat().st_size * 9
    try:
        storage.ensure_free_space(work, need, "save_as")
    except storage.InsufficientDiskSpace as exc:
        lines.append(f"- **Pulado:** {exc}  (precisa de ~{_mb(need)} livres; use `--pasta` em outro disco)")
        rep.write()
        return
    copy = work / "projeto_copia" / src.name
    copy.parent.mkdir()
    info = describe(src)
    lines += [f"- {i}" for i in info]
    rep.write()
    for i in info:
        print("    " + i.replace("**", ""))
    step(rep, lines, "copiar o projeto para a pasta de trabalho (o original não é tocado)", lambda: shutil.copyfile(src, copy))
    res: dict = {}                                       # etapa -> (segundos, extra)
    t0 = time.perf_counter()
    p = step(rep, lines, "A. abrir o arquivo original", lambda: ttwtools.open_project(copy, progress=ticker()))
    if p is None:
        return
    res["abrir_original"] = time.perf_counter() - t0
    res["banco_original"] = Path(p.path).stat().st_size
    corpus = max(p.list_corpus_names(), key=lambda n: len(p.list_documents(n)))
    tables = p.has_search_tables
    n_tokens = p._con.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
    lines.append(f"- Corpus maior: **{corpus}**; {n_tokens:,} tokens; arquivo original "
                 f"{'com' if tables else 'sem'} tabelas de busca.".replace(",", "."))
    if tables:
        qt = step(rep, lines, "B. consultas com as tabelas dentro do projeto", lambda: queries(p, corpus))
        if qt:
            res["q_tabela"] = qt

    # compactar (remover tagged_files legados)
    dry = step(rep, lines, "C. compactar (simulação)", lambda: ttwtools.compact_project(p, dry_run=True))
    if dry and dry["n_removed"]:
        r = step(rep, lines, "C. compactar (remoção + VACUUM)", lambda: ttwtools.compact_project(p, dry_run=False))
        if r:
            res["compactar"] = (r["size_before"], r["size_after"], r["n_removed"])
    elif dry is not None:
        res["compactar"] = None                          # nada a remover (já compacto)

    # salvar as duas variantes
    t = time.perf_counter()
    full = step(rep, lines, "D. salvar com tabelas de busca (compactado)",
                lambda: ttwtools.save_project_as(p.path, work / "com_tabelas.ttwa", search_tables=True))
    if full:
        res["salvar_com"] = (time.perf_counter() - t, full.stat().st_size)
    t = time.perf_counter()
    lean = step(rep, lines, "E. salvar SEM tabelas de busca (compactado)",
                lambda: ttwtools.save_project_as(p.path, work / "sem_tabelas.ttwa", search_tables=False))
    if lean:
        res["salvar_sem"] = (time.perf_counter() - t, lean.stat().st_size)
    t = time.perf_counter()
    leve = step(rep, lines, "F. exportar o corpus maior (.ttwcl, leve)",
                lambda: ttwtools.save_corpus_as(p, corpus, work / "exp" / f"{corpus}.ttwcl"))
    if leve:
        res["ttwcl"] = (time.perf_counter() - t, leve.stat().st_size)
    p.close()
    shutil.rmtree(work / "projeto_copia", ignore_errors=True)

    # abrir cada variante
    if full:
        t = time.perf_counter()
        q = step(rep, lines, "G. abrir COM tabelas", lambda: ttwtools.open_project(full))
        if q:
            res["abrir_com"] = time.perf_counter() - t
            res["banco_com"] = Path(q.path).stat().st_size
            q.close()
    if lean:
        os.environ["TTWTOOLS_INDEX_CACHE"] = "0"
        t = time.perf_counter()
        q = step(rep, lines, "H. abrir SEM tabelas, cache desligado (recria as tabelas em toda abertura)",
                 lambda: ttwtools.open_project(lean, progress=ticker()))
        if q:
            res["abrir_recria"] = time.perf_counter() - t
            q.close()
        os.environ.pop("TTWTOOLS_INDEX_CACHE", None)

        stages: list[str] = []
        t = time.perf_counter()
        q = step(rep, lines, "I. abrir SEM tabelas com índice em cache, 1ª vez (constrói)",
                 lambda: ttwtools.open_project(lean, progress=_both(ticker(), stages)))
        if q:
            res["abrir_cache_1"] = time.perf_counter() - t
            res["banco_cache"] = Path(q.path).stat().st_size
            res["cache_bytes"] = sum(e["bytes"] for e in storage.cache_entries())
            res["cache_entradas"] = len(searchindex.status(q)["entries"])
            qc = step(rep, lines, "J. consultas via índice em cache", lambda: queries(q, corpus))
            if qc:
                res["q_cache"] = qc
            q.close()
            t = time.perf_counter()
            q = step(rep, lines, "K. abrir SEM tabelas com índice em cache, 2ª vez (pronto)", lambda: ttwtools.open_project(lean))
            if q:
                res["abrir_cache_2"] = time.perf_counter() - t
                q.close()
    rep.data["real"] = res
    summarize_real(rep, lines, res)
    rep.write()


def summarize_real(rep: Report, lines: list[str], r: dict) -> None:
    def g(k, f=_sec):
        return f(r[k]) if k in r else "—"
    lines += ["", "### Resumo das opções", "",
              "| opção | abrir (1ª vez) | abrir (demais) | arquivo em disco | banco de trabalho | cache |",
              "|---|---|---|---|---|---|",
              f"| **1. com tabelas de busca** | {g('abrir_com')} | {g('abrir_com')} | "
              f"{_mb(r['salvar_com'][1]) if 'salvar_com' in r else '—'} | {_mb(r['banco_com']) if 'banco_com' in r else '—'} | — |",
              f"| **2. sem tabelas + índice em cache** | {g('abrir_cache_1')} | {g('abrir_cache_2')} | "
              f"{_mb(r['salvar_sem'][1]) if 'salvar_sem' in r else '—'} | {_mb(r['banco_cache']) if 'banco_cache' in r else '—'} | "
              f"{_mb(r['cache_bytes']) if 'cache_bytes' in r else '—'} |",
              f"| **3. sem tabelas, sem cache** (recria sempre) | {g('abrir_recria')} | {g('abrir_recria')} | "
              f"{_mb(r['salvar_sem'][1]) if 'salvar_sem' in r else '—'} | — | — |", ""]
    if "salvar_com" in r or "salvar_sem" in r:
        lines += [f"- Tempo de salvar: com tabelas {_sec(r['salvar_com'][0]) if 'salvar_com' in r else '—'}; "
                  f"sem tabelas {_sec(r['salvar_sem'][0]) if 'salvar_sem' in r else '—'}."]
    if "ttwcl" in r:
        lines.append(f"- `.ttwcl` do corpus maior: {_mb(r['ttwcl'][1])} em {_sec(r['ttwcl'][0])}.")
    if r.get("compactar"):
        b, a, n = r["compactar"]
        lines.append(f"- Compactar projeto: {n} cópias antigas removidas; banco {_mb(b)} → {_mb(a)}.")
    elif "compactar" in r:
        lines.append("- Compactar projeto: nada a remover (o projeto já estava compacto).")
    if "q_tabela" in r and "q_cache" in r:
        lines += ["", "### Consultas: tabela dentro do projeto × índice em cache (segundos)", "",
                  "| consulta | tabela | cache |", "|---|---|---|"]
        lines += [f"| {k} | {v:.3f} | {r['q_cache'][k]:.3f} |" for k, v in r["q_tabela"].items() if k in r["q_cache"]]
    elif "q_cache" in r:
        lines += ["", "### Consultas via índice em cache (segundos)", "", "| consulta | tempo |", "|---|---|"]
        lines += [f"| {k} | {v:.3f} |" for k, v in r["q_cache"].items()]


# ---------------------------------------------------------------------------
# 4. Recomendação
# ---------------------------------------------------------------------------

def decision(rep: Report, tol_min: float) -> str:
    r = rep.data.get("real", {})
    out = ["", "## 4. Para decidir", ""]
    cold = r.get("abrir_cache_1")
    if cold is not None:
        tol = tol_min * 60
        out += [f"Regra usada (ajuste com `--tolerancia-min`): esperar **até {tol_min:g} min** na 1ª abertura é aceitável "
                "com barra de progresso.", ""]
        if cold <= tol:
            out += [f"- **Índice em cache: suficiente.** 1ª abertura {_sec(cold)} (dentro da tolerância); as demais "
                    f"{_sec(r.get('abrir_cache_2', 0))}. Um modo \"abre pronto\" não é necessário nesta máquina."]
        elif cold <= tol * 3:
            out += [f"- **Índice em cache: aceitável, mas lento na 1ª vez** ({_sec(cold)}). Vale um modo opcional "
                    "\"abre pronto\" (entrada de cache dentro do pacote) para quem não quer esperar."]
        else:
            out += [f"- **Índice em cache: lento demais na 1ª vez** ({_sec(cold)}). Priorizar o modo \"abre pronto\" "
                    "(B2/B4) e, enquanto isso, recomendar salvar **com** tabelas de busca nesta máquina."]
        if "abrir_recria" in r:
            out.append(f"- Sem cache, abrir recria as tabelas em {_sec(r['abrir_recria'])} **a cada abertura** "
                       f"(com cache: {_sec(r.get('abrir_cache_2', 0))} depois da 1ª).")
    else:
        out += ["_(Sem medição do projeto real: rode com o caminho do projeto para a recomendação.)_"]
    out += ["", "### Suas respostas (preencha e envie este arquivo de volta)", "",
            "- [ ] Esperar a 1ª abertura com barra de progresso é aceitável? Quanto, no máximo? ______ min",
            "- [ ] Espaço de cache (em disco) é aceitável? Quanto, no máximo? ______ GB",
            "- [ ] Prefiro que o arquivo **abra pronto** (maior, sem espera) quando a máquina é lenta? sim / não / como opção",
            "- [ ] O tamanho do arquivo em disco importa mais do que o tempo de abrir? sim / não",
            "- Observações (travou? barra de progresso clara? mensagens de erro?): ",
            ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("projeto", nargs="?", help="projeto real (.ttwa/.ttwt) a medir numa cópia; sem ele só o sintético")
    ap.add_argument("--saida", help="relatório .md (padrão: relatorio_armazenamento_<máquina>_<data>.md)")
    ap.add_argument("--pasta", help="pasta de trabalho (padrão: temporária do sistema); apagada ao fim")
    ap.add_argument("--tokens", type=int, default=1_000_000, help="tamanho do projeto sintético (padrão 1 milhão)")
    ap.add_argument("--tolerancia-min", type=float, default=5, help="espera aceitável na 1ª abertura, em minutos (padrão 5)")
    ap.add_argument("--sem-sintetico", action="store_true")
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="ttw_bench_", dir=args.pasta))
    # o cache e os dados desta medição ficam na pasta de trabalho: nada toca o cache real do usuário
    os.environ["TTWTOOLS_CACHE_DIR"] = str(work / "cache")
    os.environ["TTWTOOLS_DATA_DIR"] = str(work / "data")
    os.environ["TMPDIR"] = str(work / "tmp")
    (work / "tmp").mkdir()
    tempfile.tempdir = str(work / "tmp")

    host = platform.node().split(".")[0] or "maquina"
    out = Path(args.saida or f"relatorio_armazenamento_{host}_{dt.date.today():%Y%m%d}.md").resolve()
    rep = Report(out)
    try:
        rep.env = machine_info()
        print(f"Relatório: {out}\nPasta de trabalho (apagada ao fim): {work}\n")
        rep.write()
        print("1. velocidade bruta")
        micro(rep)
        if not args.sem_sintetico:
            print("2. índice sintético")
            synthetic(rep, work, args.tokens)
        if args.projeto:
            print("3. projeto real")
            real_project(rep, work, Path(args.projeto).expanduser().resolve())
        rep.write(decision(rep, args.tolerancia_min))
        print(f"\nPronto. Relatório gravado em {out}")
        return 0
    except KeyboardInterrupt:
        rep.write("\n> **Interrompido pelo usuário:** o relatório tem só o que foi medido até aqui.")
        print("\nInterrompido; relatório parcial gravado.")
        return 130
    finally:
        shutil.rmtree(work, ignore_errors=True)
        print("Pasta de trabalho apagada.")


if __name__ == "__main__":
    sys.exit(main())
