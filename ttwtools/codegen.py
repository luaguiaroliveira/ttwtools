"""
codegen.py — O comando de linha de comando e o código Python equivalentes a uma
análise feita na interface ("copiar como código", novomodelo.md §15.2 item 10).

    cli_command("kwic", "projeto.ttwa", {"corpus": "c", "query": "cat", "context": 3})
    → "ttwtools kwic projeto.ttwa cat --corpus c --context 3"
    python_code("kwic", "projeto.ttwa", {...})
    → "import ttwtools\\nproj = ttwtools.open_project('projeto.ttwa')\\nresult = ttwtools.kwic(proj, 'c', 'cat', context=3)"

Só entram os parâmetros informados (os padrões do CLI e da função podem diferir,
então nada informado é omitido). Aspas no estilo POSIX
(macOS e Linux); no Windows (cmd/PowerShell) as aspas simples viram duplas.
"""

from __future__ import annotations

import json
import shlex
from typing import Any, Mapping

# análise → (subcomando, função Python, posicionais além do projeto, {param: (opção CLI, padrão)})
SPECS: dict[str, tuple[str, str, list[str], dict[str, tuple[str, Any]]]] = {
    "search": ("search", "search", ["corpus", "query"],
               {"layer": ("--layer", None), "group_by": ("--group-by", None)}),
    "kwic": ("kwic", "kwic", ["corpus", "query"],
             {"layer": ("--layer", None), "context": ("--context", 5), "limit": ("--limit", 50),
              "offset": ("--offset", 0), "sort": ("--sort", "position")}),
    "frequency": ("freq", "frequency", ["corpus"],
                  {"unit": ("--unit", "form"), "n": ("-n", 2), "by": ("--by", "corpus"), "layer": ("--layer", None),
                   "top": ("--top", 100)}),
    "collocates": ("collocates", "collocates", ["corpus", "node"],
                   {"left": ("--left", 5), "right": ("--right", 5), "unit": ("--unit", "form"),
                    "layer": ("--layer", None), "min_freq": ("--min-freq", 2), "top": ("--top", 50),
                    "sort": ("--sort", "ll")}),
    "dispersion": ("dispersion", "dispersion", ["corpus", "query"], {"layer": ("--layer", None)}),
    "describe": ("describe", "describe", ["corpus"],
                 {"layer": ("--layer", None), "top": ("--top", 20), "hide_stopwords": ("--hide-stopwords", False)}),
    "keywords": ("keywords", "keywords", ["corpus", "reference"],
                 {"unit": ("--unit", "form"), "measure": ("--measure", "ll"), "layer": ("--layer", None),
                  "min_freq": ("--min-freq", 5), "min_range": ("--min-range", 1),
                  "correction": ("--correction", "bonferroni"), "top": ("--top", 100)}),
    "kfa": ("compare", "kfa_layers", ["corpus", "corpus2", "layer"],
            {"feature": ("--feature", None), "metric": ("--metric", "kfa"), "min_effect": ("--min-effect", 0.0),
             "join": ("--join", "union")}),
    "tag": ("tag", "tag_corpus", ["corpus", "tagger"],
            {"preset": ("--preset", None), "options": ("--set", None), "components": ("--components", None),
             "force": ("--force", False)}),
}


def _check(analysis: str) -> tuple:
    if analysis not in SPECS:
        raise ValueError(f"análise desconhecida '{analysis}' (conhecidas: {', '.join(SPECS)})")
    return SPECS[analysis]


def cli_command(analysis: str, project_path: str, params: Mapping[str, Any], windows: bool = False) -> str:
    """Comando `ttwtools ...` equivalente."""
    sub, _fn, positional, options = _check(analysis)
    q = (lambda s: '"' + str(s).replace('"', '\\"') + '"' if any(c in str(s) for c in ' &|<>^"\'') else str(s)) \
        if windows else (lambda s: shlex.quote(str(s)))
    parts = ["ttwtools", sub, q(project_path)]
    for name in positional:
        if name == "corpus":
            continue
        if name == "node":
            parts.append(q(params["node"]))
        elif name in ("reference", "tagger", "corpus2", "layer"):
            continue
        else:
            parts.append(q(params[name]))
    parts += ["--corpus", q(params["corpus"])]
    if analysis == "keywords":
        parts += ["--reference", q(params["reference"])]
    if analysis == "tag":
        parts += ["--tagger", q(params["tagger"])]
    if analysis == "kfa":
        parts += ["--corpus2", q(params["corpus2"]), "--layer", q(params["layer"])]
    for name, (flag, _default) in options.items():
        value = params.get(name)
        if value is None:
            continue
        if isinstance(value, bool):
            if value:
                parts.append(flag)
        elif name == "options":
            for k, v in value.items():
                parts += [flag, q(f"{k}={json.dumps(v) if not isinstance(v, str) else v}")]
        elif name == "components":
            parts += [flag, q(",".join(value))]
        else:
            parts += [flag, q(value)]
    for key, values in (params.get("where") or {}).items():
        for v in ([values] if isinstance(values, str) else values):
            parts += ["--where", q(f"{key}={v}")]
    return " ".join(parts)


def python_code(analysis: str, project_path: str, params: Mapping[str, Any]) -> str:
    """Trecho Python equivalente, usando a API pública do pacote."""
    _sub, fn, positional, options = _check(analysis)
    args = [repr(params[name]) for name in positional]
    kwargs = []
    for name in options:
        value = params.get(name)
        if value is not None:
            if analysis == "collocates" and name in ("left", "right"):
                continue
            kwargs.append(f"{name}={value!r}")
    if analysis == "collocates" and ("left" in params or "right" in params):
        kwargs.append(f"window={(params.get('left', 5), params.get('right', 5))!r}")
    if params.get("where"):
        kwargs.append(f"where={dict(params['where'])!r}")
    call = ", ".join(["proj", *args, *kwargs])
    return "\n".join([
        "import ttwtools",
        "",
        f"proj = ttwtools.open_project({project_path!r})",
        f"result = ttwtools.{fn}({call})",
    ])
