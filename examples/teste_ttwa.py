"""
teste_ttwa.py
─────────────────────────────────────────────────────────────────────────────
Roda o pipeline completo do Exemplo 2 e salva/verifica um arquivo .ttwa.

Pipeline:
  1. Tagging BiberPlus (rawcount CSV)
  2. Normalização (norm1000 CSV)
  3. Key Feature Analysis (KFA)
  4. Salva tudo em  out_test/exemplo2.ttwa
  5. Reabre o .ttwa e verifica que todos os dados estão recuperáveis

Uso:
    python examples/teste_ttwa.py
"""

from pathlib import Path
import sys

# ── garante que o código local do pacote é encontrado ───────────────────────
ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

import ttwtools
from ttwtools.project import TTWAProject, save_analysis_to_project

# ─────────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────────
CORPORA_DIR = ROOT / "examples" / "test_corpora"
CORPUS1     = "teste1"
CORPUS2     = "teste2"
OUT_DIR     = ROOT / "out_test"
TTWA_FILE   = OUT_DIR / "exemplo2.ttwa"
JOIN        = "intersection"

OUT_DIR.mkdir(parents=True, exist_ok=True)

SEP = "=" * 60

# ─────────────────────────────────────────────────────────────────────────────
# PASSO 1 — Tagging + rawcount CSVs
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  PASSO 1 — Tagging BiberPlus")
print(SEP)

for corpus_name in (CORPUS1, CORPUS2):
    folder = CORPORA_DIR / corpus_name
    ttwtools.biberplus(
        folder_path_str=str(folder),
        configdict={"n_processes": 4, "function_words": False},
        usenlp=False,
        save_tagged=True,
        output_dir=str(OUT_DIR),
        copy_originals=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# PASSO 2 — Normalização
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  PASSO 2 — Normalização por 1000 palavras")
print(SEP)

for corpus_name in (CORPUS1, CORPUS2):
    raw_csv = OUT_DIR / f"{corpus_name}_biberfeatures_rawcount.csv"
    ttwtools.normalize_biber_features(str(raw_csv))

# ─────────────────────────────────────────────────────────────────────────────
# PASSO 3 — Key Feature Analysis
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  PASSO 3 — Key Feature Analysis")
print(SEP)

norm1 = OUT_DIR / f"{CORPUS1}_biberfeatures_norm1000.csv"
norm2 = OUT_DIR / f"{CORPUS2}_biberfeatures_norm1000.csv"

kfa_df = ttwtools.kfa(str(norm1), str(norm2), join=JOIN)

print(f"\n  Features distintivas encontradas : {len(kfa_df)}")
print(f"\n  Top 10:")
print(kfa_df.head(10).to_string(index=False))

# ─────────────────────────────────────────────────────────────────────────────
# PASSO 4 — Salvar no .ttwa
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print(f"  PASSO 4 — Salvando em '{TTWA_FILE.name}'")
print(SEP)

proj = save_analysis_to_project(
    project_path=TTWA_FILE,
    corpus1_name=CORPUS1,
    corpus1_rawcount_csv=OUT_DIR / f"{CORPUS1}_biberfeatures_rawcount.csv",
    corpus1_norm1000_csv=norm1,
    corpus2_name=CORPUS2,
    corpus2_rawcount_csv=OUT_DIR / f"{CORPUS2}_biberfeatures_rawcount.csv",
    corpus2_norm1000_csv=norm2,
    kfa_results_df=kfa_df,
    corpus1_folder=CORPORA_DIR / CORPUS1,
    corpus2_folder=CORPORA_DIR / CORPUS2,
    corpus1_tagged_folder=OUT_DIR / f"{CORPUS1}_tagged",
    corpus2_tagged_folder=OUT_DIR / f"{CORPUS2}_tagged",
    project_name="Exemplo 2 — ttwtools",
    overwrite=True,
    kfa_min_effect=0.2,
    kfa_join_method=JOIN,
)
proj.close()

print(f"\n  Arquivo salvo: {TTWA_FILE}")
print(f"  Tamanho      : {TTWA_FILE.stat().st_size / 1024:.1f} KB")

# ─────────────────────────────────────────────────────────────────────────────
# PASSO 5 — Verificar recuperação dos dados
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  PASSO 5 — Verificando recuperação dos dados do .ttwa")
print(SEP)

with TTWAProject.open(TTWA_FILE) as p:
    s = p.summary()

    print(f"\n  Metadados:")
    for k, v in s["meta"].items():
        print(f"    {k}: {v}")

    print(f"\n  Corpora armazenados:")
    for name, info in s["corpora"].items():
        print(f"    [{name}]  {info['files']} txt(s)  |  {info['tagged']} tagged  |  tables: {info['feature_tables']}")

    print(f"\n  KFAs armazenadas:")
    for kfa_meta in s["kfa_results"]:
        print(f"    {kfa_meta['corpus1_name']} vs {kfa_meta['corpus2_name']}"
              f"  d>={kfa_meta['min_effect']}  {kfa_meta['join_method']}")

    # Recupera arquivo de texto original
    files1 = p.list_corpus_files(CORPUS1)
    first_file = files1[0] if files1 else None
    if first_file:
        content = p.get_corpus_file(CORPUS1, first_file)
        print(f"\n  Texto '{first_file}' (primeiros 120 chars):")
        print(f"    {content[:120].strip()!r}")

    # Recupera feature table norm1000
    df_norm = p.load_feature_table(CORPUS1, "norm1000")
    print(f"\n  Feature table norm1000 '{CORPUS1}': {len(df_norm)} docs, {len(df_norm.columns)} colunas")

    # Recupera KFA
    df_kfa = p.load_kfa_result(CORPUS1, CORPUS2, join_method=JOIN)
    print(f"\n  KFA recuperada: {len(df_kfa)} features")
    print(f"\n  Top 5 features recuperadas do .ttwa:")
    print(df_kfa.head(5).to_string(index=False))

print(f"\n{SEP}")
print("  TUDO OK — arquivo .ttwa lido e dados recuperados com sucesso.")
print(SEP)
