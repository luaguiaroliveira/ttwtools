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
    """Opções: data/taggers/spacy.options.json (model, components, max_length...)."""
    name = "spacy"
    defaults = {"model": "en_core_web_sm"}
    # pos = UPOS (token.pos_), tag = Penn/XPOS (token.tag_), lemma, morph = atributos (feats)
    components = ("pos", "tag", "lemma", "morph")
    default_components = ("pos", "tag", "lemma", "morph")

    def tool_version(self) -> str:
        return _pkg_version("spacy")

    def model(self, options: dict) -> str:
        return options["model"]

    def _nlp(self, options: dict, components):
        from .taggers.spacy_pos import _load_spacy_pipeline, disabled_pipes
        nlp = _load_spacy_pipeline(options["model"], disable=disabled_pipes(components))
        nlp.max_length = int(options.get("max_length", 5_000_000))
        return nlp

    def model_version(self, options: dict) -> str:
        # pelos metadados do pacote do modelo: não carrega o pipeline
        return _pkg_version(options["model"].replace("_", "-"))

    def tag(self, text, options, components):
        from .taggers.spacy_pos import tag_from_doc_spacy_pos
        stripped, offset_map = _strip_markup(text)
        tokens = tag_from_doc_spacy_pos(self._nlp(options, components)(stripped), text, offset_map, mode="upos")
        drop = {"pos": "upos", "tag": "ptb", "lemma": "lemma", "morph": "feats"}
        for comp, field in drop.items():
            if comp not in components:
                for t in tokens:
                    t.pop(field, None)
        for t in tokens:
            t["tags"] = []   # as classes ficam em upos/xpos; tags é para taggers de atributos
        return tokens


# ---------------------------------------------------------------------------
# Stanza (e MFTE, que usa o mesmo pipeline)
# ---------------------------------------------------------------------------

def _require_torch(tagger: str) -> None:
    from .taggers.catalog import TaggerUnavailable, _torch_status
    from .i18n import t
    ok, why = _torch_status()
    if not ok:
        raise TaggerUnavailable(tagger, t(f"tagger.reason.{why[0]}", **why[1]))


def _stanza_nlp(tagger: str, options: dict, processors: str):
    _require_torch(tagger)
    from .taggers.stanza_pos import _detect_device, _load_stanza_pipeline
    device = options.get("device", "auto")
    extra = {k: options[k] for k in ("tokenize_no_ssplit", "tokenize_pretokenized", "pos_batch_size") if k in options}
    return _load_stanza_pipeline(
        _detect_device() if device == "auto" else device, options.get("model_dir") or None,
        lang=options.get("lang", "en"), package=options.get("package", "default"),
        processors=processors, download=False, **extra,
    )


class StanzaBackend(Backend):
    """Opções: data/taggers/stanza.options.json (lang, package, components, tokenize_*...)."""
    name = "stanza"
    defaults = {"lang": "en", "package": "default", "tokenize_no_ssplit": False, "tokenize_pretokenized": False}
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
        doc = _stanza_nlp(self.name, options, processors)(stripped)
        tokens = tag_from_doc_stanza_pos(doc, text, offset_map, mode="upos")
        for t in tokens:
            t["tags"] = []
            if "morph" not in components:
                t.pop("feats", None)
        return tokens


class MfteBackend(Backend):
    """Opções: data/taggers/mfte.options.json (extended, lang, device...)."""
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
        doc = _stanza_nlp(self.name, {**options, "package": "default"}, "tokenize,pos")(stripped)
        tokens = tag_from_doc_mfte(doc, text, offset_map, extended=bool(options["extended"]))
        for t in tokens:
            if "pos" not in components:
                t.pop("upos", None)
            if "morph" not in components:
                t.pop("feats", None)
        return tokens


# ---------------------------------------------------------------------------
# BiberPlus
# ---------------------------------------------------------------------------

class BiberPlusBackend(Backend):
    name = "biberplus"
    defaults = {"function_words": False, "binary_tags": False}
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
        from biberplus.tagger import load_config, tag_text  # ImportError → indisponível (tag_corpus)
        from .taggers.biberplus import _tokens_with_offsets_regex
        config = load_config()
        config.update({k: options[k] for k in ("function_words", "binary_tags") if k in options})
        config.update({k: options[k] for k in ("n_processes", "processing_size") if k in options})
        stripped, offset_map = _strip_markup(text)
        tagged_words = tag_text(stripped, pipeline=self._pipeline(config), config=config)
        return _tokens_with_offsets_regex(stripped, tagged_words, offset_map)


# ---------------------------------------------------------------------------
# Tokenizador simples (sem dependências): camada de formas para buscar sem tagger
# ---------------------------------------------------------------------------

class SimpleBackend(Backend):
    """Só formas e posições, com o tokenizador do pacote (corpus.tokenize).
    Permite KWIC, frequência e colocados antes de etiquetar."""
    name = "simple"
    defaults = {"contractions": "keep"}
    components = ("tokens",)
    default_components = ("tokens",)

    def tool_version(self) -> str:
        from ._version import __version__
        return __version__

    def model(self, options: dict) -> str:
        return "regex"

    def tag(self, text, options, components):
        from .corpus import _TOKEN_RE, _SPLIT_RE
        out = []
        sent = 0
        for m in _TOKEN_RE.finditer(text):
            word, start = m.group(), m.start()
            sm = _SPLIT_RE.match(word) if m.lastgroup == "word" and options.get("contractions") == "split" else None
            parts = [(sm.group("head"), start), (sm.group("clitic"), start + len(sm.group("head")))] if sm and sm.group("head") else [(word, start)]
            for w, s in parts:
                out.append({"start_char": s, "end_char": s + len(w), "word": w, "tags": [], "sent": sent})
            if m.lastgroup == "punct" and word in ".!?":
                sent += 1
        return out


BACKENDS: dict[str, Backend] = {b.name: b for b in (SpacyBackend(), StanzaBackend(), MfteBackend(),
                                                     BiberPlusBackend(), SimpleBackend())}


def get_backend(name: str) -> Backend:
    """Adaptador pelo nome ou por um atalho do descritor (spacy_upos → spacy, mfte_ext → mfte)."""
    if name not in BACKENDS:
        from .taggers.catalog import has_descriptor, resolve
        if has_descriptor(name):
            name = resolve(name)[0]
    try:
        return BACKENDS[name]
    except KeyError:
        raise ValueError(f"tagger desconhecido '{name}'; disponíveis: {', '.join(sorted(BACKENDS))}") from None


def register_backend(backend: Backend) -> None:
    """Registra um adaptador (usado em testes e por extensões)."""
    BACKENDS[backend.name] = backend
