# plano.md — ttwtools & ttwtools-app: Roadmap Consolidado

> Versão: 2025-04 (supersede versão anterior)
> Este arquivo é o único plano canônico. Mantido em sincronia entre `ttwtools/` e `ttwtools-app/libs/ttwtools/`.

---

## 1. Visão Geral

O ttwtools evolui para suportar **análise multi-tagger de pares de corpora dentro de um único arquivo .ttwa**.

### Princípio central

Um arquivo `.ttwa` é um **container**, análogo a um projeto. Ele pode conter:
- Os textos originais dos dois corpora (modo `full`)
- Múltiplas camadas de tagging (ex: `biberplus`, `mfte`, `stanza`) dos mesmos arquivos
- Feature tables normalizadas por camada de tagging
- KFAs calculadas por camada de tagging
- Metadados do projeto e das análises

O usuário pode adicionar novas camadas de análise a um projeto existente a qualquer momento, sem reprocessar o que já foi feito.

---

## 2. Arquitetura Alvo do .ttwa

### 2.1 Estrutura lógica (SQLite)

```
project_meta        — metadados globais (nome, data, versão, modo)
corpus_files        — textos originais (.txt) — indexados por (corpus_name, filename)
tagged_files        — JSONL tagueados — indexados por (corpus_name, filename, tagger_type)
feature_tables      — CSVs como JSON — indexados por (corpus_name, table_type, tagger_type)
kfa_results         — KFA como JSON — indexados por (corpus1, corpus2, join, tagger_type)
```

### 2.2 Schema atual da tabela `tagged_files` (NOVO)

Atualmente `tagged_files` tem UNIQUE (corpus_name, filename) — **precisa adicionar tagger_type**:

```sql
CREATE TABLE tagged_files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    corpus_name  TEXT    NOT NULL,
    filename     TEXT    NOT NULL,
    tagger_type  TEXT    NOT NULL DEFAULT 'biberplus',
    content      TEXT    NOT NULL,          -- JSONL canônico
    UNIQUE (corpus_name, filename, tagger_type)
);
```

A tabela `feature_tables` já tem `tagger_type`. A tabela `kfa_results` recebeu `tagger_type` em 2025-04.

### 2.3 Camadas de análise disponíveis

Ao abrir um `.ttwa`, o app lista as camadas presentes via:
```python
proj.list_analysis_layers()
# → [{"tagger": "biberplus", "corpora": ["A", "B"], "kfa": True},
#    {"tagger": "mfte",      "corpora": ["A", "B"], "kfa": True}]
```

---

## 3. Taggers Suportados

| Tagger | `tagger_type` | Dependências | Features geradas |
|--------|--------------|-------------|-----------------|
| BiberPlus (regex) | `biberplus` | — | ~67 Biber features |
| BiberPlus + spaCy/Stanza | `biberplus_nlp` | spaCy ou stanza | ~67 Biber features |
| MFTE (básico) | `mfte` | stanza, torch, MFTE | ~80 features MFTE |
| MFTE (estendido) | `mfte_ext` | stanza, torch, MFTE | ~120 features MFTE |

> **Nota:** "Stanza" como tagger separado era um equívoco. Stanza é o tokenizador usado pelo MFTE e opcionalmente pelo BiberPlus. Não existe análise "Stanza puro" neste sistema.

### 3.1 Formato JSONL canônico (unificado entre taggers)

```jsonl
{"type":"metadata","tagger":"mfte","tagger_version":"1.0.0.7","stanza_model":"en","device":"cpu","extended":false,"filename":"documento.txt"}
{"start_char":0,"end_char":3,"word":"The","xpos":"DT","tags":[]}
{"start_char":4,"end_char":9,"word":"study","xpos":"NN","tags":["NN","NNABSPROC"]}
```

Campos obrigatórios em cada token: `start_char`, `end_char`, `word`, `xpos`, `tags`.
O invariante `texto_original[start_char:end_char] == word` deve ser satisfeito por todos os taggers.

---

## 4. Roadmap de Implementação

### Fase 0 — Migração de tagged_files para multi-tagger [ttwtools]

- [ ] Adicionar coluna `tagger_type TEXT NOT NULL DEFAULT 'biberplus'` à tabela `tagged_files`
- [ ] Atualizar UNIQUE constraint: `(corpus_name, filename, tagger_type)`
- [ ] Adicionar `_migrate_tagged_files(con)` em `project.py` chamada em `_connect()`
- [ ] Atualizar `save_tagged_file()`, `list_tagged_files()`, `get_tagged_file()` para aceitar `tagger_type`
- [ ] Adicionar `list_analysis_layers()` ao `TTWAProject`: lista taggers com feature tables + KFA disponíveis
- [ ] Atualizar `save_analysis_to_project()` para receber `tagger_type`

### Fase 1 — Separação de taggers em módulos [ttwtools]

- [ ] Criar `ttwtools/taggers/__init__.py`
- [ ] Criar `ttwtools/taggers/biberplus.py` (mover de `tagging.py`)
- [ ] Criar `ttwtools/taggers/mfte.py` (novo — ver §5)
- [ ] Manter `ttwtools/tagging.py` como shim de compatibilidade
- [ ] Atualizar `ttwtools/__init__.py` para importar de `taggers/`
- [ ] Migrar BiberPlus para output JSONL com offsets (ver §3.1)
- [ ] Criar `ttwtools/tagged_io.py` (leitura/escrita JSONL canônico)

### Fase 2 — Interface gráfica multi-tagger [ttwtools-app]

#### 2.1 Painel "Nova análise" / Quickrun

- [ ] Substituir dropdown de tagger por **radio boxes** (múltipla seleção):
  ```
  [x] BiberPlus (regex)
  [ ] BiberPlus + spaCy
  [ ] MFTE básico
  [ ] MFTE estendido
  ```
  O usuário pode marcar mais de um. O pipeline executa cada tagger selecionado e salva todas as camadas no mesmo .ttwa.

- [ ] Mostrar aviso quando MFTE não está instalado (stanza/torch ausentes)

#### 2.2 Painel "Abrir projeto"

- [ ] Após abrir um .ttwa, exibir **sumário das camadas de análise disponíveis**:
  ```
  CorpusA vs CorpusB
  ├─ [biberplus]  67 features  KFA ✓
  └─ [mfte]       82 features  KFA ✓
  ```
- [ ] Botão "Adicionar análise" abre o painel de tagging para adicionar nova camada ao projeto existente

#### 2.3 Painel "Resultados"

- [ ] Adicionar **dropdown de tagger** na toolbar de Resultados:
  ```
  Visualizando: [biberplus ▾]  |  Carregar
  ```
  O dropdown lista apenas taggers que têm KFA no projeto aberto.
- [ ] Ao trocar o tagger, recarregar o KFA correspondente (limpar state.kfaData antes)
- [ ] O `state.kfaTagger` já foi implementado; garantir que seja passado ao featureFiles

#### 2.4 Text Viewer — correção de quebra de palavras

- [ ] Corrigir quebra de linha no visualizador de texto:
  - Usar `word-wrap: break-word` + `overflow-wrap: break-word` + `white-space: pre-wrap` na `.tv-text`
  - **Nunca** quebrar palavras ao meio — usar `word-break: normal` (não `break-all`)
  - Comportamento desejado: palavras longas que não cabem na linha são levadas inteiramente para a próxima linha (flush-left)

### Fase 3 — Backend multi-tagger no pipeline [ttwtools-app]

- [ ] Atualizar `quickrun.py` para aceitar `taggers: list[str]` (lista de taggers a executar)
- [ ] Loop sobre taggers selecionados; salvar cada camada no mesmo .ttwa
- [ ] Atualizar `routes/analysis.py`: `run_kfa` aceita `tagger_type` explicitamente (sem auto-detect ambíguo)
- [ ] Remoção do tagger `"stanza"` como tipo separado — substituir por `"biberplus_nlp"` e `"mfte"`
- [ ] Migração de projetos com `tagger_type="stanza"` → `tagger_type="biberplus_nlp"` na abertura

### Fase 4 — MFTE Engine com offsets [ttwtools]

Ver §5 abaixo para detalhes de implementação.

- [ ] `_detect_device()` → `"cuda"` | `"cpu"` (MPS excluído: 2.4× mais lento que CPU)
- [ ] `_load_stanza_pipeline(device)` com cache lazy
- [ ] `_tag_document_mfte(text, nlp, extended)` → lista de tokens com offsets reais
- [ ] `extract_mfte_features_from_folder()` e `mfte()` de alto nível
- [ ] Testes com `test_corpora/`

### Fase 5 — PyInstaller (distribuição)

- [ ] Cenário B (CPU-only): hooks para stanza + torch CPU
- [ ] Cenário C (GPU): companion executable `mfte_worker`
- [ ] Documentar builds nos dois cenários

---

## 5. Integração MFTE — Detalhes Técnicos

### 5.1 Modo de operação: import direto da API interna

**Não usar subprocess nem pipeline de arquivos do MFTE.**

```python
import stanza
from MFTE import process_sentence, process_sentence_extended

def _tag_document_mfte(text: str, nlp, extended: bool = False) -> list[dict]:
    doc = nlp(text)
    all_tokens = []
    mfte_input = []
    for sentence in doc.sentences:
        mfte_input.extend([' '] * 20)   # sentinelas CRÍTICAS: lista de strings, não string única
        for word in sentence.words:
            mfte_input.append(f"{word.text}_{word.xpos}")
            all_tokens.append((word.start_char, word.end_char, word.text, word.xpos))
    mfte_input.extend([' '] * 20)

    tagged = process_sentence(mfte_input, extended=extended)
    if extended:
        tagged = process_sentence_extended(tagged)

    filtered = [w for w in tagged if w != " "]

    result = []
    for i, (start, end, word, stanza_xpos) in enumerate(all_tokens):
        if i >= len(filtered): break
        raw = filtered[i]
        parts = raw.split()
        mfte_xpos = parts[0].rsplit('_', 1)[-1] if parts and '_' in parts[0] else stanza_xpos
        result.append({
            "start_char": start, "end_char": end,
            "word": word, "xpos": mfte_xpos,
            "tags": parts[1:],
        })
    return result
```

### 5.2 Questões resolvidas

1. ✅ **Sentinelas**: `[' '] * 20` (lista de 20 strings `" "`). Nunca `" " * 20` (causa IndexError).
2. ✅ **process_sentence_extended()**: preserva 1:1 o tamanho da lista. Filtrar sentinelas apenas depois das duas passagens.
3. ✅ **Modelos Stanza**: `processors='tokenize,pos'` é suficiente.
4. ✅ **MPS excluído**: 2.4× mais lento que CPU para modelos BiLSTM do Stanza.
5. **Licença MFTE**: GPL-3.0 — verificar compatibilidade com redistribuição.
6. **Paralelismo**: `process_sentence()` é stateless (segura em paralelo); `stanza.Pipeline` não é thread-safe — uma instância por processo.

---

## 6. Estado Atual (o que já foi implementado)

### ttwtools (biblioteca)
- [x] `taggers/biberplus.py`, `taggers/mfte.py`, `taggers/__init__.py` — separação de módulos
- [x] `tagged_io.py` — leitura/escrita JSONL canônico
- [x] `project.py` — `tagger_type` em `feature_tables` e `kfa_results` com migração automática
- [x] `project.py` — `list_analysis_layers()` (a implementar)

### ttwtools-app (aplicação)
- [x] `state.kfaTagger` — tagger ativo armazenado no estado da UI
- [x] `main.js` — limpar kfaData/kfaTagger ao mudar de projeto
- [x] `results.js` — dropdown mostra tagger; carregamento salva kfaTagger no state
- [x] `feature-detail.js` — passa tagger1/tagger2 para featureFiles
- [x] `api.js` — featureFiles e getKfa aceitam tagger como parâmetro
- [x] `quickrun.py` — `stanza` corrigido → `biberplus+usenlp=True`; `mfte_ext` como alias para MFTE estendido

### Ainda a fazer
- [ ] Fase 0: `tagged_files` multi-tagger
- [ ] Fase 1: separação de taggers completa
- [ ] Fase 2: UI multi-tagger (radio boxes, sumário de camadas, dropdown de resultados)
- [ ] Fase 2.4: correção de word-wrap no text viewer
- [ ] Fase 3: pipeline multi-tagger no quickrun
- [ ] Fase 4: MFTE engine completa com offsets

---

## 7. Decisões de Design

### Por que radio boxes em vez de dropdown para seleção de tagger?
O usuário precisa executar **múltiplos taggers simultaneamente** num único pipeline. Dropdown permitiria apenas uma seleção. Radio boxes (com múltipla seleção) permitem marcar quais taggers devem ser executados e salvos nessa sessão de análise.

### Por que o .ttwa centraliza tudo?
Evita fragmentação de projetos. Ao abrir um único arquivo, o pesquisador tem acesso a todas as análises feitas sobre aquele par de corpora, pode comparar resultados de taggers diferentes, e exporta tudo de um lugar. O arquivo é um SQLite — inspecionável externamente, sem dependência de formato proprietário.

### Por que não quebrar palavras ao meio no text viewer?
O texto anotado é uma cópia fiel do original. Quebra de palavra ao meio (`break-all`) desfigura o texto, dificulta a leitura e cria tokens visuais que não correspondem a tokens linguísticos. O comportamento correto é mover a palavra inteira para a próxima linha.
