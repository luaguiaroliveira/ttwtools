---
titulo: KWIC (concordance)
resumo: Every hit of the search in the centre, with the words on each side.
relacionados: dispersao, keyness
---
**KWIC** (*key word in context*) lists each hit of the search aligned in the centre, with N words to the left and right, the file and the position in the text.

The search accepts: word (`house`), phrase (`black cat`), wildcards (`hous*`), regular expression (`/^run(s|ning)?$/`), lemma (`lemma=run`), class (`pos=NOUN`) and combinations. `&` joins conditions on the same token (`lemma=run&pos=VERB`); `|` gives alternatives in the same field (`tag=PASS|NN`, `pos=NOUN|VERB`). Lemma and class need a tagged layer.

## How to read
- Sorting by the word on the left or right groups similar uses and reveals patterns (collocations, constructions).
- Click a line to open the text at the position of the hit.

## Caveats
- A form may have several senses: read the lines before concluding.
- The sentence shown is approximate (punctuation-based) when the layer has no segmentation.
