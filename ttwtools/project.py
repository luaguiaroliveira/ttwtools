"""
project.py — Persistência de projetos ttwtools em arquivos .ttwa (SQLite).

O formato .ttwa (TTW Archive) é um banco SQLite renomeado. Não executa nenhum
código Python ao ser aberto — é seguro contra payloads maliciosos em pickle/HDF5.

Schema de tabelas:
    project_meta   — chave/valor com metadados do projeto (JSON para valores complexos)
    corpus_files   — textos originais (.txt) de cada corpus (vazia no .ttwl)
    tagged_files   — saída etiquetada (JSONL; TSV nos projetos antigos), comprimida
    feature_tables — DataFrames de features (rawcount / norm1000) em JSON
    kfa_results    — DataFrames de resultados KFA entre pares de corpora
  v0.3 (novomodelo.md §9.3–9.4):
    documents      — um documento por (corpus, arquivo): hash do texto; no .ttwl, caminho relativo
    document_meta  — metadados de documento (chave/valor)
    layers         — uma camada por (documento, ferramenta, versão, modelo, config_hash)
    tokens         — tokens de cada camada, com índices em word/lemma/xpos (KWIC, frequência)
    analyses       — resultados de análises (tipo, parâmetros, camadas usadas, resultado)

Tipos de projeto: `.ttwa` (texto do corpus dentro do arquivo) e `.ttwl` (leve: só
o caminho relativo e o hash de cada texto; o corpus fica numa pasta ao lado).
"""

from __future__ import annotations

import io
import json
import lzma
import os
import sqlite3
import warnings
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from . import layers as _layers


# ---------------------------------------------------------------------------
# MIME type recomendado para registro no sistema operacional / servidor web
# ---------------------------------------------------------------------------
TTWA_MIME_TYPE = "application/x-ttwa+sqlite3"
TTWA_EXTENSION = ".ttwa"
TTWL_EXTENSION = ".ttwl"

# Tipo do projeto gravado em project_meta['project_kind']
PROJECT_KIND_TTWA = "ttwa"   # texto do corpus dentro do arquivo
PROJECT_KIND_TTWL = "ttwl"   # leve: texto numa pasta ao lado, conferido por hash

# Modos de arquivo .ttwa gravados em project_meta['project_mode']
TTWA_MODE_FULL    = "full"      # corpus original + tagged + análise
TTWA_MODE_COMPACT = "compact"   # apenas tagged + análise (sem textos originais)

# Versões de schema do arquivo .ttwa
# v0.1 — formato original: tagged_files.content é TEXT sem compressão
# v0.2 — tagged_files.content é BLOB zlib-comprimido; taggers spacy/stanza unificados
# v0.3 — tabelas documents, document_meta, layers, tokens, analyses; tipo .ttwl
SCHEMA_VERSION_LEGACY     = "0.1"
SCHEMA_VERSION_COMPRESSED = "0.2"
SCHEMA_VERSION_CURRENT    = "0.3"


def _schema_version_parts(value) -> tuple[int, ...]:
    """Normaliza versão de schema para comparação segura.

    Aceita str/float/int (ex.: "0.2", 0.2, 2) e retorna uma tupla comparável.
    """
    if value is None:
        value = SCHEMA_VERSION_LEGACY
    s = str(value).strip()
    # Mantém apenas dígitos e pontos para tolerar formatos inesperados.
    s = "".join(ch for ch in s if ch.isdigit() or ch == ".")
    if not s:
        s = SCHEMA_VERSION_LEGACY
    parts = []
    for p in s.split("."):
        parts.append(int(p) if p else 0)
    return tuple(parts)


def _schema_is_at_least(value, target: str) -> bool:
    return _schema_version_parts(value) >= _schema_version_parts(target)

# Mapeamento de unificação de taggers para v0.2 (Option A):
# spacy_upos e spacy_ptb são gerados numa mesma passagem e têm conteúdo equivalente;
# no formato 0.2, ambos são armazenados como uma única linha 'spacy' (idem para stanza).
_TAGGER_UNIFIED_MAP: dict[str, str] = {
    "spacy_upos":  "spacy",
    "spacy_ptb":   "spacy",
    "stanza_upos": "stanza",
    "stanza_xpos": "stanza",
}

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project_meta (
    key   TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corpus_files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    corpus_name  TEXT    NOT NULL,
    filename     TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    UNIQUE (corpus_name, filename)
);

CREATE TABLE IF NOT EXISTS tagged_files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    corpus_name  TEXT    NOT NULL,
    filename     TEXT    NOT NULL,
    tagger_type  TEXT    NOT NULL DEFAULT 'biberplus',
    content      TEXT    NOT NULL,
    UNIQUE (corpus_name, filename, tagger_type)
);

CREATE TABLE IF NOT EXISTS feature_tables (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    corpus_name   TEXT    NOT NULL,
    table_type    TEXT    NOT NULL CHECK(table_type IN ('rawcount', 'norm1000')),
    tagger_type   TEXT    NOT NULL DEFAULT 'biberplus',
    tagger_config TEXT    NOT NULL DEFAULT '{}',
    data          TEXT    NOT NULL,
    UNIQUE (corpus_name, table_type, tagger_type)
);

CREATE TABLE IF NOT EXISTS kfa_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    corpus1_name  TEXT    NOT NULL,
    corpus2_name  TEXT    NOT NULL,
    min_effect    REAL    NOT NULL DEFAULT 0.0,
    join_method   TEXT    NOT NULL DEFAULT 'union',
    tagger_type   TEXT    NOT NULL DEFAULT 'biberplus',
    analysis_name TEXT    NOT NULL DEFAULT 'default',
    metric        TEXT    NOT NULL DEFAULT 'kfa2',
    features_meta TEXT    NOT NULL DEFAULT '[]',
    data          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    UNIQUE (corpus1_name, corpus2_name, min_effect, join_method, tagger_type, analysis_name, metric)
);

-- v0.3 -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    corpus_name   TEXT    NOT NULL,
    filename      TEXT    NOT NULL,
    content_hash  TEXT,               -- SHA-256 do texto; NULL se o texto nunca foi visto
    n_chars       INTEGER,
    rel_path      TEXT,               -- .ttwl: caminho do texto relativo à pasta do projeto
    created_at    TEXT    NOT NULL,
    UNIQUE (corpus_name, filename)
);

CREATE TABLE IF NOT EXISTS document_meta (
    doc_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    key     TEXT    NOT NULL,
    value   TEXT    NOT NULL,
    PRIMARY KEY (doc_id, key)
);

CREATE TABLE IF NOT EXISTS layers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id        INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tool          TEXT    NOT NULL,
    tool_version  TEXT    NOT NULL DEFAULT '',
    model         TEXT    NOT NULL DEFAULT '',
    config        TEXT    NOT NULL DEFAULT '{}',   -- configuração efetiva completa (JSON)
    config_hash   TEXT    NOT NULL,                -- só opções que mudam o resultado
    text_hash     TEXT,                            -- hash do texto etiquetado
    n_tokens      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL,
    UNIQUE (doc_id, tool, tool_version, model, config_hash)
);
CREATE INDEX IF NOT EXISTS idx_layers_cache ON layers (text_hash, tool, tool_version, model, config_hash);

CREATE TABLE IF NOT EXISTS tokens (
    layer_id    INTEGER NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    doc_id      INTEGER NOT NULL,
    start_char  INTEGER,
    end_char    INTEGER,
    word        TEXT,
    lemma       TEXT,
    upos        TEXT,
    xpos        TEXT,
    feats       TEXT,
    tags        TEXT,     -- lista JSON de etiquetas do tagger
    extra       TEXT,     -- campos adicionais do JSONL (JSON), para não perder nada
    PRIMARY KEY (layer_id, idx)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_tokens_word  ON tokens (word);
CREATE INDEX IF NOT EXISTS idx_tokens_lemma ON tokens (lemma);
CREATE INDEX IF NOT EXISTS idx_tokens_xpos  ON tokens (xpos);
CREATE INDEX IF NOT EXISTS idx_tokens_doc   ON tokens (doc_id);

CREATE TABLE IF NOT EXISTS analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT    NOT NULL,              -- kfa, freq, collocates, kwic...
    name        TEXT    NOT NULL DEFAULT '',
    params      TEXT    NOT NULL DEFAULT '{}', -- JSON
    layer_refs  TEXT    NOT NULL DEFAULT '[]', -- JSON: ids de layers usadas
    result      TEXT,                          -- JSON
    created_at  TEXT    NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Helpers de compressão  (v0.2)
# ---------------------------------------------------------------------------

def _compress_content(text: str) -> bytes:
    """Comprime texto UTF-8 com zlib level 6."""
    return zlib.compress(text.encode("utf-8"), level=6)


def _decompress_content(data) -> str:
    """Descomprime BLOB zlib para str."""
    raw = bytes(data) if isinstance(data, memoryview) else data
    return zlib.decompress(raw).decode("utf-8")


def _decode_content(raw, encoding: str) -> str:
    """Decodifica conteúdo retornado pelo SQLite, respeitando o campo encoding."""
    if encoding == "zlib" or isinstance(raw, (bytes, memoryview)):
        return _decompress_content(raw)
    return raw


# ---------------------------------------------------------------------------
# Helpers de compressão  (.ttwt)
# ---------------------------------------------------------------------------

_TTWT_CHUNK = 65_536  # 64 KB por chunk para progresso granular


def compress_to_ttwt(
    source_ttwa: "str | Path",
    dest_ttwt: "str | Path",
    progress_cb: "Optional[Callable[[int, int], None]]" = None,
) -> None:
    """Comprime um arquivo .ttwa (SQLite) para o formato .ttwt (lzma preset máximo).

    progress_cb(done_bytes, total_bytes) é chamado a cada chunk lido da fonte.
    """
    source = Path(source_ttwa)
    total = source.stat().st_size
    done = 0
    with source.open("rb") as src, lzma.open(dest_ttwt, "wb", preset=9 | lzma.PRESET_EXTREME) as dst:
        while True:
            chunk = src.read(_TTWT_CHUNK)
            if not chunk:
                break
            dst.write(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)


def decompress_from_ttwt(
    source_ttwt: "str | Path",
    dest_ttwa: "str | Path",
    progress_cb: "Optional[Callable[[int, int], None]]" = None,
) -> None:
    """Descomprime um arquivo .ttwt para um arquivo .ttwa (SQLite).

    O progresso é calculado sobre o tamanho do arquivo comprimido (fonte).
    progress_cb(done_bytes, total_bytes) é chamado a cada chunk lido.
    """
    source = Path(source_ttwt)
    total = source.stat().st_size
    done = 0
    dec = lzma.LZMADecompressor()
    with source.open("rb") as src, open(dest_ttwa, "wb") as dst:
        while True:
            chunk = src.read(_TTWT_CHUNK)
            if not chunk:
                break
            dst.write(dec.decompress(chunk))
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)
    if not dec.eof:
        raise ValueError("Arquivo .ttwt truncado ou corrompido.")


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _connect(path: str | Path) -> sqlite3.Connection:
    """Abre (ou cria) o arquivo .ttwa e garante o schema."""
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA_SQL)
    _migrate_tagged_files(con)
    _migrate_tagged_encoding(con)
    _migrate_feature_tables(con)
    _migrate_kfa_results(con)
    con.commit()
    return con


def _migrate_tagged_files(con: sqlite3.Connection) -> None:
    """Migra tagged_files antigos: adiciona tagger_type e reconstrói UNIQUE."""
    cols = {row[1] for row in con.execute("PRAGMA table_info(tagged_files)")}
    if "tagger_type" in cols:
        return
    con.executescript("""
        CREATE TABLE tagged_files_v2 (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            corpus_name  TEXT    NOT NULL,
            filename     TEXT    NOT NULL,
            tagger_type  TEXT    NOT NULL DEFAULT 'biberplus',
            content      TEXT    NOT NULL,
            UNIQUE (corpus_name, filename, tagger_type)
        );
        INSERT INTO tagged_files_v2 (id, corpus_name, filename, tagger_type, content)
            SELECT id, corpus_name, filename, 'biberplus', content
            FROM tagged_files;
        DROP TABLE tagged_files;
        ALTER TABLE tagged_files_v2 RENAME TO tagged_files;
    """)
    con.commit()


def _migrate_tagged_encoding(con: sqlite3.Connection) -> None:
    """v0.2 migration: adiciona coluna 'encoding' a tagged_files (DEFAULT 'plain')."""
    cols = {row[1] for row in con.execute("PRAGMA table_info(tagged_files)")}
    if "encoding" in cols:
        return
    con.execute("ALTER TABLE tagged_files ADD COLUMN encoding TEXT NOT NULL DEFAULT 'plain'")
    con.commit()


def _migrate_kfa_results(con: sqlite3.Connection) -> None:
    """Migra kfa_results: adiciona tagger_type (v1) e analysis_name/features_meta (v2)."""
    cols = {row[1] for row in con.execute("PRAGMA table_info(kfa_results)")}

    if "tagger_type" not in cols:
        # v1 migration: add tagger_type
        con.executescript("""
            CREATE TABLE kfa_results_v2 (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                corpus1_name  TEXT    NOT NULL,
                corpus2_name  TEXT    NOT NULL,
                min_effect    REAL    NOT NULL DEFAULT 0.0,
                join_method   TEXT    NOT NULL DEFAULT 'union',
                tagger_type   TEXT    NOT NULL DEFAULT 'biberplus',
                data          TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                UNIQUE (corpus1_name, corpus2_name, min_effect, join_method, tagger_type)
            );
            INSERT INTO kfa_results_v2 (id, corpus1_name, corpus2_name, min_effect, join_method, tagger_type, data, created_at)
                SELECT id, corpus1_name, corpus2_name, min_effect, join_method, 'biberplus', data, created_at
                FROM kfa_results;
            DROP TABLE kfa_results;
            ALTER TABLE kfa_results_v2 RENAME TO kfa_results;
        """)
        con.commit()
        cols = {row[1] for row in con.execute("PRAGMA table_info(kfa_results)")}

    if "analysis_name" not in cols:
        # v2 migration: add analysis_name and features_meta, rebuild UNIQUE
        con.executescript("""
            CREATE TABLE kfa_results_v3 (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                corpus1_name  TEXT    NOT NULL,
                corpus2_name  TEXT    NOT NULL,
                min_effect    REAL    NOT NULL DEFAULT 0.0,
                join_method   TEXT    NOT NULL DEFAULT 'union',
                tagger_type   TEXT    NOT NULL DEFAULT 'biberplus',
                analysis_name TEXT    NOT NULL DEFAULT 'default',
                features_meta TEXT    NOT NULL DEFAULT '[]',
                data          TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                UNIQUE (corpus1_name, corpus2_name, min_effect, join_method, tagger_type, analysis_name)
            );
            INSERT INTO kfa_results_v3 (id, corpus1_name, corpus2_name, min_effect, join_method, tagger_type, analysis_name, features_meta, data, created_at)
                SELECT id, corpus1_name, corpus2_name, min_effect, join_method, tagger_type, 'default', '[]', data, created_at
                FROM kfa_results;
            DROP TABLE kfa_results;
            ALTER TABLE kfa_results_v3 RENAME TO kfa_results;
        """)
        con.commit()
        cols = {row[1] for row in con.execute("PRAGMA table_info(kfa_results)")}

    if "metric" not in cols:
        # v4 migration: add metric column (default 'kfa2' for backward compat), rebuild UNIQUE
        con.executescript("""
            CREATE TABLE kfa_results_v4 (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                corpus1_name  TEXT    NOT NULL,
                corpus2_name  TEXT    NOT NULL,
                min_effect    REAL    NOT NULL DEFAULT 0.0,
                join_method   TEXT    NOT NULL DEFAULT 'union',
                tagger_type   TEXT    NOT NULL DEFAULT 'biberplus',
                analysis_name TEXT    NOT NULL DEFAULT 'default',
                metric        TEXT    NOT NULL DEFAULT 'kfa2',
                features_meta TEXT    NOT NULL DEFAULT '[]',
                data          TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                UNIQUE (corpus1_name, corpus2_name, min_effect, join_method, tagger_type, analysis_name, metric)
            );
            INSERT INTO kfa_results_v4 (id, corpus1_name, corpus2_name, min_effect, join_method, tagger_type, analysis_name, metric, features_meta, data, created_at)
                SELECT id, corpus1_name, corpus2_name, min_effect, join_method, tagger_type, analysis_name, 'kfa2', features_meta, data, created_at
                FROM kfa_results;
            DROP TABLE kfa_results;
            ALTER TABLE kfa_results_v4 RENAME TO kfa_results;
        """)
        con.commit()


def _migrate_feature_tables(con: sqlite3.Connection) -> None:
    """Migra feature_tables de .ttwa antigos: adiciona colunas de tagger e
    reconstrói o índice UNIQUE para incluir tagger_type.
    No-op se a tabela já estiver na versão atual."""
    cols = {row[1] for row in con.execute("PRAGMA table_info(feature_tables)")}
    if "tagger_type" in cols:
        return
    # Rename+recreate pattern (SQLite não suporta ADD CONSTRAINT após criação)
    con.executescript("""
        ALTER TABLE feature_tables ADD COLUMN tagger_type  TEXT NOT NULL DEFAULT 'biberplus';
        ALTER TABLE feature_tables ADD COLUMN tagger_config TEXT NOT NULL DEFAULT '{}';
        CREATE TABLE feature_tables_v2 (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            corpus_name   TEXT    NOT NULL,
            table_type    TEXT    NOT NULL CHECK(table_type IN ('rawcount', 'norm1000')),
            tagger_type   TEXT    NOT NULL DEFAULT 'biberplus',
            tagger_config TEXT    NOT NULL DEFAULT '{}',
            data          TEXT    NOT NULL,
            UNIQUE (corpus_name, table_type, tagger_type)
        );
        INSERT INTO feature_tables_v2 (id, corpus_name, table_type, tagger_type, tagger_config, data)
            SELECT id, corpus_name, table_type, tagger_type, tagger_config, data
            FROM feature_tables;
        DROP TABLE feature_tables;
        ALTER TABLE feature_tables_v2 RENAME TO feature_tables;
    """)
    con.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

class TTWAProject:
    """
    Representa um projeto ttwtools persistido em um arquivo .ttwa.

    Uso básico::

        proj = TTWAProject.create("meu_projeto.ttwa", name="Tese 2026")
        proj.add_corpus_folder("corpus_A", "/caminho/para/corpus_A")
        proj.save_feature_table("corpus_A", df_raw, "rawcount")
        proj.save_feature_table("corpus_A", df_norm, "norm1000")
        proj.save_kfa_result("corpus_A", "corpus_B", df_kfa)
        proj.close()

        # Reabrir depois
        proj = TTWAProject.open("meu_projeto.ttwa")
        df = proj.load_feature_table("corpus_A", "norm1000")
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self._con: sqlite3.Connection | None = None
        self.migration_report: dict | None = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        path: str | Path,
        name: str = "",
        description: str = "",
        overwrite: bool = False,
        compress: bool = True,
    ) -> "TTWAProject":
        """Cria um novo projeto. A extensão define o tipo: `.ttwl` (leve, corpus
        numa pasta ao lado) ou qualquer outra, normalmente `.ttwa` (corpus dentro).

        compress=True (default) — formato atual (v0.3): tagged_files comprimidos e
                                    tabelas de documentos, camadas e tokens.
        compress=False          — formato v0.1 compatível com versões antigas.
        """
        p = Path(path).resolve()
        if p.exists() and not overwrite:
            raise FileExistsError(
                f"O arquivo '{p}' já existe. Use overwrite=True para substituir."
            )
        if p.exists():
            p.unlink()
        proj = cls(p)
        proj._con = _connect(p)
        proj._set_meta("project_name", name or p.stem)
        proj._set_meta("description", description)
        proj._set_meta("created_at", _now_iso())
        proj._set_meta("ttwtools_version", _get_ttwtools_version())
        proj._set_meta("schema_version", SCHEMA_VERSION_CURRENT if compress else SCHEMA_VERSION_LEGACY)
        proj._set_meta("project_kind", _kind_from_suffix(p))
        proj._con.commit()
        return proj

    @classmethod
    def open(cls, path: str | Path, migrate: bool = True) -> "TTWAProject":
        """Abre um projeto `.ttwa` ou `.ttwl` existente.

        Projetos de esquema anterior ao v0.3 são migrados ao abrir (migrate=True):
        a migração só acrescenta tabelas (nada é apagado) e emite um aviso; o
        relatório fica em `proj.migration_report`.
        """
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: '{p}'")
        proj = cls(p)
        proj._con = _connect(p)
        old = proj.get_meta("schema_version", SCHEMA_VERSION_LEGACY)
        if migrate and not _schema_is_at_least(old, SCHEMA_VERSION_CURRENT):
            proj.migration_report = proj.migrate_to_v3()
            r = proj.migration_report
            warnings.warn(
                f"Projeto '{p.name}' migrado do esquema {old} para {SCHEMA_VERSION_CURRENT}: "
                f"{r['documents']} documentos, {r['layers']} camadas, {r['tokens']} tokens"
                + (f"; {r['skipped_legacy']} arquivos no formato TSV antigo não indexados" if r["skipped_legacy"] else ""),
                stacklevel=2,
            )
        return proj

    @property
    def kind(self) -> str:
        """`ttwa` (texto dentro) ou `ttwl` (texto numa pasta ao lado)."""
        return self.get_meta("project_kind") or _kind_from_suffix(self.path)

    @property
    def is_light(self) -> bool:
        return self.kind == PROJECT_KIND_TTWL

    def close(self) -> None:
        """Fecha a conexão com o banco."""
        if self._con:
            self._con.close()
            self._con = None

    def __enter__(self) -> "TTWAProject":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Metadados
    # ------------------------------------------------------------------

    def _set_meta(self, key: str, value) -> None:
        v = json.dumps(value) if not isinstance(value, str) else value
        self._con.execute(
            "INSERT INTO project_meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, v),
        )

    def get_meta(self, key: str, default=None):
        """Retorna o valor de uma chave de metadados."""
        row = self._con.execute(
            "SELECT value FROM project_meta WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    def set_meta(self, key: str, value) -> None:
        """Define um metadado personalizado."""
        self._set_meta(key, value)
        self._con.commit()

    def all_meta(self) -> dict:
        """Retorna todos os metadados como dicionário."""
        rows = self._con.execute("SELECT key, value FROM project_meta").fetchall()
        result = {}
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                result[row["key"]] = row["value"]
        return result

    # ------------------------------------------------------------------
    # Corpus (arquivos .txt originais)
    # ------------------------------------------------------------------

    def add_corpus_folder(
        self,
        corpus_name: str,
        folder_path: str | Path,
        encoding: str = "utf-8",
        glob: str = "*.txt",
    ) -> int:
        """
        Importa todos os arquivos de texto de uma pasta para o projeto.

        Retorna o número de arquivos importados.
        """
        folder = Path(folder_path).resolve()
        if not folder.is_dir():
            raise NotADirectoryError(f"Pasta não encontrada: '{folder}'")

        files = list(folder.glob(glob))
        if not files:
            raise ValueError(f"Nenhum arquivo '{glob}' encontrado em '{folder}'.")

        imported = 0
        for txt_path in files:
            content = txt_path.read_text(encoding=encoding, errors="ignore")
            self._store_text(corpus_name, txt_path, content)
            imported += 1

        self._con.commit()
        print(f"  + {imported} arquivo(s) importados para o corpus '{corpus_name}'.")
        return imported

    def add_corpus_file(
        self,
        corpus_name: str,
        file_path: str | Path,
        encoding: str = "utf-8",
    ) -> None:
        """Importa um único arquivo de texto para o corpus."""
        p = Path(file_path).resolve()
        content = p.read_text(encoding=encoding, errors="ignore")
        self._store_text(corpus_name, p, content)
        self._con.commit()

    def add_corpus_text(self, corpus_name: str, filename: str, content: str) -> None:
        """Guarda um texto já lido (ex.: enviado pela interface) no corpus de um `.ttwa`."""
        if self.is_light:
            raise ValueError("Projetos .ttwl não guardam texto; use add_corpus_file com o arquivo no disco")
        self._store_text(corpus_name, Path(filename), content)
        self._con.commit()

    def _store_text(self, corpus_name: str, file_path: Path, content: str) -> None:
        """Guarda o texto (`.ttwa`) ou só o caminho relativo (`.ttwl`), e o hash."""
        rel_path = None
        if self.is_light:
            rel_path = _relative_to_project(self.path, file_path)
        else:
            self._con.execute(
                "INSERT INTO corpus_files (corpus_name, filename, content) VALUES (?, ?, ?)"
                " ON CONFLICT(corpus_name, filename) DO UPDATE SET content=excluded.content",
                (corpus_name, file_path.name, content),
            )
        self._upsert_document(corpus_name, file_path.name, content, rel_path=rel_path)

    def list_corpus_names(self) -> list[str]:
        """
        Lista todos os nomes de corpora conhecidos pelo projeto.
        Inclui nomes presentes em corpus_files, tagged_files ou feature_tables,
        garantindo que o modo 'compact' (sem originais) também liste os corpora.
        """
        rows = self._con.execute(
            """
            SELECT corpus_name FROM corpus_files
            UNION
            SELECT corpus_name FROM documents
            UNION
            SELECT corpus_name FROM tagged_files
            UNION
            SELECT corpus_name FROM feature_tables
            ORDER BY corpus_name
            """
        ).fetchall()
        return [r["corpus_name"] for r in rows]

    def list_corpus_files(self, corpus_name: str) -> list[str]:
        """Lista os nomes dos arquivos (com texto) de um corpus."""
        if self.is_light:
            sql = "SELECT filename FROM documents WHERE corpus_name = ? AND rel_path IS NOT NULL ORDER BY filename"
        else:
            sql = "SELECT filename FROM corpus_files WHERE corpus_name = ? ORDER BY filename"
        return [r["filename"] for r in self._con.execute(sql, (corpus_name,)).fetchall()]

    def get_corpus_file(self, corpus_name: str, filename: str) -> Optional[str]:
        """Retorna o conteúdo de um arquivo do corpus, ou None se não existir.

        No `.ttwl` lê da pasta do corpus (None se o arquivo não estiver lá)."""
        if self.is_light:
            path = self._document_path(corpus_name, filename)
            return _read_text(path) if path and path.is_file() else None
        row = self._con.execute(
            "SELECT content FROM corpus_files WHERE corpus_name = ? AND filename = ?",
            (corpus_name, filename),
        ).fetchone()
        return row["content"] if row else None

    def export_corpus_to_folder(
        self,
        corpus_name: str,
        dest_folder: str | Path,
        encoding: str = "utf-8",
    ) -> int:
        """Exporta todos os arquivos de um corpus para uma pasta no disco."""
        dest = Path(dest_folder).resolve()
        dest.mkdir(parents=True, exist_ok=True)
        n = 0
        for filename in self.list_corpus_files(corpus_name):
            content = self.get_corpus_file(corpus_name, filename)
            if content is None:
                continue
            (dest / filename).write_text(content, encoding=encoding, newline="")
            n += 1
        print(f"  + {n} arquivo(s) exportados para '{dest}'.")
        return n

    # ------------------------------------------------------------------
    # Arquivos tagueados (.tsv)
    # ------------------------------------------------------------------

    def save_tagged_file(
        self,
        corpus_name: str,
        filename: str,
        content: str,
        tagger_type: str = "biberplus",
    ) -> None:
        """Armazena o conteúdo de um arquivo tagueado.

        Em projetos v0.2:
          - O conteúdo é comprimido com zlib e salvo como BLOB.
          - Taggers spacy_upos/spacy_ptb são unificados como 'spacy';
            stanza_upos/stanza_xpos são unificados como 'stanza'.
            Ao salvar o segundo tagger da dupla, o conteudo ja existente é mantido
            (ON CONFLICT DO NOTHING) para evitar sobrescrever dados equivalentes.
        """
        schema_v = self.get_meta("schema_version", SCHEMA_VERSION_LEGACY)
        is_v2 = _schema_is_at_least(schema_v, SCHEMA_VERSION_COMPRESSED)
        index_now = _schema_is_at_least(schema_v, SCHEMA_VERSION_CURRENT)

        # Option A: unify tagger name in v0.2
        stored_tagger = _TAGGER_UNIFIED_MAP.get(tagger_type, tagger_type) if is_v2 else tagger_type
        is_alias = is_v2 and tagger_type != stored_tagger

        if is_v2:
            blob = _compress_content(content)
            if is_alias:
                # Second tagger of a unified pair: keep existing row if present
                cur = self._con.execute(
                    "INSERT INTO tagged_files (corpus_name, filename, tagger_type, encoding, content) VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(corpus_name, filename, tagger_type) DO NOTHING",
                    (corpus_name, filename, stored_tagger, "zlib", blob),
                )
                index_now = index_now and cur.rowcount == 1
            else:
                self._con.execute(
                    "INSERT INTO tagged_files (corpus_name, filename, tagger_type, encoding, content) VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(corpus_name, filename, tagger_type) DO UPDATE SET content=excluded.content, encoding=excluded.encoding",
                    (corpus_name, filename, stored_tagger, "zlib", blob),
                )
        else:
            self._con.execute(
                "INSERT INTO tagged_files (corpus_name, filename, tagger_type, encoding, content) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(corpus_name, filename, tagger_type) DO UPDATE SET content=excluded.content",
                (corpus_name, filename, stored_tagger, "plain", content),
            )
        if index_now:
            self._index_tagged(corpus_name, filename, stored_tagger, content)
        self._con.commit()

    def save_tagged_folder(
        self,
        corpus_name: str,
        tagged_folder: str | Path,
        glob: str = "*.tsv",
        encoding: str = "utf-8",
        tagger_type: str = "biberplus",
    ) -> int:
        """Importa todos os .tsv/.jsonl de uma pasta tagueada para o projeto."""
        folder = Path(tagged_folder).resolve()
        files = list(folder.glob(glob))
        imported = 0
        for tsv_path in files:
            content = tsv_path.read_text(encoding=encoding, errors="ignore")
            self.save_tagged_file(corpus_name, tsv_path.name, content, tagger_type=tagger_type)
            imported += 1
        print(f"  + {imported} arquivo(s) tagueados importados para '{corpus_name}'.")
        return imported

    def list_tagged_files(self, corpus_name: str, tagger_type: str | None = None) -> list[str]:
        if tagger_type is None:
            rows = self._con.execute(
                "SELECT filename FROM tagged_files WHERE corpus_name = ? ORDER BY filename",
                (corpus_name,),
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT filename FROM tagged_files WHERE corpus_name = ? AND tagger_type = ? ORDER BY filename",
                (corpus_name, tagger_type),
            ).fetchall()
        return [r["filename"] for r in rows]

    def list_tagged_entries(self, corpus_name: str) -> list[dict]:
        rows = self._con.execute(
            "SELECT filename, tagger_type FROM tagged_files WHERE corpus_name = ? ORDER BY tagger_type, filename",
            (corpus_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_tagged_file(
        self,
        corpus_name: str,
        filename: str,
        tagger_type: str | None = None,
    ) -> Optional[str]:
        """Retorna o conteúdo de um arquivo tagueado, ou None se não existir.

        Para projetos v0.2, descomprime automaticamente.
        Retrocompat: se tagger_type é um alias (ex: 'spacy_upos'), tenta primeiro
        o nome original e depois o nome unificado ('spacy').
        """
        def _fetch(ttype):
            if ttype is None:
                return self._con.execute(
                    "SELECT content, encoding FROM tagged_files"
                    " WHERE corpus_name = ? AND filename = ? ORDER BY id DESC LIMIT 1",
                    (corpus_name, filename),
                ).fetchone()
            return self._con.execute(
                "SELECT content, encoding FROM tagged_files"
                " WHERE corpus_name = ? AND filename = ? AND tagger_type = ?",
                (corpus_name, filename, ttype),
            ).fetchone()

        row = _fetch(tagger_type)
        # Fallback to unified tagger name (v0.2)
        if row is None and tagger_type in _TAGGER_UNIFIED_MAP:
            row = _fetch(_TAGGER_UNIFIED_MAP[tagger_type])
        if row is None:
            return None
        return _decode_content(row["content"], row["encoding"] if "encoding" in row.keys() else "plain")

    # ------------------------------------------------------------------
    # Feature tables (DataFrames raw / norm1000)
    # ------------------------------------------------------------------

    def save_feature_table(
        self,
        corpus_name: str,
        df: pd.DataFrame,
        table_type: str = "rawcount",
        tagger_type: str = "biberplus",
        tagger_config: dict | None = None,
    ) -> None:
        """
        Persiste um DataFrame de features no projeto.

        Args:
            corpus_name: Nome do corpus.
            df: DataFrame com colunas de features.
            table_type: 'rawcount' ou 'norm1000'.
            tagger_type: Identificador do tagger usado (ex: 'biberplus', 'mfte').
            tagger_config: Configuração do tagger em dicionário (serializado como JSON).
        """
        if table_type not in ("rawcount", "norm1000"):
            raise ValueError("table_type deve ser 'rawcount' ou 'norm1000'.")
        data_json = df.to_json(orient="records", force_ascii=False)
        cfg_json = json.dumps(tagger_config or {})
        self._con.execute(
            "INSERT INTO feature_tables"
            " (corpus_name, table_type, tagger_type, tagger_config, data)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(corpus_name, table_type, tagger_type)"
            " DO UPDATE SET data=excluded.data, tagger_config=excluded.tagger_config",
            (corpus_name, table_type, tagger_type, cfg_json, data_json),
        )
        self._con.commit()
        print(
            f"  + Feature table '{table_type}' [{tagger_type}] salva para"
            f" corpus '{corpus_name}' ({len(df)} docs)."
        )

    def save_feature_table_from_csv(
        self,
        corpus_name: str,
        csv_path: str | Path,
        table_type: str = "rawcount",
        tagger_type: str = "biberplus",
        tagger_config: dict | None = None,
    ) -> pd.DataFrame:
        """
        Lê um CSV de features e o persiste no projeto.
        Retorna o DataFrame carregado.
        """
        df = pd.read_csv(csv_path)
        self.save_feature_table(corpus_name, df, table_type,
                                tagger_type=tagger_type, tagger_config=tagger_config)
        return df

    def load_feature_table(
        self,
        corpus_name: str,
        table_type: str = "norm1000",
        tagger_type: str = "biberplus",
    ) -> Optional[pd.DataFrame]:
        """
        Retorna o DataFrame de features de um corpus/tagger, ou None se não existir.
        """
        row = self._con.execute(
            "SELECT data FROM feature_tables"
            " WHERE corpus_name = ? AND table_type = ? AND tagger_type = ?",
            (corpus_name, table_type, tagger_type),
        ).fetchone()
        if row is None:
            return None
        return pd.read_json(io.StringIO(row["data"]), orient="records")

    def list_feature_tables(self) -> list[dict]:
        """Lista todas as feature tables disponíveis com tagger info."""
        rows = self._con.execute(
            "SELECT corpus_name, table_type, tagger_type, tagger_config"
            " FROM feature_tables ORDER BY corpus_name, table_type, tagger_type"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["tagger_config"] = json.loads(d["tagger_config"])
            except (json.JSONDecodeError, TypeError):
                pass
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # KFA results
    # ------------------------------------------------------------------

    def save_kfa_result(
        self,
        corpus1_name: str,
        corpus2_name: str,
        df: pd.DataFrame,
        min_effect: float = 0.0,
        join_method: str = "union",
        tagger_type: str = "biberplus",
        analysis_name: str = "default",
        metric: str = "kfa",
        features_meta: list | None = None,
    ) -> None:
        """Persiste o DataFrame de resultados de uma KFA entre dois corpora."""
        import json as _json
        data_json = df.to_json(orient="records", force_ascii=False)
        features_json = _json.dumps(features_meta or [])
        self._con.execute(
            """INSERT INTO kfa_results
               (corpus1_name, corpus2_name, min_effect, join_method, tagger_type, analysis_name, metric, features_meta, data, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(corpus1_name, corpus2_name, min_effect, join_method, tagger_type, analysis_name, metric)
               DO UPDATE SET data=excluded.data, features_meta=excluded.features_meta, created_at=excluded.created_at""",
            (corpus1_name, corpus2_name, min_effect, join_method, tagger_type, analysis_name, metric, features_json, data_json, _now_iso()),
        )
        self._con.commit()
        print(
            f"  + KFA salva: '{corpus1_name}' vs '{corpus2_name}'"
            f" | tagger={tagger_type} | analysis={analysis_name} | metric={metric} | d>={min_effect} | {join_method} | {len(df)} features."
        )

    def load_kfa_result(
        self,
        corpus1_name: str,
        corpus2_name: str,
        min_effect: float = 0.0,
        join_method: str = "union",
        tagger_type: str | None = None,
        analysis_name: str | None = None,
        metric: str | None = None,
    ) -> Optional[pd.DataFrame]:
        """Retorna o DataFrame de resultados de uma KFA, ou None se não existir.
        Se tagger_type=None, retorna a KFA mais recente para o par (qualquer tagger)."""
        params: list = [corpus1_name, corpus2_name, min_effect, join_method]
        where = "corpus1_name = ? AND corpus2_name = ? AND min_effect = ? AND join_method = ?"
        if tagger_type is not None:
            where += " AND tagger_type = ?"
            params.append(tagger_type)
        if analysis_name is not None:
            where += " AND analysis_name = ?"
            params.append(analysis_name)
        if metric is not None:
            where += " AND metric = ?"
            params.append(metric)
        row = self._con.execute(
            f"SELECT data FROM kfa_results WHERE {where} ORDER BY created_at DESC LIMIT 1",
            params,
        ).fetchone()
        if row is None:
            return None
        return pd.read_json(io.StringIO(row["data"]), orient="records")

    def list_kfa_results(self) -> list[dict]:
        """Lista todas as KFAs armazenadas."""
        rows = self._con.execute(
            "SELECT corpus1_name, corpus2_name, min_effect, join_method, tagger_type,"
            " analysis_name, metric, features_meta, created_at"
            " FROM kfa_results ORDER BY created_at DESC"
        ).fetchall()
        import json as _json
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["features_meta"] = _json.loads(d.get("features_meta") or "[]")
            except Exception:
                d["features_meta"] = []
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Documentos, camadas e tokens (v0.3)
    # ------------------------------------------------------------------

    def _upsert_document(self, corpus_name: str, filename: str, content: str | None,
                         rel_path: str | None = None) -> int:
        """Cria ou atualiza o documento, com hash e tamanho do texto."""
        h = _layers.text_hash(content) if content is not None else None
        n = len(content) if content is not None else None
        self._con.execute(
            "INSERT INTO documents (corpus_name, filename, content_hash, n_chars, rel_path, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(corpus_name, filename) DO UPDATE SET"
            "   content_hash = COALESCE(excluded.content_hash, documents.content_hash),"
            "   n_chars      = COALESCE(excluded.n_chars, documents.n_chars),"
            "   rel_path     = COALESCE(excluded.rel_path, documents.rel_path)",
            (corpus_name, filename, h, n, rel_path, _now_iso()),
        )
        return self._con.execute(
            "SELECT id FROM documents WHERE corpus_name = ? AND filename = ?", (corpus_name, filename)
        ).fetchone()["id"]

    def _document_path(self, corpus_name: str, filename: str) -> Path | None:
        row = self._con.execute(
            "SELECT rel_path FROM documents WHERE corpus_name = ? AND filename = ?", (corpus_name, filename)
        ).fetchone()
        if row is None or not row["rel_path"]:
            return None
        return (self.path.parent / row["rel_path"]).resolve()

    def list_documents(self, corpus_name: str | None = None) -> list[dict]:
        """Documentos do projeto (id, corpus, arquivo, hash, tamanho, caminho relativo)."""
        sql = "SELECT id, corpus_name, filename, content_hash, n_chars, rel_path FROM documents"
        args: tuple = ()
        if corpus_name is not None:
            sql += " WHERE corpus_name = ?"
            args = (corpus_name,)
        return [dict(r) for r in self._con.execute(sql + " ORDER BY corpus_name, filename", args)]

    def _index_tagged(self, corpus_name: str, tagged_filename: str, tool: str, content: str) -> int | None:
        """Cria (ou refaz) a camada e os tokens de um arquivo etiquetado JSONL.

        Devolve o id da camada, ou None se o conteúdo não for JSONL (TSV antigo)."""
        parsed = _layers.parse_tagged_jsonl(content)
        if parsed is None:
            return None
        meta, tokens = parsed
        info = _layers.layer_info(meta)
        doc_name = meta.get("filename") or tagged_filename
        doc_id = self._con.execute(
            "SELECT id FROM documents WHERE corpus_name = ? AND filename = ?", (corpus_name, doc_name)
        ).fetchone()
        doc_id = doc_id["id"] if doc_id else self._upsert_document(corpus_name, doc_name, None)
        text_h = self._con.execute("SELECT content_hash FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
        key = (doc_id, tool, info["tool_version"], info["model"], info["config_hash"])
        self._con.execute(
            "DELETE FROM layers WHERE doc_id = ? AND tool = ? AND tool_version = ? AND model = ? AND config_hash = ?",
            key,
        )
        cur = self._con.execute(
            "INSERT INTO layers (doc_id, tool, tool_version, model, config, config_hash, text_hash, n_tokens, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*key[:4], json.dumps(info["config"], ensure_ascii=False, sort_keys=True), info["config_hash"],
             text_h, len(tokens), _now_iso()),
        )
        layer_id = cur.lastrowid
        self._con.executemany(
            "INSERT INTO tokens (layer_id, idx, doc_id, start_char, end_char, word, lemma, upos, xpos, feats, tags, extra)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ((layer_id, i, doc_id, *_layers.token_row(t)) for i, t in enumerate(tokens)),
        )
        return layer_id

    def list_layers(self, corpus_name: str | None = None, tool: str | None = None) -> list[dict]:
        """Camadas do projeto, com corpus e arquivo do documento."""
        sql = ("SELECT l.id, d.corpus_name, d.filename, l.doc_id, l.tool, l.tool_version, l.model,"
               " l.config, l.config_hash, l.text_hash, l.n_tokens, l.created_at"
               " FROM layers l JOIN documents d ON d.id = l.doc_id WHERE 1=1")
        args: list = []
        if corpus_name is not None:
            sql += " AND d.corpus_name = ?"
            args.append(corpus_name)
        if tool is not None:
            sql += " AND l.tool = ?"
            args.append(tool)
        rows = [dict(r) for r in self._con.execute(sql + " ORDER BY d.corpus_name, d.filename, l.tool", args)]
        for r in rows:
            r["config"] = json.loads(r["config"])
        return rows

    def find_layer(self, text_hash: str, tool: str, tool_version: str, model: str, config_hash: str) -> dict | None:
        """Camada já existente para o mesmo texto e a mesma configuração (evita reprocessar)."""
        row = self._con.execute(
            "SELECT id, doc_id, n_tokens, created_at FROM layers WHERE text_hash = ? AND tool = ?"
            " AND tool_version = ? AND model = ? AND config_hash = ? LIMIT 1",
            (text_hash, tool, tool_version, model, config_hash),
        ).fetchone()
        return dict(row) if row else None

    def get_tokens(self, layer_id: int) -> list[dict]:
        """Tokens de uma camada, em ordem, com `tags`/`extra` decodificados."""
        rows = self._con.execute(
            "SELECT idx, start_char, end_char, word, lemma, upos, xpos, feats, tags, extra"
            " FROM tokens WHERE layer_id = ? ORDER BY idx", (layer_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []
            d["extra"] = json.loads(d["extra"]) if d["extra"] else {}
            out.append(d)
        return out

    def migrate_to_v3(self) -> dict:
        """Migra o projeto para o esquema v0.3 sem apagar nada.

        Cria `documents` a partir de `corpus_files` (com hash) e `layers`/`tokens` a
        partir dos blocos JSONL de `tagged_files`. Projetos v0.1 passam antes pela
        compressão de `upgrade_to_v2`. Arquivos no formato TSV antigo são contados
        em `skipped_legacy` e continuam em `tagged_files`.
        """
        old = self.get_meta("schema_version", SCHEMA_VERSION_LEGACY)
        if _schema_is_at_least(old, SCHEMA_VERSION_CURRENT):
            return {"from": old, "documents": 0, "layers": 0, "tokens": 0, "skipped_legacy": 0, "already_v3": True}
        if not _schema_is_at_least(old, SCHEMA_VERSION_COMPRESSED):
            self.upgrade_to_v2()

        for row in self._con.execute("SELECT corpus_name, filename, content FROM corpus_files").fetchall():
            self._upsert_document(row["corpus_name"], row["filename"], row["content"])

        n_layers = n_skipped = 0
        ids = [r["id"] for r in self._con.execute("SELECT id FROM tagged_files ORDER BY id")]
        for tid in ids:
            row = self._con.execute(
                "SELECT corpus_name, filename, tagger_type, content, encoding FROM tagged_files WHERE id = ?", (tid,)
            ).fetchone()
            content = _decode_content(row["content"], row["encoding"])
            if self._index_tagged(row["corpus_name"], row["filename"], row["tagger_type"], content) is None:
                n_skipped += 1
            else:
                n_layers += 1

        if not self.get_meta("project_kind"):
            self._set_meta("project_kind", PROJECT_KIND_TTWA)
        self._set_meta("schema_version", SCHEMA_VERSION_CURRENT)
        self._set_meta("migrated_from_schema", str(old))
        self._con.commit()
        n_docs = self._con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        n_tokens = self._con.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
        return {"from": str(old), "documents": n_docs, "layers": n_layers, "tokens": n_tokens,
                "skipped_legacy": n_skipped, "already_v3": False}

    # ------------------------------------------------------------------
    # Análises genéricas (v0.3)
    # ------------------------------------------------------------------

    def save_analysis(self, type: str, result, params: dict | None = None,
                      layer_refs: list[int] | None = None, name: str = "") -> int:
        """Guarda o resultado de uma análise (JSON) com parâmetros e camadas usadas."""
        cur = self._con.execute(
            "INSERT INTO analyses (type, name, params, layer_refs, result, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (type, name, json.dumps(params or {}, ensure_ascii=False, sort_keys=True),
             json.dumps(layer_refs or []), json.dumps(result, ensure_ascii=False, default=str), _now_iso()),
        )
        self._con.commit()
        return cur.lastrowid

    def list_analyses(self, type: str | None = None) -> list[dict]:
        sql = "SELECT id, type, name, params, layer_refs, created_at FROM analyses"
        rows = self._con.execute(sql + (" WHERE type = ?" if type else "") + " ORDER BY id",
                                 (type,) if type else ()).fetchall()
        return [{**dict(r), "params": json.loads(r["params"]), "layer_refs": json.loads(r["layer_refs"])} for r in rows]

    def load_analysis(self, analysis_id: int) -> dict | None:
        row = self._con.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        for k in ("params", "layer_refs", "result"):
            d[k] = json.loads(d[k]) if d[k] is not None else None
        return d

    # ------------------------------------------------------------------
    # Corpus fora do arquivo: .ttwl (v0.3)
    # ------------------------------------------------------------------

    def check_corpus(self) -> dict:
        """Confere, no `.ttwl`, se cada texto está no lugar e bate com o hash.

        Devolve {"ok": [...], "missing": [...], "changed": [...]} com
        `(corpus, arquivo)` de cada documento com caminho. No `.ttwa` tudo é "ok".
        """
        report: dict[str, list] = {"ok": [], "missing": [], "changed": []}
        for doc in self.list_documents():
            if not self.is_light:
                if doc["content_hash"]:
                    report["ok"].append((doc["corpus_name"], doc["filename"]))
                continue
            if not doc["rel_path"]:
                continue
            path = self.path.parent / doc["rel_path"]
            key = (doc["corpus_name"], doc["filename"])
            if not path.is_file():
                report["missing"].append(key)
            elif _layers.text_hash(_read_text(path)) != doc["content_hash"]:
                report["changed"].append(key)
            else:
                report["ok"].append(key)
        return report

    def relink_corpus(self, folder: str | Path, accept_changed: bool = False) -> dict:
        """Aponta o `.ttwl` para outra pasta de corpus, conferindo os hashes.

        Procura cada texto em `<pasta>/<corpus>/<arquivo>` e em `<pasta>/<arquivo>`.
        Textos alterados só são religados com accept_changed=True (as camadas
        daquele documento podem ficar desalinhadas). Devolve o relatório
        {"relinked", "changed", "missing"}.
        """
        if not self.is_light:
            raise ValueError("relink_corpus só se aplica a projetos .ttwl")
        folder = Path(folder).resolve()
        report: dict[str, list] = {"relinked": [], "changed": [], "missing": []}
        for doc in self.list_documents():
            key = (doc["corpus_name"], doc["filename"])
            path = next((c for c in (folder / doc["corpus_name"] / doc["filename"], folder / doc["filename"])
                         if c.is_file()), None)
            if path is None:
                report["missing"].append(key)
                continue
            changed = _layers.text_hash(_read_text(path)) != doc["content_hash"]
            if changed:
                report["changed"].append(key)
                if not accept_changed:
                    continue
            self._con.execute("UPDATE documents SET rel_path = ? WHERE id = ?",
                              (_relative_to_project(self.path, path), doc["id"]))
            if not changed:
                report["relinked"].append(key)
        self._con.commit()
        return report

    def export_corpus_next_to(self, folder: str | Path | None = None) -> Path:
        """Exporta os textos para `<pasta do projeto>/<nome>_corpus/<corpus>/<arquivo>`.

        No `.ttwl`, passa a apontar para a cópia exportada. Devolve a pasta."""
        dest = Path(folder).resolve() if folder else self.path.parent / f"{self.path.stem}_corpus"
        for corpus in self.list_corpus_names():
            for filename in self.list_corpus_files(corpus):
                content = self.get_corpus_file(corpus, filename)
                if content is None:
                    continue
                out = dest / corpus / filename
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(content, encoding="utf-8", newline="")
                if self.is_light:
                    self._con.execute("UPDATE documents SET rel_path = ? WHERE corpus_name = ? AND filename = ?",
                                      (_relative_to_project(self.path, out), corpus, filename))
        self._con.commit()
        return dest

    def _copy_to(self, dest: Path) -> "TTWAProject":
        if dest.exists():
            raise FileExistsError(f"O arquivo '{dest}' já existe.")
        self._con.commit()
        target = sqlite3.connect(str(dest))
        with target:
            self._con.backup(target)
        target.close()
        return TTWAProject.open(dest, migrate=False)

    def detach_corpus(self, dest: str | Path | None = None, corpus_folder: str | Path | None = None) -> "TTWAProject":
        """`.ttwa` → `.ttwl` + pasta de textos. O `.ttwa` original não muda.

        dest padrão: mesmo nome com `.ttwl`; pasta padrão: `<dest>_corpus` ao lado."""
        if self.is_light:
            raise ValueError("O projeto já é .ttwl")
        dest = Path(dest).resolve() if dest else self.path.with_suffix(TTWL_EXTENSION)
        folder = Path(corpus_folder).resolve() if corpus_folder else dest.parent / f"{dest.stem}_corpus"
        light = self._copy_to(dest)
        for corpus in light.list_corpus_names():
            for filename in light.list_corpus_files(corpus):
                content = light.get_corpus_file(corpus, filename)
                out = folder / corpus / filename
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(content, encoding="utf-8", newline="")
                light._upsert_document(corpus, filename, content, rel_path=_relative_to_project(dest, out))
        light._con.execute("DELETE FROM corpus_files")
        light._set_meta("project_kind", PROJECT_KIND_TTWL)
        light._con.commit()
        light._con.execute("VACUUM")
        return light

    def embed_corpus(self, dest: str | Path | None = None, allow_changed: bool = False) -> "TTWAProject":
        """`.ttwl` → `.ttwa`, trazendo os textos para dentro. O `.ttwl` original não muda.

        Falha se faltar algum texto, ou se algum mudou (salvo allow_changed=True)."""
        if not self.is_light:
            raise ValueError("O projeto já é .ttwa")
        status = self.check_corpus()
        if status["missing"] or (status["changed"] and not allow_changed):
            raise FileNotFoundError(
                f"Corpus incompleto ou alterado: {len(status['missing'])} ausente(s), "
                f"{len(status['changed'])} alterado(s). Use relink_corpus() antes."
            )
        dest = Path(dest).resolve() if dest else self.path.with_suffix(TTWA_EXTENSION)
        full = self._copy_to(dest)
        for doc in self.list_documents():
            if not doc["rel_path"]:
                continue
            content = _read_text(self.path.parent / doc["rel_path"])
            full._con.execute(
                "INSERT INTO corpus_files (corpus_name, filename, content) VALUES (?, ?, ?)"
                " ON CONFLICT(corpus_name, filename) DO UPDATE SET content=excluded.content",
                (doc["corpus_name"], doc["filename"], content),
            )
            full._con.execute("UPDATE documents SET rel_path = NULL, content_hash = ?, n_chars = ? WHERE id = ?",
                              (_layers.text_hash(content), len(content), doc["id"]))
        full._set_meta("project_kind", PROJECT_KIND_TTWA)
        full._con.commit()
        return full

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Retorna um resumo do conteúdo do projeto."""
        return {
            "path": str(self.path),
            "kind": self.kind,
            "meta": self.all_meta(),
            "schema_version": self.get_meta("schema_version", SCHEMA_VERSION_LEGACY),
            "corpora": {
                name: {
                    "files": len(self.list_corpus_files(name)),
                    "tagged": len(self.list_tagged_files(name)),
                    "feature_tables": [
                        f"{r['table_type']}[{r['tagger_type']}]"
                        for r in self.list_feature_tables()
                        if r["corpus_name"] == name
                    ],
                }
                for name in self.list_corpus_names()
            },
            "kfa_results": self.list_kfa_results(),
        }

    # ------------------------------------------------------------------
    # Migração / upgrade
    # ------------------------------------------------------------------

    def upgrade_to_v2(
        self,
        compress: bool = True,
        progress_cb: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """Atualiza o projeto para o formato v0.2 (compressão zlib + unificação de taggers).

        Args:
            compress: se True, comprime todo o conteúdo de tagged_files com zlib.
            progress_cb: callback(done, total, message) chamado durante a migração.

        Returns:
            dict com estatísticas: rows_converted, rows_deduped, size_before, size_after.
        """
        schema_v = self.get_meta("schema_version", SCHEMA_VERSION_LEGACY)
        if _schema_is_at_least(schema_v, SCHEMA_VERSION_COMPRESSED):
            return {"rows_converted": 0, "rows_deduped": 0, "already_v2": True}

        size_before = self.path.stat().st_size

        # ── Step 1: Option A — deduplicate unified taggers ───────────────────
        # Rename spacy_upos → spacy, delete spacy_ptb (keeping spacy row).
        # Same for stanza_upos/stanza_xpos → stanza.
        rows_deduped = 0
        for alias_a, alias_b, canonical in [
            ("spacy_upos",  "spacy_ptb",   "spacy"),
            ("stanza_upos", "stanza_xpos",  "stanza"),
        ]:
            if progress_cb:
                progress_cb(0, 1, f"Unificando taggers {alias_a}/{alias_b} → {canonical}…")
            # Rename first alias to canonical
            self._con.execute(
                "UPDATE tagged_files SET tagger_type=? WHERE tagger_type=?",
                (canonical, alias_a),
            )
            # Delete second alias where a canonical row now exists for same (corpus, file)
            cur = self._con.execute(
                """DELETE FROM tagged_files WHERE tagger_type=?
                   AND (corpus_name, filename) IN (
                       SELECT corpus_name, filename FROM tagged_files WHERE tagger_type=?
                   )""",
                (alias_b, canonical),
            )
            rows_deduped += cur.rowcount
            # Rename any remaining second-alias rows (files that had only that alias)
            self._con.execute(
                "UPDATE tagged_files SET tagger_type=? WHERE tagger_type=?",
                (canonical, alias_b),
            )
            self._con.commit()

        # ── Step 2: Option C — compress all plain-text rows ─────────────────
        rows_converted = 0
        if compress:
            total = self._con.execute(
                "SELECT COUNT(*) FROM tagged_files WHERE encoding='plain'"
            ).fetchone()[0]

            if progress_cb:
                progress_cb(0, total, f"Iniciando compressão de {total} arquivos…")

            # Process in batches of 200 to keep memory under control and allow
            # the caller to observe incremental progress.
            offset = 0
            batch_size = 200
            while True:
                rows = self._con.execute(
                    "SELECT id, content FROM tagged_files WHERE encoding='plain' LIMIT ? OFFSET 0",
                    (batch_size,),
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    raw = row["content"]
                    if isinstance(raw, (bytes, memoryview)):
                        # Already binary somehow — just mark as zlib (shouldn't happen)
                        self._con.execute(
                            "UPDATE tagged_files SET encoding='zlib' WHERE id=?", (row["id"],)
                        )
                    else:
                        blob = _compress_content(raw)
                        self._con.execute(
                            "UPDATE tagged_files SET content=?, encoding='zlib' WHERE id=?",
                            (blob, row["id"]),
                        )
                    rows_converted += 1
                self._con.commit()
                if progress_cb:
                    progress_cb(rows_converted, total, f"Comprimindo… {rows_converted}/{total}")

        # ── Step 3: mark schema version ──────────────────────────────────────
        self._set_meta("schema_version", SCHEMA_VERSION_COMPRESSED)
        self._con.commit()

        # ── Step 4: VACUUM to reclaim freed pages ────────────────────────────
        if progress_cb:
            progress_cb(rows_converted, rows_converted, "Compactando banco (VACUUM)…")
        # VACUUM must run outside an explicit transaction
        self._con.commit()
        self._con.execute("VACUUM")

        size_after = self.path.stat().st_size
        return {
            "rows_converted": rows_converted,
            "rows_deduped": rows_deduped,
            "size_before": size_before,
            "size_after": size_after,
            "already_v2": False,
        }

    def __repr__(self) -> str:
        name = self.get_meta("project_name", self.path.stem)
        return f"TTWAProject(name={name!r}, path={str(self.path)!r})"


# ---------------------------------------------------------------------------
# Funções de conveniência (API de alto nível)
# ---------------------------------------------------------------------------

def create_project(
    path: str | Path,
    name: str = "",
    description: str = "",
    overwrite: bool = False,
) -> TTWAProject:
    """Cria e retorna um novo projeto .ttwa."""
    return TTWAProject.create(path, name=name, description=description, overwrite=overwrite)


def open_project(path: str | Path, migrate: bool = True) -> TTWAProject:
    """Abre um projeto `.ttwa` ou `.ttwl` (o tipo vem do próprio arquivo).

    Projetos de esquema antigo são migrados para v0.3 com aviso (ver TTWAProject.open)."""
    return TTWAProject.open(path, migrate=migrate)


def export_corpus_next_to(project: TTWAProject, folder: str | Path | None = None) -> Path:
    """Exporta os textos do projeto para uma pasta ao lado dele (ver TTWAProject.export_corpus_next_to)."""
    return project.export_corpus_next_to(folder)


def relink_corpus(project: TTWAProject, folder: str | Path, accept_changed: bool = False) -> dict:
    """Aponta um `.ttwl` para outra pasta de corpus, conferindo hashes."""
    return project.relink_corpus(folder, accept_changed=accept_changed)


def embed_corpus(project: TTWAProject, dest: str | Path | None = None, allow_changed: bool = False) -> TTWAProject:
    """`.ttwl` → `.ttwa` (texto para dentro). Devolve o novo projeto aberto."""
    return project.embed_corpus(dest, allow_changed=allow_changed)


def detach_corpus(project: TTWAProject, dest: str | Path | None = None,
                  corpus_folder: str | Path | None = None) -> TTWAProject:
    """`.ttwa` → `.ttwl` + pasta de textos. Devolve o novo projeto aberto."""
    return project.detach_corpus(dest, corpus_folder)


def save_analysis_to_project(
    project_path: str | Path,
    corpus1_name: str,
    corpus1_rawcount_csv: str | Path,
    corpus1_norm1000_csv: str | Path,
    corpus2_name: str,
    corpus2_rawcount_csv: str | Path,
    corpus2_norm1000_csv: str | Path,
    kfa_results_df: "pd.DataFrame | None" = None,
    corpus1_folder: str | Path | None = None,
    corpus2_folder: str | Path | None = None,
    corpus1_tagged_folder: str | Path | None = None,
    corpus2_tagged_folder: str | Path | None = None,
    project_name: str = "",
    overwrite: bool = False,
    kfa_min_effect: float = 0.2,
    kfa_join_method: str = "union",
    include_originals: bool = True,
    tagger_type: str = "biberplus",
) -> TTWAProject:
    """
    Função all-in-one: cria (ou sobrescreve) um projeto .ttwa e importa tudo de uma vez.

    Parâmetros obrigatórios:
        project_path              — caminho do arquivo .ttwa a criar
        corpus1_name / corpus2_name   — nomes dos dois corpora
        corpus*_rawcount_csv      — CSV de contagens brutas gerado pelo biberplus
        corpus*_norm1000_csv      — CSV normalizado por 1000 palavras

    Parâmetros opcionais:
        kfa_results_df            — DataFrame de KFA já calculado
        corpus*_folder            — pasta com os .txt originais (importa conteúdos;
                                    ignorado se include_originals=False)
        corpus*_tagged_folder     — pasta com os .tsv tagueados
        include_originals         — True  → modo 'full': salva textos originais + tagged + análise
                                    False → modo 'compact': salva apenas tagged + análise
                                    O modo fica registrado em project_meta['project_mode'].

    Retorna o TTWAProject aberto (não fechado — use .close() ou `with`).
    """
    mode = TTWA_MODE_FULL if include_originals else TTWA_MODE_COMPACT
    proj = TTWAProject.create(project_path, name=project_name, overwrite=overwrite)
    proj._set_meta("project_mode", mode)
    proj._con.commit()

    for cname, raw_csv, norm_csv, folder, tagged_folder in [
        (corpus1_name, corpus1_rawcount_csv, corpus1_norm1000_csv, corpus1_folder, corpus1_tagged_folder),
        (corpus2_name, corpus2_rawcount_csv, corpus2_norm1000_csv, corpus2_folder, corpus2_tagged_folder),
    ]:
        if include_originals and folder:
            proj.add_corpus_folder(cname, folder)
        if tagged_folder:
            proj.save_tagged_folder(cname, tagged_folder, tagger_type=tagger_type)
        proj.save_feature_table_from_csv(cname, raw_csv, "rawcount", tagger_type=tagger_type)
        proj.save_feature_table_from_csv(cname, norm_csv, "norm1000", tagger_type=tagger_type)

    if kfa_results_df is not None:
        proj.save_kfa_result(
            corpus1_name,
            corpus2_name,
            kfa_results_df,
            min_effect=kfa_min_effect,
            join_method=kfa_join_method,
            tagger_type=tagger_type,
        )

    return proj


# ---------------------------------------------------------------------------
# Interno
# ---------------------------------------------------------------------------

def _kind_from_suffix(path: Path) -> str:
    return PROJECT_KIND_TTWL if Path(path).suffix.lower() == TTWL_EXTENSION else PROJECT_KIND_TTWA


def _relative_to_project(project_path: Path, file_path: Path) -> str:
    """Caminho do texto relativo à pasta do projeto (absoluto se em outro disco)."""
    try:
        return Path(os.path.relpath(Path(file_path).resolve(), Path(project_path).resolve().parent)).as_posix()
    except ValueError:  # Windows: outra unidade
        return Path(file_path).resolve().as_posix()


def _read_text(path: Path) -> str:
    # Mesma leitura de add_corpus_folder, para o hash bater.
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _get_ttwtools_version() -> str:
    try:
        from importlib.metadata import version
        return version("ttwtools")
    except Exception:
        return "unknown"
