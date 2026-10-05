---
titulo: Standard Deviation (SD)
resumo: Measures how far, on average, the rates of the texts lie from the mean; it is the "ruler" of Cohen's d.
relacionados: kfa, cohens_d, dispersao
---
The standard deviation (SD) measures how far, on average, the rates of the texts lie from the mean. The larger the SD, the more the feature varies from text to text. It is built in four steps.

1. Find the **mean** (M) of the rates.
2. For each text, compute the **deviation** from the mean: rate minus M.
3. **Square** each deviation, add them, and divide by (n minus 1). This is the **variance**.
4. Take the **square root** of the variance. This is the **SD**.

$$\text{variance} = \frac{\sum (x_i - M)^2}{n - 1}$$
$$SD = \sqrt{\text{variance}}$$

## Example
Corpus A has rates 2, 4, 4, 6, so M = 4. The deviations are −2, 0, 0, +2, and their squares are 4, 0, 0, 4. The variance is $8/3 \approx 2.67$, so $SD \approx 1.63$.

Corpus B has rates 0, 4, 4, 8: the same mean (4) but a larger spread. The variance is $32/3 \approx 10.67$, so $SD \approx 3.27$.

Two equal means can hide very different spreads: this is why KFA does not compare the means alone.

## Pooled standard deviation (in KFA)
Cohen's *d* divides the difference between the means by **a single number** that combines the spread of the two corpora: the pooled standard deviation.

$$\text{kfa:}\quad SD_{\text{pooled}} = \sqrt{\frac{SD_1^2 + SD_2^2}{2}}$$
$$\text{kfa2:}\quad SD_{\text{pooled}} = \sqrt{\frac{(n_1 - 1)\,SD_1^2 + (n_2 - 1)\,SD_2^2}{n_1 + n_2 - 2}}$$

In kfa the two corpora weigh the same; in kfa2 (for corpora with different numbers of texts) the larger corpus weighs more, because its estimate of variation is more reliable.

## How to read it
- Small SD: the texts are consistent; even a small gap between the means is striking.
- Large SD: the texts are heterogeneous; a larger gap between the means is needed for the feature to be key.
- The SD has the same unit as the rate (for example, occurrences per 1,000 words).
