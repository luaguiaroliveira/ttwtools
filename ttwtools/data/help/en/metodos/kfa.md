---
titulo: Key Feature Analysis (KFA)
resumo: Quantitative method that identifies the [lexico-grammatical features that distinguish]{marca amarelo} two text varieties, using Cohen's d.
relacionados: desvio_padrao, cohens_d, normalizacao_por_mil, tagset_biber, keyness
---
> **In one sentence:** KF analysis is a [quantitative method]{sublinhado azul} for identifying the lexico-grammatical features that distinguish two text varieties.

**Definition.** KF analysis (Key Feature Analysis, by Egbert and Biber) is an exploratory, quantitative method for comparing two text varieties (corpora or sub-corpora). It works with a set of [functionally motivated lexico-grammatical features]{sublinhado azul}, [measures the rate of occurrence of each feature in every text]{marca amarelo}, and identifies the features that distinguish the two varieties using Cohen's *d*, which expresses [the difference between the two corpora relative to the variation across texts]{marca amarelo}.

**How to use this page.** Click a box title for an extra explanation, and [move the sliders in section 4]{marca verde} to see how *d* changes.

---

## 1. The 30-second answer
| Step | Question            | Answer                                                                                                             |
| :--- | :------------------ | :----------------------------------------------------------------------------------------------------------------- |
| 1    | What do I have?     | Two text varieties (corpora) and a set of functionally motivated features                                          |
| 2    | What do I want?     | The lexico-grammatical features that distinguish the two varieties                                                 |
| 3    | How is it measured? | The difference between the two corpora, standardized by how much the feature varies across texts (**Cohen's *d***) |
| 4    | How do I read it?   | Big $\lvert d\rvert$ = strong marker of one corpus; small $\lvert d\rvert$ = similar in both                       |

## 2. When to use it
- Comparing two registers or text varieties.
- Comparing two platforms, authors, or groups.
- Choosing features to teach or to analyze further.

:::details How is it different from a keyword analysis?
A keyword analysis looks for words (or POS tags) that are significantly over- or under-used across a whole corpus. KF analysis [works **per text**, with **functionally selected features**, and reports an **effect size**]{marca amarelo} (how large the difference is), [not a yes/no significance decision]{marca rosa}.
:::

## 3. Cohen's *d* in KF analysis: the idea
In KF analysis, [we calculate a Cohen's *d* value for **each feature**]{marca amarelo}, and every value compares the same feature in two corpora. The x-axis is the rate of the feature in a text; each text of a corpus contributes one point, and the curve is the distribution of those rates. The two curves are the same feature measured in Corpus 1 and Corpus 2, never two different features.
- [**The center of the curve**]{sublinhado azul} is the mean (M): the average rate of the feature across the texts of that corpus.
- [**The width of the curve**]{sublinhado azul} is the spread of the rates around that mean, summarized by the standard deviation (SD): how much the feature varies from text to text.
- [$d = \dfrac{\text{difference between the two means}}{\text{spread}}$]{marca amarelo}. A large $\lvert d\rvert$ [means the feature is distinctive of one corpus compared with the other]{marca verde}.

:::details Why divide by the spread?
[The spread is the ruler]{sublinhado azul}. [The same gap between the two means counts for more when the texts are consistent (small spread) and for less when the texts are heterogeneous (large spread)]{marca verde}. A gap of 3 occurrences per 1,000 words is a strong marker if the texts vary by about 2, but a weak one if they vary by about 15.
:::

## 4. How *d* is calculated (step by step)
$$d = \frac{M_1 - M_2}{SD_{\text{pooled}}}$$

- **$M_1$, $M_2$**: the means of the feature (the average rate across texts) in the two corpora.
- **$SD_{\text{pooled}}$**: the pooled standard deviation, [a single number for how much the texts vary inside the two corpora]{marca amarelo}. It is the denominator of *d*, so [it sets the unit (the ruler) in which the difference between the means is measured]{marca verde}. See the **Standard Deviation (SD)** card.

$$SD_{\text{pooled}} = \sqrt{\frac{SD_1^2 + SD_2^2}{2}}$$

**Worked example.** Feature: first-person pronouns (per 1,000 words).
- Corpus 1 rates: 2, 4, 6 → mean 4.
- Corpus 2 rates: 5, 7, 9 → mean 7.

:::details Step 1. The means
$M_1 = 4$; $M_2 = 7$.
:::
:::details Step 2. The gap (numerator)
$M_1 - M_2 = 4 - 7 =$ **$-3$**. [The negative sign means the feature is more frequent in **Corpus 2**]{marca verde}.
:::
:::details Step 3. The spread (denominator)
Each corpus has a standard deviation of 2. The pooled standard deviation is $\sqrt{(2^2 + 2^2)/2} =$ **$2$**.
:::
:::details Step 4. Divide
$d = -3/2 =$ **$-1.5$** → [a large effect: the feature is strongly distinctive of Corpus 2]{marca verde}.
:::

**Try it.** Move the sliders to see how the two means and the pooled standard deviation change *d*.

::cohen-widget::

## 5. Reading the value of *d*
| $\lvert d\rvert$ | Reading | Overlap between the corpora |
| :--------------- | :------ | :-------------------------- |
| < 0.20           | not key | almost complete             |
| ≈ 0.20           | small   | high                        |
| ≈ 0.50           | medium  | moderate                    |
| ≥ 0.80           | large   | low                         |

- [The **sign** gives the direction: **positive → Corpus 1**, **negative → Corpus 2**]{marca verde}.
- [These cut-offs are conventions, not fixed laws]{marca rosa}.

:::details Can a rare feature be key?
Yes. [A rare feature can be strongly key if it is used consistently in one corpus and almost absent in the other]{marca amarelo}. [Frequency alone does not decide keyness]{marca amarelo}.
:::

## 6. Which method: kfa or wkfa?
| Your two corpora           | Use                   |
| :------------------------- | :-------------------- |
| same number of texts       | **kfa** (Biber, 2023) |
| different numbers of texts | **wkfa** (*weighted key feature analysis*)   |

:::details What changes in wkfa?
In wkfa (*weighted key feature analysis*), the pooled standard deviation is [**weighted by corpus size**]{sublinhado azul}:

$$SD_{\text{pooled}} = \sqrt{\frac{(n_1 - 1)\,SD_1^2 + (n_2 - 1)\,SD_2^2}{n_1 + n_2 - 2}}$$

[The larger corpus gets more weight, because its estimate of variation is more reliable]{marca verde}.
:::

## 7. Check yourself
:::details 1) A feature has *d* = 0.05. Is it key?
No. $\lvert d\rvert$ is below 0.20 (negligible).
:::
:::details 2) *d* = −0.70. Which corpus uses the feature more?
Corpus 2 (the sign is negative).
:::
:::details 3) Feature A has $\lvert d\rvert$ = 0.30; feature B has $\lvert d\rvert$ = 1.20. Which is more distinctive?
Feature B.
:::
:::details 4) The corpora have 50 and 120 texts. Which method?
wkfa, because the corpora have different numbers of texts.
:::

## 8. Functional analysis
The quantitative part ends with the ranking by $\lvert d\rvert$. That ranking says **which** features are key and **for which corpus**, [but it does not say **why**]{marca rosa}. [The last step is qualitative: we interpret the function that each key feature performs in the variety]{marca amarelo}, using examples from the texts.
- [Work from **examples in both corpora**, not only from the value of *d*]{marca verde}.
- Base the interpretation on the **grammar**, on **previous research**, and on the **situation** of the variety (who communicates, with whom, and for what purpose).
- [Ask what the feature **helps the writer or speaker do** in that variety]{marca verde}.
- Present the interpretation with **evidence** (patterns and concordance lines, in KWIC or the Reader).

## 9. Warnings
- [*d* is an **approximation**: it assumes roughly normal data and similar variances]{marca rosa}. Linguistic data are often skewed.
- [*d* is **not** a significance test: it does not tell whether the difference could be due to chance]{sublinhado vermelho}.
- [Small corpora give unstable values]{marca rosa}.
- Always check **examples from the texts**, not only the number.
- [Every value is relative to the corpus used as reference]{marca rosa}.
