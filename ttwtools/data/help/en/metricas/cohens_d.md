---
titulo: Cohen's d
resumo: Size of the difference between two groups, in standard deviations. The measure used by KFA.
relacionados: kfa, desvio_padrao, normalizacao_por_mil, tagset_biber
---
**Cohen's d** is a measure of [**effect size**]{sublinhado azul}: [it tells how far apart the means of two groups are, in standard-deviation units]{marca amarelo}. It was proposed by Jacob Cohen (1988) and is the measure KFA uses to compare two sets of texts.

In corpus analysis, the "group" is a set of texts and the "observation" is the feature's rate in each text, usually per 1,000 words:

$$d = \frac{\text{mean}_1 - \text{mean}_2}{\text{pooled standard deviation}}$$

[The numerator is the **signal**: how far apart the two sides are]{sublinhado azul}. [The denominator is the **noise**: how much the texts vary inside each side]{sublinhado azul}. So [d is a signal-to-noise ratio]{sublinhado azul} — [a large d means the difference between the sides is large *relative to* the variation among texts]{marca amarelo}.

## The pooled standard deviation
There are two ways to combine the two sides' standard deviations; the choice depends on whether the sides have the same number of texts:

- **KFA (Biber & Egbert):** simple average of the variances — $S_{\text{pooled}} = \sqrt{\frac{s_1^2 + s_2^2}{2}}$; use when the two sides have the [**same number of texts**]{sublinhado azul}.
- **Weighted KFA:** weights each variance by the number of texts on that side — $S_{\text{pooled}} = \sqrt{\frac{(n_1 - 1)\,s_1^2 + (n_2 - 1)\,s_2^2}{n_1 + n_2 - 2}}$; recommended when the sides have [**different numbers of texts**]{sublinhado azul}.

## A worked example
Egbert and Biber (2023) compare communication verbs in personal blogs (side 1) and other online registers (side 2). Mean₁ = 61.53 (s₁ = 27.23) and mean₂ = 26.48 (s₂ = 23.08):

$$S_{\text{pooled}} = \sqrt{\frac{27.23^2 + 23.08^2}{2}} = 25.24$$

$$d = \frac{61.53 - 26.48}{25.24} = 1.39$$

[A d of 1.39 is a large effect]{marca verde}: the blogs' mean is about 1.4 standard deviations above the other registers'.

## How to read
- **Sign:** [positive = the feature is more frequent on side 1; negative = on side 2]{marca verde}.
- **Size** (Cohen's convention): [~0.2 small, ~0.5 medium, ~0.8 or more large]{marca verde}.
- d is continuous and comparable across features, whether they are rare or frequent.
- [A d of 1.0 means the means are one standard deviation apart: the distributions still overlap a lot]{marca verde}.
- The interactive chart "How Cohen's d changes" shows that overlap as d varies.

## Caveats
- [d is **not** a significance test]{sublinhado vermelho}: it measures the size of the difference, not the evidence that it exists. Significance, practical importance and linguistic meaningfulness are distinct things (Brezina 2018).
- [With few texts per side, d is unstable]{marca rosa}: one atypical text changes it a lot. Ideally also report a confidence interval.
- The calculation assumes roughly normal rates and similar variances. Many features have many zeros and a few high values (a skewed distribution); there d is only an approximation, and a robust version exists (trimmed means and winsorized standard deviations).
- [Rare features (almost always zero) can give a large d by chance]{marca rosa}.
- [Always interpret d together with examples from the texts, not from the number alone]{marca rosa}.

## References
- BREZINA, V. *Statistics in Corpus Linguistics: A Practical Guide*. Cambridge: Cambridge University Press, 2018. (ch. 6 and 8: effect size, d and r)
- EGBERT, J.; BIBER, D. Key feature analysis: a simple, yet powerful method for comparing text varieties. *Corpora*, v. 18, n. 1, p. 121–133, 2023.
- GRIES, S. Th. *Statistics for Linguistics with R: A Practical Introduction*. 2nd ed. Berlin: De Gruyter Mouton, 2013.
- COHEN, J. *Statistical Power Analysis for the Behavioral Sciences*. 2nd ed. Hillsdale: Erlbaum, 1988.
