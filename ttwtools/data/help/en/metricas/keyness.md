---
titulo: Keywords (keyness)
resumo: What is characteristic of a corpus when compared with a reference.
relacionados: normalizacao_por_mil, dispersao, kwic
---
[A **keyword** is more (or less) frequent in the target corpus than the reference would lead us to expect]{marca amarelo}. Two different questions:

- **Is there evidence of a difference?** → [*log-likelihood* (LL)]{sublinhado azul}. With 1 degree of freedom, $LL > 3.84$ corresponds to $p < 0.05$ (before correction).
- **How big is the difference?** → [*log ratio*: 1 = twice as frequent, 2 = four times, −1 = half]{sublinhado azul}, that is, $\log_2 (f_{\text{target}} / f_{\text{ref}})$. *%DIFF* says the same as a percentage; *log-odds* also gives a z.

## How to read
- [Look at evidence (LL, corrected p) **and** size (log ratio) together]{marca verde}: [very frequent words get a high LL even with a small difference]{marca rosa}.
- [Items marked "−" are characteristic of the reference]{marca verde}.

## Caveats
- [The reference shapes the result]{marca rosa}: a general one shows genre and topic; one of the same genre shows finer differences.
- Compare corpora tagged the same way (same tagger and version) when using lemmas or classes; the app warns when that is not the case.
- [Use the dispersion filter (minimum number of texts) so that words from a single text do not stand out]{marca rosa}.
