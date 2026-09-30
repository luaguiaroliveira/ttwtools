"""Arquivos abertos recentemente (.ttwa, .ttwl, .ttwal, .ttwc, .ttwcl, .ttwt), do mais novo ao mais antigo.

A lista fica num JSON na pasta de configuração da pessoa (`TTWTOOLS_HOME` a substitui) e é a
mesma para o aplicativo e a linha de comando.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

MAX_RECENT = 12
EXTENSIONS = (".ttwa", ".ttwl", ".ttwal", ".ttwc", ".ttwcl", ".ttwt")


def config_dir() -> Path:
    env = os.environ.get("TTWTOOLS_HOME")
    if env:
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TTWtools"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "TTWtools"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ttwtools"


def _file() -> Path:
    return config_dir() / "recent.json"


def _load() -> list[dict]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        return [e for e in data if isinstance(e, dict) and e.get("path")]
    except (OSError, ValueError):
        return []


def _save(entries: list[dict]) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def add(path: str | os.PathLike) -> None:
    """Registra um arquivo aberto (vai para o topo; extensões desconhecidas são ignoradas)."""
    p = Path(path).expanduser().resolve()
    if p.suffix.lower() not in EXTENSIONS:
        return
    entries = [e for e in _load() if e["path"] != str(p)]
    entries.insert(0, {"path": str(p), "opened_at": int(time.time())})
    try:
        _save(entries[:MAX_RECENT])
    except OSError:
        pass                                    # lista de recentes nunca deve impedir de abrir


def listing(limit: int = MAX_RECENT) -> list[dict]:
    """[{path, name, ext, exists, opened_at}], mais recente primeiro."""
    out = []
    for e in _load()[:limit]:
        p = Path(e["path"])
        out.append({"path": e["path"], "name": p.name, "ext": p.suffix.lower().lstrip("."),
                    "folder": str(p.parent), "exists": p.exists(), "opened_at": e.get("opened_at", 0)})
    return out


def remove(path: str) -> None:
    p = str(Path(path).expanduser().resolve())
    _save([e for e in _load() if e["path"] not in (p, path)])


def clear() -> None:
    _save([])
