import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from ttwtools.analysis import kfa

# Configurações (sem argparse) - ajuste essas variáveis conforme desejado
OUTPUT_DIR = 'out_test'   # pasta onde estão os arquivos norm1000 e onde salvar resultados
CORPUS1 = 'teste1'        # prefixo do primeiro corpus (ex.: teste1 -> teste1_biberfeatures_norm1000.csv)
CORPUS2 = 'teste2'        # prefixo do segundo corpus
JOIN = 'intersection'     # 'intersection' ou 'union'


def run_analysis(output_dir: str, corpus1: str, corpus2: str, join: str = 'intersection'):
    out_dir = Path(output_dir).resolve()
    if not out_dir.exists():
        raise FileNotFoundError(f"Diretório de saída '{out_dir}' não encontrado.")

    corpus1_path = out_dir / f"{corpus1}_biberfeatures_norm1000.csv"
    corpus2_path = out_dir / f"{corpus2}_biberfeatures_norm1000.csv"

    if not corpus1_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {corpus1_path}")
    if not corpus2_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {corpus2_path}")

    print("\nRealizando análise de Key Features...")
    results = kfa(str(corpus1_path), str(corpus2_path), join=join)

    print("\nResultados da análise de Key Features:")
    print("\nFeatures significativas encontradas:", len(results))

    print("\nTop 10 features mais distintivas:")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    print(results.head(10).to_string(index=False))

    # Visualização
    plt.figure(figsize=(15, max(8, len(results) * 0.25)))
    sns.set_style("whitegrid")

    results = results.sort_values('Effect_Size')

    bars = plt.barh(range(len(results)), results['Effect_Size'],
                    color=['#B7D2FF' if x < 0 else '#FFB7B7' for x in results['Effect_Size']])

    plt.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    plt.yticks(range(len(results)), results['Feature'])

    max_effect = max(abs(results['Effect_Size'].min()), abs(results['Effect_Size'].max()))
    plt.xlim(-max_effect * 1.1, max_effect * 1.1)

    plt.xlabel("Cohen's D")
    plt.title(f"Cohen's D por Feature ({corpus1} vs {corpus2})")
    plt.grid(axis='x', alpha=0.3)
    plt.box(False)
    plt.subplots_adjust(left=0.3)
    plt.tight_layout()

    out_plot = out_dir / f'key_features_analysis_{corpus1}_vs_{corpus2}.png'
    plt.savefig(out_plot, dpi=300, bbox_inches='tight')
    print(f"\nGráfico salvo como '{out_plot}'")

    out_csv = out_dir / f'key_features_analysis_results_{corpus1}_vs_{corpus2}.csv'
    results.to_csv(out_csv, index=False)
    print(f"Resultados detalhados salvos em '{out_csv}'")


if __name__ == '__main__':
    run_analysis(OUTPUT_DIR, CORPUS1, CORPUS2, JOIN)
