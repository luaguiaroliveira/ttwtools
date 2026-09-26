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
                  components: Iterable[str] | None = None) -> dict:
    """Normaliza um pedido: opções padrão por extenso, componentes e versões.

    Devolve {"tool", "tool_version", "model", "config", "performance"}; `config`
    é a configuração efetiva que identifica a camada (sem as opções de desempenho).
    """
    backend = get_backend(tagger)
    options = dict(options or {})
    performance = {k: options.pop(k) for k in list(options) if k in _layers.PERFORMANCE_KEYS}
    unknown = sorted(set(options) - set(backend.defaults))
    if unknown:
        raise ValueError(f"opções desconhecidas para '{tagger}': {', '.join(unknown)} "
                         f"(aceitas: {', '.join(sorted(backend.defaults))})")
    effective = {**backend.defaults, **options}
    comps = sorted(set(components or backend.default_components))
    bad = sorted(set(comps) - set(backend.components))
    if bad:
        raise ValueError(f"componentes indisponíveis em '{tagger}': {', '.join(bad)} "
                         f"(disponíveis: {', '.join(backend.components)})")
    config = {**effective, "components": comps, "model_version": backend.model_version(effective)}
    return {"tool": backend.name, "tool_version": backend.tool_version(), "model": backend.model(effective),
            "config": config, "performance": performance}


def _candidates(project: TTWAProject, request: dict, where_sql: str, args: tuple) -> list:
    return project._con.execute(
        "SELECT id, doc_id, config FROM layers WHERE tool = ? AND tool_version = ? AND model = ? AND " + where_sql,
        (request["tool"], request["tool_version"], request["model"], *args),
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
) -> dict:
    """Etiqueta os documentos do corpus que ainda não têm camada suficiente.

    where    — filtro por metadado (ver corpus.filter_documents)
    force    — etiqueta de novo mesmo havendo camada
    progress — progress(feitos, total, arquivo)

    Devolve {"corpus", "tool", "documents", "tagged", "reused", "cloned",
    "missing_text", "layer_ids"}.
    """
    request = build_request(tagger, options, components)
    backend = get_backend(tagger)
    run_options = {**request["config"], **request["performance"]}
    run_options.pop("components")
    run_options.pop("model_version")
    comps = tuple(request["config"]["components"])

    docs = filter_documents(project, corpus_name, where)
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
                tokens = backend.tag(text, run_options, comps)
                layer_id = project.save_layer(doc["id"], request["tool"], request["tool_version"], request["model"],
                                              request["config"], tokens, text_hash=_layers.text_hash(text))
                report["tagged"] += 1
            project._con.commit()       # um documento por vez: permite retomar
            report["layer_ids"].append(layer_id)
        if progress:
            progress(i, len(docs), doc["filename"])
    return report
