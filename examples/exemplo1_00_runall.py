"""
exemplo1_00_runall.py
─────────────────────
Script principal que executa o pipeline mínimo do Exemplo 1 em sequência:

  Passo 1 → exemplo1_01: tagging BiberPlus + normalização (sem output_dir explícito)
  Passo 2 → exemplo1_02: Key Feature Analysis (KFA) + gráfico

Uso:

    python examples/exemplo1_00_runall.py
"""

import sys
import time
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÕES GLOBAIS
# ─────────────────────────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent

# Corpora processados por exemplo1_01 (pastas dentro de test_corpora/).
CORPUS1 = 'subcorpus_introduction_aphd'
CORPUS2 = 'subcorpus_introduction_articles'

# exemplo1_01 salva os CSVs na pasta-pai dos corpora (test_corpora/).
# exemplo1_02 precisa saber onde encontrá-los.
OUTPUT_DIR = str(_HERE / 'out_exemplo1')

JOIN = 'intersection'

# ─────────────────────────────────────────────────────────────────────────────


def _banner(titulo: str, passo: str = ''):
    sep = '═' * 60
    print(f"\n{sep}")
    if passo:
        print(f"  {passo}")
    print(f"  {titulo}")
    print(sep)


def main():
    inicio_total = time.time()

    _banner("Pipeline Exemplo 1 — KFA BiberPlus (mínimo)", "INÍCIO")
    print(f"  Corpus 1  : {CORPUS1}")
    print(f"  Corpus 2  : {CORPUS2}")
    print(f"  Saída CSV : {OUTPUT_DIR}")

    examples_dir = _HERE
    if str(examples_dir) not in sys.path:
        sys.path.insert(0, str(examples_dir))

    # ── PASSO 1 ───────────────────────────────────────────────────────────────
    _banner("Passo 1/2 — Tagging e Extração de Features Biber",
            "exemplo1_01_biberplus_tagger_generate_tables_raw_and_norm1000.py")

    import runpy
    t0 = time.time()
    runpy.run_path(
        str(_HERE / 'exemplo1_01_biberplus_tagger_generate_tables_raw_and_norm1000.py'),
        run_name='__main__',
    )
    print(f"\n  ⏱  Passo 1 concluído em {time.time() - t0:.1f}s")

    # ── PASSO 2 ───────────────────────────────────────────────────────────────
    _banner("Passo 2/2 — Key Feature Analysis (KFA) e Gráfico",
            "exemplo1_02_biber_kfa_analysis_graph.py → run_analysis()")

    from exemplo1_02_biber_kfa_analysis_graph import run_analysis

    t0 = time.time()
    run_analysis(
        output_dir=OUTPUT_DIR,
        corpus1=CORPUS1,
        corpus2=CORPUS2,
        join=JOIN,
    )
    print(f"\n  ⏱  Passo 2 concluído em {time.time() - t0:.1f}s")

    _banner(f"Pipeline concluído em {time.time() - inicio_total:.1f}s", "✓ CONCLUÍDO")
    print(f"  CSVs e gráfico salvos em: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
