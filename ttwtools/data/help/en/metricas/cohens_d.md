---
titulo: Cohen's d
resumo: Size of the difference between two groups, in standard deviations. The measure used by KFA.
relacionados: normalizacao_por_mil, tagset_biber
---
**Cohen's d** tells how far apart the means of two groups are, in standard deviations:

    d = (mean₁ − mean₂) / pooled standard deviation

In KFA (Biber & Egbert) each feature is counted per text (per 1,000 words) and d compares corpus 1 with corpus 2. KFA's default pooled SD is √((s₁² + s₂²)/2); the "KFA2" variant weights by group size.

## How to read
- **Sign:** positive = the feature is more frequent in corpus 1; negative = in corpus 2.
- **Size** (Cohen's convention): ~0.2 small, ~0.5 medium, ~0.8 or more large.
- A d of 1.0 means the means are one standard deviation apart: the distributions still overlap a lot.

## Caveats
- With few texts per group, d is unstable: one atypical text changes it a lot.
- d does not say whether a difference is "significant"; it measures size, not evidence.
- Rare features (almost always zero) can give a large d by chance.
