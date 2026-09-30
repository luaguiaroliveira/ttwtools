# ttwtools

Pacote Python de linguística de corpus usado pelo aplicativo [TTWtools](https://github.com/luaguiaroliveira/ttwtools-app): projetos `.ttwa` com camadas de anotação reaproveitáveis (spaCy, Stanza, BiberPlus, MFTE), busca, KWIC, frequência, colocados, dispersão, palavras-chave, faixas de frequência, KFA, comparação de N grupos (experimental), catálogo de corpora e importação/exportação (CoNLL-U, VRT, TEI, GrAF...). Tudo também pela linha de comando `ttwtools`.

*A Python corpus-linguistics package (used by the TTWtools app): reusable annotation layers, search, KWIC, frequency, collocates, dispersion, keywords, frequency bands, KFA, N-group comparison, corpus catalog and import/export — also as the `ttwtools` command.*

- **Guia rápido:** [`docs/guia_rapido.md`](docs/guia_rapido.md)
- **Referência de todas as funções públicas** (gerada das docstrings): [`docs/referencia.md`](docs/referencia.md) — `python docs/gerar_referencia.py` para atualizar
- **Mudanças:** [`CHANGELOG.md`](CHANGELOG.md)

```bash
pip install -e .              # + [mfte] para Stanza/MFTE (torch); no Mac Intel use Python 3.11 e torch 2.2.2
ttwtools --help
```

## Instalar e usar

```bash
pip install -e .                     # núcleo (BiberPlus, spaCy); + "[mfte]" para Stanza/MFTE (torch)
python -m spacy download en_core_web_sm        # ou: ttwtools catalog download-model en_core_web_sm
ttwtools --help
```

No Mac Intel com macOS 12 use Python 3.11, `torch==2.2.2` e `numpy==1.26.4`. Tudo que o aplicativo faz, em Python e na linha de comando: [`docs/guia_rapido.md`](docs/guia_rapido.md). Arquitetura, formato JSONL, API clássica da 0.1, MFTE e empacotamento: [`docs/README.md`](docs/README.md). Exemplos executáveis: [`examples/README.md`](examples/README.md).

## Licença

Código do `ttwtools` sob **MIT** ([LICENSE](LICENSE)). Dependências de terceiros:

| Componente | Licença | Relação |
|---|---|---|
| [Biberplus](https://github.com/davidjurgens/biberplus) (modificado) | MIT | código modificado incorporado em `ttwtools/taggers/biberplus.py` |
| [Stanza](https://github.com/stanfordnlp/stanza) | Apache 2.0 | dependência opcional (`ttwtools[mfte]`) |
| [MFTE](https://github.com/mshakirDr/MFTE) | GPL 3.0 | dependência opcional (`ttwtools[mfte]`) |

**Nota sobre a GPL 3.0:** o código-fonte do `ttwtools` não inclui o MFTE, então a MIT vale para este repositório. Um executável empacotado que reúna o MFTE ao `ttwtools` é obra combinada sujeita à GPL 3.0 (ver `docs/README.md`, seção 5).
