"""
annotate.py — Etiquetar corpus com cache de camadas (novomodelo.md §9.4 e §11.4).

    tag_corpus(projeto, "corpus", "spacy")                    # etiqueta o que falta
    tag_corpus(projeto, "corpus", "spacy", components=["pos"])  # atendido por camada com pos+lemma
    tag_corpus(projeto, "corpus", "mfte", {"extended": False})  # opção que muda o resultado: nova camada

Antes de etiquetar um documento procura-se uma camada suficiente: mesma
ferramenta, versão e modelo, mesmas opções que mudam o resultado e componentes
iguais ou a mais, sobre o mesmo texto (hash). Se outro documento tem o mesmo
texto e uma camada suficiente, ela é copiada. Cada documento é gravado ao
terminar, então uma execução interrompida continua de onde parou.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable, Mapping

from . import layers as _layers
from .backends import get_backend
from .corpus import filter_documents
from .project import TTWAProject


def build_request(tagger: str, options: Mapping[str, Any] | None = None,
                  components: Iterable[str] | None = None, preset: str | None = None) -> dict:
    """Normaliza um pedido: opções padrão por extenso, componentes e versões.

    tagger  — nome ou atalho (spacy, spacy_upos, stanza_xpos, mfte_ext, biberplus...)
    options — dicionário único de opções, validado contra o descritor do tagger
              (data/taggers/<tagger>.options.json); `components` pode vir aqui ou à parte
    preset  — "rapido", "recomendado" ou "preciso": preenche opções (as explícitas vencem)

    Devolve {"tool", "tool_version", "model", "config", "performance"}; `config`
    é a configuração efetiva que identifica a camada (sem as opções de desempenho).
    """
    from .taggers import catalog
    options = dict(options or {})
    if catalog.has_descriptor(tagger):
        name, info = catalog.resolve(tagger)
        backend = get_backend(name)
        merged = {**(catalog.preset(name, preset) if preset else {}), **info.get("options", {}), **options}
        if components is not None:
            merged["components"] = list(components)
        catalog.validate_options(name, merged)
        perf_keys = catalog.performance_keys(name)
        performance = {k: merged.pop(k) for k in list(merged) if k in perf_keys}
        comps = sorted(set(merged.pop("components", None) or catalog.default_components(name)))
        effective = {**catalog.result_defaults(name), **merged}
    else:  # adaptadores sem descritor (testes, extensões): validação mínima
        if preset:
            raise ValueError(f"'{tagger}' não tem predefinições")
        backend = get_backend(tagger)
        performance = {k: options.pop(k) for k in list(options) if k in _layers.PERFORMANCE_KEYS}
        unknown = sorted(set(options) - set(backend.defaults) - {"components"})
        if unknown:
            raise ValueError(f"opções desconhecidas para '{tagger}': {', '.join(unknown)} "
                             f"(aceitas: {', '.join(sorted(backend.defaults))})")
        comps = sorted(set(components or options.pop("components", None) or backend.default_components))
        effective = {**backend.defaults, **options}
        bad = sorted(set(comps) - set(backend.components))
        if bad:
            raise ValueError(f"componentes indisponíveis em '{tagger}': {', '.join(bad)} "
                             f"(disponíveis: {', '.join(backend.components)})")
    config = {**effective, "components": comps, "model_version": backend.model_version(effective)}
    # `tool` identifica a camada: o modo do MFTE (usual/extendido) muda o nome (mfte/mfte_ext),
    # para as duas camadas conviverem no projeto e na interface.
    tool = catalog.layer_tool(tagger, effective) if catalog.has_descriptor(tagger) else backend.name
    return {"tool": tool, "tool_version": backend.tool_version(), "model": backend.model(effective),
            "config": config, "performance": performance}


def _tool_names(tool: str) -> list[str]:
    """Nomes aceitos em `layers.tool` para um pedido: o próprio e, se for atalho, a ferramenta base
    (projetos antigos guardavam o MFTE estendido como `mfte`; a camada continua valendo)."""
    from .taggers import catalog
    names = [tool]
    if catalog.has_descriptor(tool):
        base, _ = catalog.resolve(tool)
        if base != tool:
            names.append(base)
    return names


def _candidates(project: TTWAProject, request: dict, where_sql: str, args: tuple) -> list:
    tools = _tool_names(request["tool"])
    marks = ",".join("?" * len(tools))
    return project._con.execute(
        f"SELECT id, doc_id, config FROM layers WHERE tool IN ({marks}) AND tool_version = ? AND model = ? AND "
        + where_sql,
        (*tools, request["tool_version"], request["model"], *args),
    ).fetchall()


def find_layer(project: TTWAProject, doc: Mapping[str, Any], request: dict) -> dict | None:
    """Camada do documento que atende o pedido (ou None).

    `doc` é um dicionário com `id` e `content_hash` (como os de `filter_documents`).
    Uma camada feita sobre um texto que depois mudou não serve."""
    if doc.get("content_hash"):
        rows = _candidates(project, request, "doc_id = ? AND text_hash = ?", (doc["id"], doc["content_hash"]))
    else:
        rows = _candidates(project, request, "doc_id = ?", (doc["id"],))
    for row in rows:
        if _layers.layer_satisfies(json.loads(row["config"]), request["config"]):
            return {"id": row["id"], "doc_id": row["doc_id"]}
    return None


def _find_same_text(project: TTWAProject, text_hash: str, request: dict) -> dict | None:
    for row in _candidates(project, request, "text_hash = ?", (text_hash,)):
        if _layers.layer_satisfies(json.loads(row["config"]), request["config"]):
            return {"id": row["id"], "doc_id": row["doc_id"]}
    return None


def tag_corpus(
    project: TTWAProject,
    corpus_name: str,
    tagger: str,
    options: Mapping[str, Any] | None = None,
    components: Iterable[str] | None = None,
    where: Mapping[str, Any] | None = None,
    force: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
    preset: str | None = None,
    filenames: Iterable[str] | None = None,
) -> dict:
    """Etiqueta os documentos do corpus que ainda não têm camada suficiente.

    filenames — só estes documentos (além do filtro `where`)

    tagger/options/components/preset — ver build_request

    where    — filtro por metadado (ver corpus.filter_documents)
    force    — etiqueta de novo mesmo havendo camada
    progress — progress(feitos, total, arquivo)

    Devolve {"corpus", "tool", "documents", "tagged", "reused", "cloned",
    "missing_text", "layer_ids"}.
    """
    request = build_request(tagger, options, components, preset)
    backend = get_backend(request["tool"])
    run_options = {**request["config"], **request["performance"]}
    run_options.pop("components")
    run_options.pop("model_version")
    comps = tuple(request["config"]["components"])

    docs = filter_documents(project, corpus_name, where)
    if filenames is not None:
        wanted = set(filenames)
        docs = [d for d in docs if d["filename"] in wanted]
    report = {"corpus": corpus_name, "tool": request["tool"], "documents": len(docs), "tagged": 0,
              "reused": 0, "cloned": 0, "missing_text": [], "layer_ids": []}
    for i, doc in enumerate(docs, 1):
        found = None if force else find_layer(project, doc, request)
        if found:
            report["reused"] += 1
            report["layer_ids"].append(found["id"])
        else:
            same = None if force or not doc["content_hash"] else _find_same_text(project, doc["content_hash"], request)
            if same:
                layer_id = project.clone_layer(same["id"], doc["id"])
                report["cloned"] += 1
            else:
                text = project.get_corpus_file(doc["corpus_name"], doc["filename"])
                if text is None:
                    report["missing_text"].append(doc["filename"])
                    if progress:
                        progress(i, len(docs), doc["filename"])
                    continue
                try:
                    tokens = backend.tag(text, run_options, comps)
                except ImportError as exc:
                    from .taggers.catalog import TaggerUnavailable
                    raise TaggerUnavailable(request["tool"], f"{type(exc).__name__}: {exc}") from exc
                layer_id = project.save_layer(doc["id"], request["tool"], request["tool_version"], request["model"],
                                              request["config"], tokens, text_hash=_layers.text_hash(text))
                report["tagged"] += 1
            project._con.commit()       # um documento por vez: permite retomar
            report["layer_ids"].append(layer_id)
        if progress:
            progress(i, len(docs), doc["filename"])
    return report


def plan_tagging(
    project: TTWAProject,
    corpus_name: str,
    tagger: str,
    options: Mapping[str, Any] | None = None,
    components: Iterable[str] | None = None,
    where: Mapping[str, Any] | None = None,
    preset: str | None = None,
) -> dict:
    """O que `tag_corpus` faria, sem etiquetar: quantos documentos já têm camada
    suficiente (`reusable`), quantos podem copiar de outro com o mesmo texto
    (`clonable`), quantos serão processados (`to_tag`) e quantos estão sem texto."""
    request = build_request(tagger, options, components, preset)
    docs = filter_documents(project, corpus_name, where)
    out = {"documents": len(docs), "reusable": 0, "clonable": 0, "to_tag": 0, "missing_text": 0,
           "tool": request["tool"], "config": request["config"]}
    for doc in docs:
        if find_layer(project, doc, request):
            out["reusable"] += 1
        elif doc["content_hash"] and _find_same_text(project, doc["content_hash"], request):
            out["clonable"] += 1
        elif doc["content_hash"] is None and not project.is_light:
            out["missing_text"] += 1
        else:
            out["to_tag"] += 1
    return out
