# Referência da API do `ttwtools`

Gerada de `docs/gerar_referencia.py` para a versão 0.2.0.dev0. Não edite à mão.

Funções marcadas com **`ttwtools.nome`** podem ser usadas direto do pacote (`import ttwtools`).
As demais ficam no módulo indicado (ex.: `from ttwtools.experimental import compare_groups`).

## Sumário

- [Projetos (.ttwa, .ttwl, .ttwt)](#project) — `ttwtools.project`
- [Corpora, documentos e metadados](#corpus) — `ttwtools.corpus`
- [Etiquetagem com cache de camadas](#annotate) — `ttwtools.annotate`
- [Taggers: opções, tagsets e disponibilidade](#taggerscatalog) — `ttwtools.taggers.catalog`
- [Formatos de entrada e saída](#formats) — `ttwtools.formats`
- [Consultas: busca, KWIC, frequência, colocados, dispersão](#query) — `ttwtools.query`
- [Estatísticas do corpus](#stats) — `ttwtools.stats`
- [Palavras-chave, listas de referência e faixas de frequência](#keyness) — `ttwtools.keyness`
- [Tabelas de traços e KFA a partir das camadas](#features) — `ttwtools.features`
- [Dados para gráficos de comparação](#viz) — `ttwtools.viz`
- [Laboratório: N grupos (experimental)](#experimental) — `ttwtools.experimental`
- [Catálogo de corpora](#corpus_catalog) — `ttwtools.corpus_catalog`
- [Modelos sob demanda](#models) — `ttwtools.models`
- [KFA e d de Cohen (API clássica)](#analysis) — `ttwtools.analysis`
- [Ajuda e tours](#help) — `ttwtools.help`
- [Traduções](#i18n) — `ttwtools.i18n`
- [Código equivalente (linha de comando e Python)](#codegen) — `ttwtools.codegen`

<a id="project"></a>
## Projetos (.ttwa, .ttwl, .ttwt)

Módulo `ttwtools.project`.

project.py — Persistência de projetos ttwtools em arquivos .ttwa (SQLite).

### `checkpoint` · **`ttwtools.checkpoint`**

```python
checkpoint(path: "'str | Path'") -> 'None'
```

Consolida o WAL no arquivo principal do projeto (antes de copiar ou compactar).

### `compress_project_file`

```python
compress_project_file(source: "'str | Path'", dest: "'str | Path'", progress_cb: "'Optional[Callable[[int, int], None]]'" = None) -> 'None'
```

Compacta o banco `source` em `dest` (gzip rápido). progress_cb(bytes lidos, total).

### `compress_to_ttwt`

```python
compress_to_ttwt(source_ttwa: "'str | Path'", dest_ttwt: "'str | Path'", progress_cb: "'Optional[Callable[[int, int], None]]'" = None) -> 'None'
```

Comprime um arquivo .ttwa (SQLite) para o formato .ttwt (lzma preset máximo).

progress_cb(done_bytes, total_bytes) é chamado a cada chunk lido da fonte.

### `compression_of` · **`ttwtools.compression_of`**

```python
compression_of(path: "'str | Path'") -> 'str | None'
```

"gzip" ou "xz" se o arquivo de projeto está compactado; None se é o banco SQLite direto.

### `create_project` · **`ttwtools.create_project`**

```python
create_project(path: 'str | Path', name: 'str' = '', description: 'str' = '', overwrite: 'bool' = False) -> 'TTWAProject'
```

Cria e retorna um novo projeto .ttwa.

### `decompress_from_ttwt`

```python
decompress_from_ttwt(source_ttwt: "'str | Path'", dest_ttwa: "'str | Path'", progress_cb: "'Optional[Callable[[int, int], None]]'" = None) -> 'None'
```

Descomprime um arquivo .ttwt (xz; gzip também é aceito) para um arquivo .ttwa (SQLite).

O progresso é calculado sobre o tamanho do arquivo comprimido (fonte).
progress_cb(done_bytes, total_bytes) é chamado a cada chunk lido.

### `decompress_project_file`

```python
decompress_project_file(source: "'str | Path'", dest: "'str | Path'", progress_cb: "'Optional[Callable[[int, int], None]]'" = None) -> 'None'
```

Descompacta um projeto (gzip ou xz, conforme o conteúdo) para o banco `dest`.
progress_cb(bytes compactados lidos, total compactado).

### `detach_corpus` · **`ttwtools.detach_corpus`**

```python
detach_corpus(project: 'TTWAProject', dest: 'str | Path | None' = None, corpus_folder: 'str | Path | None' = None) -> 'TTWAProject'
```

`.ttwa` → `.ttwl` + pasta de textos. Devolve o novo projeto aberto.

### `embed_corpus` · **`ttwtools.embed_corpus`**

```python
embed_corpus(project: 'TTWAProject', dest: 'str | Path | None' = None, allow_changed: 'bool' = False) -> 'TTWAProject'
```

`.ttwl` → `.ttwa` (texto para dentro). Devolve o novo projeto aberto.

### `export_corpus_next_to` · **`ttwtools.export_corpus_next_to`**

```python
export_corpus_next_to(project: 'TTWAProject', folder: 'str | Path | None' = None) -> 'Path'
```

Exporta os textos do projeto para uma pasta ao lado dele (ver TTWAProject.export_corpus_next_to).

### `needs_migration` · **`ttwtools.needs_migration`**

```python
needs_migration(path: 'str | Path') -> 'bool'
```

O projeto está num esquema anterior ao v0.3 (abrir vai migrar)? Não altera o arquivo.

### `open_project` · **`ttwtools.open_project`**

```python
open_project(path: 'str | Path', migrate: 'bool' = True, progress: 'Callable[[int, int, str], None] | None' = None) -> 'TTWAProject'
```

Abre um projeto `.ttwa` ou `.ttwl` (o tipo vem do próprio arquivo).

Projetos de esquema antigo são migrados para v0.3 com aviso (ver TTWAProject.open);
`progress(feitos, total, etapa)` acompanha a migração, que pode ser demorada.

### `register_working_copy` · **`ttwtools.register_working_copy`**

```python
register_working_copy(work: "'str | Path'", home: "'str | Path | None'") -> 'None'
```

Informa que `work` é a cópia de trabalho de `home` (None desfaz). Toda abertura de
`work` passa a usar `home` como arquivo real (pasta dos textos do .ttwl, nome, tipo).

### `relink_corpus` · **`ttwtools.relink_corpus`**

```python
relink_corpus(project: 'TTWAProject', folder: 'str | Path', accept_changed: 'bool' = False) -> 'dict'
```

Aponta um `.ttwl` para outra pasta de corpus, conferindo hashes.

### `save_analysis_to_project` · **`ttwtools.save_analysis_to_project`**

```python
save_analysis_to_project(project_path: 'str | Path', corpus1_name: 'str', corpus1_rawcount_csv: 'str | Path', corpus1_norm1000_csv: 'str | Path', corpus2_name: 'str', corpus2_rawcount_csv: 'str | Path', corpus2_norm1000_csv: 'str | Path', kfa_results_df: "'pd.DataFrame | None'" = None, corpus1_folder: 'str | Path | None' = None, corpus2_folder: 'str | Path | None' = None, corpus1_tagged_folder: 'str | Path | None' = None, corpus2_tagged_folder: 'str | Path | None' = None, project_name: 'str' = '', overwrite: 'bool' = False, kfa_min_effect: 'float' = 0.2, kfa_join_method: 'str' = 'union', include_originals: 'bool' = True, tagger_type: 'str' = 'biberplus') -> 'TTWAProject'
```

Função all-in-one: cria (ou sobrescreve) um projeto .ttwa e importa tudo de uma vez.

Parâmetros obrigatórios:
    project_path              — caminho do arquivo .ttwa a criar
    corpus1_name / corpus2_name   — nomes dos dois corpora
    corpus*_rawcount_csv      — CSV de contagens brutas gerado pelo biberplus
    corpus*_norm1000_csv      — CSV normalizado por 1000 palavras

Parâmetros opcionais:
    kfa_results_df            — DataFrame de KFA já calculado
    corpus*_folder            — pasta com os .txt originais (importa conteúdos;
                                ignorado se include_originals=False)
    corpus*_tagged_folder     — pasta com os .tsv tagueados
    include_originals         — True  → modo 'full': salva textos originais + tagged + análise
                                False → modo 'compact': salva apenas tagged + análise
                                O modo fica registrado em project_meta['project_mode'].

Retorna o TTWAProject aberto (não fechado — use .close() ou `with`).

### `save_corpus_as` · **`ttwtools.save_corpus_as`**

```python
save_corpus_as(project: 'TTWAProject', corpus_name: 'str', dest: 'str | Path', progress_cb: "'Optional[Callable[[int, int], None]]'" = None, compress: 'bool' = True, search_tables: 'bool' = True) -> 'Path'
```

Grava um corpus do projeto num arquivo de um corpus só: `.ttwc` (textos dentro) ou
`.ttwcl` (textos numa pasta `<nome>_corpus` ao lado do arquivo).

Vão junto os metadados, as camadas, a lista "a executar" e as análises que só usam
esse corpus (comparações com outros corpora ficam de fora). Compactado por padrão.
O projeto de origem não muda.

### `save_project_as` · **`ttwtools.save_project_as`**

```python
save_project_as(source: "'str | Path'", dest: "'str | Path'", progress_cb: "'Optional[Callable[[int, int], None]]'" = None, compress: 'bool' = True, search_tables: 'bool' = True, progress: "'Optional[Callable[[int, int, str], None]]'" = None) -> 'Path'
```

Grava o projeto `source` (banco aberto) em `dest`, com as alterações recentes.

`search_tables=False` grava sem as tabelas de busca (tokens e índices): as camadas vão
empacotadas e o arquivo fica bem menor, mas a abertura recria as tabelas (demora).
`progress(feitos, total, etapa)` acompanha o empacotamento.

Por padrão o arquivo sai compactado (gzip rápido), em qualquer extensão; `compress=False`
grava o banco direto (abre sem descompactar e salva sozinho, mas é bem maior). `.ttwt`
sai sempre compactado. O WAL é consolidado antes e a gravação vai para `.part`, que só
substitui o destino no fim. `progress_cb(feitos, total)`.

### `TTWAProject` · **`ttwtools.TTWAProject`**

```python
classe TTWAProject(path: 'str | Path', home: 'str | Path | None' = None)
```

Representa um projeto ttwtools persistido em um arquivo .ttwa.

Uso básico::

    proj = TTWAProject.create("meu_projeto.ttwa", name="Tese 2026")
    proj.add_corpus_folder("corpus_A", "/caminho/para/corpus_A")
    proj.save_feature_table("corpus_A", df_raw, "rawcount")
    proj.save_feature_table("corpus_A", df_norm, "norm1000")
    proj.save_kfa_result("corpus_A", "corpus_B", df_kfa)
    proj.close()

    # Reabrir depois
    proj = TTWAProject.open("meu_projeto.ttwa")
    df = proj.load_feature_table("corpus_A", "norm1000")

<a id="corpus"></a>
## Corpora, documentos e metadados

Módulo `ttwtools.corpus`.

corpus.py — Importação de corpora, metadados por documento, tokenização simples e filtros.

### `apply_metadata`

```python
apply_metadata(project: 'TTWAProject', corpus_name: 'str', table: 'Mapping[str, Mapping[str, Any]]') -> 'dict'
```

Aplica {arquivo: metadados} aos documentos do corpus (casa com ou sem `.txt`).

Devolve {"applied": n, "unmatched": [nomes do CSV sem documento]}.

### `filter_documents` · **`ttwtools.filter_documents`**

```python
filter_documents(project: 'TTWAProject', corpus_name: 'str | None' = None, where: 'Mapping[str, str | Iterable[str]] | None' = None) -> 'list[dict]'
```

Documentos do corpus (ou de todos) cujos metadados batem com `where`.

`where` = {chave: valor} ou {chave: [valores aceitos]}; chaves diferentes
se combinam com E, valores da mesma chave com OU. Cada documento vem com
seus metadados em `meta`.

### `get_document_meta` · **`ttwtools.get_document_meta`**

```python
get_document_meta(project: 'TTWAProject', corpus_name: 'str', filename: 'str') -> 'dict[str, str]'
```

Metadados de um documento ({chave: valor}).

### `get_tokenizer_config`

```python
get_tokenizer_config(project: 'TTWAProject', corpus_name: 'str') -> 'TokenizerConfig'
```

Configuração da tokenização simples do corpus (a padrão, se não houver).

### `import_corpus` · **`ttwtools.import_corpus`**

```python
import_corpus(project: 'TTWAProject', source: 'str | Path | None', name: 'str', *, text: 'str | None' = None, text_filename: 'str' = 'texto_colado.txt', glob: 'str' = '*.txt', encoding: 'str' = 'utf-8', filename_fields: 'list[str] | None' = None, delimiter: 'str' = '_', metadata_csv: 'str | Path | None' = None, text_column: 'str' = 'text', filename_column: 'str' = 'filename', tokenizer: 'TokenizerConfig | None' = None) -> 'dict'
```

Importa textos para o corpus `name` do projeto.

source          — pasta de .txt, um arquivo .txt, ou um .csv com uma coluna de
                  texto (`text_column`) e colunas de metadados; None com `text=`.
text            — texto colado (gravado como `text_filename`, sem sobrescrever).
filename_fields — nomes dos campos no nome do arquivo, separados por `delimiter`.
metadata_csv    — CSV com a coluna `filename_column` e colunas de metadados.
tokenizer       — configuração da tokenização simples deste corpus.

Devolve {"corpus", "imported", "files", "metadata_applied", "unmatched"}.

### `layer_summary` · **`ttwtools.layer_summary`**

```python
layer_summary(project: 'TTWAProject', corpus_name: 'str') -> 'list[dict]'
```

Camadas do corpus agrupadas por configuração: ferramenta, versão, modelo,
configuração efetiva, quantos documentos cobre e quantos tokens tem.

### `list_corpora` · **`ttwtools.list_corpora`**

```python
list_corpora(project: 'TTWAProject') -> 'list[dict]'
```

Corpora do projeto: documentos, caracteres, chaves de metadados e camadas.

### `list_groups` · **`ttwtools.list_groups`**

```python
list_groups(project: 'TTWAProject', corpus_name: 'str | None', key: 'str') -> 'dict[str, int]'
```

Valores de um metadado e quantos documentos têm cada um.

### `meta_from_filename`

```python
meta_from_filename(filename: 'str', fields: 'list[str]', delimiter: 'str' = '_') -> 'dict[str, str]'
```

Metadados a partir do nome do arquivo: `grupoA_texto01.txt` com fields
["grupo", "texto"] → {"grupo": "grupoA", "texto": "texto01"}. O último campo
recebe o resto do nome; campos a mais ficam de fora; campo vazio ("") pula
aquele pedaço.

### `metadata_keys`

```python
metadata_keys(project: 'TTWAProject', corpus_name: 'str | None' = None) -> 'list[str]'
```

Chaves de metadados usadas nos documentos do corpus, em ordem alfabética.

### `parse_where`

```python
parse_where(items: 'Iterable[str]') -> 'dict[str, list[str]]'
```

["grupo=A", "grupo=B", "ano=2020"] → {"grupo": ["A", "B"], "ano": ["2020"]} (linha de comando).

### `read_metadata_csv`

```python
read_metadata_csv(path: 'str | Path', filename_column: 'str' = 'filename') -> 'dict[str, dict[str, str]]'
```

CSV de metadados → {arquivo: {coluna: valor}}. Aceita `;` ou `,` e BOM.

### `set_document_meta` · **`ttwtools.set_document_meta`**

```python
set_document_meta(project: 'TTWAProject', corpus_name: 'str', filename: 'str', meta: 'Mapping[str, Any]') -> 'None'
```

Grava (ou substitui) pares chave/valor de metadados de um documento.

### `set_tokenizer_config`

```python
set_tokenizer_config(project: 'TTWAProject', corpus_name: 'str', config: 'TokenizerConfig') -> 'None'
```

Grava a configuração da tokenização simples do corpus.

### `tokenize` · **`ttwtools.tokenize`**

```python
tokenize(text: 'str', config: 'TokenizerConfig | None' = None) -> 'list[str]'
```

Divide o texto em tokens conforme a configuração.

### `TokenizerConfig` · **`ttwtools.TokenizerConfig`**

```python
classe TokenizerConfig(lowercase: 'bool' = False, keep_punct: 'bool' = False, keep_numbers: 'bool' = True, contractions: 'str' = 'keep') -> None
```

Opções da tokenização simples (sem tagger).

lowercase       — tudo em minúsculas
keep_punct      — manter sinais de pontuação como tokens
keep_numbers    — manter números (ex.: 2026, 3,5)
contractions    — "keep": `don't` é um token; "split": `do` + `n't`, `it` + `'s`

<a id="annotate"></a>
## Etiquetagem com cache de camadas

Módulo `ttwtools.annotate`.

annotate.py — Etiquetar corpus com cache de camadas (novomodelo.md §9.4 e §11.4).

### `build_request` · **`ttwtools.build_request`**

```python
build_request(tagger: 'str', options: 'Mapping[str, Any] | None' = None, components: 'Iterable[str] | None' = None, preset: 'str | None' = None) -> 'dict'
```

Normaliza um pedido: opções padrão por extenso, componentes e versões.

tagger  — nome ou atalho (spacy, spacy_upos, stanza_xpos, mfte_ext, biberplus...)
options — dicionário único de opções, validado contra o descritor do tagger
          (data/taggers/<tagger>.options.json); `components` pode vir aqui ou à parte
preset  — "rapido", "recomendado" ou "preciso": preenche opções (as explícitas vencem)

Devolve {"tool", "tool_version", "model", "config", "performance"}; `config`
é a configuração efetiva que identifica a camada (sem as opções de desempenho).

### `find_layer` · **`ttwtools.find_layer`**

```python
find_layer(project: 'TTWAProject', doc: 'Mapping[str, Any]', request: 'dict') -> 'dict | None'
```

Camada do documento que atende o pedido (ou None).

`doc` é um dicionário com `id` e `content_hash` (como os de `filter_documents`).
Uma camada feita sobre um texto que depois mudou não serve.

### `plan_tagging` · **`ttwtools.plan_tagging`**

```python
plan_tagging(project: 'TTWAProject', corpus_name: 'str', tagger: 'str', options: 'Mapping[str, Any] | None' = None, components: 'Iterable[str] | None' = None, where: 'Mapping[str, Any] | None' = None, preset: 'str | None' = None) -> 'dict'
```

O que `tag_corpus` faria, sem etiquetar: quantos documentos já têm camada
suficiente (`reusable`), quantos podem copiar de outro com o mesmo texto
(`clonable`), quantos serão processados (`to_tag`) e quantos estão sem texto.

### `tag_corpus` · **`ttwtools.tag_corpus`**

```python
tag_corpus(project: 'TTWAProject', corpus_name: 'str', tagger: 'str', options: 'Mapping[str, Any] | None' = None, components: 'Iterable[str] | None' = None, where: 'Mapping[str, Any] | None' = None, force: 'bool' = False, progress: 'Callable[[int, int, str], None] | None' = None, preset: 'str | None' = None, filenames: 'Iterable[str] | None' = None) -> 'dict'
```

Etiqueta os documentos do corpus que ainda não têm camada suficiente.

filenames — só estes documentos (além do filtro `where`)

tagger/options/components/preset — ver build_request

where    — filtro por metadado (ver corpus.filter_documents)
force    — etiqueta de novo mesmo havendo camada
progress — progress(feitos, total, arquivo)

Devolve {"corpus", "tool", "documents", "tagged", "reused", "cloned",
"missing_text", "layer_ids"}.

<a id="taggerscatalog"></a>
## Taggers: opções, tagsets e disponibilidade

Módulo `ttwtools.taggers.catalog`.

catalog.py — Descritores de opções, tagsets e disponibilidade dos taggers.

### `available`

```python
available(lang: 'str | None' = None) -> 'list[dict]'
```

Um item por tagger: `disponivel` (bool), `motivo` (texto) e `comando` para resolver.

Nunca levanta exceção por dependência ausente: ImportError vira "indisponível".

### `default_components`

```python
default_components(tagger: 'str') -> 'list[str]'
```

Componentes que o tagger roda por padrão (segundo o descritor).

### `get_tagset`

```python
get_tagset(tagset_or_tagger: 'str', lang: 'str | None' = None, group: 'str | None' = None) -> 'dict'
```

Repertório de tags. Aceita o id do tagset (upos, ptb, biber, mfte) ou do
tagger (spacy_upos → upos, stanza_xpos → ptb, biberplus → biber...).
Textos no idioma `lang` (padrão: TTWTOOLS_LANG ou pt); `lang=False` = chaves.

### `has_descriptor`

```python
has_descriptor(tagger: 'str') -> 'bool'
```

O tagger (ou atalho) tem descritor de opções?

### `language_defaults`

```python
language_defaults(tagger_id: 'str', lang: 'str | None', current: 'Mapping[str, Any] | None' = None) -> 'dict'
```

Opções que adaptam o tagger ao idioma do corpus (ex.: pt → model=pt_core_news_sm
no spaCy, lang=pt no Stanza). Com `current` (ex.: um atalho), mantém o tamanho do
modelo (sm, md, lg; trf → o maior disponível); senão prefere o menor já instalado.
Devolve só o que muda ({} se nada muda).

### `list_tagsets`

```python
list_tagsets() -> 'list[str]'
```

Ids dos tagsets com repertório documentado (upos, ptb, biber, mfte...).

### `options`

```python
options(tagger_id: 'str', lang: 'str | None | bool' = None) -> 'dict'
```

Descritor de opções do tagger, com os textos no idioma `lang` (padrão:
TTWTOOLS_LANG ou pt). `lang=False` devolve as chaves de tradução.

### `performance_keys`

```python
performance_keys(tagger: 'str') -> 'set[str]'
```

Opções que só mudam desempenho (lote, processos...), fora do cache de camadas.

### `preset`

```python
preset(tagger_id: 'str', name: 'str') -> 'dict'
```

Opções de um atalho do tagger (rapido, recomendado, preciso).

### `require_available`

```python
require_available(tagger: 'str') -> 'None'
```

Levanta TaggerUnavailable (com motivo e comando) se o tagger não puder rodar.

### `resolve`

```python
resolve(tagger_id: 'str') -> 'tuple[str, dict]'
```

`spacy_upos` → ("spacy", {"tagset": "upos"}); erro claro para id desconhecido.

### `result_defaults`

```python
result_defaults(tagger: 'str') -> 'dict'
```

Valores padrão das opções que mudam o resultado (sem os componentes).

### `run`

```python
run(tagger_id: 'str', corpus: 'str', options: 'Mapping[str, Any] | None' = None, *, project=None, preset: 'str | None' = None, components: 'Iterable[str] | None' = None, **kwargs)
```

Etiqueta um corpus com um único dicionário de opções, validado contra o descritor.

Com `project`, etiqueta o corpus do projeto com cache de camadas (annotate.tag_corpus)
e aceita `where`, `force` e `progress`. Sem `project`, `corpus` é uma pasta de .txt e
roda a função antiga do tagger (mesmos arquivos CSV/JSONL de antes); `kwargs` vão
direto para ela (atalhos antigos: `output_dir`, `save_tagged`...).

### `spacy_model_installed`

```python
spacy_model_installed(model: 'str') -> 'bool'
```

O modelo do spaCy pode ser importado (instalado no ambiente ou baixado)?

### `stanza_download_command`

```python
stanza_download_command(lang: 'str', package: 'str', processors: 'str' = 'tokenize,pos,lemma') -> 'str'
```

Comando para baixar o pacote de modelos do Stanza para o idioma.

### `stanza_model_dir`

```python
stanza_model_dir(model_dir: 'str | None' = None) -> 'Path'
```

Pasta dos modelos do Stanza (argumento, STANZA_RESOURCES_DIR ou a padrão).

### `stanza_package_installed`

```python
stanza_package_installed(lang: 'str', package: 'str', processors: 'Iterable[str]' = ('tokenize', 'pos'), model_dir: 'str | None' = None) -> 'bool'
```

Os modelos do pacote Stanza estão baixados? (sem baixar nada)

### `TaggerUnavailable`

```python
classe TaggerUnavailable(tagger: 'str', reason: 'str', command: 'str | None' = None)
```

Tagger ou modelo indisponível; `reason` explica e `command` diz como resolver.

### `validate_options`

```python
validate_options(tagger_id: 'str', opts: 'Mapping[str, Any] | None') -> 'dict'
```

Confere tipos e valores contra o descritor. Devolve as opções (sem alterar).

### `value_availability`

```python
value_availability(tagger_id: 'str') -> 'dict[str, dict[str, dict]]'
```

Para opções cujos valores dependem de algo instalado (modelos do spaCy,
pacotes do Stanza): {opção: {valor: {"installed": bool, "command": str}}}. Pacotes do
Stanza de outro idioma vêm em `opção@idioma` (ex.: "package@pt").

<a id="formats"></a>
## Formatos de entrada e saída

Módulo `ttwtools.formats`.

formats — Entrada e saída em formatos de corpus (novomodelo.md §9.2).

### `document_layers`

```python
document_layers(project: 'TTWAProject', corpus_name: 'str', tool: 'str | None' = None, where: 'dict | None' = None) -> 'list[tuple[dict, dict]]'
```

[(documento, camada)] com uma camada por documento: a mais recente da
ferramenta pedida (ou de qualquer uma). Documentos sem camada ficam de fora.

### `export_conllu`

```python
export_conllu(project: 'TTWAProject', corpus_name: 'str', out: 'str | Path', tool: 'str | None' = None, where: 'dict | None' = None) -> 'dict'
```

Escreve CoNLL-U de uma camada (a mais recente de `tool`) de cada documento.

### `export_tokens`

```python
export_tokens(project: 'TTWAProject', corpus_name: 'str', out: 'str | Path', fmt: 'str' = 'csv', tool: 'str | None' = None, where: 'dict | None' = None) -> 'dict'
```

Exporta os tokens de uma camada como tabela: CSV, JSONL ou Parquet (se houver pyarrow).

### `export_vrt`

```python
export_vrt(project: 'TTWAProject', corpus_name: 'str', out: 'str | Path', tool: 'str | None' = None, where: 'dict | None' = None) -> 'dict'
```

Escreve o corpus em VRT a partir da camada (mais recente de `tool`) de cada documento.

### `import_conllu`

```python
import_conllu(project: 'TTWAProject', path: 'str | Path', corpus_name: 'str') -> 'dict'
```

Importa um arquivo CoNLL-U: um documento por `# newdoc` e uma camada `conllu`.

### `import_graf`

```python
import_graf(project: 'TTWAProject', source: 'str | Path', corpus_name: 'str', token_file: 'str | None' = None, encoding: 'str' = 'utf-8') -> 'dict'
```

Importa uma pasta do OANC/MASC (ou um cabeçalho .anc/.hdr) para `corpus_name`,
com uma camada `graf` (forma, lema, PTB e UPOS) por documento.

### `import_nltk_tagged`

```python
import_nltk_tagged(project: 'TTWAProject', source: 'str | Path', corpus_name: 'str', glob: 'str' = '*', tagset: 'str' = '') -> 'dict'
```

Importa um arquivo ou uma pasta de arquivos `palavra/TAG` (um documento por arquivo).

### `import_tei`

```python
import_tei(project: 'TTWAProject', source: 'str | Path', corpus_name: 'str', glob: 'str' = '*.xml') -> 'dict'
```

Importa um arquivo TEI ou uma pasta de arquivos TEI. Texto anotado (`<w>`) ganha uma camada `tei`.

### `parse_conllu`

```python
parse_conllu(source: 'str | Path', default_doc: 'str' = 'doc') -> 'list[dict]'
```

Lê CoNLL-U e devolve documentos: {"id", "text", "tokens", "meta"}.

`source` é um caminho ou o próprio conteúdo. Cada token segue o formato
canônico (start_char, end_char, word, lemma, upos, xpos, feats) + campos
CoNLL-U em chaves próprias (head, deprel, deps, misc, conllu_id, sent, mwt).

### `parse_graf`

```python
parse_graf(text: 'str', annotations: 'dict[str, Path]', token_file: 'str | None' = None) -> 'dict'
```

Tokens e frases de um documento GrAF. Devolve {"tokens", "token_file", "mismatches", "sentences"}.

### `parse_nltk_tagged`

```python
parse_nltk_tagged(source: 'str | Path', lowercase_tags: 'bool' = False) -> 'dict'
```

Lê um arquivo `palavra/TAG` → {"text", "tokens"} (uma frase por linha).

### `parse_tei`

```python
parse_tei(source: 'str | Path') -> 'list[dict]'
```

Documentos de um arquivo TEI: [{"id", "text", "tokens", "meta", "tag_attr"}].

### `read_header`

```python
read_header(path: 'str | Path') -> 'dict'
```

Cabeçalho `.anc`/`.hdr`: {"text": caminho do .txt, "annotations": {f.id: caminho}, "meta": {...}}.

### `sentences_of`

```python
sentences_of(tokens: 'list[dict]') -> 'list[list[dict]]'
```

Divide os tokens em frases: pelo índice de frase gravado pela camada
(`sent`, em `extra`), ou, na falta dele, por pontuação final (. ! ?).

### `write_conllu`

```python
write_conllu(docs: 'list[tuple[dict, list[dict]]]') -> 'str'
```

[(documento, tokens da camada)] → texto CoNLL-U.

<a id="query"></a>
## Consultas: busca, KWIC, frequência, colocados, dispersão

Módulo `ttwtools.query`.

query.py — Busca, KWIC, frequência, colocados e dispersão sobre a tabela `tokens`.

### `collocates` · **`ttwtools.collocates`**

```python
collocates(project: 'TTWAProject', corpus_name: 'str', node: 'str', window: 'tuple[int, int]' = (5, 5), unit: 'str' = 'form', layer: 'str | None' = None, where: 'Mapping | None' = None, min_freq: 'int' = 2, top: 'int' = 50, sort: 'str' = 'll') -> 'dict'
```

Colocados de `node` (um token da sintaxe de consulta) numa janela (esquerda,
direita) de palavras. Medidas: freq (observada), MI, T-score e log-likelihood
(tabela 2×2, como no #LancsBox). `position` indica onde o colocado aparece mais.

### `dispersion` · **`ttwtools.dispersion`**

```python
dispersion(project: 'TTWAProject', corpus_name: 'str', query: 'str', layer: 'str | None' = None, where: 'Mapping | None' = None) -> 'dict'
```

DP de Gries (2008) e Range da consulta, com as posições relativas de cada
ocorrência por documento (0 a 1) para o gráfico de "código de barras".

DP = ½ Σ |oᵢ − eᵢ|, com oᵢ = parte das ocorrências no documento i e eᵢ = parte
do corpus que o documento i representa. 0 = distribuição uniforme; perto de 1 =
concentrada. DP_norm = DP / (1 − min eᵢ).

### `explain`

```python
explain(project: 'TTWAProject', corpus_name: 'str', query: 'str', layer: 'str | None' = None) -> 'list[str]'
```

Plano de execução do SQLite para a consulta (para conferir o uso de índices).

### `frequency` · **`ttwtools.frequency`**

```python
frequency(project: 'TTWAProject', corpus_name: 'str', unit: 'str' = 'form', n: 'int' = 2, by: 'str' = 'corpus', layer: 'str | None' = None, where: 'Mapping | None' = None, top: 'int | None' = 100, words_only: 'bool' = True, stop: 'Iterable[str] | None' = None) -> 'dict'
```

Lista de frequência. `unit`: form, lemma, word_pos, pos ou ngram (de formas,
tamanho `n`). `by`: corpus, document ou o nome de um metadado (grupo).
Devolve freq absoluta e por 1000 palavras.

### `kwic` · **`ttwtools.kwic`**

```python
kwic(project: 'TTWAProject', corpus_name: 'str', query: 'str', layer: 'str | None' = None, where: 'Mapping | None' = None, context: 'int' = 5, limit: 'int' = 50, offset: 'int' = 0, sort: 'str' = 'position', with_sentence: 'bool' = True) -> 'dict'
```

Concordância: cada ocorrência com `context` tokens de cada lado, classe,
arquivo e posição no texto. Paginada (`limit`/`offset`) no SQL; `sort` =
position, left (palavra à esquerda) ou right (palavra à direita).

### `read_document` · **`ttwtools.read_document`**

```python
read_document(project: 'TTWAProject', corpus_name: 'str', filename: 'str', layer: 'str | None' = None) -> 'dict'
```

Texto de um documento e os tokens da camada (a mais recente de `layer`, ou de
qualquer ferramenta), para o leitor com etiquetas. `text` é None se o texto não
estiver disponível (.ttwl sem a pasta do corpus).

### `search` · **`ttwtools.search`**

```python
search(project: 'TTWAProject', corpus_name: 'str', query: 'str', layer: 'str | None' = None, where: 'Mapping | None' = None, group_by: 'str | None' = None) -> 'dict'
```

Quantas vezes a consulta aparece: total, por documento e (com `group_by`,
nome de metadado) por grupo.

<a id="stats"></a>
## Estatísticas do corpus

Módulo `ttwtools.stats`.

stats.py — Estatísticas descritivas do corpus (novomodelo.md §12).

### `cttr`

```python
cttr(tokens: 'list[str]') -> 'float | None'
```

TTR corrigida de Carroll: types / sqrt(2 × tokens).

### `describe` · **`ttwtools.describe`**

```python
describe(project: 'TTWAProject', corpus_name: 'str', layer: 'str | None' = None, where: 'Mapping | None' = None, top: 'int' = 20, sttr_block: 'int' = 1000, mattr_window: 'int' = 50, hide_stopwords: 'bool' = False, stopwords_lang: 'str | None' = None, extra_stopwords: 'Iterable[str] | None' = None, own_stopwords: 'Iterable[str] | None' = None, use_cache: 'bool' = True, cache_only: 'bool' = False) -> 'dict | None'
```

Estatísticas do corpus (§12.1) e, com `layer` (ferramenta: spacy, stanza...), da camada (§12.2).

Devolve {"text": {...}, "layer": {...} ou None, "cached": bool}. `hide_stopwords`
tira as palavras funcionais da lista de mais frequentes (não das contagens).
`cache_only` devolve só o resultado guardado (ou None), sem calcular.

### `guess_language`

```python
guess_language(project: 'TTWAProject', corpus_name: 'str', sample_docs: 'int' = 20) -> 'str | None'
```

Idioma do corpus: o das camadas (modelo en_*/pt_*, Stanza lang), senão o que tiver
mais palavras funcionais numa amostra do texto (entre os idiomas com lista).

### `mattr`

```python
mattr(docs: 'list[list[str]]', window: 'int') -> 'float | None'
```

TTR média móvel (Covington & McFall): média da TTR de todas as janelas de
`window` palavras de cada documento; documentos menores que a janela usam a TTR simples.

### `stopword_languages`

```python
stopword_languages() -> 'list[str]'
```

Idiomas com lista de palavras funcionais (data/stopwords).

### `stopwords` · **`ttwtools.stopwords`**

```python
stopwords(lang: 'str' = 'en', add: 'Iterable[str] | None' = None, replace: 'Iterable[str] | None' = None) -> 'set[str]'
```

Lista de palavras funcionais do idioma (data/stopwords/<lang>.txt), com
palavras acrescentadas (`add`) ou uma lista própria no lugar (`replace`).

### `sttr`

```python
sttr(docs: 'list[list[str]]', block: 'int') -> 'float | None'
```

TTR padronizada: média da TTR de blocos consecutivos de `block` palavras
dentro de cada documento (blocos incompletos ficam de fora).

### `ttr`

```python
ttr(tokens: 'list[str]') -> 'float | None'
```

Razão tipo/ocorrência (TTR) de uma lista de tokens.

<a id="keyness"></a>
## Palavras-chave, listas de referência e faixas de frequência

Módulo `ttwtools.keyness`.

keyness.py — Palavras-chave de um alvo contra uma referência (novomodelo.md §16).

### `chi2_p`

```python
chi2_p(x: 'float') -> 'float'
```

Valor-p do qui-quadrado com 1 grau de liberdade.

### `comparability`

```python
comparability(target: 'FreqTable', reference: 'FreqTable', unit: 'str', lang: 'str | None' = None) -> 'list[dict]'
```

Avisos estruturados: {"code", "severity", "message", "params"}.

### `corpus_freqs`

```python
corpus_freqs(project: 'TTWAProject', corpus_name: 'str', unit: 'str' = 'form', n: 'int' = 2, layer: 'str | None' = None, where: 'Mapping | None' = None, exclude: 'Mapping | None' = None) -> 'FreqTable'
```

Frequências de um corpus do projeto (com filtro `where`, ou excluindo os
documentos que batem com `exclude`).

### `FreqTable`

```python
classe FreqTable(counts: 'Counter', docs: 'Counter | None', words: 'int', n_docs: 'int', meta: 'dict' = <factory>, doc_ids: 'frozenset' = frozenset(), doc_words: 'dict | None' = None, doc_counts: 'dict | None' = None) -> None
```

Frequências agregadas de um lado da comparação.

### `frequency_bands` · **`ttwtools.frequency_bands`**

```python
frequency_bands(project: 'TTWAProject', corpus_name: 'str', reference: 'str | Path | FreqTable', unit: 'str' = 'form', bands: 'tuple[int, ...]' = (1000, 2000, 3000, 5000, 10000), layer: 'str | None' = None, where: 'Mapping | None' = None, examples: 'int' = 8) -> 'dict'
```

Perfil de frequência lexical (Laufer & Nation 1995): quanto do texto está entre
as 1.000, 2.000... palavras mais frequentes da referência, e quanto fica fora da lista.
`reference` como em keywords() (lista .tsv, `catalog:<id>`, outro corpus ou FreqTable).
Devolve {"rows": [{band, from, to, tokens, types, pct_tokens, pct_types, examples}],
"tokens", "types", "reference", "reference_words", "unit"}.

### `keyword_rows`

```python
keyword_rows(target: 'FreqTable', ref: 'FreqTable', unit: 'str' = 'form', measure: 'str' = 'll', min_freq: 'int' = 5, min_range: 'int' = 1, correction: 'str' = 'bonferroni', alpha: 'float' = 0.05, both_directions: 'bool' = True) -> 'list[dict]'
```

Linhas de palavras-chave de `target` contra `ref`, já com p corrigido e ordenadas.

### `keywords` · **`ttwtools.keywords`**

```python
keywords(project: 'TTWAProject', corpus_name: 'str', reference: 'str | Path | FreqTable', unit: 'str' = 'form', measure: 'str' = 'll', n: 'int' = 2, layer: 'str | None' = None, where: 'Mapping | None' = None, reference_where: 'Mapping | None' = None, min_freq: 'int' = 5, min_range: 'int' = 1, correction: 'str' = 'bonferroni', alpha: 'float' = 0.05, top: 'int | None' = 100, both_directions: 'bool' = True, lang: 'str | None' = None, save: 'bool' = True) -> 'dict'
```

Palavras-chave do alvo (`corpus_name` + `where`) contra `reference`:
uma lista `.tsv`, o nome de outro corpus do projeto, `rest:<metadado>` (os
documentos do mesmo corpus fora de `where`) ou uma FreqTable.

Filtros: `min_freq` (no alvo, para itens do alvo; na referência, para os
negativos) e `min_range` (textos do alvo em que o item aparece). Ordena pela
`measure`; devolve também as demais medidas, p e p corrigido, e `warnings`.

### `log_likelihood`

```python
log_likelihood(a: 'float', b: 'float', c: 'float', d: 'float') -> 'float'
```

LL de Rayson & Garside (2000), duas células.

### `log_odds`

```python
log_odds(a: 'float', b: 'float', c: 'float', d: 'float') -> 'tuple[float, float]'
```

Log da razão de chances com +0,5 em cada célula, e o z correspondente.

### `log_ratio`

```python
log_ratio(a: 'float', b: 'float', c: 'float', d: 'float') -> 'float'
```

Log2 da razão das frequências relativas (Hardie 2014; 0,5 no lugar de zero).

### `make_reference_list` · **`ttwtools.make_reference_list`**

```python
make_reference_list(project: 'TTWAProject', corpus_name: 'str', out: 'str | Path', unit: 'str' = 'form', layer: 'str | None' = None, card: 'Mapping[str, Any] | None' = None) -> 'Path'
```

Gera a lista de referência de um corpus do projeto (para distribuir no catálogo).

### `pct_diff`

```python
pct_diff(a: 'float', b: 'float', c: 'float', d: 'float') -> 'float'
```

%DIFF de Gabrielatos & Marchi (2012).

### `read_reference_list` · **`ttwtools.read_reference_list`**

```python
read_reference_list(path: 'str | Path') -> 'FreqTable'
```

Lê uma lista de referência `.tsv` (ficha na 1ª linha) como FreqTable.

### `write_reference_list`

```python
write_reference_list(path: 'str | Path', table: 'FreqTable', card: 'Mapping[str, Any] | None' = None) -> 'Path'
```

Grava uma lista de frequência de referência (.tsv com a ficha na 1ª linha).

<a id="features"></a>
## Tabelas de traços e KFA a partir das camadas

Módulo `ttwtools.features`.

features.py — Tabelas de traços a partir das camadas e KFA entre corpora ou grupos.

### `default_feature`

```python
default_feature(tool: 'str') -> 'str'
```

Traço padrão da camada: `tags` no BiberPlus/MFTE, `upos` nos demais.

### `feature_table` · **`ttwtools.feature_table`**

```python
feature_table(project: 'TTWAProject', corpus_name: 'str', layer: 'str', feature: 'str | None' = None, per1000: 'bool' = False, where: 'Mapping | None' = None) -> 'pd.DataFrame'
```

Uma linha por documento: filename, Words, TTR e uma coluna por traço
(contagem bruta ou por 1000 palavras).

### `feature_values`

```python
feature_values(project: 'TTWAProject', corpus_name: 'str', layer: 'str', feature_name: 'str', feature: 'str | None' = None, where: 'Mapping | None' = None) -> 'list[dict]'
```

Valor por 1000 palavras de um traço em cada documento (detalhe do traço).

### `kfa_layers` · **`ttwtools.kfa_layers`**

```python
kfa_layers(project: 'TTWAProject', corpus1: 'str', corpus2: 'str', layer: 'str', feature: 'str | None' = None, metric: 'str' = 'kfa', min_effect: 'float' = 0.0, join: 'str' = 'union', where1: 'Mapping | None' = None, where2: 'Mapping | None' = None, save: 'bool' = True) -> 'dict'
```

KFA (d de Cohen por traço, por 1000 palavras) entre dois corpora — ou dois
grupos do mesmo corpus, com `where1`/`where2`. `metric`: kfa (Biber & Egbert)
ou kfa2 (desvio combinado ponderado).

<a id="viz"></a>
## Dados para gráficos de comparação

Módulo `ttwtools.viz`.

viz.py — Dados para os gráficos de comparação (a interface só desenha).

### `feature_matrix`

```python
feature_matrix(project: 'TTWAProject', sides: 'list[Mapping]', layer: 'str', features: 'Iterable[str] | None' = None, feature: 'str | None' = None, top: 'int' = 20) -> 'dict'
```

Valor (por 1000 palavras) de cada traço em cada texto, com o lado de cada texto.
Sem `features`, usa os `top` de maior variância.

### `heatmap`

```python
heatmap(project: 'TTWAProject', sides: 'list[Mapping]', layer: 'str', feature: 'str | None' = None, top: 'int' = 20) -> 'dict'
```

z-score de cada traço (colunas) em cada texto (linhas), textos agrupados por lado.

### `reduction`

```python
reduction(project: 'TTWAProject', sides: 'list[Mapping]', layer: 'str', method: 'str' = 'pca2d', feature: 'str | None' = None, top_features: 'int' = 30, perplexity: 'float' = 30.0, n_neighbors: 'int' = 15, min_dist: 'float' = 0.1, metric: 'str' = 'euclidean', random_state: 'int' = 42) -> 'dict'
```

Projeção 2D/3D dos textos. Devolve coords [{filename, side, x, y[, z]}], variância
explicada (PCA) e cargas dos traços (PCA 2D).

<a id="experimental"></a>
## Laboratório: N grupos (experimental)

Módulo `ttwtools.experimental`.

experimental.py — Laboratório: comparar N grupos (novomodelo.md §14). API EXPERIMENTAL:
nomes, parâmetros e resultados podem mudar entre versões.

### `compare_groups`

```python
compare_groups(project: 'TTWAProject', groups: 'list[Mapping]', layer: 'str', method: 'str' = 'one_vs_rest', feature: 'str | None' = None, metric: 'str' = 'kfa', top: 'int' = 10, correction: 'str' = 'fdr', lang: 'str | None' = None, save: 'bool' = True) -> 'dict[str, Any]'
```

Compara N grupos de textos pelos traços da camada `layer` (ver o cabeçalho do módulo).
Devolve {"method", "groups": [{label, n}], "warnings", ...resultado do método}.

### `groups_by_metadata`

```python
groups_by_metadata(project: 'TTWAProject', corpus_name: 'str', key: 'str', values: 'list[str] | None' = None) -> 'list[dict]'
```

Um grupo por valor do metadado `key` (ou só os `values` pedidos).

<a id="corpus_catalog"></a>
## Catálogo de corpora

Módulo `ttwtools.corpus_catalog`.

corpus_catalog.py — Pacotes de corpus, catálogo e instalação (novomodelo.md §6, §9.5, §16.3–16.5).

### `catalog_url`

```python
catalog_url() -> 'str | None'
```

URL (ou caminho) do catálogo: settings.json → TTWTOOLS_CATALOG_URL. Sem padrão até a
decisão de hospedagem (D6).

### `data_dir`

```python
data_dir() -> 'Path'
```

Pasta de dados do usuário (corpora e modelos baixados). TTWTOOLS_DATA_DIR muda o lugar.

### `install`

```python
install(package_id: 'str', version: 'str | None' = None, catalog: 'Mapping | None' = None, progress: 'Callable[[int, int, str], None] | None' = None) -> 'dict'
```

Baixa, confere o hash e extrai o pacote. Devolve o item de installed().

### `installed`

```python
installed() -> 'list[dict]'
```

Pacotes instalados: ficha + caminho de cada um.

### `load_catalog`

```python
load_catalog(url: 'str | None' = None) -> 'dict'
```

Lê o catálogo (URL http(s) ou arquivo; padrão: o configurado) e confere o formato.

### `make_package`

```python
make_package(project_path: 'str | Path', out_dir: 'str | Path', ficha: 'Mapping[str, Any]', corpus_name: 'str | None' = None, include_corpus: 'bool' = True, reference_units: 'tuple[str, ...]' = ('form', 'lemma', 'pos'), layer: 'str | None' = None) -> 'dict'
```

Cria `<id>-<versão>.zip` com a ficha, o projeto e/ou as listas de referência.
Completa a ficha com tamanho, camadas e hashes. Devolve a entrada do catálogo.

### `make_reference_package`

```python
make_reference_package(project_path: 'str | Path', out_dir: 'str | Path', ficha: 'Mapping[str, Any]', corpus_name: 'str | None' = None, layer: 'str | None' = None) -> 'dict'
```

Pacote só com as listas de frequência (`<id>-lista`): a referência de palavras-chave
e das faixas de frequência sem baixar o corpus. A licença é a da lista derivada
(`license.reference_list`), que pode diferir da do texto.

### `reference_list_path`

```python
reference_list_path(ref: 'str', unit: 'str' = 'form') -> 'Path'
```

Caminho da lista `catalog:<id>[@versão]` na unidade pedida (a versão mais nova instalada).

### `reference_lists`

```python
reference_lists() -> 'list[dict]'
```

Listas de referência instaladas (pacotes completos ou `-lista`), uma por unidade.
`ref` é o que `keywords()`/`frequency_bands()` aceitam: `catalog:<id>`.

### `remove`

```python
remove(package_id: 'str', version: 'str | None' = None) -> 'int'
```

Remove as versões instaladas (todas, ou só `version`). Devolve quantas.

### `set_setting`

```python
set_setting(key: 'str', value: 'Any') -> 'None'
```

Grava uma configuração em settings.json da pasta de dados.

### `settings`

```python
settings() -> 'dict'
```

Configurações do usuário (settings.json da pasta de dados).

### `updates`

```python
updates(catalog: 'Mapping | None' = None) -> 'list[dict]'
```

Pacotes instalados com versão mais nova no catálogo.

### `validate_catalog`

```python
validate_catalog(catalog: 'Mapping[str, Any]') -> 'list[str]'
```

Erros do catálogo (lista vazia = válido), incluindo a regra de licença de cada entrada.

### `validate_ficha`

```python
validate_ficha(ficha: 'Mapping[str, Any]', for_catalog: 'bool' = True) -> 'list[str]'
```

Erros da ficha de um corpus; `for_catalog` exige licença conferida, redistribuível e tamanho.

### `version_key`

```python
version_key(version: 'str') -> 'list[tuple[int, int | str]]'
```

Ordena versões por partes: números como números, texto depois de número.

### `write_catalog`

```python
write_catalog(entries: 'list[Mapping]', path: 'str | Path') -> 'dict'
```

Valida e grava `catalogo.json` com as entradas dadas.

<a id="models"></a>
## Modelos sob demanda

Módulo `ttwtools.models`.

models.py — Modelos de spaCy e Stanza baixados sob demanda, fora do binário.

### `activate`

```python
activate() -> 'None'
```

Põe os modelos baixados no caminho de importação (chamar ao iniciar).

### `download_spacy_model`

```python
download_spacy_model(name: 'str', progress: 'Callable[[int, int, str], None] | None' = None) -> 'Path'
```

Baixa e extrai o modelo spaCy. Devolve a pasta do pacote do modelo.

Recusa (ValueError) um modelo que não rodaria nesta instalação (ex.: en_core_web_trf sem
spacy_curated_transformers).

### `download_stanza`

```python
download_stanza(lang: 'str', package: 'str' = 'default', processors: 'str' = 'tokenize,pos,lemma', progress: 'Callable[[int, int, str], None] | None' = None) -> 'Path'
```

Baixa os modelos do Stanza para o idioma (pasta de dados, salvo STANZA_RESOURCES_DIR).

### `list_models`

```python
list_models(lang: 'str | None' = None) -> 'dict'
```

Modelos baixáveis com a ficha, se estão instalados e se podem rodar aqui (`models`);
`spacy` mantém a lista simples de antes (nome, installed, downloaded).

### `model_info`

```python
model_info() -> 'list[dict]'
```

Fichas dos modelos baixáveis (data/models.json): idioma, tamanho, fonte, licença, dados de treino.

### `models_dir`

```python
models_dir() -> 'Path'
```

Pasta dos modelos baixados (<dados>/models).

### `spacy_model_version`

```python
spacy_model_version(name: 'str') -> 'str'
```

Versão do modelo compatível com o spaCy instalado (compatibility.json).

<a id="analysis"></a>
## KFA e d de Cohen (API clássica)

Módulo `ttwtools.analysis`.

### `analyze_key_features` · **`ttwtools.analyze_key_features`**

```python
analyze_key_features(corpus1_path: str, corpus2_path: str, min_effect_size: float = 0.0, join: str = 'union', metric: str = 'kfa')
```

Realiza a analise de key features (KFA) entre dois corpora norm1000.csv.

metric="kfa"  — formula de Biber & Egbert: SD_pooled = sqrt((SD1^2+SD2^2)/2)  [padrao]
metric="kfa2" — formula ponderada pelo tamanho: SD_pooled classico (atual)

### `cohens_d` · **`ttwtools.cohens_d`**

```python
cohens_d(group1, group2)
```

Calcula o tamanho do efeito (Cohen's D) entre dois grupos.

### `cohens_d_biber` · **`ttwtools.cohens_d_biber`**

```python
cohens_d_biber(group1, group2)
```

Cohen's D usando a formula de SD combinado de Biber & Egbert: sqrt((SD1^2+SD2^2)/2).

### `kfa` · **`ttwtools.kfa`**

```python
kfa(corpus1_path: str, corpus2_path: str, min_effect_size: float = 0.0, join: str = 'union', metric: str = 'kfa')
```

KFA padrao (Biber & Egbert): SD_pooled = sqrt((SD1^2+SD2^2)/2).

### `kfa2` · **`ttwtools.kfa2`**

```python
kfa2(corpus1_path: str, corpus2_path: str, min_effect_size: float = 0.0, join: str = 'union')
```

KFA2: SD_pooled ponderado pelo tamanho — sqrt(((n1-1)s1^2+(n2-1)s2^2)/(n1+n2-2)).

### `pooled_std` · **`ttwtools.pooled_std`**

```python
pooled_std(group1, group2)
```

Calcula o desvio padrao combinado (pooled standard deviation) para dois grupos.

### `pooled_std_biber` · **`ttwtools.pooled_std_biber`**

```python
pooled_std_biber(std1: float, std2: float) -> float
```

SD combinado conforme Biber & Egbert: sqrt((SD1^2 + SD2^2) / 2).

<a id="help"></a>
## Ajuda e tours

Módulo `ttwtools.help`.

help.py — Textos de ajuda do pacote e do aplicativo (novomodelo.md §13.2).

### `get`

```python
get(topic: 'str', lang: 'str | None' = None) -> 'dict'
```

Tópico de ajuda: {"id", "area", "title", "summary", "body", "related", "lang", "fallback"}.

Aceita o id (`cohens_d`) ou o caminho relativo (`metricas/cohens_d`).

### `localize`

```python
localize(obj: 'Any', lang: 'str | None' = None) -> 'Any'
```

Copia `obj` trocando as chaves de tradução dos campos de texto pelo texto no idioma.

### `render`

```python
render(topic: 'str', lang: 'str | None' = None) -> 'str'
```

Texto para o terminal.

### `search` · **`ttwtools.search`**

```python
search(query: 'str', lang: 'str | None' = None) -> 'list[dict]'
```

Tópicos cujo título, resumo ou texto contém `query` (sem distinguir maiúsculas).

### `topics`

```python
topics(lang: 'str | None' = None) -> 'list[dict]'
```

Tópicos disponíveis (id, área, título, resumo), incluindo os que só existem em inglês.

### `tour`

```python
tour(tour_id: 'str', lang: 'str | None' = None) -> 'dict'
```

Passos do tour, com títulos traduzidos e o resumo do tópico de cada passo.

### `tours`

```python
tours() -> 'list[str]'
```

Ids dos tours guiados disponíveis.

<a id="i18n"></a>
## Traduções

Módulo `ttwtools.i18n`.

i18n.py — Textos traduzíveis do pacote (pt e en).

### `default_lang`

```python
default_lang() -> 'str'
```

Idioma padrão dos textos: TTWTOOLS_LANG ou pt.

### `localize`

```python
localize(obj: 'Any', lang: 'str | None' = None) -> 'Any'
```

Copia `obj` trocando as chaves de tradução dos campos de texto pelo texto no idioma.

### `t`

```python
t(key: 'str', lang: 'str | None' = None, **fmt: 'Any') -> 'str'
```

Texto traduzido da chave (cai no inglês e, por fim, na própria chave); `fmt` preenche {campos}.

<a id="codegen"></a>
## Código equivalente (linha de comando e Python)

Módulo `ttwtools.codegen`.

codegen.py — O comando de linha de comando e o código Python equivalentes a uma
análise feita na interface ("copiar como código", novomodelo.md §15.2 item 10).

### `cli_command`

```python
cli_command(analysis: 'str', project_path: 'str', params: 'Mapping[str, Any]', windows: 'bool' = False) -> 'str'
```

Comando `ttwtools ...` equivalente.

### `python_code`

```python
python_code(analysis: 'str', project_path: 'str', params: 'Mapping[str, Any]') -> 'str'
```

Trecho Python equivalente, usando a API pública do pacote.

## Outros nomes de `ttwtools`

Taggers da API clássica e utilitários exportados no nível do pacote.

### `TTWA_EXTENSION` · **`ttwtools.TTWA_EXTENSION`**

```python
TTWA_EXTENSION
```

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `TTWA_MIME_TYPE` · **`ttwtools.TTWA_MIME_TYPE`**

```python
TTWA_MIME_TYPE
```

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `TTWA_MODE_COMPACT` · **`ttwtools.TTWA_MODE_COMPACT`**

```python
TTWA_MODE_COMPACT
```

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `TTWA_MODE_FULL` · **`ttwtools.TTWA_MODE_FULL`**

```python
TTWA_MODE_FULL
```

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `TTWL_EXTENSION` · **`ttwtools.TTWL_EXTENSION`**

```python
TTWL_EXTENSION
```

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `add_step` · **`ttwtools.add_step`**

```python
add_step(project: 'TTWAProject', corpus_name: 'str', step: 'Mapping[str, Any]') -> 'list[dict]'
```

Acrescenta um passo à lista (validado; passo idêntico não entra duas vezes). Devolve a lista.

### `analyze_file` · **`ttwtools.analyze_file`**

```python
analyze_file(project: 'TTWAProject', blob: 'bytes', filename: 'str', reference, **kwargs) -> 'dict'
```

Lê o arquivo e chama `analyze_text` (atalho usado pela rota e pela CLI).

### `analyze_patterns` · **`ttwtools.analyze_patterns`**

```python
analyze_patterns(project: 'TTWAProject', text: 'str', reference, field: 'str' = 'upos', n: 'int' = 3, measure: 'str' = 'log_ratio', min_freq: 'int' = 2, correction: 'str' = 'fdr', alpha: 'float' = 0.05, top: 'int | None' = 60, lang: 'str | None' = None, text_name: 'str' = 'Meu texto', filename: 'str | None' = None, z_scores: 'bool' = True, layer: 'str | None' = None) -> 'dict'
```

Perfil de construções (n-gramas de UPOS/XPOS) do texto contra um corpus de referência.

### `analyze_text` · **`ttwtools.analyze_text`**

```python
analyze_text(project: 'TTWAProject', text: 'str', reference, unit: 'str' = 'form', n: 'int' = 2, measure: 'str' = 'log_ratio', min_freq: 'int' = 2, min_range: 'int' = 1, correction: 'str' = 'fdr', alpha: 'float' = 0.05, top: 'int | None' = 100, both_directions: 'bool' = True, lang: 'str | None' = None, text_name: 'str' = 'Meu texto', filename: 'str | None' = None) -> 'dict'
```

Palavras-chave de um texto único contra `reference` (corpus do projeto, lista .tsv
ou `catalog:<id>`), com dispersão na referência e badges de confiabilidade.

### `biberplus` · **`ttwtools.biberplus`**

```python
biberplus(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.biberplus on first call.

### `clear_steps` · **`ttwtools.clear_steps`**

```python
clear_steps(project: 'TTWAProject', corpus_name: 'str') -> 'None'
```

Esvazia a lista "a executar" do corpus.

### `collocate_profile` · **`ttwtools.collocate_profile`**

```python
collocate_profile(project: 'TTWAProject', text: 'str', node: 'str', reference, unit: 'str' = 'form', window: 'tuple[int, int]' = (5, 5), top: 'int' = 30, min_freq: 'int' = 2, layer: 'str | None' = None, lang: 'str | None' = None, text_name: 'str' = 'Meu texto') -> 'dict'
```

Compara os colocados de `node` no texto do aluno e na referência.

### `corpus_patterns` · **`ttwtools.corpus_patterns`**

```python
corpus_patterns(project: 'TTWAProject', corpus_name: 'str', field: 'str' = 'upos', n: 'int' = 3, layer: 'str | None' = None, where: 'Mapping | None' = None, keep: 'set[str] | None' = None) -> 'FreqTable'
```

FreqTable dos n-gramas de etiquetas de um corpus. Com `keep`, também guarda, por
documento, a contagem desses padrões (`doc_counts`) e o tamanho de cada documento
(`doc_words`) — é o que permite o z-score descritivo.

### `extract_biber_features_from_folder` · **`ttwtools.extract_biber_features_from_folder`**

```python
extract_biber_features_from_folder(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.biberplus on first call.

### `extract_mfte_features_from_folder` · **`ttwtools.extract_mfte_features_from_folder`**

```python
extract_mfte_features_from_folder(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.mfte on first call.

### `extract_spacy_combined_features_from_folder` · **`ttwtools.extract_spacy_combined_features_from_folder`**

```python
extract_spacy_combined_features_from_folder(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.spacy_pos on first call.

### `extract_spacy_pos_features_from_folder` · **`ttwtools.extract_spacy_pos_features_from_folder`**

```python
extract_spacy_pos_features_from_folder(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.spacy_pos on first call.

### `extract_stanza_combined_features_from_folder` · **`ttwtools.extract_stanza_combined_features_from_folder`**

```python
extract_stanza_combined_features_from_folder(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.stanza_pos on first call.

### `extract_stanza_pos_features_from_folder` · **`ttwtools.extract_stanza_pos_features_from_folder`**

```python
extract_stanza_pos_features_from_folder(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.stanza_pos on first call.

### `extract_text` · **`ttwtools.extract_text`**

```python
extract_text(blob: 'bytes', filename: 'str') -> 'str'
```

Texto puro de um upload: txt/md, docx, odt ou pdf (este se `pypdf` estiver instalado).

### `lexical_profile` · **`ttwtools.lexical_profile`**

```python
lexical_profile(text: 'str', tokenizer: 'TokenizerConfig | None' = None) -> 'dict'
```

Perfil lexical e de frases de um texto (descritivo).

### `mfte` · **`ttwtools.mfte`**

```python
mfte(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.mfte on first call.

### `mtld` · **`ttwtools.mtld`**

```python
mtld(tokens: 'list[str]', threshold: 'float' = 0.72) -> 'float | None'
```

MTLD (média das passagens direta e reversa); None se o texto for curto demais.

### `normalize_biber_features` · **`ttwtools.normalize_biber_features`**

```python
normalize_biber_features(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.biberplus on first call.

### `normalize_mfte_features` · **`ttwtools.normalize_mfte_features`**

```python
normalize_mfte_features(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.mfte on first call.

### `normalize_spacy_pos_features` · **`ttwtools.normalize_spacy_pos_features`**

```python
normalize_spacy_pos_features(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.spacy_pos on first call.

### `normalize_stanza_pos_features` · **`ttwtools.normalize_stanza_pos_features`**

```python
normalize_stanza_pos_features(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.stanza_pos on first call.

### `pending_steps` · **`ttwtools.pending_steps`**

```python
pending_steps(project: 'TTWAProject', corpus_name: 'str') -> 'list[dict]'
```

Passos guardados na lista "a executar" do corpus, na ordem em que rodam (`stats` no fim).

### `preview_filenames` · **`ttwtools.preview_filenames`**

```python
preview_filenames(source: 'str | Path', delimiter: 'str' = '_', fields: 'list[str] | None' = None, n: 'int' = 5, glob: 'str' = '*.txt') -> 'dict'
```

Como os nomes dos arquivos da pasta viram metadados, sem importar nada.

Devolve {"total", "parts" (nº de pedaços mais comum), "irregular" (até 5 nomes com
outro nº de pedaços), "n_irregular", "examples": [{"file", "parts", "meta"}]}.

### `remove_step` · **`ttwtools.remove_step`**

```python
remove_step(project: 'TTWAProject', corpus_name: 'str', index: 'int') -> 'list[dict]'
```

Tira o passo `index` (0 = primeiro) da lista. Devolve a lista.

### `run_steps` · **`ttwtools.run_steps`**

```python
run_steps(project: 'TTWAProject', corpus_name: 'str', progress: 'Callable[[int, int, str], None] | None' = None, on_step: 'Callable[[int, dict], None] | None' = None) -> 'dict'
```

Executa a lista do corpus: etiquetagens na ordem e, por último, as estatísticas básicas.

`progress(passo, total_de_passos, mensagem)` dá o andamento geral; `on_step(i, estado)`
dá o de cada passo, com estado = {"status": "running"|"done"|"error", "done", "total",
"item"} (feitos/total dentro do passo e o texto atual). Cada passo concluído sai da
lista (se um falhar, ele e os seguintes continuam guardados).
Devolve {"done": [{"step", "report"}], "remaining": [...]}.

### `spacy_ptb` · **`ttwtools.spacy_ptb`**

```python
spacy_ptb(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.spacy_pos on first call.

### `spacy_upos` · **`ttwtools.spacy_upos`**

```python
spacy_upos(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.spacy_pos on first call.

### `stanza_upos` · **`ttwtools.stanza_upos`**

```python
stanza_upos(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.stanza_pos on first call.

### `stanza_xpos` · **`ttwtools.stanza_xpos`**

```python
stanza_xpos(*args, **kwargs)
```

Lazy wrapper — imports ttwtools.taggers.stanza_pos on first call.

### `tag_text` · **`ttwtools.tag_text`**

```python
tag_text(text: 'str', model: 'str | None' = None, lang: 'str | None' = None) -> 'list[dict]'
```

Tokens do texto com UPOS e XPOS (spaCy). Devolve [{word, upos, xpos}].

### `text_collocates` · **`ttwtools.text_collocates`**

```python
text_collocates(text: 'str', node: 'str', window: 'tuple[int, int]' = (5, 5), tokenizer: 'TokenizerConfig | None' = None) -> 'dict'
```

Colocados de `node` no texto: contagens e nº de palavras.

### `text_freqs` · **`ttwtools.text_freqs`**

```python
text_freqs(text: 'str', unit: 'str' = 'form', n: 'int' = 2, tokenizer: 'TokenizerConfig | None' = None, name: 'str' = 'Meu texto') -> 'FreqTable'
```

FreqTable do texto (docs = 1 em cada item, pois é um único texto).

### `text_patterns` · **`ttwtools.text_patterns`**

```python
text_patterns(text: 'str', field: 'str' = 'upos', n: 'int' = 3, model: 'str | None' = None, lang: 'str | None' = None, name: 'str' = 'Meu texto') -> 'FreqTable'
```

FreqTable dos padrões do texto do aluno.
