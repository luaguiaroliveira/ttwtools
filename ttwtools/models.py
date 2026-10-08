"""
models.py — Modelos de spaCy e Stanza baixados sob demanda, fora do binário.

spaCy: a roda do modelo (GitHub explosion/spacy-models) é extraída em
<dados>/models/python, que entra no sys.path — funciona também no aplicativo
empacotado (sem pip). Stanza: stanza.download para <dados>/models/stanza
(STANZA_RESOURCES_DIR aponta para lá quando o pacote não tem modelos próprios).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .corpus_catalog import data_dir

SPACY_COMPAT = "https://raw.githubusercontent.com/explosion/spacy-models/master/compatibility.json"
SPACY_WHEEL = "https://github.com/explosion/spacy-models/releases/download/{name}-{v}/{name}-{v}-py3-none-any.whl"


def models_dir() -> Path:
    """Pasta dos modelos baixados (<dados>/models)."""
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def activate() -> None:
    """Põe os modelos baixados no caminho de importação (chamar ao iniciar)."""
    py = models_dir() / "python"
    if py.is_dir() and str(py) not in sys.path:
        sys.path.insert(0, str(py))
    stanza_dir = models_dir() / "stanza"
    if stanza_dir.is_dir() and not os.environ.get("STANZA_RESOURCES_DIR"):
        os.environ["STANZA_RESOURCES_DIR"] = str(stanza_dir)


def spacy_model_version(name: str) -> str:
    """Versão do modelo compatível com o spaCy instalado (compatibility.json)."""
    import spacy
    minor = ".".join(spacy.__version__.split(".")[:2])
    compat = json.load(urllib.request.urlopen(SPACY_COMPAT, timeout=30))["spacy"]
    versions = compat.get(minor, {}).get(name)
    if not versions:
        raise ValueError(f"modelo '{name}' sem versão compatível com spaCy {spacy.__version__}")
    return versions[0]


def download_spacy_model(name: str, progress: Callable[[int, int, str], None] | None = None) -> Path:
    """Baixa e extrai o modelo spaCy. Devolve a pasta do pacote do modelo.

    Recusa (ValueError) um modelo que não rodaria nesta instalação (ex.: en_core_web_trf sem
    spacy_curated_transformers)."""
    info = next((m for m in model_info() if m["id"] == name), None)
    if info:
        reason = _model_status(info, None)["reason"]
        if reason:
            raise ValueError(reason)
    version = spacy_model_version(name)
    url = SPACY_WHEEL.format(name=name, v=version)
    target = models_dir() / "python"
    target.mkdir(parents=True, exist_ok=True)
    tmp = models_dir() / f"{name}-{version}.whl.part"
    with urllib.request.urlopen(url, timeout=60) as src, tmp.open("wb") as dst:
        total = int(src.headers.get("Content-Length") or 0)
        done = 0
        for chunk in iter(lambda: src.read(1 << 16), b""):
            dst.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total, name)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(target)
    tmp.unlink()
    activate()
    import importlib
    importlib.invalidate_caches()
    return target / name


def download_stanza(lang: str, package: str = "default", processors: str = "tokenize,pos,lemma",
                    progress: Callable[[int, int, str], None] | None = None) -> Path:
    """Baixa os modelos do Stanza para o idioma (pasta de dados, salvo STANZA_RESOURCES_DIR)."""
    import stanza
    target = Path(os.environ.get("STANZA_RESOURCES_DIR") or models_dir() / "stanza")
    if progress:
        progress(0, 1, f"stanza {lang}/{package}")
    stanza.download(lang, package=package, processors=processors, model_dir=str(target), verbose=False)
    activate()      # o primeiro download da sessão: sem isso o Stanza só acharia o modelo após reiniciar
    if progress:
        progress(1, 1, f"stanza {lang}/{package}")
    return target


def model_info() -> list[dict]:
    """Fichas dos modelos baixáveis (data/models.json): idioma, tamanho, fonte, licença, dados de treino."""
    return json.loads((Path(__file__).parent / "data" / "models.json").read_text(encoding="utf-8"))["models"]


def _model_status(m: dict, lang: str | None) -> dict:
    import importlib.util
    from .i18n import t
    missing = [mod for mod in m.get("requires", []) if importlib.util.find_spec(mod) is None]
    if m["family"] == "stanza":
        from .taggers.catalog import stanza_package_installed
        installed = not missing and stanza_package_installed(m["lang"], m.get("package", "default"))
    else:
        installed = importlib.util.find_spec(m["id"]) is not None
    tier = m["tier"]
    return {**m,
            "installed": installed,
            "available": not missing,
            "reason": t("model.reason.requires", lang, module=missing[0]) if missing else None,
            "name": f"{t('model.family.' + m['family'], lang)} · {t('model.lang.' + m['lang'], lang)} · {t('model.tier.' + tier, lang)}",
            "purpose": t("model.purpose", lang, language=t("model.lang." + m["lang"], lang)),
            "about": t("model.about." + tier, lang)}


def list_models(lang: str | None = None) -> dict:
    """Modelos baixáveis com a ficha, se estão instalados e se podem rodar aqui (`models`);
    `spacy` mantém a lista simples de antes (nome, installed, downloaded)."""
    import importlib.util
    from .taggers.catalog import _load_descriptor
    spacy_values = next(o["valores"] for o in _load_descriptor("spacy")["options"] if o["id"] == "model")
    downloaded = {p.name for p in (models_dir() / "python").glob("*") if p.is_dir()} if (models_dir() / "python").is_dir() else set()
    return {"models": [_model_status(m, lang) for m in model_info()],
            "spacy": [{"name": m, "installed": importlib.util.find_spec(m) is not None, "downloaded": m in downloaded}
                      for m in spacy_values],
            "data_dir": str(models_dir())}
