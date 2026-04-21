# todoc.md — Notas para o app consumidor do ttwtools

Registro de decisões e tarefas de documentação que pertencem ao **app que usa
ttwtools como submódulo**, não ao ttwtools em si.

---

## 1. PyInstaller — o que o app precisa fazer

### 1.1 Cenário A — apenas BiberPlus (sem MFTE)

spaCy possui hooks oficiais para PyInstaller. O app precisa:

```python
# No .spec, incluir o modelo spaCy usado:
from spacy.util import get_package_path
spacy_model = str(get_package_path("en_core_web_sm"))
datas += [(spacy_model, "en_core_web_sm")]
hiddenimports += ["spacy", "biberplus"]
```

### 1.2 Cenário B — BiberPlus + MFTE, bundle CPU-only

Além dos itens do Cenário A:

**Dependências a instalar no ambiente de build:**
```
pip install stanza MFTE torch   # torch CPU (sem CUDA)
```

**Pré-baixar os modelos Stanza antes do build:**
```python
import stanza
stanza.download("en", processors="tokenize,pos")
# Modelos ficam em ~/stanza_resources/en/
```

**No .spec:**
```python
import os, pathlib
stanza_en = str(pathlib.Path.home() / "stanza_resources" / "en")
datas += [(stanza_en, "stanza_resources/en")]
hiddenimports += ["stanza", "torch", "MFTE"]
# torch precisa de coleta completa de binários:
from PyInstaller.utils.hooks import collect_all
datas_t, bi_t, hi_t = collect_all("torch")
datas    += datas_t
binaries += bi_t
hiddenimports += hi_t
```

**No código do app, antes de chamar `ttwtools.mfte()`:**
```python
import os, sys
if getattr(sys, "frozen", False):
    # Bundle: modelos estão em <app_dir>/stanza_resources/en/
    os.environ["STANZA_RESOURCES_DIR"] = str(
        pathlib.Path(sys._MEIPASS) / "stanza_resources"
    )
ttwtools.mfte(corpus_folder, ...)
```

O ttwtools respeita `STANZA_RESOURCES_DIR` em `_load_stanza_pipeline()`.

### 1.3 Cenário C — companion executable `mfte_worker`

Estratégia two-bundle para cenários GPU ou quando torch torna o bundle grande
demais:

```
app_principal.exe    ← PyInstaller sem torch/stanza
mfte_worker.exe      ← PyInstaller separado com torch + stanza + MFTE
```

**Entry point do worker (criar no repositório do app):**
```python
# mfte_worker_main.py
import sys, json, os, pathlib

def main():
    req = json.loads(sys.stdin.read())
    # Apontar Stanza para modelos bundlados junto ao executável
    worker_dir = pathlib.Path(sys.executable).parent
    os.environ["STANZA_RESOURCES_DIR"] = str(worker_dir / "stanza_resources")
    import ttwtools
    ttwtools.mfte(
        req["folder"],
        output_dir=req.get("output_dir"),
        save_tagged=req.get("save_tagged", False),
        use_gpu=req.get("use_gpu"),          # None = auto
        extended=req.get("extended", True),
    )
    print(json.dumps({"status": "done"}))

if __name__ == "__main__":
    main()
```

**Protocolo de comunicação (app → worker):**
```json
{"folder": "/caminho/corpus", "output_dir": "/saida", "use_gpu": null, "extended": true}
```

**No app principal, invocar o worker:**
```python
import subprocess, json, sys, pathlib

def run_mfte_worker(folder, output_dir, **kwargs):
    worker = pathlib.Path(sys.executable).parent / "mfte_worker"
    payload = json.dumps({"folder": folder, "output_dir": output_dir, **kwargs})
    result = subprocess.run(
        [str(worker)],
        input=payload.encode(),
        capture_output=True,
        timeout=3600,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode())
    return json.loads(result.stdout)
```

**Spec do worker (criar `mfte_worker.spec` no repositório do app):**
```python
# mfte_worker.spec
stanza_en = str(pathlib.Path.home() / "stanza_resources" / "en")
from PyInstaller.utils.hooks import collect_all
datas_t, bi_t, hi_t = collect_all("torch")
a = Analysis(
    ["mfte_worker_main.py"],
    datas=[(stanza_en, "stanza_resources/en")] + datas_t,
    binaries=bi_t,
    hiddenimports=["stanza", "torch", "MFTE", "ttwtools"] + hi_t,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="mfte_worker", console=True)
```

---

## 2. Gerenciamento de modelos Stanza pelo usuário final

Documentar no manual/ajuda do app:

- **Onde ficam os modelos:** `~/stanza_resources/en/` (padrão Stanza)
  ou no caminho definido por `STANZA_RESOURCES_DIR`.
- **Download inicial (modo não-bundlado):** o app deve oferecer um botão
  "Baixar modelos MFTE" que execute:
  ```python
  import stanza
  stanza.download("en", processors="tokenize,pos")
  ```
- **Tamanho dos modelos:** ~250–300 MB para `tokenize,pos`.
- **Atualização:** o ttwtools passa `download_method=REUSE_RESOURCES` —
  Stanza **não** tenta atualizar modelos automaticamente. Para forçar
  atualização, rodar `stanza.download("en")` manualmente.

---

## 3. Licença — atenção ao redistribuir MFTE

- MFTE é licenciado sob **GPL-3.0**.
- ttwtools importa `process_sentence` diretamente de `MFTE.py`.
- Redistribuir um executável bundlado que inclui o código do MFTE
  pode obrigar o app a adotar GPL-3.0 também (copyleft forte).
- **Ação necessária no app:** verificar com assessoria jurídica antes de
  distribuir Cenário B (bundle com MFTE). Cenário C (worker separado)
  pode ter implicações diferentes — o worker seria o binário GPL, e o
  app principal, se não incluir código GPL, pode usar outra licença.
- Referência: https://www.gnu.org/licenses/gpl-faq.html#GPLInProprietarySystem

---

## 4. Variáveis de ambiente reconhecidas pelo ttwtools

| Variável | Módulo | Efeito |
|---|---|---|
| `STANZA_RESOURCES_DIR` | `taggers/mfte.py` | Diretório raiz dos modelos Stanza (substitui `~/stanza_resources/`) |

---

## 5. Checklist de build (a detalhar no app)

- [ ] Ambiente de build isolado com versões fixadas (`pip freeze > build-requirements.txt`)
- [ ] `stanza.download("en", processors="tokenize,pos")` executado antes do build
- [ ] Modelo spaCy `en_core_web_sm` instalado e incluído no spec
- [ ] Teste de smoke pós-build: processar corpus de 5 docs, verificar CSV de saída
- [ ] Assinar executável (macOS: `codesign`; Windows: Authenticode) após build
