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
import re
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


# Destaques animados no texto (marca-texto e caneta): `[texto]{marca amarelo}`, `[texto]{sublinhado azul}` ou `==texto==`. Mantenha igual a
# frontend-vue/src/utils/highlights.js. Cor também em hexadecimal (`#e11d48`).
HIGHLIGHT_TYPES = {"marca", "highlight", "sublinhado", "underline"}
HIGHLIGHT_COLORS = {"amarelo", "yellow", "rosa", "pink", "verde", "green", "azul", "blue", "laranja", "orange",
                    "roxo", "purple", "vermelho", "red", "preto", "black"}
_SPAN = re.compile(r"\[([^\[\]]+?)\]\{([^{}]*)\}")


def check(lang: str | None = None) -> list[str]:
    """Confere os textos de ajuda e devolve a lista de problemas (vazia = tudo certo).

    Verifica: tópico sem tradução em pt/en, título ou resumo vazios, `relacionados` que não existem,
    destaques com tipo/cor desconhecidos e `==` sem par. Para quem edita os `.md` de `data/help`."""
    langs = [lang] if lang else list(LANGS)
    problems: list[str] = []
    every = set().union(*(set(_index(x)) for x in LANGS))
    for code in langs:
        for tid in sorted(every):
            path = _index(code).get(tid)
            if path is None:
                problems.append(f"{code}/{tid}: sem tradução (cai no inglês)")
                continue
            where = f"{code}/{path.parent.name}/{path.name}"
            d = _parse(path)
            if not d["summary"]:
                problems.append(f"{where}: sem 'resumo' no cabeçalho")
            if d["title"] == path.stem:
                problems.append(f"{where}: sem 'titulo' no cabeçalho")
            for rel in d["related"]:
                if rel not in every:
                    problems.append(f"{where}: relacionado inexistente '{rel}'")
            body = d["body"]
            for m in _SPAN.finditer(body):
                words = [w for w in re.split(r"[\s,]+", m.group(2).lower()) if w]
                bad = [w for w in words if w not in HIGHLIGHT_TYPES | HIGHLIGHT_COLORS and not re.fullmatch(r"#[0-9a-f]{6}", w)]
                if bad or not any(w in HIGHLIGHT_TYPES for w in words):
                    problems.append(f"{where}: destaque inválido [{m.group(1)[:30]}]{{{m.group(2)}}}"
                                    + (f" (desconhecido: {', '.join(bad)})" if bad else " (falta o tipo)"))
            if len(re.findall(r"==", _SPAN.sub("", body).replace("```", ""))) % 2:
                problems.append(f"{where}: '==' sem par (destaque aberto e não fechado)")
    return problems


def tours() -> list[str]:
    """Ids dos tours guiados disponíveis."""
    return sorted(p.stem for p in (_DIR / "tours").glob("*.json"))


def tour(tour_id: str, lang: str | None = None) -> dict:
    """Passos do tour, com títulos traduzidos e o resumo do tópico de cada passo."""
    data = json.loads((_DIR / "tours" / f"{tour_id}.json").read_text(encoding="utf-8"))
    out = {"id": data["id"], "title": t(data["titulo"], lang), "steps": []}
    for step in data["passos"]:
        topic = get(step["texto_ref"], lang)
        out["steps"].append({"target": step["alvo"], "title": t(step["titulo"], lang), "topic": topic["id"],
                             "text": topic["summary"], "position": step.get("posicao", "direita"),
                             "route": step.get("rota")})
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


__all__ = ["LANGS", "get", "topics", "search", "check", "tours", "tour", "render", "localize"]
