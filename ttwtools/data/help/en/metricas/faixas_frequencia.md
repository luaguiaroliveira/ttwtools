---
titulo: Lexical frequency bands
resumo: How much of the text is among a reference's most common words.
relacionados: keyness, normalizacao_por_mil
---
The **reference** vocabulary is ranked from the most to the least frequent word. [Each word of your corpus falls into a **band** according to its rank there]{marca amarelo}: among the first 1,000, between 1,001 and 2,000, and so on; words absent from the reference are **off list**. This is Laufer & Nation's (1995) *lexical frequency profile*.

## How to read
- **Tokens** (%): how much of the running text is in each band. In general English, [the 2,000 most frequent words usually cover about 80% of a text]{marca verde}.
- **Types** (%): how much of the distinct vocabulary is in each band.
- [A large **off-list** share points to technical vocabulary, proper names, different spellings, or a reference from another variety or period]{marca verde}.

## Caveats
- [The result depends on the reference (size, period, variety, genre) and on the unit]{marca rosa}: with **lemma**, *ran* and *runs* count as *run*; with **form**, they do not.
- Use the same tagging (tagger and version) in corpus and reference when the unit is lemma.
