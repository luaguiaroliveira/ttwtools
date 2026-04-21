"""
Exemplo 5 — Passo 2: KFA comparativa BiberPlus vs MFTE (não estendido).

Gera duas análises independentes — uma para cada tagger — usando os mesmos
dois corpora, permitindo comparar quais features cada tagger identifica como
mais distintivas entre os grupos.
"""
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from ttwtools.analysis import kfa

OUTPUT_DIR = 'out_exemplo5'
CORPUS1 = 'CorIFAessaysNE_100'
CORPUS2 = 'essays_bawe_somentetexto_100'
JOIN = 'intersection'


def _plot_kfa(results: pd.DataFrame, corpus1: str, corpus2: str,
              tagger_label: str, out_path: Path):
    """Gera e salva um gráfico de barras horizontais com Cohen's D."""
    plt.figure(figsize=(15, max(8, len(results) * 0.25)))
    sns.set_style("whitegrid")

    results = results.sort_values('Effect_Size')

    plt.barh(range(len(results)), results['Effect_Size'],
             color=['#B7D2FF' if x < 0 else '#FFB7B7' for x in results['Effect_Size']])

    plt.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    plt.yticks(range(len(results)), results['Feature'])

    max_effect = max(abs(results['Effect_Size'].min()), abs(results['Effect_Size'].max()))
    plt.xlim(-max_effect * 1.1, max_effect * 1.1)

    plt.xlabel("Cohen's D")
    plt.title(f"Cohen's D por Feature — {tagger_label}\n({corpus1} vs {corpus2})")
    plt.grid(axis='x', alpha=0.3)
    plt.box(False)
    plt.subplots_adjust(left=0.3)
    plt.tight_layout()

    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  Gráfico salvo: '{out_path}'")


def run_analysis(output_dir: str, corpus1: str, corpus2: str, join: str = 'intersection'):
    out_dir = Path(output_dir).resolve()
    if not out_dir.exists():
        raise FileNotFoundError(f"Diretório de saída '{out_dir}' não encontrado.")

    # ── Análise 1: BiberPlus ─────────────────────────────────────────────────
    print("\n── KFA com features BiberPlus ──────────────────────────────────────")
    biber1 = out_dir / f"{corpus1}_biberfeatures_norm1000.csv"
    biber2 = out_dir / f"{corpus2}_biberfeatures_norm1000.csv"

    if not biber1.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {biber1}")
    if not biber2.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {biber2}")

    results_biber = kfa(str(biber1), str(biber2), join=join)
    print(f"  Features significativas (BiberPlus): {len(results_biber)}")

    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    print("\n  Top 10 features BiberPlus:")
    print(results_biber.head(10).to_string(index=False))

    _plot_kfa(results_biber, corpus1, corpus2, "BiberPlus",
              out_dir / f"key_features_biber_{corpus1}_vs_{corpus2}.png")
    results_biber.to_csv(
        out_dir / f"key_features_biber_results_{corpus1}_vs_{corpus2}.csv", index=False
    )

    # ── Análise 2: MFTE (não estendido) ─────────────────────────────────────
    print("\n── KFA com features MFTE (não estendido) ───────────────────────────")
    mfte1 = out_dir / f"{corpus1}_mfte_norm1000.csv"
    mfte2 = out_dir / f"{corpus2}_mfte_norm1000.csv"

    if not mfte1.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {mfte1}")
    if not mfte2.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {mfte2}")

    results_mfte = kfa(str(mfte1), str(mfte2), join=join)
    print(f"  Features significativas (MFTE não ext.): {len(results_mfte)}")

    print("\n  Top 10 features MFTE (não estendido):")
    print(results_mfte.head(10).to_string(index=False))

    _plot_kfa(results_mfte, corpus1, corpus2, "MFTE (não estendido)",
              out_dir / f"key_features_mfte_noext_{corpus1}_vs_{corpus2}.png")
    results_mfte.to_csv(
        out_dir / f"key_features_mfte_noext_results_{corpus1}_vs_{corpus2}.csv", index=False
    )

    print(f"\n  Todos os resultados salvos em: {out_dir}")


if __name__ == '__main__':
    run_analysis(OUTPUT_DIR, CORPUS1, CORPUS2, JOIN)
