"""
teste_ttwa.py
─────────────────────────────────────────────────────────────────────────────
Roda o pipeline completo do Exemplo 2 e salva/verifica dois arquivos .ttwa:

  exemplo2_full.ttwa    — modo 'full':    corpus original + tagged + análise
  exemplo2_compact.ttwa — modo 'compact': apenas tagged + análise (sem originais)

Pipeline:
  1. Tagging BiberPlus (rawcount CSV)
  2. Normalização (norm1000 CSV)
  3. Key Feature Analysis (KFA)
  4. Salva modo full    → out_test/exemplo2_full.ttwa
  5. Salva modo compact → out_test/exemplo2_compact.ttwa
  6. Reabre ambos e verifica que os dados estão recuperáveis

Uso:
    python examples/teste_ttwa.py
"""

from pathlib import Path
import sys

# ── garante que o código local do pacote é encontrado ───────────────────────
ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

import ttwtools
from ttwtools.project import TTWAProject, save_analysis_to_project, TTWA_MODE_FULL, TTWA_MODE_COMPACT

# ─────────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────────
CORPORA_DIR    = ROOT / "examples" / "test_corpora"
CORPUS1        = "teste1"
CORPUS2        = "teste2"
OUT_DIR        = ROOT / "out_test"
TTWA_FULL      = OUT_DIR / "exemplo2_full.ttwa"
TTWA_COMPACT   = OUT_DIR / "exemplo2_compact.ttwa"
JOIN           = "intersection"

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
# PASSO 4 — Salvar modo FULL (corpus original + tagged + análise)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print(f"  PASSO 4 — Salvando modo FULL em '{TTWA_FULL.name}'")
print(SEP)

proj = save_analysis_to_project(
    project_path=TTWA_FULL,
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
    project_name="Exemplo 2 — full",
    overwrite=True,
    kfa_min_effect=0.2,
    kfa_join_method=JOIN,
    include_originals=True,
)
proj.close()

print(f"\n  Arquivo salvo: {TTWA_FULL}")
print(f"  Tamanho      : {TTWA_FULL.stat().st_size / 1024:.1f} KB")

# ─────────────────────────────────────────────────────────────────────────────
# PASSO 5 — Salvar modo COMPACT (apenas tagged + análise, sem textos originais)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print(f"  PASSO 5 — Salvando modo COMPACT em '{TTWA_COMPACT.name}'")
print(SEP)

proj = save_analysis_to_project(
    project_path=TTWA_COMPACT,
    corpus1_name=CORPUS1,
    corpus1_rawcount_csv=OUT_DIR / f"{CORPUS1}_biberfeatures_rawcount.csv",
    corpus1_norm1000_csv=norm1,
    corpus2_name=CORPUS2,
    corpus2_rawcount_csv=OUT_DIR / f"{CORPUS2}_biberfeatures_rawcount.csv",
    corpus2_norm1000_csv=norm2,
    kfa_results_df=kfa_df,
    corpus1_tagged_folder=OUT_DIR / f"{CORPUS1}_tagged",
    corpus2_tagged_folder=OUT_DIR / f"{CORPUS2}_tagged",
    project_name="Exemplo 2 — compact",
    overwrite=True,
    kfa_min_effect=0.2,
    kfa_join_method=JOIN,
    include_originals=False,   # ← sem corpus original
)
proj.close()

print(f"\n  Arquivo salvo: {TTWA_COMPACT}")
print(f"  Tamanho      : {TTWA_COMPACT.stat().st_size / 1024:.1f} KB")

# ─────────────────────────────────────────────────────────────────────────────
# PASSO 6 — Verificar recuperação dos dados de AMBOS os arquivos
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  PASSO 6 — Verificando recuperação dos dados")
print(SEP)

def _verificar(ttwa_path: Path):
    print(f"\n  {'─'*50}")
    print(f"  Arquivo : {ttwa_path.name}  ({ttwa_path.stat().st_size / 1024:.1f} KB)")
    print(f"  {'─'*50}")

    with TTWAProject.open(ttwa_path) as p:
        s = p.summary()

        mode = s["meta"].get("project_mode", "?")
        print(f"  Modo            : {mode}")
        print(f"  Projeto         : {s['meta'].get('project_name', '?')}")
        print(f"  Versão ttwtools : {s['meta'].get('ttwtools_version', '?')}")

        print(f"\n  Corpora armazenados:")
        for name, info in s["corpora"].items():
            orig = f"{info['files']} txt(s)" if info["files"] else "— (sem originais)"
            print(f"    [{name}]  originais: {orig}  |  tagged: {info['tagged']}  |  tables: {info['feature_tables']}")

        print(f"\n  KFAs armazenadas:")
        for km in s["kfa_results"]:
            print(f"    {km['corpus1_name']} vs {km['corpus2_name']}  d>={km['min_effect']}  {km['join_method']}")

        # Texto original (só existe no modo full)
        files1 = p.list_corpus_files(CORPUS1)
        if files1:
            content = p.get_corpus_file(CORPUS1, files1[0])
            print(f"\n  Texto original '{files1[0]}' (primeiros 80 chars):")
            print(f"    {content[:80].strip()!r}")
        else:
            print(f"\n  Textos originais: não armazenados (modo compact).")

        # Tagged file (existe em ambos)
        tagged1 = p.list_tagged_files(CORPUS1)
        if tagged1:
            tsv_content = p.get_tagged_file(CORPUS1, tagged1[0])
            print(f"\n  Tagged '{tagged1[0]}' (primeiros 120 chars):")
            print(f"    {tsv_content[:120].strip()!r}")

        # Feature table
        df_norm = p.load_feature_table(CORPUS1, "norm1000")
        print(f"\n  Feature table norm1000 '{CORPUS1}': {len(df_norm)} docs, {len(df_norm.columns)} colunas")

        # KFA
        df_kfa = p.load_kfa_result(CORPUS1, CORPUS2, join_method=JOIN)
        print(f"  KFA recuperada : {len(df_kfa)} features | top feature: {df_kfa.iloc[0]['Feature']} (d={df_kfa.iloc[0]['Effect_Size']:.3f})")

_verificar(TTWA_FULL)
_verificar(TTWA_COMPACT)

print(f"\n{SEP}")
print("  TUDO OK — ambos os modos salvos e recuperados com sucesso.")
print(f"  full    : {TTWA_FULL.stat().st_size / 1024:.1f} KB  (com corpus original)")
print(f"  compact : {TTWA_COMPACT.stat().st_size / 1024:.1f} KB  (sem corpus original)")
print(SEP)
