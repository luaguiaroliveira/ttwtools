"""
i18n.py — Textos traduzíveis do pacote (pt e en).

Os arquivos de dados (descritores de taggers, tagsets...) guardam chaves como
`tagger.spacy.opt.model.explain`; os textos ficam em `data/i18n/*.<idioma>.json`.
Idioma padrão: variável TTWTOOLS_LANG, senão "pt". Falta de tradução cai no
inglês e, por fim, na própria chave.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

LANGS = ("pt", "en")
_DIR = Path(__file__).parent / "data" / "i18n"
# campos cujos valores são chaves de tradução nos arquivos de dados
TEXT_FIELDS = {"name", "about", "nome", "explicacao", "label", "definition"}


def default_lang() -> str:
    lang = os.environ.get("TTWTOOLS_LANG", "pt").split("_")[0].lower()
    return lang if lang in LANGS else "pt"


@lru_cache(maxsize=None)
def messages(lang: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in sorted(_DIR.glob(f"*.{lang}.json")):
        out.update(json.loads(f.read_text(encoding="utf-8")))
    return out


def t(key: str, lang: str | None = None, **fmt: Any) -> str:
    lang = lang or default_lang()
    text = messages(lang).get(key) or messages("en").get(key) or key
    return text.format(**fmt) if fmt else text


def localize(obj: Any, lang: str | None = None) -> Any:
    """Copia `obj` trocando as chaves de tradução dos campos de texto pelo texto no idioma."""
    if isinstance(obj, dict):
        return {k: (t(v, lang) if k in TEXT_FIELDS and isinstance(v, str) else localize(v, lang)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [localize(v, lang) for v in obj]
    return obj
