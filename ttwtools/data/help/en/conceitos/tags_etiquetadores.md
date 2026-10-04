---
titulo: Tagger tags
resumo: What each tagger produces and what each tag means.
relacionados: tagset_biber, cohens_d, normalizacao_por_mil
---
Each **tagger** (spaCy, Stanza, BiberPlus, MFTE) marks the corpus words with a different **tag set**. The main ones:

- **UPOS** (Universal Dependencies): the universal part-of-speech classes — NOUN, VERB, ADJ, ADP, PRON... valid for any language.
- **Penn Treebank (XPOS)**: finer English classes (NN, NNS, VBD, JJ...).
- **Biber**: the lexico-grammatical features of multidimensional analysis (categories A to P).
- **MFTE**: English functional features, documented one by one.

What appears depends on **two things**: the tagger and the chosen **configuration**. For example, MFTE only includes the columns whose components are enabled; Stanza in Portuguese has no XPOS. Choose the tagger and, when there is more than one, the tag set. The table shows the tag, its group, the definition and an example.

## Cautions
- Tagging is automatic: check a few examples in the KWIC before drawing conclusions.
- Tags from different tag sets have similar names; check the selector to see which tag set they come from.

## References
- Universal Dependencies (Nivre et al.): https://universaldependencies.org/u/pos/
- Marcus, M.; Santorini, B.; Marcinkiewicz, M. A. Building a Large Annotated Corpus of English: The Penn Treebank. *Computational Linguistics*, 1993.
- Biber, D. *Variation across Speech and Writing*. Cambridge: Cambridge University Press, 1988.
- MFTE — Multidimensional Functional Tagging of English (Lee et al., 2024).
