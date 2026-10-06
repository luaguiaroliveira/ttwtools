---
titulo: Normalisation per 1,000 words
resumo: Relative frequency that lets you compare texts and corpora of different sizes.
relacionados: cohens_d, keyness
---
A 3,000-word text tends to have more occurrences of anything than a 500-word one. To compare, [divide the count by the size and multiply by 1,000]{marca amarelo}:

$$\text{frequency per 1,000} = \frac{\text{count} \times 1000}{\text{number of words}}$$

Example: 12 passives in a 2,400-word text: $12 \times 1000 / 2400 = 5$ per 1,000; 4 passives in 500 words: $4 \times 1000 / 500 = 8$ per 1,000. [The second text uses **more** passives, although it has fewer occurrences]{marca verde}.

## How to read
- The number is "[how many times every 1,000 words]{marca verde}". For rare items, use per million.
- In feature tables (rawcount × norm1000), [the normalised version is what KFA uses]{marca verde}.

## Caveats
- [In very short texts, one extra occurrence changes the value a lot]{marca rosa}.
- What counts as a "word" depends on tokenisation (the tagger); compare numbers made the same way.
