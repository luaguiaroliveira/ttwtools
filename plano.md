# Plano de Expansão: Suporte a Múltiplos Taggers no ttwtools

## 1. Diagnóstico da Arquitetura Atual

### O que existe hoje

**Estado atual:**
```
ttwtools/
  tagging.py   — lógica de tagging 100% acoplada ao BiberPlus/spaCy
  analysis.py  — KFA agnóstica a colunas (funciona com qualquer CSV de features)
  project.py   — persistência SQLite (.ttwa); armazena feature tables como JSON
  __init__.py  — re-exporta as funções públicas
```

**Estrutura alvo (após refatoração):**
```
ttwtools/
  taggers/
    __init__.py        — re-exporta os entry points públicos de cada tagger
    biberplus.py       — todo o código atual de tagging.py (BiberPlus/spaCy)
    mfte.py            — novo backend MFTE (Stanza API + process_sentence)
  tagging.py           — shim de compatibilidade: re-exporta de taggers.biberplus
  analysis.py          — inalterado
  project.py           — inalterado
  __init__.py          — atualizado: importa de taggers/ em vez de tagging.py
```

Vantagens da separação em `taggers/`:
- Cada arquivo de tagger tem suas próprias dependências de import no topo — fácil
  de ver quais pacotes externos cada backend requer.
- Adicionar um novo tagger = criar um novo arquivo em `taggers/` sem tocar em nenhum
  outro módulo existente.
- `tagging.py` mantido como shim garante que código externo que faça
  `from ttwtools.tagging import biberplus` continua funcionando durante a transição.
- A separação torna trivial o bundling PyInstaller seletivo: spec do Cenário B
  inclui `ttwtools/taggers/mfte.py` e suas dependências; Cenário A não inclui.

**Pontos fortes da arquitetura atual (mantidos):**
- `analysis.py` e `project.py` são completamente agnósticos ao tagger — trabalham com
  qualquer DataFrame de features, independente de quais colunas existam.
- O schema SQLite de `project.py` já suporta múltiplos corpora com tipos diferentes.
- As dependências de tagging (BiberPlus, spaCy) só são importadas em `tagging.py`.

**Limitações atuais (a resolver no roadmap):**
- `tagging.py` tem um único backend (BiberPlus) e sem interface abstrata.
- Não há mecanismo de seleção de tagger: sempre BiberPlus.
- PyInstaller hoje bundla spaCy (razoavelmente estável); stanza+torch demanda estratégia diferente.
- O formato TSV taggeado não registra qual tagger foi usado.

---

## 2. O MFTE e suas Dependências

### Cadeia de dependências

```
MFTE (pip install MFTE)
  └─ stanza  (Stanford NLP)
       └─ torch (PyTorch)
            ├─ CPU  — ~250 MB, portable, funciona em qualquer máquina
            ├─ CUDA — ~2 GB+, requer GPU nVidia + drivers CUDA 11.8+
            └─ MPS  — macOS 12.3+, aceleração via Apple Silicon/Metal
```

### O que o MFTE faz

1. Roda Stanza (POS tagging neural) no texto.
2. Aplica expressões regulares sobre o output do Stanza para marcar >100 features
   lexico-gramaticais e semânticas (incluindo as tags Biber 1999/2006).
3. Gera três CSVs:
   - `counts_raw.csv` — contagens brutas
   - `counts_word-based_normed.csv` — normalizado por 100 palavras
   - `counts_mixed_normed.csv` — normalizado por bases linguisticamente motivadas
4. Estrutura de saída: `<corpus>_MFTE/MFTE_Tagged/`, `POS_Tagged/`, `Statistics/`

### CLI do MFTE
```
mfte --path "/caminho/corpus/" --ttr 400 --extended True --parallel_md_tagging False
```

### GPU/PyTorch no MFTE
- Stanza detecta automaticamente CUDA quando PyTorch com suporte CUDA está instalado.
- A instalação GPU é separada da instalação do stanza/MFTE:
  - Windows/Linux: `pip install torch ... --index-url .../cu118`
  - macOS 12.3+: `pip install --pre torch ... --index-url .../nightly/cpu` (MPS)
- **Não há parâmetro `--gpu` no CLI do MFTE** — o suporte GPU é transparente via torch.

---

## 3. Desafios de Integração

### 3.1 PyInstaller com torch/stanza

| Abordagem | Tamanho do Bundle | GPU Possível? | Complexidade |
|-----------|-------------------|---------------|--------------|
| Bundlar torch CPU + stanza + MFTE | ~500 MB–1 GB | Não (bundle fixo) | Alta |
| Bundlar torch CUDA + stanza + MFTE | ~3 GB+ | Sim, mas fixo | Muito alta |
| MFTE como processo externo (subprocess) | Pequeno (sem torch) | Sim (user instala GPU torch) | Baixa |
| Companion executable (two-bundle) | Médio | Sim | Média |

**PyInstaller e torch têm problemas conhecidos:**
- Torch usa extensões C++ com shared libraries que o PyInstaller não encontra automaticamente.
- Stanza baixa modelos em runtime — precisam ser pré-baixados e bundlados ou acessados de path externo.
- spaCy (atual) tem hooks oficiais para PyInstaller; torch/stanza não têm hooks maduros.

### 3.2 Compatibilidade de features

BiberPlus e MFTE possuem conjuntos de features sobrepostos mas não idênticos:
- Ambos cobrem as features Biber (1988) e semânticas Biber (1999/2006).
- MFTE tem features extras (TTR, feature count por tipos diferentes).
- Colunas distintas → `analysis.py` funciona sem modificação (trabalha com intersecção/união).
- `project.py` já armazena DataFrames como JSON → nenhuma mudança de schema necessária.

### 3.3 Alinhamento com o texto original — problema central

**Requisito:** para qualquer tagger, o arquivo taggeado deve permitir identificar,
inequivocamente, o início e o fim de cada token/tag no **arquivo de texto original**.
O arquivo original é sempre preservado ao lado do taggeado (via `copy_originals=True`).

---

#### 3.3.1 Formato canônico unificado: JSONL

O formato primário de arquivo taggeado é **JSONL** (JSON Lines: um objeto JSON
por linha). É usado por **todos** os taggers do ttwtools (BiberPlus, MFTE,
Stanza puro ou qualquer futuro backend).

Estrutura: primeira linha = objeto de metadados; linhas seguintes = um token
por linha.

```jsonl
{"type":"metadata","tagger":"mfte","tagger_version":"1.0.0.7","stanza_model":"en","device":"cpu","extended":true,"filename":"documento.txt"}
{"start_char":0,"end_char":3,"word":"The","xpos":"DT","tags":[]}
{"start_char":4,"end_char":9,"word":"study","xpos":"NN","tags":["NN","NNABSPROC"]}
{"start_char":10,"end_char":13,"word":"was","xpos":"VBD","tags":[]}
{"start_char":14,"end_char":23,"word":"conducted","xpos":"VBN","tags":["PASS"]}
```

Campos obrigatórios em cada token:
- `start_char` / `end_char`: offsets de caractere UTF-8 em relação ao arquivo
  original (inclusive no `start`, exclusivo no `end`). Invariante:
  `original[start_char:end_char] == word` para todo token.
- `word`: forma superficial exata do token como aparece no arquivo original.
- `xpos`: POS tag Penn Treebank. Fonte: spaCy (`token.tag_`) para BiberPlus;
  Stanza (`word.xpos`) para MFTE/Stanza puro. String vazia se o backend não fornece POS.
- `tags`: array JSON com os tags do tagger. Array vazio `[]` se nenhum.
  Para BiberPlus: tags Biber. Para MFTE: tags MFTE. Para Stanza puro: `[]`.

Campos extras (opcionais, extensíveis por tagger ou versão futura):
- Qualquer tagger pode acrescentar campos adicionais ao objeto token
  (ex.: `"confidence": 0.97`, `"t_start": 1.23`, `"speaker": "A"`).
  Leitores que não conhecem o campo ignoram-no — nenhuma quebra de compatibilidade.

Campos do objeto de metadados:
- `type`: sempre `"metadata"` — identifica a linha de cabeçalho.
- `tagger`, `tagger_version`, `filename`: obrigatórios.
- Demais chaves (`stanza_model`, `device`, `extended`, etc.): opcionais, específicas
  do backend. Leitores ignoram chaves desconhecidas.

**Uso pela GUI / leitor:**
```python
import json

with open("doc_mfte.jsonl") as f:
    meta   = json.loads(f.readline())       # primeiro objeto = metadados
    tokens = [json.loads(line) for line in f]  # restante = tokens

# Invariante: token encontrado no original
original = open(meta["filename"]).read()
for tok in tokens:
    assert original[tok["start_char"]:tok["end_char"]] == tok["word"]

# Gap entre tokens (espaços, pontuação, quebras de linha):
gap = original[tokens[i]["end_char"]: tokens[i+1]["start_char"]]
```

**Nomenclatura de arquivos:** ao lado do original, um JSONL por tagger/configuração:
```
originals/<corpus>/documento.txt
<corpus>_tagged/documento_biberplus.jsonl
<corpus>_tagged/documento_mfte.jsonl
```
O campo `filename` no JSONL referencia o nome do original. A GUI cruza os dois
pelo nome do arquivo.

---

#### 3.3.2 Como cada backend produz offsets

**MFTE (via Stanza API):**

(ver §4.2 para o fluxo completo)

O Stanza via API Python fornece `word.start_char` e `word.end_char` por token
em relação ao texto passado. Isso garante o invariante diretamente.

**Por que o pipeline de arquivos do MFTE não funciona aqui:**
- `stanza_pre_processing()` transforma o texto antes do Stanza (divide contrações,
  normaliza espaços), quebrando o alinhamento com o original.
- Os arquivos `POS_Tagged/` e `MFTE_Tagged/` não contêm nenhuma informação de offset.
- Por isso usamos a API Python do Stanza diretamente, sem `stanza_pre_processing()`.

**BiberPlus (via spaCy):**

Quändo `usenlp=True`, spaCy tokeniza o texto e fornece offsets por token:
```python
for token in doc:
    start = token.idx
    end   = token.idx + len(token.text)
    xpos  = token.tag_          # Penn Treebank (en_core_web_sm/trf)
    # passar token para biberplus.tag_text() e recuperar Biber tags
```
Quando `usenlp=False` (regex), os offsets são recuperados por `re.finditer()`
sobre o texto original.

A migração do BiberPlus do formato `type|content|tags` para o novo formato
unificado é executada na **Fase 0** do roadmap (não é optativa).

---

#### 3.3.3 Convivência com arquivos legados e exports

**Formato legado** (`type|content|tags` TSV): identificado pela ausência de
`start_char` na primeira linha de dados. O `tagged_io.py` detecta e avisa o
usuário; não converte automaticamente (offsets não recuperáveis sem reprocessar).

**Exports opcionais** a partir de um JSONL canônico (gerados sob demanda pelo
`tagged_io.py`):
- `.json` — array JSON completo (metadados + tokens); útil para APIs REST
- `.tsv` — `start_char \t end_char \t word \t xpos \t tags` (tags espaço-separadas)
- `.csv` — mesmo schema do TSV, separador `,`; útil para Excel/planilhas

O armazenamento primário é sempre JSONL. Os exports não são mantidos
automaticamente — são gerados quando solicitados pelo usuário ou pela GUI.

---

## 4. Estratégia Recomendada

### 4.1 Abstração de Tagger (etapa 1 — arquitetural)

Cada tagger expõe a mesma **convenção de assinatura** (protocolo informal, sem ABC):

```python
def tag_folder(
    folder_path_str: str,
    output_dir: str | None = None,
    save_tagged: bool = False,
    copy_originals: bool = False,
    **kwargs,                        # parâmetros específicos do backend
) -> None
```

`biberplus()` (em `taggers/biberplus.py`) continua como está, apenas movido.
`mfte()` (em `taggers/mfte.py`) segue o mesmo protocolo.

O `taggers/__init__.py` re-exporta ambos:
```python
# ttwtools/taggers/__init__.py
from .biberplus import biberplus, extract_biber_features_from_folder, normalize_biber_features
from .mfte import mfte, extract_mfte_features_from_folder  # import lazy p/ não carregar torch
```

O `__init__.py` raiz do pacote importa de `taggers/` em vez de `tagging.py`:
```python
# ttwtools/__init__.py (trecho)
from .taggers import biberplus, extract_biber_features_from_folder, normalize_biber_features
from .taggers import mfte, extract_mfte_features_from_folder
```

### 4.2 Integração MFTE — modo de operação: import direto da API interna

**Não usaremos subprocess nem o pipeline de arquivos do MFTE.**

Após inspecionar o código-fonte (`MFTE.py` instalado em `site-packages`),
confirmamos que:
- `process_sentence(words, extended)` — função pura: recebe lista de strings
  `"palavra_POS"`, retorna lista de strings `"palavra_TAG1 TAG2"`.
- `process_sentence_extended(words)` — segunda passagem opcional para categorias
  semânticas Biber 2006.
- `stanza_pre_processing(text)` — normalização de texto antes do Stanza.
- O Stanza é inicializado via `stanza.Pipeline()` com `use_gpu=True/False`.

O fluxo de integração no ttwtools é:

```python
import stanza
from MFTE import process_sentence, process_sentence_extended, stanza_pre_processing

def _tag_document_mfte(text: str, nlp, extended: bool = True) -> list[dict]:
    """
    Retorna lista de tokens com offsets e tags MFTE.
    Cada item: {"start": int, "end": int, "word": str, "xpos": str, "tags": list[str]}
    """
    # 1. Stanza com offsets (texto ORIGINAL — sem preprocessing)
    doc = nlp(text)
    
    # 2. Montar lista no formato esperado pelo MFTE, por sentença
    all_tokens = []   # (start_char, end_char, word, xpos)
    mfte_input = []   # ["word_xpos", ...] com sentinelas de sentença
    
    for sentence in doc.sentences:
        # MFTE usa listas com pelo menos 20 espaços entre sentenças como sentinela
        mfte_input.append(" " * 20)
        all_tokens.append(None)  # sentinela
        for word in sentence.words:
            mfte_input.append(f"{word.text}_{word.xpos}")
            all_tokens.append((word.start_char, word.end_char, word.text, word.xpos))
    
    # 3. Aplicar tagging MFTE (função pura — sem I/O)
    mfte_input.append(" " * 20)  # sentinela final
    tagged = process_sentence(mfte_input, extended=extended)
    if extended:
        tagged = process_sentence_extended(tagged)
    
    # 4. Reassociar tags com offsets originais
    result = []
    for i, token_info in enumerate(all_tokens):
        if token_info is None:
            continue  # sentinela de sentença
        start, end, word, xpos = token_info
        raw_tag_str = tagged[i]             # e.g. "study_NN NNABSPROC"
        # Extrair só os tags (remover a parte "word_POS")
        parts = raw_tag_str.split()
        tags = parts[1:] if len(parts) > 1 else []
        result.append({
            "start": start,
            "end": end,
            "word": word,
            "xpos": xpos,
            "tags": tags,
        })
    return result
```

**Nota sobre preprocessing:** `stanza_pre_processing()` altera o texto (divide
contrações, etc.) melhorando a acurácia do POS. Em vez de aplicá-lo antes de
passar ao Stanza (o que quebraria os offsets), usaremos o Stanza diretamente no
texto original. A perda de acurácia em contrações é aceitável para a maioria dos
casos; se necessário, podemos aplicar o preprocessing e depois realinhar os
tokens com o texto original usando difflib (tarefa da Fase 2).

**Detecção de device (GPU/MPS/CPU):**

```python
def _detect_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"
```

- `use_gpu=None` → auto-detect via `_detect_device()`
- `use_gpu=True` → forçar GPU; avisa se não disponível  
- `use_gpu=False` → forçar CPU

O device é passado para `stanza.Pipeline('en', use_gpu=<bool>)`.

### 4.3 Formato JSONL de saída (formato canônico unificado)

Ver §3.3.1 para a especificação completa. O mesmo schema JSONL é usado por todos
os backends; apenas os campos do objeto de metadados variam. Exemplos:

**BiberPlus** (via spaCy):
```jsonl
{"type":"metadata","tagger":"biberplus","tagger_version":"<versão>","spacy_model":"en_core_web_sm","filename":"documento.txt"}
{"start_char":0,"end_char":3,"word":"The","xpos":"DT","tags":[]}
{"start_char":4,"end_char":9,"word":"study","xpos":"NN","tags":["NN","NNS"]}
```

**MFTE** (via Stanza API):
```jsonl
{"type":"metadata","tagger":"mfte","tagger_version":"1.0.0.7","stanza_model":"en","device":"cpu","extended":true,"filename":"documento.txt"}
{"start_char":0,"end_char":3,"word":"The","xpos":"DT","tags":["DT"]}
{"start_char":4,"end_char":9,"word":"study","xpos":"NN","tags":["NN","NNABSPROC"]}
```

**Stanza puro** (apenas POS):
```jsonl
{"type":"metadata","tagger":"stanza","tagger_version":"<versão>","stanza_model":"en","device":"cpu","filename":"documento.txt"}
{"start_char":0,"end_char":3,"word":"The","xpos":"DT","tags":[]}
{"start_char":4,"end_char":9,"word":"study","xpos":"NN","tags":[]}
```

**Exports opcionais** gerados por `tagged_io.export_tagged(path, fmt)` onde
`fmt` ∈ `{"json", "tsv", "csv"}`. Ver §3.3.3.

### 4.4 Normalização de features para o formato ttwtools

Depois do tagging, as contagens de features são extraídas da lista de tokens
(contando ocorrências de cada tag no campo `tags`) e armazenadas no CSV padrão:
uma linha por documento, colunas = features.

A função `normalize_biber_features()` existente funciona sem modificação.

Mapeamento de metadados:
- `Filename` (MFTE) → `filename` (ttwtools)
- `Words`, `TTR`, `AWL`, `LDE` são preservados como colunas extras
- `field` e `section` são inferidos do nome de arquivo (convenção atual)

### 4.5 Metadados de tagger no projeto (.ttwa)

Adicionar `tagger_type` e `tagger_config` na tabela `feature_tables`:

```sql
-- Migração automática ao abrir .ttwa antigos:
ALTER TABLE feature_tables ADD COLUMN tagger_type TEXT NOT NULL DEFAULT 'biberplus';
ALTER TABLE feature_tables ADD COLUMN tagger_config TEXT NOT NULL DEFAULT '{}';
-- tagger_config armazena JSON: {"extended": true, "device": "cpu", "stanza_model": "en"}
```

Isso permite projetos mistos (corpora com taggers diferentes) sem ambiguidade,
e a GUI pode exibir com qual configuração cada corpus foi processado.

---

## 5. Estratégia PyInstaller

**Cenários confirmados:**
- **Cenário B**: distribuição simples CPU-only (primeira release pública)
- **Cenário C**: arquitetura de produção GPU-ready (companion process) — preferido para uso profissional

Em ambos, o código de tagging MFTE (Stanza API + `process_sentence()` importado) roda  
**dentro do `mfte_worker`** — nunca via subprocess ao CLI `mfte`.

### Cenário A — App sem MFTE (apenas BiberPlus)
Estado atual. Continua funcionando sem mudanças. spaCy tem hooks estáveis.

### Cenário B — App com MFTE, bundle CPU-only (recomendado para distribuição inicial)

1. Instalar MFTE + stanza + torch CPU no ambiente de build.
2. Usar hooks customizados para stanza e torch:
   - Incluir pasta de modelos stanza pré-baixados como `datas` no spec.
   - Adicionar hidden imports para stanza e torch.
3. Resultado: bundle ~700 MB–1.2 GB, sem GPU, mas portátil.
4. Arquivo `.spec` de referência a criar: `ttwtools_mfte_cpu.spec`

```python
# Trecho do .spec para incluir modelos stanza
import stanza, os
stanza_dir = os.path.dirname(stanza.__file__)
# Incluir modelos pré-baixados em ~/stanza_resources/
datas += [("~/stanza_resources/en", "stanza_resources/en")]
hiddenimports += ["stanza", "torch", "MFTE"]
```

### Cenário C — App com MFTE + GPU (recomendado para uso profissional)

**Two-bundle / companion process:**

```
app_principal.exe      ← PyInstaller sem torch
mfte_worker.exe        ← PyInstaller separado com torch + stanza + MFTE
```

`app_principal.exe` invoca `mfte_worker.exe` via subprocess com protocolo JSON:

```
app → mfte_worker: {"action": "tag", "folder": "...", "use_gpu": true, "ttr": 400}
mfte_worker → app: {"status": "done", "output_dir": "...", "tagger": "mfte"}
```

Vantagens:
- Bundle principal continua pequeno.
- `mfte_worker` atualiza torch/stanza independentemente.
- GPU/CPU é selecionado em `mfte_worker` em runtime.
- Se o usuário não tem GPU, torch auto-usa CPU — transparente.

**Interface do worker (a implementar):**

```python
# ttwtools/mfte_worker_main.py
# Entry point para o companion executable.
# Importa stanza e MFTE.process_sentence diretamente (não usa CLI do MFTE).
# Recebe JSON de stdin ou arquivo temporário; devolve JSON com output_dir e metadados.
```

### Cenário D — MFTE instalado externamente pelo usuário (mais simples, técnico)

Para casos onde o usuário é técnico:
- App distribuído sem MFTE bundlado.
- Instruções para instalar MFTE + torch (GPU opcional) separadamente.
- ttwtools importa `process_sentence` de MFTE e `stanza` diretamente (sem subprocess).
- Sem necessidade de hooks complexos no PyInstaller.

---

## 6. Roadmap de Implementação

### Fase 0 — Separação de módulos e migração para formato unificado
- [ ] Criar `ttwtools/taggers/__init__.py` (vazio ou com re-exports)
- [ ] Criar `ttwtools/taggers/biberplus.py` — mover TODO o conteúdo de
  `ttwtools/tagging.py` para cá sem alterar nenhuma lógica ainda
- [ ] **Migrar BiberPlus para o formato unificado com offsets:**
  - Quando `usenlp=True`: usar `token.idx` e `token.idx + len(token.text)` do
    spaCy como `start_char`/`end_char`; `token.tag_` como `xpos`
  - Quando `usenlp=False` (regex): usar `match.start()` / `match.end()` do
    `re.finditer()` como offsets
  - Gravar no formato JSONL canônico via `tagged_io.write_tagged_jsonl()`
    (arquivo `<stem>_biberplus.jsonl` ao lado do original)
  - Remover `_build_interleaved_rows()` e `_escape_tsv_content()` (não necessários
    no novo formato)
- [ ] Converter `ttwtools/tagging.py` em shim de compatibilidade:
  ```python
  # ttwtools/tagging.py — compatibility shim (deprecated, será removido na v2)
  from .taggers.biberplus import (
      biberplus,
      extract_biber_features_from_folder,
      normalize_biber_features,
  )
  ```
- [ ] Atualizar `ttwtools/__init__.py` — importar de `taggers/` em vez de `tagging`
- [ ] Criar `ttwtools/tagged_io.py` com:
  - `write_tagged_jsonl(metadata, tokens, path)` — grava o JSONL canônico
  - `read_tagged_jsonl(path)` → `(metadata: dict, tokens: list[dict])`
  - `export_tagged(jsonl_path, fmt, out_path=None)` — exporta para `"json"`,
    `"tsv"` ou `"csv"`; `out_path=None` deriva o nome do jsonl_path
  - Detecção de formato legacy (`type|content|tags`) pelo cabeçalho com aviso
- [ ] Rodar os exemplos (`exemplo1_00_runall.py` etc.) para confirmar que nada quebrou

### Fase 1 — Engine de tagging MFTE com offsets (fundação)
- [ ] Criar `ttwtools/taggers/mfte.py` com:
  - `_detect_device()` — retorna `"cuda"` | `"mps"` | `"cpu"`
  - `_load_stanza_pipeline(device, model_dir=None)` — carrega Stanza lazy, com
    cache de instância para evitar recarregamento entre documentos
  - `_tag_document_mfte(text, nlp, extended)` — função core descrita em 4.2:
    retorna `list[dict]` com `start`, `end`, `word`, `xpos`, `tags`
  - `_write_tagged_jsonl(token_dicts, path, metadata)` — delega a `tagged_io.write_tagged_jsonl()`
  - `extract_mfte_features_from_folder(folder, output_dir, save_tagged,
    copy_originals, use_gpu, ttr, extended)` — loop sobre `.txt`
  - `mfte()` — alias de alto nível
- [ ] Atualizar `ttwtools/taggers/__init__.py` — importar e re-exportar `mfte`,
  `extract_mfte_features_from_folder` com import lazy (não importar torch/stanza
  no nível do módulo)
- [ ] Atualizar `ttwtools/__init__.py` — exportar `mfte`, `extract_mfte_features_from_folder`
  e `tagged_io`
- [ ] Atualizar `requirements.txt` — dependências opcionais comentadas
- [ ] Atualizar `pyproject.toml`:
  ```toml
  [project.optional-dependencies]
  mfte = ["stanza>=1.9", "MFTE>=1.0", "torch"]
  ```

### Fase 2 — Integração com projeto
- [ ] Adicionar `tagger_type` em `feature_tables` no schema SQLite
- [ ] Migração automática de arquivos .ttwa antigos (ADD COLUMN com DEFAULT)
- [ ] `TTWAProject.add_corpus_folder()` aceitar parâmetro `tagger_type`

### Fase 3 — PyInstaller
- [ ] Investigar API interna do MFTE após `pip install MFTE` (ver `src/`)
- [ ] Criar `ttwtools_mfte_cpu.spec` de referência para Cenário B
- [ ] Criar `mfte_worker_main.py` para Cenário C (companion)
- [ ] Documentar processo de build nos dois cenários

### Fase 4 — Testes e documentação
- [ ] Testes com corpus de exemplo usando MFTE
- [ ] Comparar output MFTE vs BiberPlus para features sobrepostas
- [ ] Notebook de exemplo `exemplo4_mfte.ipynb`
- [ ] Atualizar `docs/README.md`

---

## 7. Questões Abertas (a investigar)

1. **Sentinelas de sentença no process_sentence()**: O MFTE usa strings com 20+
   espaços como sentinelas de limite de sentença na lista de entrada. Verificar
   se o índice `i` da lista de retorno está 1:1 com o de entrada ou se as
   sentinelas são removidas — isso afeta o reassociamento de offsets.

2. **process_sentence_extended() modifica índices?**: Verificar se a segunda
   passagem (`process_sentence_extended`) retorna a mesma lista com os mesmos
   índices ou uma lista diferente.

3. **Modelos Stanza necessários**: O MFTE usa apenas `tokenize` + `pos`. Confirmar
   que `processors='tokenize,pos'` é suficiente (sem `lemma`, `depparse`, `ner`),
   mantendo o modelo menor para bundling.

4. **stanza.download() em ambiente PyInstaller**: Stanza baixa modelos em
   `~/stanza_resources/`. No `mfte_worker.exe`, esse path precisa ser configurável
   via variável de ambiente `STANZA_RESOURCES_DIR` apontando para um diretório
   junto ao executável.

5. **Licença do MFTE**: GPL-3.0 — verificar compatibilidade com a licença do
   ttwtools e com redistribuição em executáveis PyInstaller. O import direto da
   função `process_sentence()` pode ter implicações diferentes do que redistribuir
   o executável com o código bundlado.

6. **Paralelismo**: `process_sentence()` é pura e stateless — segura para rodar
   em paralelo por documento. O pipeline Stanza, porém, não deve ser compartilhado
   entre threads; usar uma instância por processo ou `multiprocessing.Pool`.

7. **Acurácia com contrações sem preprocessing**: Medir impacto de não aplicar
   `stanza_pre_processing()` para preservar offsets. Se a perda for significativa,
   implementar realinhamento via `difflib.SequenceMatcher` entre o texto
   preprocessado e o original.

---

## 8. Próximos Passos Imediatos

1. **Verificar comportamento das sentinelas em process_sentence()**:
   ```python
   conda activate ttw314
   python - <<'EOF'
   from MFTE import process_sentence
   words = [" " * 20, "The_DT", "study_NN", "was_VBD", "conducted_VBN", " " * 20]
   result = process_sentence(words, extended=True)
   for i, (inp, out) in enumerate(zip(words, result)):
       print(i, repr(inp[:10]), "→", repr(out[:40]))
   EOF
   ```
   Confirmar se `len(result) == len(words)` (1:1) ou se sentinelas são removidas.

2. **Verificar device disponível no ambiente ttw314**:
   ```python
   import torch
   print("CUDA:", torch.cuda.is_available())
   print("MPS:", torch.backends.mps.is_available())
   ```

3. **Teste de tagging com offsets** num documento de exemplo:
   ```python
   import stanza
   stanza.download('en', processors='tokenize,pos')
   nlp = stanza.Pipeline('en', processors='tokenize,pos', use_gpu=False)
   text = open('examples/test_corpora/teste_corpus/algum.txt').read()
   doc = nlp(text)
   for sent in doc.sentences:
       for w in sent.words:
           print(w.start_char, w.end_char, w.text, w.xpos)
   ```
   Confirmar que `text[w.start_char:w.end_char] == w.text` para vários tokens.

4. **Implementar `_tag_document_mfte()`** (núcleo da Fase 1) e testar com
   um arquivo do corpus `test_corpora/teste_corpus/`.

5. Avançar para a implementação completa de `mfte_tagger.py` (Fase 1 do roadmap).
