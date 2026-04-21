"""
exemplo6_00_runall.py
─────────────────────
Script principal que executa o pipeline completo do Exemplo 6 em sequência.
Compara dois corpora usando BiberPlus e MFTE (versão estendida) em paralelo,
gerando dois gráficos KFA para contraste metodológico.

A versão estendida do MFTE inclui, além das features Biber originais,
categorias semânticas adicionais (nominalizações, construções passivas
complexas, cadeias referenciais, etc.), resultando em um inventário maior.

  Passo 1 → exemplo6_01: tagging com BiberPlus + MFTE (extended=True) + normalização
  Passo 2 → exemplo6_02: KFA separada para cada tagger + gráficos comparativos

Uso:

    python examples/exemplo6_00_runall.py
"""

from pathlib import Path
import time
import sys


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÕES GLOBAIS
# ─────────────────────────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent

OUTPUT_DIR = str(_HERE / 'out_exemplo6')
TEST_CORPORA_DIR = _HERE / 'test_corpora'

CORPUS1 = 'CorIFAessaysNE_100'
CORPUS2 = 'essays_bawe_somentetexto_100'

COPY_ORIGINALS = True
USENLP = False          # spaCy para BiberPlus
USE_GPU = None          # GPU para MFTE: None = auto-detectar

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

    _banner("Pipeline Exemplo 6 — KFA BiberPlus vs MFTE (estendido)", "INÍCIO")
    print(f"  Corpus 1     : {CORPUS1}")
    print(f"  Corpus 2     : {CORPUS2}")
    print(f"  Pasta saída  : {OUTPUT_DIR}")
    print(f"  Copiar orig. : {COPY_ORIGINALS}")
    print(f"  Usar spaCy   : {USENLP}")
    print(f"  Usar GPU     : {USE_GPU}")
    print(f"  MFTE extend. : True")
    print(f"  Join KFA     : {JOIN}")

    examples_dir = Path(__file__).resolve().parent
    if str(examples_dir) not in sys.path:
        sys.path.insert(0, str(examples_dir))

    # ── PASSO 1 ───────────────────────────────────────────────────────────────
    _banner("Passo 1/2 — Tagging com BiberPlus e MFTE (estendido)",
            "exemplo6_01_biberplus_and_mfte_ext_tagging.py → run_tagging()")

    from exemplo6_01_biberplus_and_mfte_ext_tagging import run_tagging

    t0 = time.time()
    out_dir = run_tagging(
        output_dir=OUTPUT_DIR,
        pastas=[str(TEST_CORPORA_DIR / CORPUS1), str(TEST_CORPORA_DIR / CORPUS2)],
        copy_originals=COPY_ORIGINALS,
        usenlp=USENLP,
        use_gpu=USE_GPU,
    )
    print(f"\n  ⏱  Passo 1 concluído em {time.time() - t0:.1f}s")

    # ── PASSO 2 ───────────────────────────────────────────────────────────────
    _banner("Passo 2/2 — Key Feature Analysis (KFA) e Gráficos Comparativos",
            "exemplo6_02_biber_vs_mfte_ext_kfa_graph.py → run_analysis()")

    from exemplo6_02_biber_vs_mfte_ext_kfa_graph import run_analysis

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
        f"{CORPUS1}_mfte_rawcount.csv",
        f"{CORPUS1}_mfte_norm1000.csv",
        f"{CORPUS2}_mfte_rawcount.csv",
        f"{CORPUS2}_mfte_norm1000.csv",
        f"key_features_biber_{CORPUS1}_vs_{CORPUS2}.png",
        f"key_features_mfte_ext_{CORPUS1}_vs_{CORPUS2}.png",
        f"key_features_biber_results_{CORPUS1}_vs_{CORPUS2}.csv",
        f"key_features_mfte_ext_results_{CORPUS1}_vs_{CORPUS2}.csv",
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
