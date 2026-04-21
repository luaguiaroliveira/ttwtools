"""
exemplo4_00_runall.py
─────────────────────
Script principal que executa o pipeline completo do Exemplo 4 em sequência,
comparando dois corpora de ensaios acadêmicos em inglês usando o tagger MFTE:

  • CorIFAessaysNE_100  — ensaios do corpus CorIFA (português como L2)
  • essays_bawe_somentetexto_100 — ensaios do corpus BAWE (inglês nativo)

  Passo 1 → exemplo4_01: tagging MFTE + extração de features + normalização
  Passo 2 → exemplo4_02: Key Feature Analysis (KFA) + gráfico

Uso:

    python examples/exemplo4_00_runall.py
"""

from pathlib import Path
import time
import sys


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÕES GLOBAIS — altere aqui para adaptar ao seu estudo
# ─────────────────────────────────────────────────────────────────────────────

# Diretório base: sempre relativo a este script, independente do CWD.
_HERE = Path(__file__).resolve().parent

# Pasta de saída onde todos os artefatos gerados serão gravados.
OUTPUT_DIR = str(_HERE / 'out_exemplo4')

# Pasta onde estão os corpora de teste usados nos exemplos.
TEST_CORPORA_DIR = _HERE / 'test_corpora'

# Corpora a processar (nomes das pastas dentro de TEST_CORPORA_DIR).
CORPUS1 = 'CorIFAessaysNE_100'
CORPUS2 = 'essays_bawe_somentetexto_100'

# Se True, copia os arquivos originais de cada corpus para OUTPUT_DIR/originals/
COPY_ORIGINALS = True

# Usar GPU para o pipeline Stanza: None = auto-detectar, True = forçar GPU, False = forçar CPU
USE_GPU = None

# Se True, aplica as categorias semânticas estendidas do MFTE
EXTENDED = True

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

    _banner("Pipeline Exemplo 4 — KFA MFTE", "INÍCIO")
    print(f"  Corpus 1     : {CORPUS1}")
    print(f"  Corpus 2     : {CORPUS2}")
    print(f"  Pasta saída  : {OUTPUT_DIR}")
    print(f"  Copiar orig. : {COPY_ORIGINALS}")
    print(f"  Usar GPU     : {USE_GPU}")
    print(f"  Estendido    : {EXTENDED}")
    print(f"  Join KFA     : {JOIN}")

    # Garante que a pasta examples/ esteja no sys.path para os imports relativos
    examples_dir = Path(__file__).resolve().parent
    if str(examples_dir) not in sys.path:
        sys.path.insert(0, str(examples_dir))

    # ── PASSO 1: Tagging + Extração de features + Normalização ───────────────
    _banner("Passo 1/2 — Tagging e Extração de Features MFTE",
            "exemplo4_01_mfte_tagger_generate_tables_raw_and_norm1000.py → run_tagging()")

    from exemplo4_01_mfte_tagger_generate_tables_raw_and_norm1000 import run_tagging

    t0 = time.time()
    out_dir = run_tagging(
        output_dir=OUTPUT_DIR,
        pastas=[str(TEST_CORPORA_DIR / CORPUS1), str(TEST_CORPORA_DIR / CORPUS2)],
        copy_originals=COPY_ORIGINALS,
        use_gpu=USE_GPU,
        extended=EXTENDED,
    )
    print(f"\n  ⏱  Passo 1 concluído em {time.time() - t0:.1f}s")

    # ── PASSO 2: Key Feature Analysis + Gráfico ──────────────────────────────
    _banner("Passo 2/2 — Key Feature Analysis (KFA) e Gráfico",
            "exemplo4_02_mfte_kfa_analysis_graph.py → run_analysis()")

    from exemplo4_02_mfte_kfa_analysis_graph import run_analysis

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
        f"{CORPUS1}_mfte_rawcount.csv",
        f"{CORPUS1}_mfte_norm1000.csv",
        f"{CORPUS2}_mfte_rawcount.csv",
        f"{CORPUS2}_mfte_norm1000.csv",
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
