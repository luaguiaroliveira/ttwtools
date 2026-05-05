"""
project.py — Persistência de projetos ttwtools em arquivos .ttwa (SQLite).

O formato .ttwa (TTW Archive) é um banco SQLite renomeado. Não executa nenhum
código Python ao ser aberto — é seguro contra payloads maliciosos em pickle/HDF5.

Schema de tabelas:
    project_meta   — chave/valor com metadados do projeto (JSON para valores complexos)
    corpus_files   — textos originais (.txt) de cada corpus
    tagged_files   — saída tagueada (.tsv) gerada pelo biberplus
    feature_tables — DataFrames de features (rawcount / norm1000) em JSON
    kfa_results    — DataFrames de resultados KFA entre pares de corpora
"""

from __future__ import annotations

import io
import json
import lzma
import sqlite3
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# MIME type recomendado para registro no sistema operacional / servidor web
# ---------------------------------------------------------------------------
TTWA_MIME_TYPE = "application/x-ttwa+sqlite3"
TTWA_EXTENSION = ".ttwa"

# Modos de arquivo .ttwa gravados em project_meta['project_mode']
TTWA_MODE_FULL    = "full"      # corpus original + tagged + análise
TTWA_MODE_COMPACT = "compact"   # apenas tagged + análise (sem textos originais)

# Versões de schema do arquivo .ttwa
# v0.1 — formato original: tagged_files.content é TEXT sem compressão
# v0.2 — tagged_files.content é BLOB zlib-comprimido; taggers spacy/stanza unificados
SCHEMA_VERSION_LEGACY  = "0.1"
SCHEMA_VERSION_CURRENT = "0.2"

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
        """Cria um novo arquivo .ttwa.

        compress=True (default) — gera arquivo no formato v0.2 com conteudo comprimido
                                    (tagged_files armazenados como BLOB zlib).
        compress=False          — formato v0.1 compatível com versões anteriores.
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
        proj._con.commit()
        return proj

    @classmethod
    def open(cls, path: str | Path) -> "TTWAProject":
        """Abre um arquivo .ttwa existente."""
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: '{p}'")
        proj = cls(p)
        proj._con = _connect(p)
        return proj

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
            self._con.execute(
                "INSERT INTO corpus_files (corpus_name, filename, content) VALUES (?, ?, ?)"
                " ON CONFLICT(corpus_name, filename) DO UPDATE SET content=excluded.content",
                (corpus_name, txt_path.name, content),
            )
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
        self._con.execute(
            "INSERT INTO corpus_files (corpus_name, filename, content) VALUES (?, ?, ?)"
            " ON CONFLICT(corpus_name, filename) DO UPDATE SET content=excluded.content",
            (corpus_name, p.name, content),
        )
        self._con.commit()

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
            SELECT corpus_name FROM tagged_files
            UNION
            SELECT corpus_name FROM feature_tables
            ORDER BY corpus_name
            """
        ).fetchall()
        return [r["corpus_name"] for r in rows]

    def list_corpus_files(self, corpus_name: str) -> list[str]:
        """Lista os nomes dos arquivos de um corpus."""
        rows = self._con.execute(
            "SELECT filename FROM corpus_files WHERE corpus_name = ? ORDER BY filename",
            (corpus_name,),
        ).fetchall()
        return [r["filename"] for r in rows]

    def get_corpus_file(self, corpus_name: str, filename: str) -> Optional[str]:
        """Retorna o conteúdo de um arquivo do corpus, ou None se não existir."""
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
        rows = self._con.execute(
            "SELECT filename, content FROM corpus_files WHERE corpus_name = ?",
            (corpus_name,),
        ).fetchall()
        for row in rows:
            (dest / row["filename"]).write_text(row["content"], encoding=encoding)
        print(f"  + {len(rows)} arquivo(s) exportados para '{dest}'.")
        return len(rows)

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
        is_v2 = self.get_meta("schema_version", SCHEMA_VERSION_LEGACY) >= SCHEMA_VERSION_CURRENT

        # Option A: unify tagger name in v0.2
        stored_tagger = _TAGGER_UNIFIED_MAP.get(tagger_type, tagger_type) if is_v2 else tagger_type
        is_alias = is_v2 and tagger_type != stored_tagger

        if is_v2:
            blob = _compress_content(content)
            if is_alias:
                # Second tagger of a unified pair: keep existing row if present
                self._con.execute(
                    "INSERT INTO tagged_files (corpus_name, filename, tagger_type, encoding, content) VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(corpus_name, filename, tagger_type) DO NOTHING",
                    (corpus_name, filename, stored_tagger, "zlib", blob),
                )
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
    # Utilitários
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Retorna um resumo do conteúdo do projeto."""
        return {
            "path": str(self.path),
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
        if schema_v >= SCHEMA_VERSION_CURRENT:
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
        self._set_meta("schema_version", SCHEMA_VERSION_CURRENT)
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


def open_project(path: str | Path) -> TTWAProject:
    """Abre e retorna um projeto .ttwa existente."""
    return TTWAProject.open(path)


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

def _get_ttwtools_version() -> str:
    try:
        from importlib.metadata import version
        return version("ttwtools")
    except Exception:
        return "unknown"
