"""
catalog.py — Descritores de opções, tagsets e disponibilidade dos taggers.

    from ttwtools import taggers
    taggers.available()                 # quais taggers rodam neste sistema, e por quê não
    taggers.options("spacy_upos")       # descritor de opções (mesmo conteúdo do painel "Personalizar")
    taggers.get_tagset("biberplus")     # repertório de tags com definições
    taggers.run("spacy", "corpus", project=proj, preset="rapido", options={"model": "en_core_web_sm"})

Os dados ficam em `ttwtools/data/taggers/<tagger>.options.json` e
`ttwtools/data/tagsets/<tagset>.tagset.json`; os textos, em `data/i18n`.
Nada aqui importa spaCy, Stanza ou torch, exceto `available()`, que testa o torch.
"""

from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..i18n import localize, t

_DATA = Path(__file__).resolve().parent.parent / "data"
TAGGERS = ("spacy", "stanza", "mfte", "biberplus")
PRESETS = ("rapido", "recomendado", "preciso")


class TaggerUnavailable(RuntimeError):
    """Tagger ou modelo indisponível; `reason` explica e `command` diz como resolver."""

    def __init__(self, tagger: str, reason: str, command: str | None = None):
        super().__init__(f"{tagger}: {reason}")
        self.tagger, self.reason, self.command = tagger, reason, command


# ---------------------------------------------------------------------------
# Descritores
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _load_descriptor(tagger: str) -> dict:
    return json.loads((_DATA / "taggers" / f"{tagger}.options.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _aliases() -> dict[str, tuple[str, dict]]:
    """id aceito → (tagger, informações do atalho: tagset e opções fixas)."""
    out: dict[str, tuple[str, dict]] = {}
    for name in TAGGERS:
        out[name] = (name, {})
        for alias, info in _load_descriptor(name).get("aliases", {}).items():
            out[alias] = (name, info)
    return out


def resolve(tagger_id: str) -> tuple[str, dict]:
    """`spacy_upos` → ("spacy", {"tagset": "upos"}); erro claro para id desconhecido."""
    try:
        return _aliases()[tagger_id]
    except KeyError:
        raise ValueError(f"tagger desconhecido '{tagger_id}'; disponíveis: {', '.join(sorted(_aliases()))}") from None


def has_descriptor(tagger: str) -> bool:
    return tagger in _aliases()


def options(tagger_id: str, lang: str | None | bool = None) -> dict:
    """Descritor de opções do tagger, com os textos no idioma `lang` (padrão:
    TTWTOOLS_LANG ou pt). `lang=False` devolve as chaves de tradução."""
    name, _ = resolve(tagger_id)
    d = json.loads(json.dumps(_load_descriptor(name)))  # cópia
    return d if lang is False else localize(d, lang)


def result_defaults(tagger: str) -> dict:
    """Valores padrão das opções que mudam o resultado (sem os componentes)."""
    return {o["id"]: o["padrao"] for o in _load_descriptor(tagger)["options"]
            if o["afeta_resultado"] and o["id"] != "components"}


def default_components(tagger: str) -> list[str]:
    for o in _load_descriptor(tagger)["options"]:
        if o["id"] == "components":
            return list(o["padrao"])
    return []


def performance_keys(tagger: str) -> set[str]:
    return {o["id"] for o in _load_descriptor(tagger)["options"] if not o["afeta_resultado"]}


def preset(tagger_id: str, name: str) -> dict:
    tagger, _ = resolve(tagger_id)
    presets = _load_descriptor(tagger).get("presets", {})
    if name not in presets:
        raise ValueError(f"predefinição '{name}' inexistente para '{tagger}' (use: {', '.join(presets)})")
    return dict(presets[name])


def validate_options(tagger_id: str, opts: Mapping[str, Any] | None) -> dict:
    """Confere tipos e valores contra o descritor. Devolve as opções (sem alterar)."""
    tagger, _ = resolve(tagger_id)
    spec = {o["id"]: o for o in _load_descriptor(tagger)["options"]}
    errors = []
    for key, value in (opts or {}).items():
        o = spec.get(key)
        if o is None:
            errors.append(f"opção desconhecida '{key}' (aceitas: {', '.join(spec)})")
            continue
        kind = o["tipo"]
        if kind == "booleano" and not isinstance(value, bool):
            errors.append(f"'{key}' deve ser verdadeiro ou falso")
        elif kind == "inteiro" and (not isinstance(value, int) or isinstance(value, bool)
                                    or value < o.get("min", -10**18)):
            errors.append(f"'{key}' deve ser inteiro" + (f" ≥ {o['min']}" if "min" in o else ""))
        elif kind == "escolha" and value not in o["valores"]:
            errors.append(f"'{key}' deve ser um de: {', '.join(map(str, o['valores']))}")
        elif kind == "lista" and (not isinstance(value, (list, tuple)) or not value
                                  or not set(value) <= set(o["valores"])):
            errors.append(f"'{key}' deve ser uma lista com valores entre: {', '.join(o['valores'])}")
        elif kind == "texto" and not isinstance(value, str):
            errors.append(f"'{key}' deve ser texto")
    if errors:
        raise ValueError(f"opções inválidas para '{tagger}': " + "; ".join(errors))
    return dict(opts or {})


# ---------------------------------------------------------------------------
# Tagsets
# ---------------------------------------------------------------------------

def list_tagsets() -> list[str]:
    return sorted(p.name.split(".")[0] for p in (_DATA / "tagsets").glob("*.tagset.json"))


def get_tagset(tagset_or_tagger: str, lang: str | None = None, group: str | None = None) -> dict:
    """Repertório de tags. Aceita o id do tagset (upos, ptb, biber, mfte) ou do
    tagger (spacy_upos → upos, stanza_xpos → ptb, biberplus → biber...).
    Textos no idioma `lang` (padrão: TTWTOOLS_LANG ou pt); `lang=False` = chaves."""
    name = tagset_or_tagger
    if name not in list_tagsets():
        tagger, info = resolve(name)
        tagsets = _load_descriptor(tagger).get("tagsets", {})
        name = info.get("tagset") or tagsets.get("tags") or tagsets.get("upos")
    data = json.loads((_DATA / "tagsets" / f"{name}.tagset.json").read_text(encoding="utf-8"))
    if group:
        data["tags"] = [tg for tg in data["tags"] if tg["group"] == group]
    return data if lang is False else localize(data, lang)


# ---------------------------------------------------------------------------
# Disponibilidade
# ---------------------------------------------------------------------------

def _pkg_version(dist: str) -> str | None:
    try:
        from importlib.metadata import version
        return version(dist)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _torch_status() -> tuple[bool, str | None]:
    """torch importa e conversa com o numpy? (no Intel, torch 2.2 + numpy 2 falha)."""
    if importlib.util.find_spec("torch") is None:
        return False, ("missing_module", {"module": "torch"})
    try:
        import numpy as np
        import torch
        torch.from_numpy(np.arange(2.0))
        return True, None
    except Exception as exc:  # noqa: BLE001 — qualquer falha = indisponível
        return False, ("torch_numpy", {"error": f"{type(exc).__name__}: {exc}"})


def spacy_model_installed(model: str) -> bool:
    return importlib.util.find_spec(model) is not None


def stanza_model_dir(model_dir: str | None = None) -> Path:
    import os
    if model_dir:
        return Path(model_dir)
    if os.environ.get("STANZA_RESOURCES_DIR"):
        return Path(os.environ["STANZA_RESOURCES_DIR"])
    from stanza.resources.common import DEFAULT_MODEL_DIR
    return Path(DEFAULT_MODEL_DIR)


def stanza_package_installed(lang: str, package: str, processors: Iterable[str] = ("tokenize", "pos"),
                             model_dir: str | None = None) -> bool:
    """Os modelos do pacote Stanza estão baixados? (sem baixar nada)"""
    base = stanza_model_dir(model_dir)
    try:
        resources = json.loads((base / "resources.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    lang_res = resources.get(lang, {})
    pkg = lang_res.get("packages", {}).get(package) or (lang_res.get("default_processors") if package == "default" else None)
    for proc in processors:
        if pkg and proc in pkg:
            name = pkg[proc]
        elif proc in lang_res and package in lang_res[proc]:
            name = package
        else:
            return False
        if not (base / lang / proc / f"{name}.pt").is_file():
            return False
    return True


def stanza_download_command(lang: str, package: str, processors: str = "tokenize,pos,lemma") -> str:
    return f"python -c \"import stanza; stanza.download('{lang}', package='{package}', processors='{processors}')\""


def _check(tagger: str, lang: str | None) -> dict:
    d = _load_descriptor(tagger)
    reason = None
    command = None
    for module in d["requires"]:
        if module == "torch":
            ok, why = _torch_status()
            if not ok:
                reason = why
                break
        elif importlib.util.find_spec(module) is None:
            reason = ("missing_module", {"module": module})
            command = f"pip install {module.lower()}"
            break
    if reason is None and tagger in ("spacy", "biberplus"):
        model = result_defaults("spacy")["model"]
        if not spacy_model_installed(model):
            command = f"python -m spacy download {model}"
            reason = ("missing_model", {"model": model, "command": command})
    if reason is None and tagger in ("stanza", "mfte"):
        if not stanza_package_installed("en", "default"):
            command = stanza_download_command("en", "default")
            reason = ("missing_model", {"model": "stanza en/default", "command": command})
    versions = {m: _pkg_version(m) for m in d["requires"]}
    return {
        "id": tagger,
        "disponivel": reason is None,
        "motivo": t(f"tagger.reason.{reason[0]}", lang, **reason[1]) if reason else "",
        "comando": command or "",
        "versoes": versions,
        "idiomas": d.get("langs", []),
        "atalhos": sorted(d.get("aliases", {})),
        "tagsets": d.get("tagsets", {}),
    }


def available(lang: str | None = None) -> list[dict]:
    """Um item por tagger: `disponivel` (bool), `motivo` (texto) e `comando` para resolver.

    Nunca levanta exceção por dependência ausente: ImportError vira "indisponível"."""
    out = []
    for tagger in TAGGERS:
        try:
            out.append(_check(tagger, lang))
        except Exception as exc:  # noqa: BLE001
            out.append({"id": tagger, "disponivel": False, "comando": "", "versoes": {}, "idiomas": [],
                        "atalhos": [], "tagsets": {},
                        "motivo": t("tagger.reason.import_error", lang, module=tagger, error=exc)})
    return out


def require_available(tagger: str) -> None:
    info = _check(tagger, None)
    if not info["disponivel"]:
        raise TaggerUnavailable(tagger, info["motivo"], info["comando"] or None)


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def run(tagger_id: str, corpus: str, options: Mapping[str, Any] | None = None, *,
        project=None, preset: str | None = None, components: Iterable[str] | None = None, **kwargs):
    """Etiqueta um corpus com um único dicionário de opções, validado contra o descritor.

    Com `project`, etiqueta o corpus do projeto com cache de camadas (annotate.tag_corpus)
    e aceita `where`, `force` e `progress`. Sem `project`, `corpus` é uma pasta de .txt e
    roda a função antiga do tagger (mesmos arquivos CSV/JSONL de antes); `kwargs` vão
    direto para ela (atalhos antigos: `output_dir`, `save_tagged`...).
    """
    if project is not None:
        from ..annotate import tag_corpus
        return tag_corpus(project, corpus, tagger_id, options, components=components, preset=preset, **kwargs)
    from . import (biberplus, mfte, spacy_ptb, spacy_upos, stanza_upos, stanza_xpos)
    tagger, info = resolve(tagger_id)
    opts = {**(globals()["preset"](tagger_id, preset) if preset else {}), **info.get("options", {}), **(options or {})}
    validate_options(tagger, opts)
    legacy = {"spacy_upos": spacy_upos, "spacy": spacy_upos, "spacy_ptb": spacy_ptb, "stanza_upos": stanza_upos,
              "stanza": stanza_upos, "stanza_xpos": stanza_xpos, "mfte": mfte, "mfte_ext": mfte, "biberplus": biberplus}
    fn = legacy[tagger_id]
    if tagger == "spacy":
        if "model" in opts:
            kwargs.setdefault("spacy_model", opts["model"])
    elif tagger in ("stanza", "mfte"):
        if opts.get("model_dir"):
            kwargs.setdefault("model_dir", opts["model_dir"])
        if opts.get("device") in ("cpu", "cuda"):
            kwargs.setdefault("use_gpu", opts["device"] == "cuda")
        if tagger == "mfte" and "extended" in opts:
            kwargs.setdefault("extended", opts["extended"])
    elif tagger == "biberplus":
        config = {"n_processes": opts.get("n_processes", 1), "function_words": opts.get("function_words", False)}
        if "binary_tags" in opts:
            config["binary_tags"] = opts["binary_tags"]
        kwargs.setdefault("configdict", config)
    return fn(corpus, **kwargs)
