"""
exemplo2_00_runall.py
─────────────────────
Script principal que executa o pipeline completo do Exemplo 2 em sequência:

  Passo 1 → exemplo2_01: tagging + extração de features Biber + normalização
  Passo 2 → exemplo2_02: Key Feature Analysis (KFA) + gráfico

Ajuste as variáveis de configuração abaixo e execute:

    python examples/exemplo2_00_runall.py
"""

from pathlib import Path
import time
import sys

_HERE = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÕES GLOBAIS — altere aqui para adaptar ao seu estudo
# ─────────────────────────────────────────────────────────────────────────────

# Pasta de saída onde todos os artefatos gerados serão gravados.
# None → cria 'out' incremental (out, out_1, out_2, ...) no diretório atual.
OUTPUT_DIR = str(_HERE / 'out_exemplo2')

# Pasta onde estao os corpora de teste usados nos exemplos.
TEST_CORPORA_DIR = _HERE / 'test_corpora'

# Corpora a processar (pastas com arquivos .txt).
# A análise KFA será feita comparando CORPUS1 vs CORPUS2.
CORPUS1 = 'teste1'
CORPUS2 = 'teste2'

# Se True, copia os arquivos originais de cada corpus para OUTPUT_DIR/originals/
COPY_ORIGINALS = True

# Se True, usa pipeline spaCy para tokenização (requer modelo instalado no env)
USENLP = False

# Método de join para a KFA: 'intersection' ou 'union'
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

    _banner("Pipeline Exemplo 2 — KFA Biberplus", "INÍCIO")
    print(f"  Corpus 1     : {CORPUS1}")
    print(f"  Corpus 2     : {CORPUS2}")
    print(f"  Pasta saída  : {OUTPUT_DIR or 'out (incremental)'}")
    print(f"  Copiar orig. : {COPY_ORIGINALS}")
    print(f"  Usar spaCy   : {USENLP}")
    print(f"  Join KFA     : {JOIN}")

    # ── PASSO 1: Tagging + Extração de features + Normalização ───────────────
    _banner("Passo 1/2 — Tagging e Extração de Features Biber",
            "exemplo2_01_biberplus_tagging.py → run_tagging()")

    examples_dir = Path(__file__).resolve().parent
    if str(examples_dir) not in sys.path:
        sys.path.insert(0, str(examples_dir))

    from exemplo2_01_biberplus_tagging import run_tagging

    t0 = time.time()
    out_dir = run_tagging(
        output_dir=OUTPUT_DIR,
        pastas=[str(TEST_CORPORA_DIR / CORPUS1), str(TEST_CORPORA_DIR / CORPUS2)],
        copy_originals=COPY_ORIGINALS,
        usenlp=USENLP,
    )
    print(f"\n  ⏱  Passo 1 concluído em {time.time() - t0:.1f}s")

    # ── PASSO 2: Key Feature Analysis + Gráfico ──────────────────────────────
    _banner("Passo 2/2 — Key Feature Analysis (KFA) e Gráfico",
            "exemplo2_02_biber_kfa_analysis_graph.py → run_analysis()")

    from exemplo2_02_biber_kfa_analysis_graph import run_analysis

    t0 = time.time()
    run_analysis(
        output_dir=str(out_dir),
        corpus1=CORPUS1,
        corpus2=CORPUS2,
        join=JOIN,
    )
    print(f"\n  ⏱  Passo 2 concluído em {time.time() - t0:.1f}s")

    # ── Resumo final ─────────────────────────────────────────────────────────
    _banner(f"Pipeline concluído em {time.time() - inicio_total:.1f}s", "✓ CONCLUÍDO")
    print(f"  Todos os arquivos foram salvos em: {out_dir}")
    print(f"\n  Arquivos gerados:")

    expected = [
        f"{CORPUS1}_biberfeatures_rawcount.csv",
        f"{CORPUS1}_biberfeatures_norm1000.csv",
        f"{CORPUS2}_biberfeatures_rawcount.csv",
        f"{CORPUS2}_biberfeatures_norm1000.csv",
        f"key_features_analysis_{CORPUS1}_vs_{CORPUS2}.png",
        f"key_features_analysis_results_{CORPUS1}_vs_{CORPUS2}.csv",
    ]
    for fname in expected:
        fpath = out_dir / fname
        status = "✓" if fpath.exists() else "✗ (não encontrado)"
        print(f"    {status}  {fpath}")

    if COPY_ORIGINALS:
        for corpus in [CORPUS1, CORPUS2]:
            dpath = out_dir / 'originals' / corpus
            status = "✓" if dpath.exists() else "✗"
            print(f"    {status}  {dpath}/  (cópia original)")


if __name__ == '__main__':
    main()
