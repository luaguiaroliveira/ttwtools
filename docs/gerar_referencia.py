"""
gerar_referencia.py — Gera docs/referencia.md a partir das docstrings do pacote.

    python docs/gerar_referencia.py            # reescreve docs/referencia.md
    python docs/gerar_referencia.py --check    # sai com 1 se o arquivo estiver desatualizado

Inclui os nomes de `ttwtools.<nome>` (tabela _EXPORTS do __init__) e as funções
públicas dos módulos listados em MODULES (as definidas no próprio módulo).
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

import ttwtools

OUT = Path(__file__).with_name("referencia.md")

# módulo → título; funções públicas definidas nele entram na referência
MODULES = {
    "project": "Projetos (.ttwa, .ttwl, .ttwt)",
    "corpus": "Corpora, documentos e metadados",
    "annotate": "Etiquetagem com cache de camadas",
    "taggers.catalog": "Taggers: opções, tagsets e disponibilidade",
    "formats": "Formatos de entrada e saída",
    "query": "Consultas: busca, KWIC, frequência, colocados, dispersão",
    "stats": "Estatísticas do corpus",
    "keyness": "Palavras-chave, listas de referência e faixas de frequência",
    "features": "Tabelas de traços e KFA a partir das camadas",
    "viz": "Dados para gráficos de comparação",
    "experimental": "Laboratório: N grupos (experimental)",
    "corpus_catalog": "Catálogo de corpora",
    "models": "Modelos sob demanda",
    "analysis": "KFA e d de Cohen (API clássica)",
    "help": "Ajuda e tours",
    "i18n": "Traduções",
    "codegen": "Código equivalente (linha de comando e Python)",
}


def _public(mod) -> list[tuple[str, object]]:
    names = getattr(mod, "__all__", None) or [n for n in vars(mod) if not n.startswith("_")]
    out = []
    for name in names:
        obj = getattr(mod, name, None)
        if not (inspect.isfunction(obj) or inspect.isclass(obj)):
            continue
        if not hasattr(mod, "__all__") and getattr(obj, "__module__", None) != mod.__name__:
            continue
        out.append((name, obj))
    return sorted(out, key=lambda x: x[0].lower())


def _signature(obj) -> str:
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return "(...)"


def _doc(obj) -> str:
    doc = inspect.getdoc(obj) or "*(sem descrição)*"
    return doc.strip()


def build() -> str:
    lines = ["# Referência da API do `ttwtools`", "",
             f"Gerada de `docs/gerar_referencia.py` para a versão {ttwtools.__version__}. Não edite à mão.", "",
             "Funções marcadas com **`ttwtools.nome`** podem ser usadas direto do pacote (`import ttwtools`).",
             "As demais ficam no módulo indicado (ex.: `from ttwtools.experimental import compare_groups`).", ""]
    top = {name for name, mod in ttwtools._EXPORTS.items()}
    lines.append("## Sumário")
    lines.append("")
    for mod_name, title in MODULES.items():
        lines.append(f"- [{title}](#{mod_name.replace('.', '')}) — `ttwtools.{mod_name}`")
    lines.append("")
    documented: set[str] = set()
    for mod_name, title in MODULES.items():
        try:
            mod = importlib.import_module(f"ttwtools.{mod_name}")
        except Exception as exc:   # dependência opcional ausente
            lines += [f'<a id="{mod_name.replace(".", "")}"></a>', f"## {title}", "",
                      f"*Módulo `ttwtools.{mod_name}` indisponível neste ambiente ({type(exc).__name__}).*", ""]
            continue
        lines += [f'<a id="{mod_name.replace(".", "")}"></a>', f"## {title}", "", f"Módulo `ttwtools.{mod_name}`.", ""]
        head = (inspect.getdoc(mod) or "").split("\n\n")[0].strip()
        if head:
            lines += [head, ""]
        for name, obj in _public(mod):
            marker = f" · **`ttwtools.{name}`**" if name in top else ""
            kind = "classe " if inspect.isclass(obj) else ""
            lines += [f"### `{name}`{marker}", "", f"```python\n{kind}{name}{_signature(obj)}\n```", "", _doc(obj), ""]
            documented.add(name)
    missing = sorted(top - documented)
    if missing:
        lines += ["## Outros nomes de `ttwtools`", "",
                  "Taggers da API clássica e utilitários exportados no nível do pacote.", ""]
        for name in missing:
            try:
                obj = getattr(ttwtools, name)
            except Exception as exc:
                lines += [f"### `{name}`", "", f"*Indisponível neste ambiente ({type(exc).__name__}).*", ""]
                continue
            sig = _signature(obj) if callable(obj) else ""
            lines += [f"### `{name}` · **`ttwtools.{name}`**", "", f"```python\n{name}{sig}\n```", "", _doc(obj), ""]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    text = build()
    if "--check" in argv:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            print("docs/referencia.md desatualizado: rode python docs/gerar_referencia.py")
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"ok: {OUT} ({text.count(chr(10))} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
