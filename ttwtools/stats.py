"""
stats.py — Estatísticas descritivas do corpus (novomodelo.md §12).

    describe(projeto, "corpus")                  # só texto: estimativas, sem tagger (§12.1)
    describe(projeto, "corpus", layer="spacy")   # + classes, densidade lexical, frases, lemas (§12.2)

Sem camada, os números vêm da tokenização simples do corpus (corpus.tokenize) e
são **estimativas**: um tagger pode separar as palavras de outro jeito. Palavras
= tokens com letras; types contados em minúsculas. O resultado é guardado em
`analyses` e reaproveitado enquanto textos, camadas e parâmetros não mudarem.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

from .corpus import TokenizerConfig, filter_documents, get_tokenizer_config, tokenize
from .project import TTWAProject

_STOP_DIR = Path(__file__).parent / "data" / "stopwords"
_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_SENT_RE = re.compile(r"[.!?]+(?=[\s\"'”’)\]]|$)")
CONTENT_UPOS = {"NOUN", "PROPN", "VERB", "ADJ", "ADV"}
NON_WORD_UPOS = {"PUNCT", "SYM", "X", "SPACE"}


# ---------------------------------------------------------------------------
# Stopwords
# ---------------------------------------------------------------------------

def stopword_languages() -> list[str]:
    return sorted(p.stem for p in _STOP_DIR.glob("*.txt"))


def guess_language(project: TTWAProject, corpus_name: str, sample_docs: int = 20) -> str | None:
    """Idioma do corpus: o das camadas (modelo en_*/pt_*, Stanza lang), senão o que tiver
    mais palavras funcionais numa amostra do texto (entre os idiomas com lista)."""
    import re as _re
    from .keyness import _lang_of
    langs = Counter()
    for r in project._con.execute(
            "SELECT l.tool, l.model, l.config FROM layers l JOIN documents d ON d.id = l.doc_id WHERE d.corpus_name = ?",
            (corpus_name,)):
        lang = _lang_of(r["tool"], r["model"] or "", json.loads(r["config"] or "{}"))
        if lang:
            langs[lang] += 1
    if langs:
        return langs.most_common(1)[0][0]
    words: Counter = Counter()
    for d in filter_documents(project, corpus_name)[:sample_docs]:
        text = project.get_corpus_file(corpus_name, d["filename"]) or ""
        words.update(w.lower() for w in _re.findall(r"\w+", text[:5000]))
    if not words:
        return None
    scores = {lang: sum(words[w] for w in stopwords(lang)) for lang in stopword_languages()}
    best = max(scores, key=scores.get)
    return best if scores[best] else None


def stopwords(lang: str = "en", add: Iterable[str] | None = None, replace: Iterable[str] | None = None) -> set[str]:
    """Lista de palavras funcionais do idioma (data/stopwords/<lang>.txt), com
    palavras acrescentadas (`add`) ou uma lista própria no lugar (`replace`)."""
    if replace is not None:
        return {w.lower() for w in replace}
    path = _STOP_DIR / f"{lang}.txt"
    if not path.is_file():
        raise ValueError(f"sem lista de stopwords para '{lang}' (há: {', '.join(stopword_languages())})")
    words = {w.lower() for line in path.read_text(encoding="utf-8").splitlines()
             if not line.startswith("#") for w in line.split()}
    return words | {w.lower() for w in (add or [])}


# ---------------------------------------------------------------------------
# Medidas
# ---------------------------------------------------------------------------

def ttr(tokens: list[str]) -> float | None:
    return len(set(tokens)) / len(tokens) if tokens else None


def cttr(tokens: list[str]) -> float | None:
    """TTR corrigida de Carroll: types / sqrt(2 × tokens)."""
    return len(set(tokens)) / math.sqrt(2 * len(tokens)) if tokens else None


def sttr(docs: list[list[str]], block: int) -> float | None:
    """TTR padronizada: média da TTR de blocos consecutivos de `block` palavras
    dentro de cada documento (blocos incompletos ficam de fora)."""
    values = [len(set(d[i:i + block])) / block for d in docs for i in range(0, len(d) - block + 1, block)]
    return statistics.fmean(values) if values else None


def mattr(docs: list[list[str]], window: int) -> float | None:
    """TTR média móvel (Covington & McFall): média da TTR de todas as janelas de
    `window` palavras de cada documento; documentos menores que a janela usam a TTR simples."""
    values = []
    for d in docs:
        if len(d) >= window:
            counts = Counter(d[:window])
            values.append(len(counts) / window)
            for i in range(window, len(d)):
                out_w = d[i - window]
                counts[out_w] -= 1
                if not counts[out_w]:
                    del counts[out_w]
                counts[d[i]] += 1
                values.append(len(counts) / window)
        elif d:
            values.append(len(set(d)) / len(d))
    return statistics.fmean(values) if values else None


def _summary(values: list[float]) -> dict:
    if not values:
        return {"min": None, "median": None, "max": None, "mean": None, "stdev": None}
    return {"min": min(values), "median": statistics.median(values), "max": max(values),
            "mean": statistics.fmean(values), "stdev": statistics.stdev(values) if len(values) > 1 else 0.0}


# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------

def _state_hash(project: TTWAProject, docs: list[dict], layer: str | None) -> str:
    h = hashlib.sha256()
    for d in docs:
        h.update(f"{d['id']}:{d['content_hash']};".encode())
    if layer:
        rows = project._con.execute(
            f"SELECT id, config_hash, text_hash FROM layers WHERE tool = ? AND doc_id IN ({','.join('?' * len(docs))})"
            " ORDER BY id", (layer, *[d["id"] for d in docs])).fetchall() if docs else []
        for r in rows:
            h.update(f"{r['id']}:{r['config_hash']}:{r['text_hash']};".encode())
    return h.hexdigest()[:16]


def _text_stats(project: TTWAProject, corpus_name: str, docs: list[dict], tok_cfg: TokenizerConfig,
                top: int, block: int, window: int, stop: set[str] | None) -> dict:
    cfg = TokenizerConfig(lowercase=True, keep_punct=False, keep_numbers=False, contractions=tok_cfg.contractions)
    per_doc = []
    streams: list[list[str]] = []
    word_lengths = 0
    n_sent = 0
    for d in docs:
        text = project.get_corpus_file(corpus_name, d["filename"])
        if text is None:
            per_doc.append({"filename": d["filename"], "missing_text": True})
            continue
        words = [w for w in tokenize(text, cfg) if _HAS_LETTER.search(w)]
        sents = len(_SENT_RE.findall(text)) or (1 if words else 0)
        streams.append(words)
        word_lengths += sum(len(w) for w in words)
        n_sent += sents
        per_doc.append({"filename": d["filename"], "tokens": len(words), "types": len(set(words)),
                        "ttr": ttr(words), "sentences": sents})
    all_words = [w for s in streams for w in s]
    freq = Counter(all_words)
    shown = [(w, n) for w, n in freq.most_common() if not stop or w not in stop]
    sizes = [p["tokens"] for p in per_doc if "tokens" in p]
    return {
        "estimated": True,
        "documents": len(docs),
        "tokens": len(all_words),
        "types": len(freq),
        "hapax": sum(1 for n in freq.values() if n == 1),
        "ttr": ttr(all_words),
        "sttr": sttr(streams, block),
        "sttr_block": block,
        "cttr": cttr(all_words),
        "mattr": mattr(streams, window),
        "mattr_window": window,
        "mean_word_length": word_lengths / len(all_words) if all_words else None,
        "sentences": n_sent,
        "mean_sentence_length": len(all_words) / n_sent if n_sent else None,
        "document_tokens": _summary(sizes),
        "top_words": [{"word": w, "freq": n} for w, n in shown[:top]],
        "zipf": [n for _, n in freq.most_common(1000)],
        "per_document": per_doc,
    }


def _layer_stats(project: TTWAProject, corpus_name: str, layer: str, top: int, where) -> dict:
    from .formats.common import document_layers, sentences_of
    upos, xpos, tags = Counter(), Counter(), Counter()
    lemmas: dict[str, Counter] = {}
    sent_lengths: list[int] = []
    per_doc_tags: list[tuple[int, Counter]] = []
    n_words = n_content = n_docs = 0
    for doc, lay in document_layers(project, corpus_name, layer, where):
        toks = project.get_tokens(lay["id"])
        n_docs += 1
        doc_tags = Counter()
        doc_words = 0
        for t in toks:
            if t["upos"]:
                upos[t["upos"]] += 1
            if t["xpos"]:
                xpos[t["xpos"]] += 1
            for tag in t["tags"]:
                tags[tag] += 1
                doc_tags[tag] += 1
            is_word = (t["upos"] not in NON_WORD_UPOS) if t["upos"] else bool(t["word"] and _HAS_LETTER.search(t["word"]))
            if is_word:
                doc_words += 1
                if t["upos"] in CONTENT_UPOS:
                    n_content += 1
                if t["lemma"] and t["upos"] in CONTENT_UPOS:
                    lemmas.setdefault(t["upos"], Counter())[t["lemma"].lower()] += 1
        n_words += doc_words
        for s in sentences_of(toks):
            n = sum(1 for t in s if (t["upos"] not in NON_WORD_UPOS if t["upos"] else _HAS_LETTER.search(t["word"] or "")))
            if n:
                sent_lengths.append(n)
        per_doc_tags.append((doc_words, doc_tags + Counter({f"UPOS:{k}": v for k, v in
                                                            Counter(t["upos"] for t in toks if t["upos"]).items()})))
    # média e desvio por documento (por 1000 palavras) das classes/tags mais frequentes
    main = [k for k, _ in (tags or Counter()).most_common(top)] + [f"UPOS:{k}" for k, _ in upos.most_common(top)]
    spread = []
    for key in main:
        rates = [1000 * c[key] / w for w, c in per_doc_tags if w]
        if rates:
            spread.append({"feature": key, "mean_per_1000": statistics.fmean(rates),
                           "stdev_per_1000": statistics.stdev(rates) if len(rates) > 1 else 0.0})
    return {
        "layer": layer,
        "documents": n_docs,
        "words": n_words,
        "upos": dict(upos.most_common()),
        "xpos": dict(xpos.most_common()),
        "tags": dict(tags.most_common()),
        "lexical_density": n_content / n_words if upos and n_words else None,
        "sentences": len(sent_lengths),
        "sentence_length": _summary(sent_lengths),
        "top_lemmas": {cls: [{"lemma": l, "freq": n} for l, n in c.most_common(top)] for cls, c in sorted(lemmas.items())},
        "per_document": spread,
    }


def describe(
    project: TTWAProject,
    corpus_name: str,
    layer: str | None = None,
    where: Mapping | None = None,
    top: int = 20,
    sttr_block: int = 1000,
    mattr_window: int = 50,
    hide_stopwords: bool = False,
    stopwords_lang: str | None = None,
    extra_stopwords: Iterable[str] | None = None,
    own_stopwords: Iterable[str] | None = None,
    use_cache: bool = True,
    cache_only: bool = False,
) -> dict | None:
    """Estatísticas do corpus (§12.1) e, com `layer` (ferramenta: spacy, stanza...), da camada (§12.2).

    Devolve {"text": {...}, "layer": {...} ou None, "cached": bool}. `hide_stopwords`
    tira as palavras funcionais da lista de mais frequentes (não das contagens).
    `cache_only` devolve só o resultado guardado (ou None), sem calcular.
    """
    docs = filter_documents(project, corpus_name, where)
    if hide_stopwords and not stopwords_lang:
        stopwords_lang = guess_language(project, corpus_name) or "en"
    stop = stopwords(stopwords_lang, extra_stopwords, own_stopwords) if hide_stopwords else None
    tok_cfg = get_tokenizer_config(project, corpus_name)
    params = {"corpus": corpus_name, "layer": layer, "where": dict(where or {}), "top": top,
              "sttr_block": sttr_block, "mattr_window": mattr_window, "tokenizer": tok_cfg.to_dict(),
              "stopwords": sorted(stop) if stop else None, "state": _state_hash(project, docs, layer)}
    if use_cache:
        for a in reversed(project.list_analyses("describe")):
            if a["params"] == json.loads(json.dumps(params, sort_keys=True)):
                return {**project.load_analysis(a["id"])["result"], "cached": True}
    if cache_only:
        return None
    result = {
        "text": _text_stats(project, corpus_name, docs, tok_cfg, top, sttr_block, mattr_window, stop),
        "layer": _layer_stats(project, corpus_name, layer, top, where) if layer else None,
    }
    project.save_analysis("describe", result, params=params, name=corpus_name)
    return {**result, "cached": False}
