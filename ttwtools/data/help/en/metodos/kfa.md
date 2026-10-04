---
titulo: Key-Feature Analysis (KFA)
resumo: Compares two sets of texts feature by feature, by effect size (Cohen's d).
relacionados: cohens_d, normalizacao_por_mil, tagset_biber, keyness
---
**Key-Feature analysis** (KF analysis, by Egbert and Biber) compares two sets of texts — two corpora or two groups of the same corpus — and shows which **lexico-grammatical features** (tenses, pronouns, passives, modals...) characterise each side. It answers the question "what distinguishes this register from that one?".

## How it works
KF analysis follows six steps:
1. Define the two sides of the comparison (target × reference, or two groups).
2. Select features **motivated by a linguistic question** — preferably features already used in the literature, not the whole tag repertory.
3. Count each feature **in each text** and normalise (e.g. per 1,000 words).
4. Compute the mean and standard deviation of the feature on each side.
5. Compute the feature's **Cohen's d**: the difference between the means expressed in standard deviations.
6. Rank the features by d and interpret the extremes with examples from the texts themselves.

The key point is that the unit of observation is the **text**, not the whole corpus. Comparing only overall frequencies loses the variation from text to text; KFA measures that variation in the denominator of d. A feature is therefore "key" only when it is used **consistently more** on one side, beyond that normal variation.

## How to read
- **Sign:** positive = the feature is more frequent on side 1; negative = on side 2.
- **Size** (Cohen's convention): |d| ~ 0.2 small; ~ 0.5 medium; 0.8 or more large. These are only guidelines: in short texts, large effects may be accidental.
- KFA is **exploratory**: it ranks features by effect size but does not decide "significant / not significant" as a hypothesis test does.
- Compare with the alternatives: keyword and key-tag analysis compare whole-corpus frequencies; Multidimensional (MD) analysis looks for dimensions that vary together. KFA sits in between: as simple as keyness but looking at each text, like MD.

## Caveats
- KFA does **not** test significance: the value of d says nothing about whether the difference could be due to chance.
- Rare features (almost always zero) can give a large d by chance; a high d is not automatically "important".
- Feature selection matters: including dozens of features only raises the chance of spurious differences. Prefer interpretable features.
- Every value is relative to the chosen reference corpus.
- Always interpret the number together with real examples from the texts (open the KWIC or the Reader), never from the bar alone.

## References
- EGBERT, J.; BIBER, D. Key feature analysis: a simple, yet powerful method for comparing text varieties. *Corpora*, v. 18, n. 1, p. 121–133, 2023.
- BIBER, D.; EGBERT, J. *Register Variation Online*. Cambridge: Cambridge University Press, 2018.
- BIBER, D. *Variation across Speech and Writing*. Cambridge: Cambridge University Press, 1988.
- BREZINA, V. *Statistics in Corpus Linguistics: A Practical Guide*. Cambridge: Cambridge University Press, 2018.
