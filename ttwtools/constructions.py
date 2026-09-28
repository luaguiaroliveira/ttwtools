"""
constructions.py — construções como sequências de classes/etiquetas (menu "Escrita").

Em vez de contar palavras, compara **padrões** (n-gramas de UPOS ou XPOS) do texto do aluno
com a referência: `DT JJ NN`, `VBN by`, `MD VB`, etc. A unidade é o molde, não o lexema —
aproximação operacional da *Pattern Grammar* (Hunston & Francis) e ponte para a escrita.

O texto é etiquetado na hora com o mesmo etiquetador da referência (spaCy), para que as
classes sejam comparáveis. Cada padrão recebe significância (LL/p corrigido), magnitude
(log ratio/%DIFF), dispersão (em quantos textos da referência aparece) e um **z-score**
descritivo (taxa do padrão no texto vs distribuição dos textos da referência).
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Mapping

from .i18n import t
from .keyness import FreqTable, comparability, keyword_rows
from .project import TTWAProject
from .query import _layer_tokens, _select_layers

FIELDS = ("upos", "xpos")
MIN_PATTERN_WORDS = 100          # abaixo disto, o perfil de construções é só indicativo
_DEFAULT_MODEL = {"en": "en_core_web_sm", "pt": "pt_core_news_sm"}
_NON_WORD_POS = {"PUNCT", "SYM", "X", "SPACE", "SP"}


# ---------------------------------------------------------------------------
# Etiquetar o texto do aluno (mesmo tagger da referência, quando possível)
# ---------------------------------------------------------------------------

def tag_text(text: str, model: str | None = None, lang: str | None = None) -> list[dict]:
    """Tokens do texto com UPOS e XPOS (spaCy). Devolve [{word, upos, xpos}]."""
    from .models import activate
    from .taggers.spacy_pos import _load_spacy_pipeline, _tag_document_spacy_pos
    activate()                                       # modelos do catálogo entram no caminho
    model = model or _DEFAULT_MODEL.get((lang or "en")[:2], _DEFAULT_MODEL["en"])
    nlp = _load_spacy_pipeline(model)
    toks = _tag_document_spacy_pos(text, nlp, mode="upos")
    return [{"word": tk.get("word", ""), "upos": tk.get("upos", ""), "xpos": tk.get("ptb", ""),
             "start": tk.get("start_char"), "end": tk.get("end_char")} for tk in toks]


def _is_word_row(r: Mapping) -> bool:
    upos = r.get("upos") or ""
    if upos:
        return upos not in _NON_WORD_POS
    w = r.get("word") or ""
    return any(ch.isalpha() for ch in w)


def _pattern_items(rows: list[dict], field: str, n: int) -> tuple[list[str], int]:
    """n-gramas de etiquetas (ignorando pontuação) e o nº de palavras considerado."""
    tags = []
    for r in rows:
        if not _is_word_row(r):
            continue
        v = (r.get(field) or "").strip()
        if v:
            tags.append(v)
    items = [" ".join(tags[i:i + n]) for i in range(len(tags) - n + 1)]
    return items, len(tags)


# ---------------------------------------------------------------------------
# Padrões de um corpus da referência
# ---------------------------------------------------------------------------

def corpus_patterns(project: TTWAProject, corpus_name: str, field: str = "upos", n: int = 3,
                    layer: str | None = None, where: Mapping | None = None,
                    keep: set[str] | None = None) -> FreqTable:
    """FreqTable dos n-gramas de etiquetas de um corpus. Com `keep`, também guarda, por
    documento, a contagem desses padrões (`doc_counts`) e o tamanho de cada documento
    (`doc_words`) — é o que permite o z-score descritivo."""
    if field not in FIELDS:
        raise ValueError(f"campo deve ser um de {FIELDS}")
    sel = _select_layers(project, corpus_name, layer, where, "pos")
    counts, docs = Counter(), Counter()
    doc_words: dict = {}
    doc_counts: dict = {}
    words = 0
    for doc, rows in _layer_tokens(project, sel):
        items, w = _pattern_items([dict(r) for r in rows], field, n)
        c = Counter(items)
        counts.update(c)
        docs.update(c.keys())
        words += w
        doc_words[doc["id"]] = w
        if keep:
            doc_counts[doc["id"]] = Counter({k: v for k, v in c.items() if k in keep})
    tools = Counter()
    if sel:
        layer_rows = project._con.execute(
            f"SELECT tool, tool_version, model, config FROM layers WHERE id IN ({','.join('?' * len(sel))})",
            list(sel)).fetchall()
        for r in layer_rows:
            cfg = json.loads(r["config"])
            lang = cfg.get("lang") or (r["model"].split("_")[0] if r["model"] and "_" in r["model"] else None)
            tools[(r["tool"], r["tool_version"], r["model"], lang)] += 1
    tool, version, model, lang = tools.most_common(1)[0][0] if tools else ("", "", "", None)
    return FreqTable(counts, docs, words, len(sel),
                     {"name": corpus_name, "lang": lang, "tool": tool, "tool_version": version,
                      "model": model, "unit": field, "pattern_n": n},
                     frozenset(d["id"] for d in sel.values()), doc_words, doc_counts)


def text_patterns(text: str, field: str = "upos", n: int = 3, model: str | None = None,
                  lang: str | None = None, name: str = "Meu texto") -> FreqTable:
    """FreqTable dos padrões do texto do aluno."""
    rows = tag_text(text, model=model, lang=lang)
    items, words = _pattern_items(rows, field, n)
    counts = Counter(i for i in items if i)
    docs = Counter({k: 1 for k in counts})
    return FreqTable(counts, docs, words, 1, {"name": name, "unit": field, "pattern_n": n, "lang": lang})


# ---------------------------------------------------------------------------
# z-score descritivo: taxa do padrão no texto vs distribuição dos documentos
# ---------------------------------------------------------------------------

def _z_scores(ref: FreqTable, items: set[str]) -> dict:
    if not ref.doc_counts or not ref.doc_words:
        return {}
    import numpy as np
    out = {}
    word_counts = [w for w in ref.doc_words.values() if w > 0]
    for item in items:
        rates = [1000 * ref.doc_counts.get(d, Counter()).get(item, 0) / w
                 for d, w in ref.doc_words.items() if w > 0]
        if len(rates) < 2:
            continue
        mean = float(np.mean(rates))
        sd = float(np.std(rates))
        out[item] = {"mean": mean, "sd": sd}
    return out


# ---------------------------------------------------------------------------
# Análise
# ---------------------------------------------------------------------------

def analyze_patterns(project: TTWAProject, text: str, reference, field: str = "upos", n: int = 3,
                     measure: str = "log_ratio", min_freq: int = 2, correction: str = "fdr",
                     alpha: float = 0.05, top: int | None = 60, lang: str | None = None,
                     text_name: str = "Meu texto", filename: str | None = None,
                     z_scores: bool = True, layer: str | None = None) -> dict:
    """Perfil de construções (n-gramas de UPOS/XPOS) do texto contra um corpus de referência."""
    if field not in FIELDS:
        raise ValueError(f"campo deve ser um de {FIELDS}")
    if not isinstance(reference, FreqTable) and str(reference).endswith((".tsv", ".txt")):
        raise ValueError("patterns_need_corpus")     # listas de referência guardam palavras, não padrões
    if isinstance(reference, FreqTable):
        ref, ref_id = reference, reference.meta.get("name", "tabela")
    else:
        ref = corpus_patterns(project, str(reference), field, n, layer=layer)
        ref_id = str(reference)
    tool = (ref.meta.get("tool") or "").lower()
    if tool and "spacy" not in tool:
        raise ValueError(f"patterns_tagger_unsupported:{ref.meta.get('tool')}")
    model = ref.meta.get("model") or None
    msg_lang = lang                                    # idioma das mensagens
    text_lang = ref.meta.get("lang") or lang           # idioma do texto (= o da referência)
    target = text_patterns(text, field, n, model=model, lang=text_lang, name=text_name)

    warnings = comparability(target, ref, "pos", msg_lang)
    warnings = [w for w in warnings if w["code"] not in ("unit_unavailable",)]
    reliability = ["single_text"]
    if target.words < MIN_PATTERN_WORDS:
        reliability.append("short_text")
        warnings.append({"code": "writing_short_text", "severity": "warning",
                         "message": t("writing.warn.short_patterns", msg_lang, words=target.words),
                         "params": {"words": target.words}})

    rows = keyword_rows(target, ref, "pos", measure, min_freq, 1, correction, alpha, True)
    if z_scores and rows:
        items = {r["item"] for r in rows}
        ref2 = corpus_patterns(project, str(reference), field, n, layer=layer, keep=items) \
            if not isinstance(reference, FreqTable) else ref
        zs = _z_scores(ref2, items)
    else:
        zs = {}
    for r in rows:
        r["range_reference_pct"] = (100 * ref.docs.get(r["item"], 0) / ref.n_docs) if (ref.docs is not None and ref.n_docs) else None
        z = zs.get(r["item"])
        if z:
            sd = z["sd"] or 1e-9
            r["z_reference"] = (r["per_1000_target"] - z["mean"]) / sd
            r["per_1000_reference_doc_mean"] = z["mean"]
        else:
            r["z_reference"] = None
            r["per_1000_reference_doc_mean"] = None
        flags = []
        if r["freq_target"] < 3:
            flags.append("rare_in_text")
        if r["range_reference_pct"] is not None and r["range_reference_pct"] < 20:
            flags.append("concentrated_reference")
        if not r.get("significant"):
            flags.append("not_significant")
        r["flags"] = flags
    if top:
        pos = [r for r in rows if r["direction"] == "+"][:top]
        neg = [r for r in rows if r["direction"] == "-"][:top]
        rows = pos + neg
    return {"kind": "patterns", "text_name": text_name, "filename": filename,
            "target_words": target.words, "reference": ref_id, "reference_words": ref.words,
            "reference_documents": ref.n_docs, "reference_card": {k: v for k, v in ref.meta.items() if k != "missing_field"},
            "field": field, "n": n, "measure": measure, "correction": correction, "alpha": alpha,
            "reliability": reliability, "warnings": warnings, "rows": rows}
