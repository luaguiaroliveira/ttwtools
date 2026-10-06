---
titulo: Dispersion (Gries' DP and Range)
resumo: Whether a word is spread across the corpus or concentrated in a few texts.
relacionados: keyness, kwic
---
[Frequency does not say **where** a word occurs]{marca amarelo}. Two words with 100 hits may be in every text or in just one.

- **Range:** in how many texts the word occurs.
- **Gries' DP:** compares the share of hits in each text with the share of the corpus that text represents. [DP = ½ Σ |oᵢ − eᵢ|]{sublinhado azul}. **0** = spread as expected; close to **1** = concentrated. Normalised DP goes from 0 to 1 regardless of the number of texts.

The "barcode" plot shows each hit as a line at its relative position within each text.

## How to read
- [A keyword with high DP and low range is usually the topic of one text, not of the corpus]{marca verde}.

## Caveats
- [With few texts, DP varies a lot]{marca rosa}.
- Texts of very different sizes weigh differently in the expected share (eᵢ).
