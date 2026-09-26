"""
cli.py — Linha de comando `ttwtools`.

Cada recurso do pacote tem uma função pública e um subcomando aqui (princípio
de paridade com o aplicativo). Os subcomandos imprimem o resultado como tabela
legível (padrão), `--json` ou `--csv`, sempre pela função `emit`.

Só a biblioteca padrão é usada aqui; os módulos pesados (spaCy, pandas, torch)
são importados dentro de cada subcomando.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from typing import Any, Callable, Iterable, Sequence

from ._version import __version__

# Códigos de saída
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_IMPLEMENTED = 3


# ---------------------------------------------------------------------------
# Saída padronizada
# ---------------------------------------------------------------------------

def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def format_table(rows: Sequence[dict], columns: Sequence[str] | None = None) -> str:
    """Tabela de texto alinhada; números à direita."""
    if not rows:
        return "(nenhum resultado)"
    columns = list(columns or rows[0].keys())
    cells = [[_cell(r.get(c)) for c in columns] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(columns)]
    numeric = [all(isinstance(r.get(c), (int, float)) or r.get(c) is None for r in rows) for c in columns]

    def fmt(values):
        return "  ".join(v.rjust(w) if num else v.ljust(w) for v, w, num in zip(values, widths, numeric)).rstrip()

    lines = [fmt(columns), "  ".join("-" * w for w in widths)]
    lines += [fmt(row) for row in cells]
    return "\n".join(lines)


def format_csv(rows: Sequence[dict], columns: Sequence[str] | None = None) -> str:
    buf = io.StringIO()
    columns = list(columns or (rows[0].keys() if rows else []))
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                         for c, v in r.items()})
    return buf.getvalue().rstrip("\n")


def emit(result: Any, fmt: str = "table", columns: Sequence[str] | None = None, file=None) -> None:
    """Imprime um resultado no formato pedido.

    `result` pode ser uma lista de dicionários (tabela), um dicionário (vira
    tabela de duas colunas `campo`/`valor`) ou um texto.
    """
    file = file or sys.stdout
    if fmt == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str), file=file)
        return
    if isinstance(result, str):
        print(result, file=file)
        return
    if isinstance(result, dict):
        rows, columns = [{"campo": k, "valor": v} for k, v in result.items()], ["campo", "valor"]
    else:
        rows = list(result)
    print(format_csv(rows, columns) if fmt == "csv" else format_table(rows, columns), file=file)


# ---------------------------------------------------------------------------
# Subcomandos
# ---------------------------------------------------------------------------

# nome → (descrição, passo do plano que o implementa)
COMMANDS: dict[str, tuple[str, str]] = {
    "describe":       ("Estatísticas e descrição de um corpus", "1.7"),
    "tag":            ("Etiqueta um corpus com um tagger", "1.4/1.5"),
    "tagger-options": ("Lista os taggers disponíveis e suas opções", "1.5"),
    "tagset":         ("Mostra o tagset de um tagger", "1.5"),
    "kwic":           ("Concordância (palavra-chave em contexto)", "1.8"),
    "freq":           ("Listas de frequência", "1.8"),
    "keywords":       ("Palavras-chave contra um corpus de referência", "1.9"),
    "compare":        ("Compara corpora (KFA e afins)", "1.7/1.9"),
    "help":           ("Ajuda sobre conceitos e ferramentas", "1.10"),
}


def _not_implemented(name: str) -> Callable[[argparse.Namespace], int]:
    def handler(args: argparse.Namespace) -> int:
        step = COMMANDS[name][1]
        result = {"command": name, "status": "not_implemented",
                  "message": f"'{name}' ainda não implementado (passo {step} do plano)"}
        if args.format == "table":
            print(result["message"], file=sys.stderr)
        else:
            emit(result, args.format)
        return EXIT_NOT_IMPLEMENTED
    return handler


# ---------------------------------------------------------------------------
# Subcomandos implementados
# ---------------------------------------------------------------------------

def _open_or_create(path: str, create: bool):
    from .project import TTWAProject
    from pathlib import Path
    p = Path(path)
    if p.exists():
        return TTWAProject.open(p)
    if not create:
        raise SystemExit(f"ttwtools: projeto não encontrado: {p}")
    return TTWAProject.create(p)


def _cmd_import(args: argparse.Namespace) -> int:
    from .corpus import TokenizerConfig, import_corpus
    text = sys.stdin.read() if args.source == "-" else None
    tokenizer = None
    if any(v is not None for v in (args.lowercase, args.keep_punct, args.no_numbers, args.contractions)):
        tokenizer = TokenizerConfig(lowercase=bool(args.lowercase), keep_punct=bool(args.keep_punct),
                                    keep_numbers=not args.no_numbers, contractions=args.contractions or "keep")
    with _open_or_create(args.project, create=True) as proj:
        report = import_corpus(
            proj, None if text is not None else args.source, args.name, text=text,
            filename_fields=args.fields.split(",") if args.fields else None, delimiter=args.delimiter,
            metadata_csv=args.meta_csv, text_column=args.text_column, tokenizer=tokenizer,
        )
    report.pop("files")
    emit(report, args.format)
    return EXIT_OK


def _cmd_documents(args: argparse.Namespace) -> int:
    from .corpus import filter_documents, parse_where
    with _open_or_create(args.project, create=False) as proj:
        docs = filter_documents(proj, args.corpus, parse_where(args.where or []))
    keys = sorted({k for d in docs for k in d["meta"]})
    rows = [{"corpus": d["corpus_name"], "arquivo": d["filename"], "caracteres": d["n_chars"],
             **{k: d["meta"].get(k) for k in keys}} for d in docs]
    emit(rows, args.format, columns=["corpus", "arquivo", "caracteres", *keys])
    return EXIT_OK


def _configure_import(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", help="arquivo .ttwa ou .ttwl (criado se não existir)")
    p.add_argument("source", help="pasta de .txt, arquivo .txt, .csv com coluna de texto, ou - (texto pela entrada padrão)")
    p.add_argument("--name", required=True, help="nome do corpus no projeto")
    p.add_argument("--fields", help="campos no nome do arquivo, separados por vírgula (ex.: grupo,texto)")
    p.add_argument("--delimiter", default="_", help="delimitador dos campos no nome do arquivo (padrão: _)")
    p.add_argument("--meta-csv", help="CSV de metadados com a coluna filename")
    p.add_argument("--text-column", default="text", help="coluna de texto quando a origem é um CSV")
    tok = p.add_argument_group("tokenização simples (estatísticas antes de etiquetar)")
    tok.add_argument("--lowercase", action="store_const", const=True, help="minúsculas")
    tok.add_argument("--keep-punct", action="store_const", const=True, help="manter pontuação")
    tok.add_argument("--no-numbers", action="store_const", const=True, help="remover números")
    tok.add_argument("--contractions", choices=["keep", "split"], help="contrações: manter ou separar")


def _configure_documents(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", help="arquivo .ttwa ou .ttwl")
    p.add_argument("--corpus", help="só este corpus")
    p.add_argument("--where", action="append", metavar="CHAVE=VALOR",
                   help="filtro por metadado; repita para OU na mesma chave e E entre chaves")


# nome → (descrição, configuração dos argumentos, função)
IMPLEMENTED: dict[str, tuple[str, Callable, Callable[[argparse.Namespace], int]]] = {
    "import":    ("Importa textos para um corpus do projeto (pasta, .txt, CSV ou texto colado)",
                  _configure_import, _cmd_import),
    "documents": ("Lista documentos e metadados, com filtro por metadado",
                  _configure_documents, _cmd_documents),
}


def _add_output_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", dest="format", action="store_const", const="json",
                       help="saída em JSON")
    group.add_argument("--csv", dest="format", action="store_const", const="csv",
                       help="saída em CSV")
    parser.set_defaults(format="table")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ttwtools",
        description="Ferramentas de análise de corpus do TTWtools (mesmos recursos do aplicativo).",
    )
    parser.add_argument("--version", action="version", version=f"ttwtools {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<comando>")
    for name, (description, configure, handler) in IMPLEMENTED.items():
        p = sub.add_parser(name, help=description, description=description)
        configure(p)
        _add_output_flags(p)
        p.set_defaults(handler=handler)
    for name, (description, _step) in COMMANDS.items():
        p = sub.add_parser(name, help=description, description=description)
        _add_output_flags(p)
        p.set_defaults(handler=_not_implemented(name))
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(None if argv is None else list(argv))
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_OK
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
