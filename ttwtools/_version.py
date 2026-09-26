"""Versão do pacote. Fonte única: `version` do pyproject.toml.

No código-fonte lê o pyproject.toml ao lado do pacote (evita o número antigo de
uma instalação editável); instalado, usa importlib.metadata.
"""

from __future__ import annotations

from pathlib import Path


def _read_version() -> str:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        import tomllib
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        if data.get("project", {}).get("name") == "ttwtools":
            return data["project"]["version"]
    except Exception:
        pass
    try:
        from importlib.metadata import version
        return version("ttwtools")
    except Exception:
        return "0+unknown"


__version__ = _read_version()
