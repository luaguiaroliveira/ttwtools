"""
help.py — Textos de ajuda do pacote e do aplicativo (novomodelo.md §13.2).

Arquivos em `data/help/<idioma>/<área>/<tópico>.md`, com cabeçalho:

    ---
    titulo: d de Cohen
    resumo: uma frase (vira o balão curto)
    relacionados: tópico, tópico
    ---
    corpo em Markdown, com seções "Como ler" e "Cuidados"

Tours em `data/help/tours/<id>.json` (passos com `alvo`, `titulo`, `texto_ref`,
`posicao`). O mesmo texto serve ao balão, ao tour, à GUI e ao `ttwtools help`.
Sem tradução, cai no inglês (`fallback: True`).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .i18n import LANGS, default_lang, localize, t

_DIR = Path(__file__).parent / "data" / "help"


def _parse(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---\n"):
        head, _, body = text[4:].partition("\n---\n")
        for line in head.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip()] = value.strip()
    return {"title": meta.get("titulo", path.stem), "summary": meta.get("resumo", ""),
            "related": [r.strip() for r in meta.get("relacionados", "").split(",") if r.strip()],
            "body": body.strip()}


@lru_cache(maxsize=None)
def _index(lang: str) -> dict[str, Path]:
    base = _DIR / lang
    return {p.stem: p for p in sorted(base.rglob("*.md"))} if base.is_dir() else {}


def topics(lang: str | None = None) -> list[dict]:
    """Tópicos disponíveis (id, área, título, resumo), incluindo os que só existem em inglês."""
    lang = lang or default_lang()
    ids = sorted(set(_index(lang)) | set(_index("en")))
    return [{"id": i, "area": (_index(lang).get(i) or _index("en")[i]).parent.name,
             **{k: v for k, v in get(i, lang).items() if k in ("title", "summary", "fallback")}} for i in ids]


def get(topic: str, lang: str | None = None) -> dict:
    """Tópico de ajuda: {"id", "area", "title", "summary", "body", "related", "lang", "fallback"}.

    Aceita o id (`cohens_d`) ou o caminho relativo (`metricas/cohens_d`)."""
    lang = lang or default_lang()
    topic = topic.split("/")[-1].removesuffix(".md")
    for candidate in (lang, "en"):
        path = _index(candidate).get(topic)
        if path:
            return {"id": topic, "area": path.parent.name, **_parse(path), "lang": candidate,
                    "fallback": candidate != lang}
    raise KeyError(t("help.not_found", lang, topic=topic))


def search(query: str, lang: str | None = None) -> list[dict]:
    """Tópicos cujo título, resumo ou texto contém `query` (sem distinguir maiúsculas)."""
    q = query.lower()
    out = []
    for item in topics(lang):
        d = get(item["id"], lang)
        if q in d["title"].lower() or q in d["summary"].lower() or q in d["body"].lower():
            out.append({"id": d["id"], "title": d["title"], "summary": d["summary"]})
    return out


def tours() -> list[str]:
    return sorted(p.stem for p in (_DIR / "tours").glob("*.json"))


def tour(tour_id: str, lang: str | None = None) -> dict:
    """Passos do tour, com títulos traduzidos e o resumo do tópico de cada passo."""
    data = json.loads((_DIR / "tours" / f"{tour_id}.json").read_text(encoding="utf-8"))
    out = {"id": data["id"], "title": t(data["titulo"], lang), "steps": []}
    for step in data["passos"]:
        topic = get(step["texto_ref"], lang)
        out["steps"].append({"target": step["alvo"], "title": t(step["titulo"], lang), "topic": topic["id"],
                             "text": topic["summary"], "position": step.get("posicao", "direita")})
    return out


def render(topic: str, lang: str | None = None) -> str:
    """Texto para o terminal."""
    d = get(topic, lang)
    lines = [d["title"], "=" * len(d["title"]), "", d["summary"], "", d["body"]]
    if d["related"]:
        lines += ["", f"{t('help.related', lang)}: {', '.join(d['related'])}"]
    if d["fallback"]:
        lines += ["", t("help.fallback", lang)]
    return "\n".join(lines)


__all__ = ["LANGS", "get", "topics", "search", "tours", "tour", "render", "localize"]
