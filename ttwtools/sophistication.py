"""
sophistication.py — riqueza lexical e tamanho de frase para a Escrita, sem dependências.

Medidas robustas ao tamanho do texto (para não premiar textos longos):
    ttr      razão tipos/tokens (simples, sensível ao tamanho)
    guiraud  tipos / sqrt(tokens) (Guiraud 1954), menos sensível
    mtld     Measure of Textual Lexical Diversity (McCarthy & Jarvis 2010)
    sent     comprimento médio de frase (palavras por frase)
    long_pct % de palavras com 7+ letras (proxy de sofisticação)
Não é legibilidade (fórmulas de sílaba/idioma ficam para depois, com libs específicas).
"""

from __future__ import annotations

import re

from .corpus import TokenizerConfig, tokenize

_SENT = re.compile(r"[.!?…]+")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def _words(text: str, tokenizer: TokenizerConfig | None = None) -> list[str]:
    return [t.lower() for t in tokenize(text, tokenizer) if _LETTER.search(t)]


def mtld(tokens: list[str], threshold: float = 0.72) -> float | None:
    """MTLD (média das passagens direta e reversa); None se o texto for curto demais."""
    if len(tokens) < 50:
        return None

    def one_pass(seq: list[str]) -> float:
        factors = 0.0
        types: set[str] = set()
        count = 0
        for t in seq:
            types.add(t)
            count += 1
            if len(types) / count < threshold:
                factors += 1
                types, count = set(), 0
        if count:
            ttr = len(types) / count
            if ttr < 1:
                factors += (1 - ttr) / (1 - threshold)
        return factors

    fwd = one_pass(tokens)
    rev = one_pass(list(reversed(tokens)))
    if fwd == 0 or rev == 0:
        return None
    return (len(tokens) / fwd + len(tokens) / rev) / 2


def lexical_profile(text: str, tokenizer: TokenizerConfig | None = None) -> dict:
    """Perfil lexical e de frases de um texto (descritivo)."""
    words = _words(text, tokenizer)
    n = len(words)
    types = len(set(words))
    sentences = [s for s in _SENT.split(text) if _words(s)]
    long_pct = (100 * sum(1 for w in words if len(w) >= 7) / n) if n else 0.0
    return {
        "words": n, "types": types,
        "ttr": (types / n) if n else 0.0,
        "guiraud": (types / (n ** 0.5)) if n else 0.0,
        "mtld": mtld(words),
        "sentences": len(sentences),
        "mean_sentence_len": (n / len(sentences)) if sentences else 0.0,
        "long_pct": long_pct,
    }
