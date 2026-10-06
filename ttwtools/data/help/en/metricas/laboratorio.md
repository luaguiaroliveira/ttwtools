---
titulo: Lab: comparing N groups
resumo: Experimental methods to compare three or more groups of texts by the features of a layer.
relacionados: cohens_d, keyness
---
[A **group** is a whole corpus or the texts of a corpus with a given metadata value (level, author, decade...)]{marca amarelo}. [Every method starts from the same table: each text with the frequency of each feature **per 1,000 words**]{marca amarelo}.

- **One against all:** Cohen's d of each group against all the others together. [Tells what sets each group apart]{marca verde}.
- **Pairwise:** Cohen's d for each pair; the matrix shows mean $\lvert d\rvert$ (larger = farther apart).
- **Features that vary across groups:** Kruskal-Wallis test per feature, with effect size ($\varepsilon^2$: 0.01 small, 0.08 medium, 0.26 large) and corrected p.
- **Profile space:** PCA of the texts, each point coloured by group.
- **Dendrogram:** clusters the groups' mean profiles (Ward, standardised features): who resembles whom.
- **My text against references:** the first group against each of the others; distance is the root mean $z^2$ (0 = same as the reference mean) and the features are those that set it farthest apart.

## Caveats
- [This is **exploratory**: the methods are under evaluation and the API may change]{marca rosa}.
- [Many features × many groups = many tests]{marca rosa}: look at effect sizes and corrected p.
- [Groups with fewer than 5 texts give unstable estimates]{marca rosa}; groups of very different sizes call for care (the kfa2 metric weights by size).
