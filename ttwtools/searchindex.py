"""searchindex.py — Índice de busca em cache, por grupo de camadas (passo B3 do plano de armazenamento).

Um arquivo salvo **sem tabelas de busca** guarda as camadas empacotadas (`layer_blobs`, formato
`layerfmt`). Em vez de recriar `tokens` e seus índices dentro do projeto a cada abertura (segundos a
minutos, e GBs numa cópia de trabalho), o índice é construído **uma vez** num banco SQLite da pasta de
cache (`storage.cache_entry`) e **anexado** (`ATTACH`, somente leitura) a cada abertura:

    projeto (pequeno)  ── layer_blobs ──►  build  ──►  cache/idx-<chave>/tokens.sqlite
         │                                                       ▲
         └── TEMP VIEW tokens = main.tokens ∪ idx1.tokens ∪ ...  ┘   (as consultas não mudam)

- **Chave = conteúdo.** Hash (SHA-256) do formato, dos ids (camada e documento) e dos blobs do grupo.
  Mesma chave ⇒ mesmos tokens. Os ids são **nativos do projeto** (medido: remapear ids na view impede o
  uso da chave primária e deixa o KWIC 1000× mais lento). Por isso o cache é compartilhado por quem
  descende do mesmo arquivo (cópias, "salvar como", `.ttwc` exportado), não por projetos sem relação.
- **Grupos** = camadas do mesmo corpus, ferramenta, versão, modelo e configuração. Se houver mais
  grupos que o limite de bancos anexados do SQLite, agrupa por ferramenta (entre corpora) e, em
  último caso, tudo num só.
- **Só leitura, atômico.** Constrói em `tokens.sqlite.part<pid>` e renomeia no fim; uma entrada sem
  `tokens.sqlite` não existe. O cache é descartável (LRU e limite em `storage`); perdido, reconstrói.
- **Etapas com progresso** (`progress(feitos, total, etapa)`): `idx_read` (camadas lidas), depois uma
  etapa por índice: `idx_words`, `idx_lemmas`, `idx_doc`, `idx_upos`, `idx_xpos`.

O formato de cada entrada (`entry.json` + `tokens.sqlite`) é autocontido: uma entrada pode, no futuro,
viajar dentro de um pacote ("abre pronto", para máquinas lentas) e ser copiada para o cache no lugar
de construída.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Callable, Optional

from . import layerfmt, storage

FORMAT = 1                      # mude ao alterar colunas ou o conjunto de índices
BYTES_PER_TOKEN = 120           # estimativa do tamanho da entrada (tabela + 5 índices)
_COLS = "layer_id, idx, doc_id, start_char, end_char, word, lemma, upos, xpos, feats, tags, extra"
_DDL = """CREATE TABLE tokens (
    layer_id INTEGER NOT NULL, idx INTEGER NOT NULL, doc_id INTEGER NOT NULL,
    start_char INTEGER, end_char INTEGER, word TEXT, lemma TEXT, upos TEXT, xpos TEXT,
    feats TEXT, tags TEXT, extra TEXT, PRIMARY KEY (layer_id, idx)) WITHOUT ROWID"""
_STAGE_OF = {"idx_tokens_lword": "idx_words", "idx_tokens_llemma": "idx_lemmas", "idx_tokens_doc": "idx_doc",
             "idx_tokens_upos": "idx_upos", "idx_tokens_xpos": "idx_xpos"}
STAGES = ("idx_read",) + tuple(_STAGE_OF.values())

Progress = Optional[Callable[[int, int, str], None]]
_memo: dict = {}                # (caminho, tamanho e data do banco e do WAL) -> entradas planejadas


def enabled() -> bool:
    """O cache de índice está ligado? Desliga com `TTWTOOLS_INDEX_CACHE=0` ou `index_cache: false` no
    settings.json (volta a recriar as tabelas de busca dentro do projeto, como antes)."""
    if os.environ.get("TTWTOOLS_INDEX_CACHE") == "0":
        return False
    from .corpus_catalog import settings
    return settings().get("index_cache", True) is not False


def _max_attached(con: sqlite3.Connection) -> int:
    try:
        return max(1, min(con.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED), 10))
    except AttributeError:                      # Python < 3.11
        return 8


def blob_layers(con: sqlite3.Connection) -> list[dict]:
    """Camadas que só existem empacotadas (têm blob e nenhuma linha em `main.tokens`)."""
    rows = con.execute(
        "SELECT l.id, l.doc_id, d.corpus_name, l.tool, l.tool_version, l.model, l.config_hash, l.n_tokens"
        " FROM layers l JOIN layer_blobs b ON b.layer_id = l.id JOIN documents d ON d.id = l.doc_id"
        " WHERE NOT EXISTS (SELECT 1 FROM main.tokens t WHERE t.layer_id = l.id) ORDER BY l.id").fetchall()
    return [{"id": r[0], "doc_id": r[1], "corpus": r[2], "tool": r[3], "version": r[4], "model": r[5],
             "config": r[6], "tokens": r[7]} for r in rows]


def plan_entries(layers: list[dict], max_entries: int) -> list[list[dict]]:
    """Agrupa as camadas em entradas de cache: por (corpus, ferramenta, versão, modelo, configuração);
    se passar do limite, por ferramenta (entre corpora); se ainda passar, tudo junto."""
    for keyf in (lambda l: (l["corpus"], l["tool"], l["version"], l["model"], l["config"]),
                 lambda l: (l["tool"], l["version"], l["model"], l["config"]),
                 lambda l: ()):
        groups: dict = {}
        for l in layers:
            groups.setdefault(keyf(l), []).append(l)
        if len(groups) <= max_entries:
            break
    return [groups[k] for k in sorted(groups, key=repr)]


def entry_key(con: sqlite3.Connection, group: list[dict]) -> str:
    """Chave de conteúdo do grupo (formato, ids e blobs)."""
    h = hashlib.sha256(f"tcidx{FORMAT}".encode())
    for l in group:
        blob = con.execute("SELECT data FROM layer_blobs WHERE layer_id = ?", (l["id"],)).fetchone()[0]
        h.update(f"{l['id']}:{l['doc_id']}:{l['tokens']}:{len(blob)}:".encode())
        h.update(hashlib.sha256(blob).digest())
    return h.hexdigest()[:24]


def _stamp(path: Path) -> tuple:
    out = [str(path)]
    for p in (path, Path(str(path) + "-wal")):
        try:
            st = p.stat()
            out += [st.st_size, st.st_mtime_ns]
        except OSError:
            out += [0, 0]
    return tuple(out)


def _entry_dir(key: str) -> Path:
    return storage.cache_dir() / f"idx-{key}"


def is_ready(key: str) -> bool:
    return (_entry_dir(key) / "tokens.sqlite").is_file()


def plan(project) -> list[dict]:
    """Entradas de cache que o projeto precisa: [{key, layers, tokens, ready, group}]. Calcula as chaves
    (lê os blobs: ~0,3 s por 100 MB) e lembra o resultado enquanto o arquivo não mudar."""
    con = project._con
    stamp = _stamp(project.path)
    if stamp not in _memo:
        groups = plan_entries(blob_layers(con), _max_attached(con))
        _memo.clear()                         # uma memória só: o projeto atual
        _memo[stamp] = [{"key": entry_key(con, g), "group": g} for g in groups]
    out = []
    for e in _memo[stamp]:
        g = e["group"]
        out.append({"key": e["key"], "layers": len(g), "tokens": sum(l["tokens"] for l in g),
                    "ready": is_ready(e["key"]), "group": g})
    return out


def status(project) -> dict:
    """Situação do índice do projeto (sem construir nada): entradas, prontas ou não, e os bytes."""
    entries = plan(project)
    for e in entries:
        e["bytes"] = storage.dir_size(_entry_dir(e["key"])) if e["ready"] else 0
        e.pop("group")
    return {"enabled": enabled(), "attached": list(getattr(project, "_idx_attached", [])), "entries": entries,
            "missing_tokens": sum(e["tokens"] for e in entries if not e["ready"])}


def build_entry(con: sqlite3.Connection, group: list[dict], key: str, progress: Progress = None,
                done_layers: int = 0, total_layers: int = 0, index_no: int = 1, n_entries: int = 1) -> None:
    """Constrói a entrada `key` a partir dos blobs do grupo. Atômico: só existe depois de pronta."""
    d = storage.cache_entry(f"idx-{key}")
    final = d / "tokens.sqlite"
    part = d / f"tokens.sqlite.part{os.getpid()}"
    part.unlink(missing_ok=True)
    total_layers = total_layers or len(group)
    db = sqlite3.connect(part)
    try:
        db.execute("PRAGMA journal_mode = OFF")
        db.execute("PRAGMA synchronous = OFF")
        db.execute(_DDL)
        for n, l in enumerate(group, 1):
            blob = con.execute("SELECT data FROM layer_blobs WHERE layer_id = ?", (l["id"],)).fetchone()[0]
            db.executemany(
                f"INSERT INTO tokens ({_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ((l["id"], i, l["doc_id"], *t) for i, t in enumerate(layerfmt.decode(blob))))
            if n % 20 == 0 or n == len(group):
                db.commit()
                if progress:
                    progress(done_layers + n, total_layers, "idx_read")
        from .project import _TOKEN_INDEXES
        for k, (name, sql) in enumerate(_TOKEN_INDEXES, 1):
            if progress:
                progress(k - 1 + (index_no - 1) * len(_TOKEN_INDEXES), len(_TOKEN_INDEXES) * n_entries,
                         _STAGE_OF.get(name, "idx_words"))
            db.execute(sql)
        db.commit()
        db.close()
        db = None
        (d / "entry.json").write_text(json.dumps({
            "format": FORMAT, "key": key, "layers": len(group), "tokens": sum(l["tokens"] for l in group),
            "layer_ids": [l["id"] for l in group], "created": time.time()}), encoding="utf-8")
        os.replace(part, final)
    finally:
        if db is not None:
            db.close()
        part.unlink(missing_ok=True)


def attach(project, keys: list[str]) -> list[str]:
    """Anexa as entradas (somente leitura) e cria a view temporária `tokens` = main ∪ entradas."""
    detach(project)
    con = project._con
    names = []
    for i, key in enumerate(keys, 1):
        uri = (_entry_dir(key) / "tokens.sqlite").resolve().as_uri() + "?mode=ro"
        con.execute("ATTACH DATABASE ? AS " + f"idx{i}", (uri,))
        names.append(f"idx{i}")
        storage.touch_cache(f"idx-{key}")
    if names:
        parts = ["SELECT " + _COLS + " FROM main.tokens"] + [f"SELECT {_COLS} FROM {n}.tokens" for n in names]
        con.execute("CREATE TEMP VIEW tokens AS " + " UNION ALL ".join(parts))
    project._idx_attached = names
    return names


def detach(project) -> None:
    """Desfaz `attach`: apaga a view e solta os bancos anexados."""
    con = project._con
    if con is None:
        return
    con.execute("DROP VIEW IF EXISTS temp.tokens")
    for n in getattr(project, "_idx_attached", []):
        try:
            con.execute(f"DETACH DATABASE {n}")
        except sqlite3.Error:
            pass
    project._idx_attached = []


def ensure(project, progress: Progress = None) -> list[str]:
    """Constrói as entradas que faltam (com progresso por etapa) e anexa todas. Devolve as chaves.
    Recusa antes de gravar (InsufficientDiskSpace) se a pasta de cache não comporta a construção."""
    entries = plan(project)
    missing = [e for e in entries if not e["ready"]]
    if missing:
        need = sum(e["tokens"] for e in missing) * BYTES_PER_TOKEN
        storage.ensure_free_space(storage.cache_dir(), storage.with_margin(need), "index")
        total_layers = sum(e["layers"] for e in missing)
        done = 0
        for n, e in enumerate(missing, 1):
            build_entry(project._con, e["group"], e["key"], progress, done, total_layers, n, len(missing))
            done += e["layers"]
        storage.enforce_cache_limit(keep=tuple(f"idx-{e['key']}" for e in entries))
    return attach(project, [e["key"] for e in entries])


def clear(project) -> int:
    """Apaga do cache as entradas deste projeto. Devolve os bytes liberados."""
    freed = 0
    detach(project)
    for e in plan(project):
        freed += storage.clear_cache(f"idx-{e['key']}")
    _memo.clear()
    return freed
