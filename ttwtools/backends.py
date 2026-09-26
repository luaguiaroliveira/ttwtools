"""
backends.py — Adaptadores dos taggers para etiquetar um texto por vez.

Cada adaptador declara:
  - `name`               ferramenta gravada em `layers.tool`;
  - `defaults`           opções que MUDAM o resultado, com o valor padrão por extenso;
  - `components`         o que a ferramenta pode produzir (pos, lemma, morph...);
  - `default_components` o que se pede quando nada é dito;
e implementa `tool_version()`, `model(options)`, `model_version(options)` e
`tag(text, options, components)`, que devolve tokens no formato JSONL canônico
(`start_char`, `end_char`, `word`, `upos`, `xpos`/`ptb`, `lemma`, `feats`, `tags`).

Opções de desempenho (processos, lote, dispositivo) são aceitas mas não entram
na identidade da camada (ver `layers.PERFORMANCE_KEYS`). Os núcleos de cada
tagger ficam em `ttwtools/taggers/`; aqui só se escolhe o pipeline e se chamam.
"""

from __future__ import annotations

import re
from typing import Any

_pipelines: dict[tuple, Any] = {}


def _pkg_version(dist: str) -> str:
    try:
        from importlib.metadata import version
        return version(dist)
    except Exception:
        return "unknown"


def _strip_markup(original_text: str) -> tuple[str, list[int] | None]:
    """Remove `<...>` e devolve o mapa de posições para o texto original."""
    from .taggers.spacy_pos import _build_offset_map
    text = re.sub(r"<[^>]*>", "", original_text)
    return text, _build_offset_map(original_text, text)


class Backend:
    name: str = ""
    defaults: dict[str, Any] = {}
    components: tuple[str, ...] = ()
    default_components: tuple[str, ...] = ()

    def tool_version(self) -> str:
        raise NotImplementedError

    def model(self, options: dict) -> str:
        return ""

    def model_version(self, options: dict) -> str:
        return ""

    def tag(self, text: str, options: dict, components: tuple[str, ...]) -> list[dict]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# spaCy
# ---------------------------------------------------------------------------

class SpacyBackend(Backend):
    name = "spacy"
    defaults = {"model": "en_core_web_sm"}
    # pos = UPOS (token.pos_), tag = Penn/XPOS (token.tag_), lemma, morph = traços (feats)
    components = ("pos", "tag", "lemma", "morph")
    default_components = ("pos", "tag", "lemma", "morph")

    def tool_version(self) -> str:
        return _pkg_version("spacy")

    def model(self, options: dict) -> str:
        return options["model"]

    def _nlp(self, options: dict):
        key = ("spacy", options["model"])
        if key not in _pipelines:
            import spacy
            nlp = spacy.load(options["model"], disable=["ner", "parser"])
            nlp.max_length = 5_000_000
            _pipelines[key] = nlp
        return _pipelines[key]

    def model_version(self, options: dict) -> str:
        # pelos metadados do pacote do modelo: não carrega o pipeline
        return _pkg_version(options["model"].replace("_", "-"))

    def tag(self, text, options, components):
        from .taggers.spacy_pos import tag_from_doc_spacy_pos
        stripped, offset_map = _strip_markup(text)
        tokens = tag_from_doc_spacy_pos(self._nlp(options)(stripped), text, offset_map, mode="upos")
        drop = {"pos": "upos", "tag": "ptb", "lemma": "lemma", "morph": "feats"}
        for comp, field in drop.items():
            if comp not in components:
                for t in tokens:
                    t.pop(field, None)
        for t in tokens:
            t["tags"] = []   # as classes ficam em upos/xpos; tags é para taggers de traços
        return tokens


# ---------------------------------------------------------------------------
# Stanza (e MFTE, que usa o mesmo pipeline)
# ---------------------------------------------------------------------------

def _stanza_nlp(lang: str, processors: str):
    key = ("stanza", lang, processors)
    if key not in _pipelines:
        import stanza
        from .taggers.stanza_pos import _detect_device
        _pipelines[key] = stanza.Pipeline(
            lang, processors=processors, device=_detect_device(), verbose=False,
            download_method=stanza.DownloadMethod.REUSE_RESOURCES,
        )
    return _pipelines[key]


class StanzaBackend(Backend):
    name = "stanza"
    defaults = {"lang": "en", "package": "default"}
    components = ("pos", "morph", "lemma")
    default_components = ("pos", "morph")      # lema pede outro processador (mais lento)

    def tool_version(self) -> str:
        return _pkg_version("stanza")

    def model(self, options: dict) -> str:
        return f"{options['lang']}/{options['package']}"

    def tag(self, text, options, components):
        from .taggers.stanza_pos import tag_from_doc_stanza_pos
        processors = "tokenize,pos" + (",lemma" if "lemma" in components else "")
        stripped, offset_map = _strip_markup(text)
        doc = _stanza_nlp(options["lang"], processors)(stripped)
        tokens = tag_from_doc_stanza_pos(doc, text, offset_map, mode="upos")
        for t in tokens:
            t["tags"] = []
            if "morph" not in components:
                t.pop("feats", None)
        return tokens


class MfteBackend(Backend):
    name = "mfte"
    defaults = {"extended": True, "lang": "en"}
    components = ("mfte", "pos", "morph")
    default_components = ("mfte", "pos", "morph")

    def tool_version(self) -> str:
        return _pkg_version("mfte")

    def model(self, options: dict) -> str:
        return f"stanza-{options['lang']}"

    def model_version(self, options: dict) -> str:
        return _pkg_version("stanza")

    def tag(self, text, options, components):
        from .taggers.mfte import tag_from_doc_mfte
        stripped, offset_map = _strip_markup(text)
        doc = _stanza_nlp(options["lang"], "tokenize,pos")(stripped)
        return tag_from_doc_mfte(doc, text, offset_map, extended=bool(options["extended"]))


# ---------------------------------------------------------------------------
# BiberPlus
# ---------------------------------------------------------------------------

class BiberPlusBackend(Backend):
    name = "biberplus"
    defaults = {"biber": True, "function_words": False, "binary_tags": False}
    components = ("biber",)
    default_components = ("biber",)

    def tool_version(self) -> str:
        return _pkg_version("biberplus")

    def model(self, options: dict) -> str:
        return "biberplus-spacy"      # o BiberPlus carrega o próprio pipeline spaCy

    def model_version(self, options: dict) -> str:
        return _pkg_version("en-core-web-sm")

    def _pipeline(self, config: dict):
        key = ("biberplus",)
        if key not in _pipelines:
            from biberplus.tagger import load_pipeline
            _pipelines[key] = load_pipeline(config)
        return _pipelines[key]

    def tag(self, text, options, components):
        from biberplus.tagger import load_config, tag_text
        from .taggers.biberplus import _tokens_with_offsets_regex
        config = load_config()
        config.update({k: options[k] for k in self.defaults})
        config.update({k: options[k] for k in ("n_processes", "processing_size") if k in options})
        stripped, offset_map = _strip_markup(text)
        tagged_words = tag_text(stripped, pipeline=self._pipeline(config), config=config)
        return _tokens_with_offsets_regex(stripped, tagged_words, offset_map)


BACKENDS: dict[str, Backend] = {b.name: b for b in (SpacyBackend(), StanzaBackend(), MfteBackend(), BiberPlusBackend())}


def get_backend(name: str) -> Backend:
    try:
        return BACKENDS[name]
    except KeyError:
        raise ValueError(f"tagger desconhecido '{name}'; disponíveis: {', '.join(sorted(BACKENDS))}") from None


def register_backend(backend: Backend) -> None:
    """Registra um adaptador (usado em testes e por extensões)."""
    BACKENDS[backend.name] = backend
