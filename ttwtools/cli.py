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
from pathlib import Path
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
    p = Path(path).expanduser()
    if p.exists():
        return TTWAProject.open(p)
    if not create:
        raise SystemExit(f"ttwtools: projeto não encontrado: {p}")
    return TTWAProject.create(p)


def _import_format(args: argparse.Namespace) -> str:
    from pathlib import Path
    if args.format_in != "auto":
        return args.format_in
    suffix = Path(args.source).suffix.lower()
    if suffix in (".anc", ".hdr"):
        return "graf"
    if suffix == ".xml":
        return "tei"
    return {".conllu": "conllu", ".conll": "conllu"}.get(suffix, "txt")


def _cmd_compact(args: argparse.Namespace) -> int:
    from .project import compact_project
    with _open_or_create(args.project, create=False) as proj:
        report = compact_project(proj, dry_run=args.dry_run,
                                 progress=None if args.format != "table" else
                                 lambda d, t, s: print(f"\r  {s}: {d}/{t}", end="", file=sys.stderr))
        if args.format == "table":
            print(file=sys.stderr)
        if not args.dry_run and proj.is_working_copy and report["n_removed"]:
            proj.save()             # arquivo compactado (.ttwt): grava a cópia de trabalho de volta
    out = {"simulação": args.dry_run, "removidos": report["n_removed"], "mantidos": report["n_kept"],
           "mb_liberados": round(report["bytes_freed"] / 1e6, 1)}
    if "size_after" in report:
        out["tamanho_antes_mb"] = round(report["size_before"] / 1e6, 1)
        out["tamanho_depois_mb"] = round(report["size_after"] / 1e6, 1)
    if report["kept"]:
        out["motivos"] = {r: sum(1 for k in report["kept"] if k["reason"] == r) for r in sorted({k["reason"] for k in report["kept"]})}
    emit(out, args.format)
    return EXIT_OK


def _configure_compact(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", help="arquivo .ttwa, .ttwl ou .ttwt")
    p.add_argument("--dry-run", action="store_true", help="só mostra o que seria removido, sem alterar o arquivo")


def _cmd_import(args: argparse.Namespace) -> int:
    from .corpus import TokenizerConfig, import_corpus
    fmt = _import_format(args) if args.source != "-" else "txt"
    if fmt in ("conllu", "nltk", "tei", "graf"):
        from .formats import import_conllu, import_graf, import_nltk_tagged, import_tei
        with _open_or_create(args.project, create=True) as proj:
            if fmt == "conllu":
                report = import_conllu(proj, args.source, args.name)
            elif fmt == "tei":
                report = import_tei(proj, args.source, args.name)
            elif fmt == "graf":
                report = import_graf(proj, args.source, args.name)
            else:
                report = import_nltk_tagged(proj, args.source, args.name, tagset=args.tagset or "")
        report.pop("files")
        emit(report, args.format)
        return EXIT_OK
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


def _cmd_names(args: argparse.Namespace) -> int:
    from .corpus import preview_filenames
    fields = args.fields.split(",") if args.fields else None
    pv = preview_filenames(args.folder, args.delimiter, fields, n=args.n)
    rows = [{"arquivo": e["file"], **({k: v for k, v in e["meta"].items()} if fields else
                                       {f"pedaço {i + 1}": v for i, v in enumerate(e["parts"])})}
            for e in pv["examples"]]
    emit(rows, args.format)
    if pv["n_irregular"]:
        print(f"aviso: {pv['n_irregular']} de {pv['total']} nomes não têm {pv['parts']} pedaços "
              f"(ex.: {', '.join(pv['irregular'])})", file=sys.stderr)
    return EXIT_OK


def _configure_names(p: argparse.ArgumentParser) -> None:
    p.add_argument("folder", help="pasta com os .txt")
    p.add_argument("--delimiter", default="_", help="separador dos pedaços do nome (padrão: _)")
    p.add_argument("--fields", help="nomes dos pedaços, separados por vírgula; vazio pula o pedaço (ex.: aluno,,ano)")
    p.add_argument("-n", type=int, default=5, help="quantos arquivos mostrar")


def _cmd_save_as(args: argparse.Namespace) -> int:
    from .project import MULTI_CORPUS_EXTENSIONS, SINGLE_CORPUS_EXTENSIONS, compression_of, save_corpora_as, save_corpus_as, save_project_as
    suffix = Path(args.dest).suffix.lower()
    single = suffix in SINGLE_CORPUS_EXTENSIONS
    corpora = args.corpus or []
    if single and len(corpora) != 1:
        raise SystemExit("ttwtools: .ttwc/.ttwcl guardam um corpus só: diga qual com --corpus")
    if corpora and not single and suffix not in MULTI_CORPUS_EXTENSIONS:
        raise SystemExit("ttwtools: --corpus vale para .ttwc/.ttwcl (um corpus) e .ttwal/.ttwl/.ttwa (uma seleção)")
    compress = not args.no_compress
    tables = False if args.no_search_tables else (True if args.with_search_tables else None)   # None: o padrão do formato
    with _open_or_create(args.project, create=False) as proj:
        if not (single or corpora or suffix == ".ttwal"):       # exportar não muda as opções lembradas no projeto de origem
            proj._set_meta("save.compress", compress)
            proj._set_meta("save.search_tables", True if tables is None else tables)
        proj._con.commit()
        if single:
            out = save_corpus_as(proj, corpora[0], args.dest, compress=compress, search_tables=tables)
        elif corpora or suffix == ".ttwal":          # seleção de corpora (.ttwal sem --corpus = todos, em versão leve)
            out = save_corpora_as(proj, corpora or proj.list_corpus_names(), args.dest, compress=compress, search_tables=tables)
        else:
            out = save_project_as(proj.path, args.dest, compress=compress, search_tables=True if tables is None else tables)
    emit({"arquivo": str(out), "compactado": compression_of(out) is not None,
          "tamanho_mb": round(out.stat().st_size / 1e6, 1)}, args.format)
    return EXIT_OK


def _configure_save_as(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", help="projeto de origem (.ttwa, .ttwl, .ttwal, .ttwc, .ttwcl ou .ttwt)")
    p.add_argument("dest", help="arquivo de destino; a extensão diz o tipo (.ttwc/.ttwcl: um corpus, com --corpus; "
                                ".ttwal: pacote leve com vários corpora, com --corpus repetido ou sem ele para todos)")
    p.add_argument("--corpus", action="append", help="corpus a gravar (repita para uma seleção, em .ttwal/.ttwl/.ttwa)")
    p.add_argument("--no-compress", action="store_true",
                   help="grava o banco sem compressão (abre sem descompactar, arquivo bem maior)")
    p.add_argument("--no-search-tables", action="store_true",
                   help="grava sem as tabelas de busca (tokens e índices): arquivo bem menor, mas abrir recria as tabelas")
    p.add_argument("--with-search-tables", action="store_true",
                   help="grava COM as tabelas de busca também nos formatos leves (.ttwcl, .ttwal), que por padrão ficam sem elas")


def _cmd_pipeline(args: argparse.Namespace) -> int:
    from . import pipeline
    with _open_or_create(args.project, create=False) as proj:
        if args.action == "add-stats":
            pipeline.add_step(proj, args.corpus, {"kind": "stats"})
        elif args.action == "add-tag":
            if not args.tagger:
                raise SystemExit("ttwtools: add-tag precisa de --tagger")
            options = {}
            for item in args.set or []:
                key, sep, value = item.partition("=")
                if not sep:
                    raise SystemExit(f"ttwtools: opção inválida '{item}' (use chave=valor)")
                options[key.strip()] = _parse_value(value.strip())
            pipeline.add_step(proj, args.corpus, {"kind": "tag", "tagger": args.tagger, "options": options,
                                                  "preset": args.preset})
        elif args.action == "remove":
            pipeline.remove_step(proj, args.corpus, args.index - 1)
        elif args.action == "clear":
            pipeline.clear_steps(proj, args.corpus)
        elif args.action == "run":
            def progress(done, total, msg):
                if args.format == "table":
                    print(f"  [{done}/{total}] {msg}", file=sys.stderr)
            r = pipeline.run_steps(proj, args.corpus, progress=progress)
            emit([{"passo": d["step"].get("tagger", "estatísticas"), **{k: v for k, v in d["report"].items()
                                                                          if not isinstance(v, (list, dict))}}
                  for d in r["done"]], args.format)
            return EXIT_OK
        steps = pipeline.pending_steps(proj, args.corpus)
    emit([{"nº": i + 1, "passo": s.get("tagger", "estatísticas básicas"),
           "opções": json.dumps(s.get("options") or {}, ensure_ascii=False), "atalho": s.get("preset", "")}
          for i, s in enumerate(steps)] or "lista vazia", args.format)
    return EXIT_OK


def _configure_pipeline(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", help="arquivo .ttwa ou .ttwl")
    p.add_argument("action", choices=["list", "add-stats", "add-tag", "remove", "clear", "run"],
                   help="list (mostra), add-stats, add-tag (com --tagger), remove (com --index), clear, run (executa)")
    p.add_argument("--corpus", required=True, help="corpus")
    p.add_argument("--tagger", help="spacy, stanza, mfte ou biberplus (add-tag)")
    p.add_argument("--set", "--option", dest="set", action="append", metavar="CHAVE=VALOR", help="opção do tagger (add-tag)")
    p.add_argument("--preset", choices=["rapido", "recomendado", "preciso"], help="atalho de opções (add-tag)")
    p.add_argument("--index", type=int, default=1, help="nº do passo a remover (remove; 1 = primeiro)")


def _cmd_documents(args: argparse.Namespace) -> int:
    from .corpus import filter_documents, parse_where
    with _open_or_create(args.project, create=False) as proj:
        docs = filter_documents(proj, args.corpus, parse_where(args.where or []))
    keys = sorted({k for d in docs for k in d["meta"]})
    rows = [{"corpus": d["corpus_name"], "arquivo": d["filename"], "caracteres": d["n_chars"],
             **{k: d["meta"].get(k) for k in keys}} for d in docs]
    emit(rows, args.format, columns=["corpus", "arquivo", "caracteres", *keys])
    return EXIT_OK


def _parse_value(text: str):
    try:
        return json.loads(text)          # true, false, 3, 0.5, "x"
    except json.JSONDecodeError:
        return text


def _cmd_tag(args: argparse.Namespace) -> int:
    from .annotate import tag_corpus
    from .corpus import parse_where
    options = {}
    for item in args.set or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"ttwtools: opção inválida '{item}' (use chave=valor)")
        options[key.strip()] = _parse_value(value.strip())

    def progress(done, total, filename):
        if args.format == "table":
            print(f"  [{done}/{total}] {filename}", file=sys.stderr)

    with _open_or_create(args.project, create=False) as proj:
        report = tag_corpus(proj, args.corpus, args.tagger, options,
                            components=args.components.split(",") if args.components else None,
                            where=parse_where(args.where or []), force=args.force, progress=progress,
                            preset=args.preset)
    report["layer_ids"] = len(report["layer_ids"])
    emit(report, args.format)
    return EXIT_OK


def _configure_tag(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", help="arquivo .ttwa ou .ttwl")
    p.add_argument("--corpus", required=True, help="corpus a etiquetar")
    p.add_argument("--tagger", required=True, help="spacy, stanza, mfte ou biberplus (ou atalhos: spacy_upos...)")
    p.add_argument("--set", "--option", dest="set", action="append", metavar="CHAVE=VALOR",
                   help="opção do tagger (ex.: model=en_core_web_sm, extended=false); ver tagger-options")
    p.add_argument("--preset", choices=["rapido", "recomendado", "preciso"], help="predefinição de opções")
    p.add_argument("--components", help="componentes, separados por vírgula (ex.: pos,lemma)")
    p.add_argument("--where", action="append", metavar="CHAVE=VALOR", help="só documentos com este metadado")
    p.add_argument("--force", action="store_true", help="etiquetar de novo mesmo havendo camada")


def _cmd_tagger_options(args: argparse.Namespace) -> int:
    from .i18n import t
    from .taggers import catalog
    if not args.tagger:
        rows = [{"tagger": a["id"], "disponivel": "sim" if a["disponivel"] else "não", "atalhos": ", ".join(a["atalhos"]),
                 "motivo": a["motivo"]} for a in catalog.available(args.lang)]
        emit(rows, args.format)
        return EXIT_OK
    d = catalog.options(args.tagger, lang=args.lang)
    if args.format == "json":
        emit(d, "json")
        return EXIT_OK
    rows = []
    for o in d["options"]:
        rows.append({
            "opcao": o["id"],
            "grupo": t(f"tagger.group.{o['grupo']}", args.lang),
            "padrao": o["padrao"],
            "valores": ", ".join(map(str, o.get("valores", []))),
            "efeito": t("tagger.affects.yes" if o["afeta_resultado"] else "tagger.affects.no", args.lang),
            "explicacao": o["explicacao"],
        })
    if args.format == "table":
        print(f"{d['name']} — {d['about']}\n")
        emit(rows, "table", columns=["opcao", "grupo", "padrao", "valores", "efeito"])
        print()
        for r in rows:
            print(f"  {r['opcao']}: {r['explicacao']}")
        presets = "; ".join(f"{t('tagger.preset.' + k, args.lang)} ({k}): "
                            + ", ".join(f"{kk}={vv}" for kk, vv in val.items()) for k, val in d.get("presets", {}).items())
        print(f"\n  --preset → {presets}")
    else:
        emit(rows, args.format)
    return EXIT_OK


def _cmd_tagset(args: argparse.Namespace) -> int:
    from .taggers import catalog
    if not args.id:
        emit([{"tagset": name} for name in catalog.list_tagsets()], args.format)
        return EXIT_OK
    ts = catalog.get_tagset(args.id, lang=args.lang, group=args.group)
    if args.format == "json":
        emit(ts, "json")
        return EXIT_OK
    groups = {g["id"]: g["label"] for g in ts["groups"]}
    rows = [{"tag": tg["tag"], "grupo": groups.get(tg["group"], tg["group"]), "definicao": tg["definition"],
             "exemplo": tg["example"]} for tg in ts["tags"]]
    if args.format == "table":
        print(f"{ts['name']} — {ts['about']}\n")
    emit(rows, args.format)
    return EXIT_OK


def _configure_tagger_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("tagger", nargs="?", help="spacy, stanza, mfte, biberplus ou atalho; vazio = disponibilidade")
    p.add_argument("--lang", choices=["pt", "en"], help="idioma das explicações (padrão: TTWTOOLS_LANG ou pt)")


def _configure_tagset(p: argparse.ArgumentParser) -> None:
    p.add_argument("id", nargs="?", help="tagset (upos, ptb, biber, mfte) ou tagger (spacy_upos, biberplus...)")
    p.add_argument("--group", help="só as tags deste grupo")
    p.add_argument("--lang", choices=["pt", "en"], help="idioma das definições")


def _configure_import(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", help="arquivo .ttwa ou .ttwl (criado se não existir)")
    p.add_argument("source", help="pasta de .txt, arquivo .txt, .csv com coluna de texto, ou - (texto pela entrada padrão)")
    p.add_argument("--name", required=True, help="nome do corpus no projeto")
    p.add_argument("--format", dest="format_in", default="auto", choices=["auto", "txt", "conllu", "nltk", "tei", "graf"],
                   help="auto (pela extensão), txt (pasta/.txt/.csv), conllu, nltk (palavra/TAG: Brown, LOB), "
                        "tei (TEI XML, BNC XML), graf (standoff do OANC/MASC: pasta ou cabeçalho .anc)")
    p.add_argument("--tagset", help="nome do tagset das etiquetas (só --format nltk; ex.: brown)")
    p.add_argument("--fields", help="campos no nome do arquivo, separados por vírgula (ex.: grupo,texto)")
    p.add_argument("--delimiter", default="_", help="delimitador dos campos no nome do arquivo (padrão: _)")
    p.add_argument("--meta-csv", help="CSV de metadados com a coluna filename")
    p.add_argument("--text-column", default="text", help="coluna de texto quando a origem é um CSV")
    tok = p.add_argument_group("tokenização simples (estatísticas antes de etiquetar)")
    tok.add_argument("--lowercase", action="store_const", const=True, help="minúsculas")
    tok.add_argument("--keep-punct", action="store_const", const=True, help="manter pontuação")
    tok.add_argument("--no-numbers", action="store_const", const=True, help="remover números")
    tok.add_argument("--contractions", choices=["keep", "split"], help="contrações: manter ou separar")


def _cmd_export(args: argparse.Namespace) -> int:
    from .corpus import parse_where
    from .formats import export_conllu, export_tokens, export_vrt
    where = parse_where(args.where or [])
    with _open_or_create(args.project, create=False) as proj:
        if args.to == "conllu":
            report = export_conllu(proj, args.corpus, args.out, tool=args.tool, where=where)
        elif args.to == "vrt":
            report = export_vrt(proj, args.corpus, args.out, tool=args.tool, where=where)
        else:
            report = export_tokens(proj, args.corpus, args.out, fmt=args.to, tool=args.tool, where=where)
    emit(report, args.format)
    return EXIT_OK


def _configure_export(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", help="arquivo .ttwa ou .ttwl")
    p.add_argument("--corpus", required=True)
    p.add_argument("--to", required=True, choices=["conllu", "vrt", "csv", "jsonl", "parquet"],
                   help="formato de saída (jsonl: uma pasta, um arquivo por documento)")
    p.add_argument("--out", required=True, help="arquivo (ou pasta, para jsonl) de saída")
    p.add_argument("--tool", help="camada de qual ferramenta (padrão: a mais recente de cada documento)")
    p.add_argument("--where", action="append", metavar="CHAVE=VALOR", help="só documentos com este metadado")


def _cmd_describe(args: argparse.Namespace) -> int:
    import tempfile
    from pathlib import Path
    from .corpus import import_corpus, parse_where
    from .project import TTWAProject
    from .stats import describe
    kwargs = dict(layer=args.layer, where=parse_where(args.where or []), top=args.top,
                  hide_stopwords=args.hide_stopwords, stopwords_lang=args.stopwords_lang,
                  extra_stopwords=args.add_stopword)
    src = Path(args.project)
    if src.is_dir():                      # pasta de .txt: projeto temporário
        with tempfile.TemporaryDirectory() as tmp:
            with TTWAProject.create(Path(tmp) / "tmp.ttwa") as proj:
                import_corpus(proj, src, src.name)
                result = describe(proj, src.name, **kwargs)
    else:
        if not args.corpus:
            raise SystemExit("ttwtools: informe --corpus")
        with _open_or_create(args.project, create=False) as proj:
            result = describe(proj, args.corpus, **kwargs)
    if args.format == "json":
        emit(result, "json")
        return EXIT_OK
    txt = result["text"]
    summary = {k: txt[k] for k in ("documents", "tokens", "types", "hapax", "ttr", "sttr", "cttr", "mattr",
                                    "mean_word_length", "sentences", "mean_sentence_length")}
    summary.update({f"doc_{k}": v for k, v in txt["document_tokens"].items()})
    if args.format == "csv":
        emit(summary, "csv")
        return EXIT_OK
    print("Estatísticas do texto (estimativas: tokenização simples, sem tagger)"
          + (" — do cache" if result["cached"] else ""))
    emit(summary)
    print("\nPalavras mais frequentes")
    emit(txt["top_words"])
    lay = result["layer"]
    if lay:
        print(f"\nCamada {lay['layer']}: {lay['words']} palavras, densidade lexical {lay['lexical_density']}")
        emit([{"classe": k, "freq": n} for k, n in list(lay["upos"].items())[:args.top]])
    return EXIT_OK


def _configure_describe(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", help="arquivo .ttwa/.ttwl, ou uma pasta de .txt")
    p.add_argument("--corpus", help="corpus do projeto")
    p.add_argument("--layer", help="ferramenta da camada (spacy, stanza, mfte, biberplus, conllu...) para as estatísticas pós-etiquetagem")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--hide-stopwords", action="store_true", help="tirar palavras funcionais da lista de mais frequentes")
    p.add_argument("--stopwords-lang", help="idioma da lista de palavras funcionais (en, pt; padrão: o do corpus)")
    p.add_argument("--add-stopword", action="append", help="palavra funcional a acrescentar (repita)")
    p.add_argument("--where", action="append", metavar="CHAVE=VALOR", help="só documentos com este metadado")


def _query_common(p: argparse.ArgumentParser, needs_query: bool = True) -> None:
    p.add_argument("project", help="arquivo .ttwa ou .ttwl")
    p.add_argument("--corpus", required=True)
    if needs_query:
        p.add_argument("query", help="consulta: casa, cas*, /regex/, lemma=run, pos=NOUN, tag=PASS; espaços = frase")
    p.add_argument("--layer", help="ferramenta da camada (padrão: a mais recente; sem camada: formas)")
    p.add_argument("--where", action="append", metavar="CHAVE=VALOR", help="só documentos com este metadado")


def _cmd_search(args):
    from .corpus import parse_where
    from .query import search
    with _open_or_create(args.project, create=False) as proj:
        r = search(proj, args.corpus, args.query, args.layer, parse_where(args.where or []), args.group_by)
    if args.format == "json":
        emit(r, "json")
    else:
        if args.format == "table":
            print(f"{r['query']}: {r['total']} ocorrência(s) em {r['documents']} documento(s)")
        emit(r.get("per_group") or r["per_document"], args.format)
    return EXIT_OK


def _cmd_kwic(args):
    from .corpus import parse_where
    from .query import kwic
    with _open_or_create(args.project, create=False) as proj:
        r = kwic(proj, args.corpus, args.query, args.layer, parse_where(args.where or []), context=args.context,
                 limit=args.limit, offset=args.offset, sort=args.sort, with_sentence=args.sentence)
    if args.format == "json":
        emit(r, "json")
        return EXIT_OK
    if args.format == "table":
        print(f"{r['total']} ocorrência(s); mostrando {args.offset + 1}–{args.offset + len(r['lines'])}")
        w = max((len(l["left"]) for l in r["lines"]), default=0)
        for l in r["lines"]:
            print(f"{l['left'].rjust(w)}  [{l['match']}]  {l['right']}    ({l['filename']}:{l['start_char']})")
    else:
        emit(r["lines"], "csv", columns=["filename", "idx", "start_char", "end_char", "left", "match", "right", "pos", "lemma"])
    return EXIT_OK


def _cmd_freq(args):
    from .corpus import parse_where
    from .query import frequency
    from .stats import guess_language, stopwords
    with _open_or_create(args.project, create=False) as proj:
        stop = stopwords(args.stopwords_lang or guess_language(proj, args.corpus) or "en") if args.hide_stopwords else None
        r = frequency(proj, args.corpus, args.unit, args.n, args.by, args.layer, parse_where(args.where or []),
                      args.top, stop=stop)
    emit(r if args.format == "json" else r["rows"], args.format)
    return EXIT_OK


def _cmd_collocates(args):
    from .corpus import parse_where
    from .query import collocates
    with _open_or_create(args.project, create=False) as proj:
        r = collocates(proj, args.corpus, args.query, (args.left, args.right), args.unit, args.layer,
                       parse_where(args.where or []), args.min_freq, args.top, args.sort)
    if args.format == "json":
        emit(r, "json")
    else:
        if args.format == "table":
            print(f"nó: {r['node']} ({r['node_freq']}x) · janela {r['window'][0]}E/{r['window'][1]}D · {r['corpus_words']} palavras")
        emit(r["rows"], args.format, columns=["collocate", "freq", "coll_total", "ll", "mi", "t_score", "position"])
    return EXIT_OK


def _cmd_dispersion(args):
    from .corpus import parse_where
    from .query import dispersion
    with _open_or_create(args.project, create=False) as proj:
        r = dispersion(proj, args.corpus, args.query, args.layer, parse_where(args.where or []))
    if args.format == "json":
        emit(r, "json")
    else:
        if args.format == "table":
            print(f"{r['query']}: freq {r['freq']} · range {r['range']}/{r['documents']} · DP {r['dp']} · DP norm. {r['dp_norm']}")
        emit(r["per_document"], args.format, columns=["filename", "size", "freq"])
    return EXIT_OK


def _configure_search(p):
    _query_common(p)
    p.add_argument("--group-by", help="metadado para contar por grupo")


def _configure_kwic(p):
    _query_common(p)
    p.add_argument("--context", type=int, default=5, help="tokens de cada lado (padrão 5)")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--sort", choices=["position", "left", "right"], default="position")
    p.add_argument("--no-sentence", dest="sentence", action="store_false", help="não buscar a frase inteira")


def _configure_freq(p):
    _query_common(p, needs_query=False)
    p.add_argument("--unit", choices=["form", "lemma", "word_pos", "pos", "ngram"], default="form")
    p.add_argument("-n", type=int, default=2, help="tamanho do n-grama (com --unit ngram)")
    p.add_argument("--by", default="corpus", help="corpus, document ou nome de metadado")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--hide-stopwords", action="store_true")
    p.add_argument("--stopwords-lang", help="en, pt (padrão: o do corpus)")


def _configure_collocates(p):
    _query_common(p)
    p.add_argument("--left", type=int, default=5)
    p.add_argument("--right", type=int, default=5)
    p.add_argument("--unit", choices=["form", "lemma", "word_pos", "pos"], default="form")
    p.add_argument("--min-freq", type=int, default=2)
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--sort", choices=["ll", "mi", "t", "freq"], default="ll")


def _configure_dispersion(p):
    _query_common(p)


def _cmd_tag_counts(args):
    from .query import tag_counts
    with _open_or_create(args.project, create=False) as proj:
        r = tag_counts(proj, args.corpus, args.layer, args.field)
    rows = [{"tag": k, "freq": v} for k, v in sorted(r["counts"].items(), key=lambda kv: (-kv[1], kv[0]))]
    if args.format == "json":
        emit(r, "json")
    else:
        emit(rows, args.format, columns=["tag", "freq"])
    return EXIT_OK


def _configure_tag_counts(p):
    _query_common(p, needs_query=False)
    p.add_argument("--field", choices=["upos", "xpos", "tags"], default="tags", help="o que contar (padrão: primeira tag do token)")


def _cmd_keywords(args):
    from .corpus import parse_where
    from .keyness import keywords
    with _open_or_create(args.project, create=False) as proj:
        r = keywords(proj, args.corpus, args.reference, unit=args.unit, measure=args.measure, n=args.n,
                     layer=args.layer, where=parse_where(args.where or []), min_freq=args.min_freq,
                     min_range=args.min_range, correction=args.correction, top=args.top, lang=args.lang)
    if args.format == "json":
        emit(r, "json")
        return EXIT_OK
    cols = ["item", "direction", "freq_target", "freq_reference", "ll", "log_ratio", "pct_diff", "log_odds",
            "p_adj", "range_target"]
    if args.format == "table":
        print(f"{r['target']} ({r['target_words']} palavras) × {r['reference']} ({r['reference_words']} palavras)"
              f" · unidade {args.unit} · ordenado por {args.measure}")
        for w in r["warnings"]:
            print(f"  [{w['severity']}] {w['message']}")
    emit(r["rows"], args.format, columns=cols)
    return EXIT_OK


def _cmd_bands(args):
    from .corpus import parse_where
    from .keyness import frequency_bands
    with _open_or_create(args.project, create=False) as proj:
        r = frequency_bands(proj, args.corpus, args.reference, unit=args.unit, layer=args.layer,
                            where=parse_where(args.where or []),
                            bands=tuple(int(b) for b in args.bands.split(",")))
    if args.format == "json":
        emit(r, "json")
        return EXIT_OK
    if args.format == "table":
        print(f"{r['target']} ({r['tokens']} ocorrências, {r['types']} tipos) × {r['reference']}"
              f" ({r['reference_words']} palavras) · unidade {args.unit}")
    emit([{**{k: row[k] for k in ("band", "tokens", "types")}, "pct_tokens": round(row["pct_tokens"], 2),
           "pct_types": round(row["pct_types"], 2), "examples": " ".join(row["examples"])} for row in r["rows"]],
         args.format)
    return EXIT_OK


def _configure_bands(p):
    _query_common(p, needs_query=False)
    p.add_argument("--reference", required=True, help="catalog:<id>, lista .tsv ou nome de outro corpus do projeto")
    p.add_argument("--unit", choices=["form", "lemma", "word_pos"], default="form")
    p.add_argument("--bands", default="1000,2000,3000,5000,10000", help="limites das faixas (posições na referência)")


def _cmd_reference_list(args):
    from .keyness import make_reference_list
    card = {k: getattr(args, k) for k in ("lang", "variety", "period", "genres", "license", "source", "version")
            if getattr(args, k)}
    card["name"] = args.name or args.corpus
    with _open_or_create(args.project, create=False) as proj:
        out = make_reference_list(proj, args.corpus, args.out, unit=args.unit, layer=args.layer, card=card)
    emit({"out": str(out), **card}, args.format)
    return EXIT_OK


def _configure_keywords(p):
    _query_common(p, needs_query=False)
    p.add_argument("--reference", required=True,
                   help="lista .tsv, catalog:<id> (lista instalada pelo catálogo), nome de outro corpus do projeto, "
                        "ou rest:<metadado> (com --where definindo o alvo)")
    p.add_argument("--unit", choices=["form", "lemma", "pos", "word_pos", "ngram"], default="form")
    p.add_argument("-n", type=int, default=2, help="tamanho do n-grama")
    p.add_argument("--measure", choices=["ll", "log_ratio", "pct_diff", "log_odds"], default="ll")
    p.add_argument("--min-freq", type=int, default=5)
    p.add_argument("--min-range", type=int, default=1, help="mínimo de textos do alvo em que o item aparece")
    p.add_argument("--correction", choices=["bonferroni", "fdr", "none"], default="bonferroni")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--lang", choices=["pt", "en"], help="idioma dos avisos")


def _cmd_writing(args):
    from .writing import analyze_file
    name = "entrada.txt" if args.text == "-" else args.text
    blob = sys.stdin.buffer.read() if args.text == "-" else Path(args.text).read_bytes()
    with _open_or_create(args.project, create=False) as proj:
        r = analyze_file(proj, blob, name, args.reference, unit=args.unit, n=args.n, measure=args.measure,
                         min_freq=args.min_freq, correction=args.correction, top=args.top, lang=args.lang)
    if args.format == "json":
        emit(r, "json")
        return EXIT_OK
    if args.format == "table":
        print(f"{r['text_name']} ({r['target_words']} palavras) × {r['reference']} ({r['reference_words']} palavras)"
              f" · unidade {r['unit']} · correção {r['correction']}")
        print("  Texto único: resultado descritivo/exploratório — não é inferência sobre uma população.")
        lx = r.get("lexis")
        if lx:
            mtld_txt = "—" if lx["mtld"] is None else f"{lx['mtld']:.1f}"
            print(f"  Léxico: {lx['types']} tipos / {lx['words']} palavras · TTR {lx['ttr']:.3f} · "
                  f"MTLD {mtld_txt} · {lx['mean_sentence_len']:.1f} palavras/frase")
    cols = ["item", "direction", "freq_target", "per_1000_target", "freq_reference", "per_1000_reference",
            "ll", "p_adj", "log_ratio", "pct_diff", "range_reference_pct", "flags"]
    emit(r["rows"], args.format, columns=cols)
    return EXIT_OK


def _configure_writing(p):
    p.add_argument("project", help="arquivo .ttwa ou .ttwl (para referência de corpus/catálogo)")
    p.add_argument("--text", required=True, help="arquivo txt/md/docx/odt/pdf, ou - para a entrada padrão")
    p.add_argument("--reference", required=True, help="lista .tsv, catalog:<id> ou nome de um corpus do projeto")
    p.add_argument("--unit", choices=["form", "ngram"], default="form")
    p.add_argument("-n", type=int, default=2, help="tamanho do n-grama")
    p.add_argument("--measure", choices=["ll", "log_ratio", "pct_diff", "log_odds"], default="log_ratio")
    p.add_argument("--min-freq", type=int, default=2)
    p.add_argument("--correction", choices=["bonferroni", "fdr", "none"], default="fdr")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--lang", choices=["pt", "en"], help="idioma dos avisos")


def _cmd_patterns(args):
    from .constructions import analyze_patterns
    from .writing import extract_text
    name = "entrada.txt" if args.text == "-" else args.text
    blob = sys.stdin.buffer.read() if args.text == "-" else Path(args.text).read_bytes()
    text = extract_text(blob, name)
    with _open_or_create(args.project, create=False) as proj:
        r = analyze_patterns(proj, text, args.reference, field=args.field, n=args.n, measure=args.measure,
                             min_freq=args.min_freq, correction=args.correction, top=args.top, lang=args.lang,
                             text_name=name)
    if args.format == "json":
        emit(r, "json")
        return EXIT_OK
    if args.format == "table":
        print(f"{r['text_name']} ({r['target_words']} palavras) × {r['reference']} · construções de "
              f"{r['field']} (n={r['n']}) · correção {r['correction']}")
        print("  Sequências de classes gramaticais (moldes), não palavras: 'DT JJ NN', 'VBN by'...")
    cols = ["item", "direction", "freq_target", "per_1000_target", "freq_reference", "per_1000_reference",
            "ll", "p_adj", "log_ratio", "range_reference_pct", "z_reference", "flags"]
    emit(r["rows"], args.format, columns=cols)
    return EXIT_OK


def _configure_patterns(p):
    p.add_argument("project", help="arquivo .ttwa ou .ttwl")
    p.add_argument("--text", required=True, help="arquivo txt/md/docx/odt/pdf, ou - para a entrada padrão")
    p.add_argument("--reference", required=True, help="corpus do projeto com camada POS (spaCy/Stanza)")
    p.add_argument("--field", choices=["upos", "xpos"], default="upos", help="classe universal (upos) ou detalhada (xpos)")
    p.add_argument("-n", type=int, default=3, help="tamanho do n-grama de classes")
    p.add_argument("--measure", choices=["ll", "log_ratio", "pct_diff", "log_odds"], default="log_ratio")
    p.add_argument("--min-freq", type=int, default=2)
    p.add_argument("--correction", choices=["bonferroni", "fdr", "none"], default="fdr")
    p.add_argument("--top", type=int, default=60)
    p.add_argument("--lang", choices=["pt", "en"], help="idioma dos avisos")


def _cmd_collocates_text(args):
    from .collocations import collocate_profile
    from .writing import extract_text
    name = "entrada.txt" if args.text == "-" else args.text
    blob = sys.stdin.buffer.read() if args.text == "-" else Path(args.text).read_bytes()
    text = extract_text(blob, name)
    with _open_or_create(args.project, create=False) as proj:
        r = collocate_profile(proj, text, args.node, args.reference, window=(args.left, args.right),
                              top=args.top, min_freq=args.min_freq, layer=args.layer, lang=args.lang, text_name=name)
    if args.format == "json":
        emit(r, "json")
        return EXIT_OK
    if args.format == "table":
        print(f"Colocados de '{r['node']}': texto ({r['node_freq_text']}×) × {r['reference']} "
              f"({r['node_freq_reference']}×) · janela {r['window']}")
    cols = ["collocate", "freq_text", "per_1000_text", "freq_reference", "per_1000_reference",
            "log_ratio", "ll", "position"]
    emit(r["rows"], args.format, columns=cols)
    return EXIT_OK


def _configure_collocates_text(p):
    p.add_argument("project")
    p.add_argument("--text", required=True, help="arquivo txt/md/docx/odt/pdf, ou - para a entrada padrão")
    p.add_argument("--reference", required=True, help="corpus do projeto")
    p.add_argument("--node", required=True, help="palavra consultada")
    p.add_argument("--left", type=int, default=5)
    p.add_argument("--right", type=int, default=5)
    p.add_argument("--min-freq", type=int, default=2)
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--layer")
    p.add_argument("--lang", choices=["pt", "en"])


def _configure_reference_list(p):
    p.add_argument("project")
    p.add_argument("--corpus", required=True)
    p.add_argument("--out", required=True, help="arquivo .tsv de saída")
    p.add_argument("--unit", choices=["form", "lemma", "pos", "word_pos"], default="form")
    p.add_argument("--layer")
    for k in ("name", "lang", "variety", "period", "genres", "license", "source", "version"):
        p.add_argument(f"--{k}", help=f"ficha do corpus: {k}")


def _cmd_help(args):
    from . import help as h
    if args.search:
        emit(h.search(args.search, args.lang), args.format)
        return EXIT_OK
    if not args.topic:
        emit(h.topics(args.lang), args.format, columns=["id", "area", "title", "summary"])
        return EXIT_OK
    try:
        if args.format == "table":
            print(h.render(args.topic, args.lang))
        else:
            emit(h.get(args.topic, args.lang), args.format)
    except KeyError as exc:
        print(exc.args[0], file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


def _cmd_recent(args):
    from . import recent
    if args.clear:
        recent.clear()
    elif args.remove:
        recent.remove(args.remove)
    emit(recent.listing(), args.format, columns=["name", "ext", "exists", "folder"])
    return EXIT_OK


def _configure_recent(p):
    p.add_argument("--remove", metavar="ARQUIVO", help="tira um arquivo da lista")
    p.add_argument("--clear", action="store_true", help="esvazia a lista")


def _configure_help(p):
    p.add_argument("topic", nargs="?", help="tópico (ex.: cohens_d, kwic, keyness); vazio = lista")
    p.add_argument("--lang", choices=["pt", "en"])
    p.add_argument("--search", help="procurar nos textos de ajuda")


def _parse_group(spec: str, default_corpus: str) -> dict:
    """`rótulo=corpus[:chave=valor[,valor]]` ou `corpus[:chave=valor]` → grupo de experimental."""
    label, _, rest = spec.partition("=") if "=" in spec.split(":", 1)[0] else ("", "", spec)
    corpus, _, cond = rest.partition(":")
    group: dict = {"corpus": corpus or default_corpus}
    if cond:
        key, _, vals = cond.partition("=")
        group["where"] = {key: vals.split(",")}
    group["label"] = label or (f"{group['corpus']}:{cond}" if cond else group["corpus"])
    return group


def _cmd_compare_groups(args):
    from . import experimental as ex
    with _open_or_create(args.project, create=False) as proj:
        groups = ex.groups_by_metadata(proj, args.corpus, args.group_by) if args.group_by else \
            [_parse_group(g, args.corpus) for g in args.group]
        r = ex.compare_groups(proj, groups, args.layer, method=args.method, feature=args.feature, metric=args.metric,
                              top=args.top, correction=args.correction, lang=args.lang)
    if args.format == "json":
        emit(r, "json")
        return EXIT_OK
    sizes = ", ".join("{} ({})".format(g["label"], g["n"]) for g in r["groups"])
    print(f"[experimental] {args.method} · {sizes} · camada {args.layer}", file=sys.stderr)
    for w in r["warnings"]:
        print(f"  [{w['severity']}] {w['message']}", file=sys.stderr)
    m = args.method
    if m == "one_vs_rest":
        rows = [{"grupo": g["label"], **f} for g in r["results"] for f in g["features"]]
    elif m == "pairwise":
        rows = [{"a": pr["a"], "b": pr["b"], "mean_abs_d": pr["mean_abs_d"], "d>=0.8": pr["large"],
                 "traços": " ".join(f["feature"] for f in pr["features"][:5])} for pr in r["pairs"]]
    elif m == "anova":
        rows = [{k: x[k] for k in ("feature", "H", "epsilon2", "p", "p_adj")} for x in r["results"]]
    elif m == "profile":
        rows = r["reduction"]["coords"]
    elif m == "dendrogram":
        rows = [{"ordem": i + 1, "grupo": g} for i, g in enumerate(r["order"])]
    else:
        rows = [{"referência": x["label"], "distância": x["distance"],
                 "traços": " ".join(f["feature"] for f in x["features"][:5])} for x in r["results"]]
    emit(rows, args.format)
    return EXIT_OK


def _cmd_compare(args):
    from .corpus import parse_where
    from .features import kfa_layers
    if args.group_by or args.group:
        return _cmd_compare_groups(args)
    with _open_or_create(args.project, create=False) as proj:
        r = kfa_layers(proj, args.corpus, args.corpus2 or args.corpus, args.layer, args.feature, args.metric,
                       args.min_effect, args.join, parse_where(args.where or []), parse_where(args.where2 or []))
    if args.format == "json":
        emit(r, "json")
        return EXIT_OK
    if args.format == "table":
        print(f"KFA {r['corpus1']} ({r['n1']}) × {r['corpus2']} ({r['n2']}) · camada {r['layer']} · {r['metric']}")
    emit(r["rows"], args.format, columns=["Feature", "Effect_Size", "Mean_Corpus1", "Mean_Corpus2", "Difference"])
    return EXIT_OK


def _configure_compare(p):
    p.add_argument("project")
    p.add_argument("--corpus", required=True, help="corpus 1")
    p.add_argument("--corpus2", help="corpus 2 (padrão: o mesmo, comparando grupos com --where/--where2)")
    p.add_argument("--layer", required=True, help="camada: biberplus, mfte, spacy, stanza...")
    p.add_argument("--feature", choices=["tags", "upos", "xpos"], help="o que contar (padrão: tags no BiberPlus/MFTE, upos nos demais)")
    p.add_argument("--metric", choices=["kfa", "kfa2"], default="kfa")
    p.add_argument("--min-effect", type=float, default=0.0)
    p.add_argument("--join", choices=["union", "intersection"], default="union")
    p.add_argument("--where", action="append", metavar="CHAVE=VALOR", help="filtro do lado 1")
    p.add_argument("--where2", action="append", metavar="CHAVE=VALOR", help="filtro do lado 2")
    lab = p.add_argument_group("N grupos (experimental; ttwtools.experimental.compare_groups)")
    lab.add_argument("--group-by", metavar="CHAVE", help="um grupo por valor deste metadado do --corpus")
    lab.add_argument("--group", action="append", metavar="[RÓTULO=]CORPUS[:CHAVE=VALOR]",
                     help="um grupo; repita (com nearest, o primeiro é o 'meu texto')")
    lab.add_argument("--method", choices=["one_vs_rest", "pairwise", "anova", "profile", "dendrogram", "nearest"],
                     default="one_vs_rest")
    lab.add_argument("--top", type=int, default=10, help="traços por grupo ou par")
    lab.add_argument("--correction", choices=["fdr", "bonferroni", "none"], default="fdr")
    lab.add_argument("--lang", choices=["pt", "en"], help="idioma dos avisos")


def _cmd_catalog(args):
    from . import corpus_catalog as cc
    from . import models
    act = args.action
    if act == "list":
        cat = cc.load_catalog(args.url)
        have = {(i["id"], i["version"]) for i in cc.installed()}
        rows = [{"id": e["id"], "versão": e["version"], "tipo": e.get("kind", "package"), "idioma": e["ficha"].get("lang"),
                 "palavras": e["ficha"].get("size", {}).get("words"), "licença": e["ficha"].get("license", {}).get("name"),
                 "instalado": "sim" if (e["id"], e["version"]) in have else ""} for e in cat["packages"]]
        emit(rows, args.format)
    elif act == "installed":
        emit([{"id": i["id"], "versão": i["version"], "pasta": i["path"]} for i in cc.installed()], args.format)
    elif act == "install":
        def progress(done, total, name):
            if args.format == "table":
                print(f"\r  {name}: {done // 1024} / {total // 1024} KB", end="", file=sys.stderr)
        item = cc.install(args.id, args.version, cc.load_catalog(args.url), progress)
        if args.format == "table":
            print(file=sys.stderr)
        emit({"id": item["id"], "versão": item["version"], "pasta": item["path"], "projeto": item["project"]}, args.format)
    elif act == "remove":
        emit({"removidos": cc.remove(args.id, args.version)}, args.format)
    elif act == "update":
        emit(cc.updates(cc.load_catalog(args.url)), args.format)
    elif act == "validate":
        import json as _json
        errors = cc.validate_catalog(_json.loads(open(args.id, encoding="utf-8").read()))
        emit([{"erro": e} for e in errors] if errors else "catálogo válido", args.format)
        return EXIT_ERROR if errors else EXIT_OK
    elif act == "references":
        emit([{k: r[k] for k in ("ref", "unit", "words", "documents", "lang", "license", "version")}
              for r in cc.reference_lists()], args.format)
    elif act == "models":
        emit([{k: m[k] for k in ("id", "lang", "tier", "download_mb", "license", "installed", "available", "reason")}
              for m in models.list_models()["models"]], args.format)
    elif act == "download-model":
        path = models.download_spacy_model(args.id) if not args.id.startswith("stanza:") else \
            models.download_stanza(args.id.split(":", 1)[1])
        emit({"modelo": args.id, "pasta": str(path)}, args.format)
    return EXIT_OK


def _configure_catalog(p):
    p.add_argument("action", choices=["list", "installed", "install", "remove", "update", "validate", "references",
                                      "models", "download-model"])
    p.add_argument("id", nargs="?", help="id do pacote (install/remove), caminho do catálogo (validate) ou modelo "
                                         "(download-model: en_core_web_md, stanza:pt)")
    p.add_argument("--version", dest="version", help="versão do pacote")
    p.add_argument("--url", help="URL ou caminho do catalogo.json (padrão: configuração)")


def _configure_documents(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", help="arquivo .ttwa ou .ttwl")
    p.add_argument("--corpus", help="só este corpus")
    p.add_argument("--where", action="append", metavar="CHAVE=VALOR",
                   help="filtro por metadado; repita para OU na mesma chave e E entre chaves")


# nome → (descrição, configuração dos argumentos, função)
IMPLEMENTED: dict[str, tuple[str, Callable, Callable[[argparse.Namespace], int]]] = {
    "import":    ("Importa textos para um corpus do projeto (pasta, .txt, CSV ou texto colado)",
                  _configure_import, _cmd_import),
    "save-as":   ("Salva o projeto em outro arquivo (compactado por padrão; --no-compress para o banco direto)",
                  _configure_save_as, _cmd_save_as),
    "compact":   ("Remove do projeto as cópias antigas das etiquetagens (tagged_files) já presentes nas camadas",
                  _configure_compact, _cmd_compact),
    "pipeline":  ("Lista de camadas a calcular depois (estatísticas e etiquetagens) e a execução dela",
                  _configure_pipeline, _cmd_pipeline),
    "names":     ("Mostra como os nomes dos arquivos de uma pasta viram metadados (sem importar)",
                  _configure_names, _cmd_names),
    "documents": ("Lista documentos e metadados, com filtro por metadado",
                  _configure_documents, _cmd_documents),
    "tag":       ("Etiqueta um corpus, reaproveitando camadas já feitas",
                  _configure_tag, _cmd_tag),
    "search":    ("Conta ocorrências de uma consulta (total, por documento ou grupo)", _configure_search, _cmd_search),
    "kwic":      ("Concordância (palavra-chave em contexto), paginada", _configure_kwic, _cmd_kwic),
    "freq":      ("Lista de frequência (forma, lema, palavra+classe, classe, n-grama)", _configure_freq, _cmd_freq),
    "collocates": ("Colocados com log-likelihood, MI, T-score e frequência", _configure_collocates, _cmd_collocates),
    "dispersion": ("Dispersão (DP de Gries, Range) e posições para o gráfico", _configure_dispersion, _cmd_dispersion),
    "tag-counts": ("Ocorrências de cada etiqueta no corpus todo (upos, xpos ou tags)", _configure_tag_counts, _cmd_tag_counts),
    "compare":   ("KFA (d de Cohen por traço) entre dois corpora ou grupos, a partir das camadas",
                  _configure_compare, _cmd_compare),
    "keywords":  ("Palavras-chave do corpus contra uma referência (LL, log ratio, %%DIFF, log-odds)",
                  _configure_keywords, _cmd_keywords),
    "bands":     ("Faixas de frequência lexical: parte do texto entre as 1.000, 2.000... palavras mais frequentes",
                  _configure_bands, _cmd_bands),
    "reference-list": ("Gera a lista de frequência de referência (.tsv com ficha) de um corpus",
                       _configure_reference_list, _cmd_reference_list),
    "writing":   ("Compara um texto individual (n=1) com um corpus de referência; descritivo, com dispersão e FDR",
                  _configure_writing, _cmd_writing),
    "patterns":  ("Perfil de construções do texto (n-gramas de classes/etiquetas) contra a referência",
                  _configure_patterns, _cmd_patterns),
    "collocates-text": ("Colocados de uma palavra no texto do aluno, comparados com a referência",
                        _configure_collocates_text, _cmd_collocates_text),
    "catalog":   ("Catálogo de corpora e modelos: list, install, remove, update, validate, references, models, download-model",
                  _configure_catalog, _cmd_catalog),
    "recent":    ("Arquivos .ttwa/.ttwl/.ttwal/.ttwc/.ttwcl abertos recentemente (lista, --remove, --clear)",
                  _configure_recent, _cmd_recent),
    "help":      ("Ajuda sobre conceitos, métricas e telas (ex.: ttwtools help cohens_d)", _configure_help, _cmd_help),
    "describe":  ("Estatísticas do corpus (sem tagger) e, com --layer, da camada",
                  _configure_describe, _cmd_describe),
    "export":    ("Exporta uma camada em CoNLL-U, VRT, CSV, JSONL ou Parquet",
                  _configure_export, _cmd_export),
    "tagger-options": ("Opções de um tagger, com explicações (sem argumento: disponibilidade)",
                       _configure_tagger_options, _cmd_tagger_options),
    "tagset":    ("Repertório de tags de um tagger ou tagset, com definições",
                  _configure_tagset, _cmd_tagset),
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
    from .models import activate
    activate()                      # modelos baixados pelo catálogo entram no caminho
    parser = build_parser()
    args = parser.parse_args(None if argv is None else list(argv))
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_OK
    from .storage import InsufficientDiskSpace
    try:
        return args.handler(args)
    except InsufficientDiskSpace as exc:        # recusado antes de gravar: nada ficou pela metade
        print(f"ttwtools: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
