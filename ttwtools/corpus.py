"""
corpus.py — Importação de corpora, metadados por documento, tokenização simples e filtros.

- `import_corpus`: pasta de .txt, um .txt, CSV (texto + colunas de metadados) ou texto colado.
- Metadados de documento (`document_meta`): do nome do arquivo (campos separados por um
  delimitador) e/ou de um CSV com a coluna `filename`.
- `TokenizerConfig` / `tokenize`: tokenização por expressão regular, sem tagger, usada nas
  estatísticas antes da etiquetagem; a configuração fica gravada por corpus no projeto.
- `filter_documents`: seleção de documentos por metadado, reutilizada pelas análises.
"""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .project import TTWAProject

# ---------------------------------------------------------------------------
# Tokenização
# ---------------------------------------------------------------------------

CONTRACTIONS = ("keep", "split")


@dataclass(frozen=True)
class TokenizerConfig:
    """Opções da tokenização simples (sem tagger).

    lowercase       — tudo em minúsculas
    keep_punct      — manter sinais de pontuação como tokens
    keep_numbers    — manter números (ex.: 2026, 3,5)
    contractions    — "keep": `don't` é um token; "split": `do` + `n't`, `it` + `'s`
    """
    lowercase: bool = False
    keep_punct: bool = False
    keep_numbers: bool = True
    contractions: str = "keep"

    def __post_init__(self):
        if self.contractions not in CONTRACTIONS:
            raise ValueError(f"contractions deve ser um de {CONTRACTIONS}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping | None) -> "TokenizerConfig":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


_APOS = "'’"
_WORD = rf"[^\W\d_]+(?:[{_APOS}][^\W\d_]+)*"          # letras, com apóstrofo interno
_NUMBER = r"\d+(?:[.,]\d+)*"
_TOKEN_RE = re.compile(rf"(?P<word>{_WORD})|(?P<number>{_NUMBER})|(?P<punct>[^\w\s])", re.UNICODE)
_SPLIT_RE = re.compile(rf"^(?P<head>.+?)(?P<clitic>n[{_APOS}]t|[{_APOS}](?:s|re|ve|ll|d|m))$", re.IGNORECASE)


def tokenize(text: str, config: TokenizerConfig | None = None) -> list[str]:
    """Divide o texto em tokens conforme a configuração."""
    config = config or TokenizerConfig()
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        tok = m.group()
        if kind == "punct" and not config.keep_punct:
            continue
        if kind == "number" and not config.keep_numbers:
            continue
        if config.lowercase:
            tok = tok.lower()
        if kind == "word" and config.contractions == "split":
            sm = _SPLIT_RE.match(tok)
            if sm and sm.group("head"):
                out += [sm.group("head"), sm.group("clitic")]
                continue
        out.append(tok)
    return out


def set_tokenizer_config(project: TTWAProject, corpus_name: str, config: TokenizerConfig) -> None:
    """Grava a configuração da tokenização simples do corpus."""
    configs = project.get_meta("tokenizer_configs") or {}
    configs[corpus_name] = config.to_dict()
    project.set_meta("tokenizer_configs", configs)


def get_tokenizer_config(project: TTWAProject, corpus_name: str) -> TokenizerConfig:
    """Configuração da tokenização simples do corpus (a padrão, se não houver)."""
    return TokenizerConfig.from_dict((project.get_meta("tokenizer_configs") or {}).get(corpus_name))


# ---------------------------------------------------------------------------
# Metadados de documento
# ---------------------------------------------------------------------------

def _doc_id(project: TTWAProject, corpus_name: str, filename: str) -> int | None:
    row = project._con.execute(
        "SELECT id FROM documents WHERE corpus_name = ? AND filename = ?", (corpus_name, filename)
    ).fetchone()
    return row["id"] if row else None


def set_document_meta(project: TTWAProject, corpus_name: str, filename: str, meta: Mapping[str, Any]) -> None:
    """Grava (ou substitui) pares chave/valor de metadados de um documento."""
    doc_id = _doc_id(project, corpus_name, filename)
    if doc_id is None:
        raise KeyError(f"documento não encontrado: {corpus_name}/{filename}")
    project._con.executemany(
        "INSERT INTO document_meta (doc_id, key, value) VALUES (?, ?, ?)"
        " ON CONFLICT(doc_id, key) DO UPDATE SET value = excluded.value",
        [(doc_id, str(k), "" if v is None else str(v)) for k, v in meta.items()],
    )
    project._con.commit()


def get_document_meta(project: TTWAProject, corpus_name: str, filename: str) -> dict[str, str]:
    """Metadados de um documento ({chave: valor})."""
    doc_id = _doc_id(project, corpus_name, filename)
    if doc_id is None:
        return {}
    rows = project._con.execute("SELECT key, value FROM document_meta WHERE doc_id = ? ORDER BY key", (doc_id,))
    return {r["key"]: r["value"] for r in rows}


def meta_from_filename(filename: str, fields: list[str], delimiter: str = "_") -> dict[str, str]:
    """Metadados a partir do nome do arquivo: `grupoA_texto01.txt` com fields
    ["grupo", "texto"] → {"grupo": "grupoA", "texto": "texto01"}. O último campo
    recebe o resto do nome; campos a mais ficam de fora; campo vazio ("") pula
    aquele pedaço."""
    parts = Path(filename).stem.split(delimiter, len(fields) - 1) if fields else []
    return {k: v for k, v in zip(fields, parts) if k}


def preview_filenames(source: str | Path, delimiter: str = "_", fields: list[str] | None = None,
                      n: int = 5, glob: str = "*.txt") -> dict:
    """Como os nomes dos arquivos da pasta viram metadados, sem importar nada.

    Devolve {"total", "parts" (nº de pedaços mais comum), "irregular" (até 5 nomes com
    outro nº de pedaços), "n_irregular", "examples": [{"file", "parts", "meta"}]}."""
    from collections import Counter
    src = Path(source).expanduser()
    files = sorted(f.name for f in src.glob(glob)) if src.is_dir() else []
    split = {f: Path(f).stem.split(delimiter) if delimiter else [Path(f).stem] for f in files}
    counts = Counter(len(p) for p in split.values())
    parts = counts.most_common(1)[0][0] if counts else 0
    irregular = [f for f, p in split.items() if len(p) != parts]
    return {"total": len(files), "parts": parts, "irregular": irregular[:5], "n_irregular": len(irregular),
            "examples": [{"file": f, "parts": split[f],
                          "meta": meta_from_filename(f, fields, delimiter) if fields else {}}
                         for f in files[:n]]}


def subfolders(source: str | Path, glob: str = "*.txt") -> list[dict]:
    """Subpastas imediatas com arquivos que casam com `glob` — uma por corpus a importar.

    Devolve [{"name", "path", "files"}] em ordem alfabética, só as que têm arquivos
    (pastas ocultas ficam de fora)."""
    src = Path(source).expanduser()
    if not src.is_dir():
        return []
    out = []
    for sub in sorted((p for p in src.iterdir() if p.is_dir() and not p.name.startswith(".")),
                      key=lambda p: p.name.lower()):
        n = sum(1 for f in sub.glob(glob) if f.is_file())
        if n:
            out.append({"name": sub.name, "path": str(sub), "files": n})
    return out


def _csv_reader(fh) -> csv.DictReader:
    """DictReader com delimitador detectado (`,`, `;` ou tab); vírgula se não der para saber."""
    sample = fh.read(8192)
    fh.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return csv.DictReader(fh, dialect=dialect)


def read_metadata_csv(path: str | Path, filename_column: str = "filename") -> dict[str, dict[str, str]]:
    """CSV de metadados → {arquivo: {coluna: valor}}. Aceita `;` ou `,` e BOM."""
    path = Path(path).expanduser()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = _csv_reader(fh)
        if filename_column not in (reader.fieldnames or []):
            raise ValueError(f"o CSV '{path.name}' não tem a coluna '{filename_column}'")
        return {row[filename_column]: {k: v for k, v in row.items() if k != filename_column and k is not None}
                for row in reader if row.get(filename_column)}


def apply_metadata(project: TTWAProject, corpus_name: str, table: Mapping[str, Mapping[str, Any]]) -> dict:
    """Aplica {arquivo: metadados} aos documentos do corpus (casa com ou sem `.txt`).

    Devolve {"applied": n, "unmatched": [nomes do CSV sem documento]}."""
    docs = {d["filename"]: d["filename"] for d in project.list_documents(corpus_name)}
    docs.update({Path(f).stem: f for f in list(docs)})
    applied, unmatched = 0, []
    for name, meta in table.items():
        filename = docs.get(name) or docs.get(Path(name).stem)
        if filename is None:
            unmatched.append(name)
            continue
        set_document_meta(project, corpus_name, filename, meta)
        applied += 1
    return {"applied": applied, "unmatched": unmatched}


# ---------------------------------------------------------------------------
# Importação
# ---------------------------------------------------------------------------

def _add_text(project: TTWAProject, corpus_name: str, filename: str, content: str) -> None:
    """Texto sem arquivo de origem: dentro do `.ttwa`; no `.ttwl`, gravado na pasta do corpus."""
    if project.is_light:
        dest = project.path.parent / f"{project.path.stem}_corpus" / corpus_name / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", newline="")
        project.add_corpus_file(corpus_name, dest)
    else:
        project.add_corpus_text(corpus_name, filename, content)


def _unique_filename(project: TTWAProject, corpus_name: str, base: str) -> str:
    existing = {d["filename"] for d in project.list_documents(corpus_name)}
    stem, suffix = Path(base).stem, Path(base).suffix or ".txt"
    name, n = f"{stem}{suffix}", 1
    while name in existing:
        n += 1
        name = f"{stem}_{n}{suffix}"
    return name


def _check_import_space(project: TTWAProject, source, glob: str, text: str | None) -> None:
    """Recusa antes de gravar se o disco do projeto não comporta os textos (no banco e no WAL)."""
    from . import storage
    size = len(text.encode("utf-8")) if text else 0
    if source is not None:
        src = Path(source).expanduser()
        if src.is_dir():
            size += sum(f.stat().st_size for f in src.glob(glob) if f.is_file())
        elif src.is_file():
            size += src.stat().st_size
    if size:
        storage.ensure_free_space(project.path.parent, storage.with_margin(size * 2), "import")


def import_corpus(
    project: TTWAProject,
    source: str | Path | None,
    name: str,
    *,
    text: str | None = None,
    text_filename: str = "texto_colado.txt",
    glob: str = "*.txt",
    encoding: str = "utf-8",
    filename_fields: list[str] | None = None,
    delimiter: str = "_",
    metadata_csv: str | Path | None = None,
    text_column: str = "text",
    filename_column: str = "filename",
    tokenizer: TokenizerConfig | None = None,
) -> dict:
    """Importa textos para o corpus `name` do projeto.

    source          — pasta de .txt, um arquivo .txt, ou um .csv com uma coluna de
                      texto (`text_column`) e colunas de metadados; None com `text=`.
    text            — texto colado (gravado como `text_filename`, sem sobrescrever).
    filename_fields — nomes dos campos no nome do arquivo, separados por `delimiter`.
    metadata_csv    — CSV com a coluna `filename_column` e colunas de metadados.
    tokenizer       — configuração da tokenização simples deste corpus.

    Devolve {"corpus", "imported", "files", "metadata_applied", "unmatched"}.
    """
    added: list[str] = []
    csv_meta: dict[str, dict[str, str]] = {}
    _check_import_space(project, source, glob, text)

    if text is not None:
        filename = _unique_filename(project, name, text_filename)
        _add_text(project, name, filename, text)
        added.append(filename)

    if source is not None:
        src = Path(source).expanduser()
        if src.is_dir():
            files = sorted(src.glob(glob))
            if not files:
                raise ValueError(f"Nenhum arquivo '{glob}' em '{src}'.")
            for f in files:
                project._store_text(name, f.resolve(), f.read_text(encoding=encoding, errors="ignore"))
                added.append(f.name)
            project._con.commit()
        elif src.suffix.lower() == ".csv":
            with src.open(encoding="utf-8-sig", newline="") as fh:
                reader = _csv_reader(fh)
                if text_column not in (reader.fieldnames or []):
                    raise ValueError(f"o CSV '{src.name}' não tem a coluna de texto '{text_column}'")
                for i, row in enumerate(reader, 1):
                    base = row.get(filename_column) or f"{name}_{i:04d}.txt"
                    filename = _unique_filename(project, name, base)
                    _add_text(project, name, filename, row[text_column] or "")
                    added.append(filename)
                    csv_meta[filename] = {k: v for k, v in row.items()
                                          if k not in (text_column, filename_column) and k is not None}
        elif src.is_file():
            project.add_corpus_file(name, src, encoding=encoding)
            added.append(src.name)
        else:
            raise FileNotFoundError(f"Origem não encontrada: '{src}'")

    applied = 0
    if filename_fields:
        for f in added:
            set_document_meta(project, name, f, meta_from_filename(f, filename_fields, delimiter))
        applied = len(added)
    if csv_meta:
        applied = max(applied, apply_metadata(project, name, csv_meta)["applied"])
    unmatched: list[str] = []
    if metadata_csv is not None:
        report = apply_metadata(project, name, read_metadata_csv(metadata_csv, filename_column))
        applied = max(applied, report["applied"])
        unmatched = report["unmatched"]
    if tokenizer is not None:
        set_tokenizer_config(project, name, tokenizer)

    return {"corpus": name, "imported": len(added), "files": added,
            "metadata_applied": applied, "unmatched": unmatched}


def import_subfolders(project: TTWAProject, source: str | Path, *,
                      glob: str = "*.txt", encoding: str = "utf-8",
                      filename_fields: list[str] | None = None, delimiter: str = "_",
                      metadata_csv: str | Path | None = None, text_column: str = "text",
                      names: list[str] | None = None) -> dict:
    """Importa cada subpasta de `source` como um corpus com o nome da pasta.

    `names` restringe (e ordena) as subpastas; sem ele, todas as que têm `glob`.
    Devolve {"parent", "corpora": [relatórios de import_corpus], "imported": total,
    "files": [...], "folders": [nomes]}.
    """
    folders = subfolders(source, glob)
    if not folders:
        raise ValueError(f"Nenhuma subpasta com '{glob}' em '{Path(source).expanduser()}'.")
    if names is not None:
        wanted = list(dict.fromkeys(names))
        known = {f["name"] for f in folders}
        missing = [n for n in wanted if n not in known]
        if missing:
            raise ValueError(f"subpasta sem '{glob}': {', '.join(missing)}")
        folders = [f for n in wanted for f in folders if f["name"] == n]
    reports = [import_corpus(project, f["path"], f["name"], glob=glob, encoding=encoding,
                             filename_fields=filename_fields, delimiter=delimiter,
                             metadata_csv=metadata_csv, text_column=text_column)
               for f in folders]
    return {"parent": str(Path(source).expanduser()), "corpora": reports,
            "imported": sum(r["imported"] for r in reports),
            "files": [filename for r in reports for filename in r["files"]],
            "folders": [f["name"] for f in folders]}


# ---------------------------------------------------------------------------
# Filtros por metadado
# ---------------------------------------------------------------------------

def parse_where(items: Iterable[str]) -> dict[str, list[str]]:
    """["grupo=A", "grupo=B", "ano=2020"] → {"grupo": ["A", "B"], "ano": ["2020"]} (linha de comando)."""
    where: dict[str, list[str]] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError(f"filtro inválido '{item}' (use chave=valor)")
        where.setdefault(key.strip(), []).append(value.strip())
    return where


def filter_documents(
    project: TTWAProject,
    corpus_name: str | None = None,
    where: Mapping[str, str | Iterable[str]] | None = None,
) -> list[dict]:
    """Documentos do corpus (ou de todos) cujos metadados batem com `where`.

    `where` = {chave: valor} ou {chave: [valores aceitos]}; chaves diferentes
    se combinam com E, valores da mesma chave com OU. Cada documento vem com
    seus metadados em `meta`.
    """
    sql = "SELECT d.id, d.corpus_name, d.filename, d.content_hash, d.n_chars FROM documents d WHERE 1=1"
    args: list = []
    if corpus_name is not None:
        sql += " AND d.corpus_name = ?"
        args.append(corpus_name)
    for key, values in (where or {}).items():
        values = [values] if isinstance(values, str) else list(values)
        sql += (" AND EXISTS (SELECT 1 FROM document_meta m WHERE m.doc_id = d.id AND m.key = ?"
                f" AND m.value IN ({','.join('?' * len(values))}))")
        args += [key, *values]
    docs = [dict(r) for r in project._con.execute(sql + " ORDER BY d.corpus_name, d.filename", args)]
    if docs:
        ids = [d["id"] for d in docs]
        meta: dict[int, dict] = {i: {} for i in ids}
        for r in project._con.execute(
            f"SELECT doc_id, key, value FROM document_meta WHERE doc_id IN ({','.join('?' * len(ids))})", ids
        ):
            meta[r["doc_id"]][r["key"]] = r["value"]
        for d in docs:
            d["meta"] = meta[d["id"]]
    return docs


def list_groups(project: TTWAProject, corpus_name: str | None, key: str) -> dict[str, int]:
    """Valores de um metadado e quantos documentos têm cada um."""
    sql = ("SELECT m.value, COUNT(*) AS n FROM document_meta m JOIN documents d ON d.id = m.doc_id"
           " WHERE m.key = ?")
    args: list = [key]
    if corpus_name is not None:
        sql += " AND d.corpus_name = ?"
        args.append(corpus_name)
    return {r["value"]: r["n"] for r in project._con.execute(sql + " GROUP BY m.value ORDER BY m.value", args)}


def metadata_keys(project: TTWAProject, corpus_name: str | None = None) -> list[str]:
    """Chaves de metadados usadas nos documentos do corpus, em ordem alfabética."""
    sql = "SELECT DISTINCT m.key FROM document_meta m JOIN documents d ON d.id = m.doc_id"
    args: tuple = ()
    if corpus_name is not None:
        sql += " WHERE d.corpus_name = ?"
        args = (corpus_name,)
    return [r["key"] for r in project._con.execute(sql + " ORDER BY m.key", args)]


# ---------------------------------------------------------------------------
# Resumo dos corpora e das camadas (biblioteca na interface)
# ---------------------------------------------------------------------------

def layer_summary(project: TTWAProject, corpus_name: str) -> list[dict]:
    """Camadas do corpus agrupadas por configuração: ferramenta, versão, modelo,
    configuração efetiva, quantos documentos cobre e quantos tokens tem."""
    import json as _json
    rows = project._con.execute(
        "SELECT l.tool, l.tool_version, l.model, l.config, l.config_hash, COUNT(*) AS documents,"
        " SUM(l.n_tokens) AS tokens, MAX(l.created_at) AS created_at"
        " FROM layers l JOIN documents d ON d.id = l.doc_id WHERE d.corpus_name = ?"
        " GROUP BY l.tool, l.tool_version, l.model, l.config_hash ORDER BY created_at DESC",
        (corpus_name,)).fetchall()
    total = project._con.execute("SELECT COUNT(*) FROM documents WHERE corpus_name = ?", (corpus_name,)).fetchone()[0]
    return [{**dict(r), "config": _json.loads(r["config"]), "coverage": r["documents"] / total if total else 0.0,
             "fields": _layer_fields(project, corpus_name, r["tool"], r["tool_version"], r["model"], r["config_hash"])}
            for r in rows]


def _layer_fields(project: TTWAProject, corpus_name: str, tool: str, version: str, model: str, config_hash: str) -> list[str]:
    """Campos preenchidos da camada (`tags`, `upos`, `xpos`, `lemma`, `feats`), por amostra das 3 primeiras camadas:
    a interface só oferece `upos`/`xpos` como atributo quando existem."""
    ids = [r[0] for r in project._con.execute(
        "SELECT l.id FROM layers l JOIN documents d ON d.id = l.doc_id WHERE d.corpus_name = ? AND l.tool = ?"
        " AND l.tool_version = ? AND l.model = ? AND l.config_hash = ? ORDER BY l.id LIMIT 3",
        (corpus_name, tool, version, model, config_hash))]
    if not ids:
        return []
    from . import idquery
    store = idquery.available(project, {i: {"corpus_name": corpus_name} for i in ids})
    if store is not None:                       # camada `TCL2` empacotada: dos ids, sem montar o índice de busca
        return [name for name in ("tags", "upos", "xpos", "lemma", "feats") if any(idquery.layer_has(store, i, name) for i in ids)]
    marks = ",".join("?" * len(ids))
    row = project._con.execute(
        "SELECT MAX(tags IS NOT NULL AND tags NOT IN ('', '[]')), MAX(upos IS NOT NULL AND upos <> ''),"
        " MAX(xpos IS NOT NULL AND xpos <> ''), MAX(lemma IS NOT NULL AND lemma <> ''),"
        f" MAX(feats IS NOT NULL AND feats <> '') FROM tokens WHERE layer_id IN ({marks})", ids).fetchone()
    return [name for name, v in zip(("tags", "upos", "xpos", "lemma", "feats"), row) if v]


def list_corpora(project: TTWAProject) -> list[dict]:
    """Corpora do projeto: documentos, caracteres, chaves de metadados e camadas."""
    out = []
    for name in project.list_corpus_names():
        row = project._con.execute(
            "SELECT COUNT(*) AS documents, COALESCE(SUM(n_chars), 0) AS chars FROM documents WHERE corpus_name = ?",
            (name,)).fetchone()
        out.append({"name": name, "documents": row["documents"], "chars": row["chars"],
                    "metadata_keys": metadata_keys(project, name), "layers": layer_summary(project, name)})
    return out


__all__ = [
    "layer_summary", "list_corpora",
    "TokenizerConfig", "tokenize", "set_tokenizer_config", "get_tokenizer_config",
    "set_document_meta", "get_document_meta", "meta_from_filename", "read_metadata_csv", "apply_metadata",
    "import_corpus", "import_subfolders", "subfolders", "parse_where", "filter_documents",
    "list_groups", "metadata_keys",
]
