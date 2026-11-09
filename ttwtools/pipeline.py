"""
pipeline.py — Lista "a executar" de cada corpus: camadas escolhidas agora e calculadas depois.

A pessoa monta a lista com as camadas que quer acrescentar ao corpus (estatísticas
básicas e etiquetagens, cada uma com as suas opções) e executa tudo numa etapa só,
"análise e etiquetagem do corpus". A lista fica guardada no projeto, então dá para
voltar e ampliá-la a qualquer momento; o que já existe não é refeito (as etiquetagens
passam por `tag_corpus`, que reaproveita camadas equivalentes).

Passos:
    {"kind": "tag", "tagger": "spacy", "options": {...}}   uma camada de etiquetas
    {"kind": "stats"}                                      estatísticas básicas do texto
                                                           e de cada camada (sempre por último)
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from .project import TTWAProject

_KEY = "pipeline.{corpus}"


def _key(corpus_name: str) -> str:
    return _KEY.format(corpus=corpus_name)


def _normalize(step: Mapping[str, Any]) -> dict:
    kind = step.get("kind")
    if kind == "stats":
        return {"kind": "stats"}
    if kind == "tag":
        if not step.get("tagger"):
            raise ValueError("passo 'tag' precisa de 'tagger'")
        from .annotate import build_request
        options = dict(step.get("options") or {})
        build_request(step["tagger"], options, step.get("components"), step.get("preset"))   # valida já
        out = {"kind": "tag", "tagger": step["tagger"], "options": options}
        for k in ("components", "preset"):
            if step.get(k):
                out[k] = step[k]
        return out
    raise ValueError(f"tipo de passo desconhecido: {kind!r} (use 'tag' ou 'stats')")


def pending_steps(project: TTWAProject, corpus_name: str) -> list[dict]:
    """Passos guardados na lista "a executar" do corpus, na ordem em que rodam (`stats` no fim)."""
    raw = project.get_meta(_key(corpus_name))
    if not raw:
        return []
    return json.loads(raw) if isinstance(raw, str) else list(raw)


def _save(project: TTWAProject, corpus_name: str, steps: list[dict]) -> list[dict]:
    project.set_meta(_key(corpus_name), json.dumps(steps, ensure_ascii=False))
    return steps


def add_step(project: TTWAProject, corpus_name: str, step: Mapping[str, Any]) -> list[dict]:
    """Acrescenta um passo à lista (validado; passo idêntico não entra duas vezes). Devolve a lista."""
    if corpus_name not in {c["name"] for c in _corpora(project)}:
        raise ValueError(f"corpus '{corpus_name}' não existe no projeto")
    new = _normalize(step)
    steps = pending_steps(project, corpus_name)
    if new not in steps:
        steps.append(new)
    return _save(project, corpus_name, _ordered(steps))      # guardada na ordem em que roda


def remove_step(project: TTWAProject, corpus_name: str, index: int) -> list[dict]:
    """Tira o passo `index` (0 = primeiro) da lista. Devolve a lista."""
    steps = pending_steps(project, corpus_name)
    if not 0 <= index < len(steps):
        raise ValueError(f"não há passo {index} na lista (tem {len(steps)})")
    steps.pop(index)
    return _save(project, corpus_name, steps)


def clear_steps(project: TTWAProject, corpus_name: str) -> None:
    """Esvazia a lista "a executar" do corpus."""
    _save(project, corpus_name, [])


def _corpora(project: TTWAProject) -> list[dict]:
    from .corpus import list_corpora
    return list_corpora(project)


def _names(project: TTWAProject, corpora: list[str] | None = None) -> list[str]:
    """Nomes dos corpora do projeto (ou só os indicados, sem repetir e na ordem dada)."""
    names = [c["name"] for c in _corpora(project)]
    if corpora is None:
        return names
    unknown = [c for c in corpora if c not in names]
    if unknown:
        raise ValueError(f"corpus não existe no projeto: {', '.join(unknown)}")
    return list(dict.fromkeys(corpora))


def pending_steps_all(project: TTWAProject, corpora: list[str] | None = None) -> dict[str, list[dict]]:
    """Listas "a executar" de todos os corpora que têm passos: {corpus: passos}, na ordem do projeto."""
    out = {}
    for name in _names(project, corpora):
        steps = pending_steps(project, name)
        if steps:
            out[name] = steps
    return out


def add_step_all(project: TTWAProject, step: Mapping[str, Any],
                 corpora: list[str] | None = None) -> dict[str, list[dict]]:
    """Acrescenta o mesmo passo à lista de cada corpus (todos, se `corpora` for None). Devolve {corpus: passos}."""
    names = _names(project, corpora)
    _normalize(step)                                     # valida uma vez, antes de tocar no projeto
    return {name: add_step(project, name, step) for name in names}


def _ordered(steps: list[dict]) -> list[dict]:
    return [s for s in steps if s["kind"] != "stats"] + [s for s in steps if s["kind"] == "stats"]


def run_steps(project: TTWAProject, corpus_name: str,
              progress: Callable[[int, int, str], None] | None = None,
              on_step: Callable[[int, dict], None] | None = None) -> dict:
    """Executa a lista do corpus: etiquetagens na ordem e, por último, as estatísticas básicas.

    `progress(passo, total_de_passos, mensagem)` dá o andamento geral; `on_step(i, estado)`
    dá o de cada passo, com estado = {"status": "running"|"done"|"error", "done", "total",
    "item"} (feitos/total dentro do passo e o texto atual). Cada passo concluído sai da
    lista (se um falhar, ele e os seguintes continuam guardados).
    Devolve {"done": [{"step", "report"}], "remaining": [...]}.
    """
    from .annotate import tag_corpus
    from .corpus import layer_summary
    from .stats import describe

    steps = _ordered(pending_steps(project, corpus_name))
    done = []

    def tell(i, **state):
        if on_step:
            on_step(i, state)

    for i, step in enumerate(steps):
        label = step.get("tagger", "stats")
        if progress:
            progress(i, len(steps), label)
        tell(i, status="running", done=0, total=None, item=None)
        try:
            if step["kind"] == "tag":
                def sub(d, t, f, i=i):
                    tell(i, status="running", done=d, total=t, item=f)
                    if progress:
                        progress(i, len(steps), f"{label}: {f} ({d}/{t})")
                report = tag_corpus(project, corpus_name, step["tagger"], step.get("options"),
                                    components=step.get("components"), preset=step.get("preset"), progress=sub)
                report = {k: v for k, v in report.items() if k != "layer_ids"}
            else:
                layers = [None] + sorted({layer["tool"] for layer in layer_summary(project, corpus_name)})
                jobs = [(layer, hide) for layer in layers for hide in (False, True)]
                for n, (layer, hide) in enumerate(jobs):
                    tell(i, status="running", done=n, total=len(jobs), item=layer or "texto")
                    if progress:
                        progress(i, len(steps), f"stats: {layer or 'texto'}")
                    describe(project, corpus_name, layer=layer, hide_stopwords=hide)
                report = {"layers": [layer or "texto" for layer in layers]}
        except BaseException:
            tell(i, status="error", done=None, total=None, item=None)
            raise
        done.append({"step": step, "report": report})
        _save(project, corpus_name, [s for s in pending_steps(project, corpus_name) if s != step])
        tell(i, status="done", done=1, total=1, item=None)
    if progress:
        progress(len(steps), len(steps), "ok")
    return {"done": done, "remaining": pending_steps(project, corpus_name)}


def run_all(project: TTWAProject, corpora: list[str] | None = None,
            progress: Callable[[int, int, str], None] | None = None,
            on_step: Callable[[int, dict], None] | None = None) -> dict:
    """Executa as listas dos corpora em sequência, numa etapa só.

    Os passos de todos os corpora formam uma fila única: `on_step(i, estado)` recebe o
    índice global (`i`) e o estado de cada passo com o campo extra `"corpus"`;
    `progress(feitos, total, mensagem)` conta os passos de todos os corpora e prefixa a
    mensagem com o corpus em execução. Devolve {"done": [{"corpus", "step", "report"}],
    "remaining": {corpus: passos}}.
    """
    queues = pending_steps_all(project, corpora)
    total = sum(len(_ordered(steps)) for steps in queues.values())
    done = []
    remaining = {}
    base = 0                                             # passos já executados nos corpora anteriores
    for name in queues:
        steps = _ordered(pending_steps(project, name))   # a mesma ordem que run_steps vai executar
        if not steps:
            continue

        def on_local(i, state, base=base, name=name):
            if on_step:
                on_step(base + i, {**state, "corpus": name})

        def tell(d, t, msg, base=base, name=name):
            if progress:
                progress(base + d, total, f"{name}: {msg}")

        r = run_steps(project, name, progress=tell, on_step=on_local)
        done.extend({**d, "corpus": name} for d in r["done"])
        if r["remaining"]:
            remaining[name] = r["remaining"]
        base += len(steps)
    return {"done": done, "remaining": remaining}
