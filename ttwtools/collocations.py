"""
collocations.py — perfis de colocação: como o texto do aluno combina uma palavra em
comparação com a referência (menu "Escrita").

Colocado é a palavra que anda junto. Comparar os colocados de um nó (`analysis`) no texto
do aluno e na referência mostra escolhas de combinabilidade — algo que a contagem isolada de
palavras esconde. Medidas de associação e log ratio vêm do mesmo arsenal de `keyness`.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping

from .corpus import TokenizerConfig, get_tokenizer_config, tokenize
from .keyness import log_likelihood, log_ratio
from .project import TTWAProject
from .query import collocates as _ref_collocates

_WORD = lambda s: any(ch.isalpha() for ch in s)   # noqa: E731


def _words(text: str, tokenizer: TokenizerConfig | None = None) -> list[str]:
    return [t.lower() for t in tokenize(text, tokenizer) if _WORD(t)]


def _hits(words: list[str], node: str) -> list[tuple[int, int]]:
    """Ocorrências de `node` (palavra ou expressão, com `*` no fim): (início, fim)."""
    node = node.lower().strip()
    prefix = node.endswith("*")
    parts = node.rstrip("*").split()
    out = []
    if len(parts) == 1:
        for i, w in enumerate(words):
            if (w.startswith(parts[0]) if prefix else w == parts[0]):
                out.append((i, i))
    else:
        n = len(parts)
        for i in range(len(words) - n + 1):
            if words[i:i + n] == parts:
                out.append((i, i + n - 1))
    return out


def text_collocates(text: str, node: str, window: tuple[int, int] = (5, 5),
                    tokenizer: TokenizerConfig | None = None) -> dict:
    """Colocados de `node` no texto: contagens e nº de palavras."""
    words = _words(text, tokenizer)
    left, right = window
    hits = _hits(words, node)
    observed: Counter = Counter()
    for i, e in hits:
        for j in range(max(0, i - left), min(len(words), e + right + 1)):
            if i <= j <= e:
                continue
            observed[words[j]] += 1
    return {"node_freq": len(hits), "words": len(words), "observed": observed}


def collocate_profile(project: TTWAProject, text: str, node: str, reference,
                      unit: str = "form", window: tuple[int, int] = (5, 5), top: int = 30,
                      min_freq: int = 2, layer: str | None = None, lang: str | None = None,
                      text_name: str = "Meu texto") -> dict:
    """Compara os colocados de `node` no texto do aluno e na referência."""
    if unit != "form":
        raise ValueError("por enquanto a colocação da Escrita usa a unidade forma")
    ref = _ref_collocates(project, str(reference), node, window, unit, layer=layer,
                          min_freq=1, top=400, sort="ll")
    tokenizer = get_tokenizer_config(project, str(reference)) if not layer else None
    txt = text_collocates(text, node, window, tokenizer)
    tt, tr = txt["words"], ref["corpus_words"]
    ref_by = {r["collocate"]: r for r in ref["rows"]}
    items = set(txt["observed"]) | set(ref_by)
    rows = []
    for c in items:
        ft = txt["observed"].get(c, 0)
        fr = ref_by.get(c, {}).get("freq", 0)
        if max(ft, fr) < min_freq:
            continue
        rows.append({"collocate": c, "freq_text": ft, "freq_reference": fr,
                     "per_1000_text": 1000 * ft / tt if tt else 0.0,
                     "per_1000_reference": 1000 * fr / tr if tr else 0.0,
                     "log_ratio": log_ratio(ft, fr, tt or 1, tr or 1),
                     "ll": log_likelihood(ft, fr, tt or 1, tr or 1),
                     "mi": ref_by.get(c, {}).get("mi"), "position": ref_by.get(c, {}).get("position")})
    for r in rows:
        r["only_in_text"] = r["freq_reference"] == 0 and r["freq_text"] > 0
        r["typical_reference"] = r["freq_reference"] >= min_freq and (r["ll"] >= 3.84)
    rows.sort(key=lambda r: (r["freq_text"] == 0, -r["per_1000_text"], -r["per_1000_reference"]))
    return {"kind": "collocations", "text_name": text_name, "node": node,
            "node_freq_text": txt["node_freq"], "node_freq_reference": ref["node_freq"],
            "target_words": tt, "reference": str(reference), "reference_words": tr,
            "unit": unit, "window": list(window), "rows": rows[:top]}
