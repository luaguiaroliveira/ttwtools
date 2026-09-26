"""
keyness.py — Palavras-chave de um alvo contra uma referência (novomodelo.md §16).

    keywords(proj, "meu_corpus", reference="brown.tsv", unit="lemma", measure="log_ratio")
    keywords(proj, "meu_corpus", reference="outro_corpus")                 # corpus do projeto
    keywords(proj, "meu_corpus", reference="rest:grupo", where={"grupo": "A"})   # A × os demais

Medidas (a, b = frequência no alvo e na referência; c, d = tamanhos em palavras):
    ll         log-likelihood de Rayson & Garside (2 células): 2·Σ O·ln(O/E)
    log_ratio  log2 da razão das frequências relativas (Hardie 2014; 0,5 no lugar de zero)
    pct_diff   %DIFF de Gabrielatos & Marchi (2012)
    log_odds   log da razão de chances com +0,5 em cada célula, e o z correspondente
Valor-p do LL: qui-quadrado com 1 grau de liberdade; correção: bonferroni, fdr
(Benjamini-Hochberg) ou none.

Lista de frequência de referência (`.tsv`): 1ª linha `# {json da ficha}`, depois
`item<TAB>pos<TAB>freq<TAB>docs`. A ficha registra idioma, variedade, período,
gêneros, tamanho, licença, fonte, unidade e o tagger/versão que gerou a lista.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .i18n import t
from .project import TTWAProject
from .query import _is_word, _layer_tokens, _select_layers, _unit_value

UNITS = ("form", "lemma", "pos", "word_pos", "ngram")
MEASURES = ("ll", "log_ratio", "pct_diff", "log_odds")
MIN_WORDS = 10_000


@dataclass
class FreqTable:
    """Frequências agregadas de um lado da comparação."""
    counts: Counter
    docs: Counter | None          # em quantos textos cada item aparece (None se desconhecido)
    words: int
    n_docs: int
    meta: dict = field(default_factory=dict)   # lang, tool, tool_version, model, name...
    doc_ids: frozenset = frozenset()


# ---------------------------------------------------------------------------
# De onde vêm as frequências
# ---------------------------------------------------------------------------

def _lang_of(tool: str, model: str, config: dict) -> str | None:
    if config.get("lang"):
        return config["lang"]
    if model and "_" in model and len(model.split("_")[0]) == 2:      # en_core_web_sm
        return model.split("_")[0]
    if model and "/" in model:                                        # en/default (Stanza)
        return model.split("/")[0]
    if model.startswith("stanza-"):
        return model.split("-", 1)[1]
    return None


def corpus_freqs(project: TTWAProject, corpus_name: str, unit: str = "form", n: int = 2,
                 layer: str | None = None, where: Mapping | None = None, exclude: Mapping | None = None) -> FreqTable:
    """Frequências de um corpus do projeto (com filtro `where`, ou excluindo os
    documentos que batem com `exclude`)."""
    if unit not in UNITS:
        raise ValueError(f"unidade deve ser uma de {UNITS}")
    sel = _select_layers(project, corpus_name, layer, None if exclude else where)
    if exclude:
        from .corpus import filter_documents
        drop = {d["id"] for d in filter_documents(project, corpus_name, exclude)}
        sel = {lid: d for lid, d in sel.items() if d["id"] not in drop}
    counts, docs = Counter(), Counter()
    words = 0
    tools = Counter()
    missing_field = 0
    for doc, rows in _layer_tokens(project, sel):
        toks = [r for r in rows if _is_word(r)] if unit != "pos" else [r for r in rows if r["upos"] or r["xpos"]]
        words += sum(1 for r in rows if _is_word(r))
        if unit == "ngram":
            forms = [(r["word"] or "").lower() for r in toks]
            items = [" ".join(forms[i:i + n]) for i in range(len(forms) - n + 1)]
        else:
            items = []
            for r in toks:
                if unit == "lemma" and not r["lemma"]:
                    missing_field += 1
                items.append(_unit_value(r, unit))
            items = [i for i in items if i]
        c = Counter(items)
        counts.update(c)
        docs.update(c.keys())
    layer_rows = project._con.execute(
        f"SELECT tool, tool_version, model, config FROM layers WHERE id IN ({','.join('?' * len(sel))})",
        list(sel)).fetchall() if sel else []
    for r in layer_rows:
        tools[(r["tool"], r["tool_version"], r["model"], _lang_of(r["tool"], r["model"], json.loads(r["config"])))] += 1
    tool, version, model, lang = tools.most_common(1)[0][0] if tools else ("", "", "", None)
    return FreqTable(counts, docs, words, len(sel),
                     {"name": corpus_name, "lang": lang, "tool": tool, "tool_version": version, "model": model,
                      "unit": unit, "missing_field": missing_field},
                     frozenset(d["id"] for d in sel.values()))


def write_reference_list(path: str | Path, table: FreqTable, card: Mapping[str, Any] | None = None) -> Path:
    """Grava uma lista de frequência de referência (.tsv com a ficha na 1ª linha)."""
    path = Path(path)
    meta = {**{k: v for k, v in table.meta.items() if k != "missing_field"}, **(card or {}),
            "words": table.words, "documents": table.n_docs, "format": "ttwtools-reference-list/1"}
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("# " + json.dumps(meta, ensure_ascii=False, sort_keys=True) + "\n")
        fh.write("item\tpos\tfreq\tdocs\n")
        for item, f in table.counts.most_common():
            word, _, pos = item.rpartition("/") if meta.get("unit") == "word_pos" and "/" in item else (item, "", "")
            fh.write(f"{word}\t{pos}\t{f}\t{table.docs[item] if table.docs is not None else ''}\n")
    return path


def read_reference_list(path: str | Path) -> FreqTable:
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("# {"):
        raise ValueError(f"'{path.name}' não é uma lista de referência do ttwtools (falta a ficha na 1ª linha)")
    meta = json.loads(lines[0][2:])
    counts, docs = Counter(), Counter()
    has_docs = True
    for line in lines[2:]:
        if not line:
            continue
        item, pos, freq, nd = (line.split("\t") + ["", "", "", ""])[:4]
        key = f"{item}/{pos}" if pos else item
        counts[key] += int(freq)
        if nd:
            docs[key] += int(nd)
        else:
            has_docs = False
    return FreqTable(counts, docs if has_docs else None, int(meta.get("words") or sum(counts.values())),
                     int(meta.get("documents") or 0), meta)


def make_reference_list(project: TTWAProject, corpus_name: str, out: str | Path, unit: str = "form",
                        layer: str | None = None, card: Mapping[str, Any] | None = None) -> Path:
    """Gera a lista de referência de um corpus do projeto (para distribuir no catálogo)."""
    return write_reference_list(out, corpus_freqs(project, corpus_name, unit, layer=layer), card)


# ---------------------------------------------------------------------------
# Medidas
# ---------------------------------------------------------------------------

def log_likelihood(a: float, b: float, c: float, d: float) -> float:
    """LL de Rayson & Garside (2000), duas células."""
    e1 = c * (a + b) / (c + d)
    e2 = d * (a + b) / (c + d)
    ll = (a * math.log(a / e1) if a else 0.0) + (b * math.log(b / e2) if b else 0.0)
    return 2 * ll


def log_ratio(a: float, b: float, c: float, d: float) -> float:
    return math.log2(((a or 0.5) / c) / ((b or 0.5) / d))


def pct_diff(a: float, b: float, c: float, d: float) -> float:
    na, nb = a / c * 1e6, b / d * 1e6
    return (na - nb) * 100 / (nb or 1e-18)


def log_odds(a: float, b: float, c: float, d: float) -> tuple[float, float]:
    lo = math.log((a + 0.5) / (c - a + 0.5)) - math.log((b + 0.5) / (d - b + 0.5))
    se = math.sqrt(1 / (a + 0.5) + 1 / (c - a + 0.5) + 1 / (b + 0.5) + 1 / (d - b + 0.5))
    return lo, lo / se


def chi2_p(x: float) -> float:
    """Valor-p do qui-quadrado com 1 grau de liberdade."""
    return math.erfc(math.sqrt(max(x, 0) / 2))


def _adjust(pvals: list[float], method: str) -> list[float]:
    m = len(pvals)
    if method == "none" or not m:
        return pvals
    if method == "bonferroni":
        return [min(1.0, p * m) for p in pvals]
    if method == "fdr":                               # Benjamini-Hochberg
        order = sorted(range(m), key=lambda i: pvals[i])
        adj = [0.0] * m
        prev = 1.0
        for rank in range(m, 0, -1):
            i = order[rank - 1]
            prev = min(prev, pvals[i] * m / rank)
            adj[i] = prev
        return adj
    raise ValueError("correction deve ser bonferroni, fdr ou none")


# ---------------------------------------------------------------------------
# Comparabilidade
# ---------------------------------------------------------------------------

def comparability(target: FreqTable, reference: FreqTable, unit: str, lang: str | None = None) -> list[dict]:
    """Avisos estruturados: {"code", "severity", "message", "params"}."""
    warns = []

    def add(code, severity, **params):
        warns.append({"code": code, "severity": severity, "params": params,
                      "message": t(f"keywords.warn.{code}", lang, **params)})

    tl, rl = target.meta.get("lang"), reference.meta.get("lang")
    if tl and rl and tl != rl:
        add("language_mismatch", "error", target=tl, reference=rl)
    tt, rt = target.meta.get("tool") or "", reference.meta.get("tool") or ""
    if unit in ("lemma", "pos", "word_pos") and tt and rt and tt != rt:
        add("tool_mismatch", "warning", target=tt, reference=rt)
    elif tt and tt == rt and target.meta.get("tool_version") != reference.meta.get("tool_version"):
        add("tool_version_mismatch", "info", tool=tt, target=target.meta.get("tool_version"),
            reference=reference.meta.get("tool_version"))
    elif unit in ("form", "ngram") and tt and rt and tt != rt:
        add("tokenizer_mismatch", "info", target=tt, reference=rt)
    if target.words < MIN_WORDS:
        add("small_target", "warning", words=target.words, minimum=MIN_WORDS)
    if reference.words < target.words:
        add("small_reference", "warning", words=reference.words)
    if unit == "lemma" and target.meta.get("missing_field"):
        add("unit_unavailable", "warning", unit=unit, field="lemma", tool=tt or "?")
    if reference.docs is None:
        add("no_reference_docs", "info")
    if target.doc_ids and target.doc_ids == reference.doc_ids:
        add("same_data", "error")
    return warns


# ---------------------------------------------------------------------------
# keywords
# ---------------------------------------------------------------------------

def keywords(
    project: TTWAProject,
    corpus_name: str,
    reference: str | Path | FreqTable,
    unit: str = "form",
    measure: str = "ll",
    n: int = 2,
    layer: str | None = None,
    where: Mapping | None = None,
    reference_where: Mapping | None = None,
    min_freq: int = 5,
    min_range: int = 1,
    correction: str = "bonferroni",
    alpha: float = 0.05,
    top: int | None = 100,
    both_directions: bool = True,
    lang: str | None = None,
    save: bool = True,
) -> dict:
    """Palavras-chave do alvo (`corpus_name` + `where`) contra `reference`:
    uma lista `.tsv`, o nome de outro corpus do projeto, `rest:<metadado>` (os
    documentos do mesmo corpus fora de `where`) ou uma FreqTable.

    Filtros: `min_freq` (no alvo, para itens do alvo; na referência, para os
    negativos) e `min_range` (textos do alvo em que o item aparece). Ordena pela
    `measure`; devolve também as demais medidas, p e p corrigido, e `warnings`.
    """
    if measure not in MEASURES:
        raise ValueError(f"medida deve ser uma de {MEASURES}")
    target = corpus_freqs(project, corpus_name, unit, n, layer, where)
    ref_id: str
    if isinstance(reference, FreqTable):
        ref, ref_id = reference, reference.meta.get("name", "tabela")
    elif str(reference).startswith("rest:"):
        if not where:
            raise ValueError("'rest:' pede um filtro `where` que defina o grupo-alvo")
        ref = corpus_freqs(project, corpus_name, unit, n, layer, exclude=where)
        ref_id = f"{corpus_name} (demais grupos)"
    elif Path(str(reference)).suffix.lower() in (".tsv", ".txt") and Path(str(reference)).is_file():
        ref = read_reference_list(reference)
        ref_id = f"{ref.meta.get('name', Path(str(reference)).stem)} {ref.meta.get('version', '')}".strip()
    else:
        ref = corpus_freqs(project, str(reference), unit, n, layer, reference_where)
        ref_id = str(reference)
    warnings = comparability(target, ref, unit, lang)
    c, d = target.words, ref.words
    if not c or not d:
        return {"target": corpus_name, "reference": ref_id, "rows": [], "warnings": warnings,
                "target_words": c, "reference_words": d}

    rows = []
    for item in set(target.counts) | (set(ref.counts) if both_directions else set()):
        a, b = target.counts.get(item, 0), ref.counts.get(item, 0)
        rng = target.docs.get(item, 0)
        over = a / c >= b / d
        if over and (a < min_freq or rng < min_range):
            continue
        if not over and (not both_directions or b < min_freq):
            continue
        ll = log_likelihood(a, b, c, d)
        lo, z = log_odds(a, b, c, d)
        rows.append({"item": item, "direction": "+" if over else "-", "freq_target": a, "freq_reference": b,
                     "per_1000_target": 1000 * a / c, "per_1000_reference": 1000 * b / d,
                     "range_target": rng, "range_reference": ref.docs.get(item, 0) if ref.docs is not None else None,
                     "ll": ll, "p": chi2_p(ll), "log_ratio": log_ratio(a, b, c, d),
                     "pct_diff": pct_diff(a, b, c, d) if b else None, "log_odds": lo, "z": z})
    for r, padj in zip(rows, _adjust([r["p"] for r in rows], correction)):
        r["p_adj"] = padj
        r["significant"] = padj < alpha
    key = {"ll": "ll", "log_ratio": "log_ratio", "pct_diff": "pct_diff", "log_odds": "log_odds"}[measure]
    rows.sort(key=lambda r: (r["direction"] != "+", -(abs(r[key]) if r[key] is not None else math.inf)))
    if top:
        pos = [r for r in rows if r["direction"] == "+"][:top]
        neg = [r for r in rows if r["direction"] == "-"][:top]
        rows = pos + neg
    result = {"target": corpus_name, "reference": ref_id, "unit": unit, "measure": measure,
              "correction": correction, "alpha": alpha, "target_words": c, "reference_words": d,
              "reference_card": {k: v for k, v in ref.meta.items() if k != "missing_field"},
              "warnings": warnings, "rows": rows}
    if save:
        project.save_analysis("keywords", result, name=f"{corpus_name} × {ref_id}",
                              params={"target": corpus_name, "where": dict(where or {}), "reference": ref_id,
                                      "reference_version": ref.meta.get("version"), "unit": unit, "measure": measure,
                                      "min_freq": min_freq, "min_range": min_range, "correction": correction})
    return result
