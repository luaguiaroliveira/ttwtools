import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from ttwtools.analysis import kfa


def run_analysis(output_dir: str, corpus1: str, corpus2: str, join: str = 'intersection'):
    out_dir = Path(output_dir).resolve()
    if not out_dir.exists():
        print(f"Diretório de saída '{out_dir}' não encontrado.")
        return

    corpus1_path = out_dir / f"{corpus1}_biberfeatures_norm1000.csv"
    corpus2_path = out_dir / f"{corpus2}_biberfeatures_norm1000.csv"

    if not corpus1_path.exists():
        print(f"Arquivo não encontrado: {corpus1_path}")
        return
    if not corpus2_path.exists():
        print(f"Arquivo não encontrado: {corpus2_path}")
        return

    # Realizar análise de Key Features
    print("\nRealizando análise de Key Features...")
    results = kfa(str(corpus1_path), str(corpus2_path), join=join)

    # Exibir resultados
    print("\nResultados da análise de Key Features:")
    print("\nFeatures significativas encontradas:", len(results))

    # Mostrar resumo das features mais distintivas
    print("\nTop 10 features mais distintivas:")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    print(results.head(10).to_string(index=False))

    # Criar visualização
    plt.figure(figsize=(15, max(8, len(results) * 0.25)))  # Altura adaptativa baseada no número de features
    sns.set_style("whitegrid")

    # Ordenar resultados por Effect_Size
    results = results.sort_values('Effect_Size')

    plt.barh(range(len(results)), results['Effect_Size'],
             color=['#B7D2FF' if x < 0 else '#FFB7B7' for x in results['Effect_Size']])

    # Customizar o gráfico
    plt.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    plt.yticks(range(len(results)), results['Feature'])

    # Ajustar limites do eixo x para ser simétrico
    max_effect = max(abs(results['Effect_Size'].min()), abs(results['Effect_Size'].max()))
    plt.xlim(-max_effect * 1.1, max_effect * 1.1)

    # Adicionar rótulos e título
    plt.xlabel("Cohen's D")
    plt.title(f"Cohen's D por Feature ({corpus1} vs {corpus2})")

    # Adicionar grid vertical
    plt.grid(axis='x', alpha=0.3)

    # Remover linhas do frame
    plt.box(False)

    # Ajustar layout para não cortar os labels
    plt.subplots_adjust(left=0.3)

    # Ajustar layout
    plt.tight_layout()

    # Salvar o gráfico e resultados no diretório de saída
    out_plot = out_dir / f'key_features_analysis_{corpus1}_vs_{corpus2}.png'
    plt.savefig(out_plot, dpi=300, bbox_inches='tight')
    print(f"\nGráfico salvo como '{out_plot}'")

    out_csv = out_dir / f'key_features_analysis_results_{corpus1}_vs_{corpus2}.csv'
    results.to_csv(out_csv, index=False)
    print(f"Resultados detalhados salvos em '{out_csv}'")


def main():
    parser = argparse.ArgumentParser(description='Análise de Key Features (gráfico)')
    parser.add_argument('--output-dir', '-o', default='examples/test_corpora',
                        help='Diretório onde estão os arquivos norm1000.csv e onde salvar os resultados')
    parser.add_argument('--corpus1', default='subcorpus_introduction_aphd',
                        help='Nome do primeiro corpus (prefixo dos arquivos)')
    parser.add_argument('--corpus2', default='subcorpus_introduction_articles',
                        help='Nome do segundo corpus (prefixo dos arquivos)')
    parser.add_argument('--join', default='intersection', choices=['intersection', 'union'],
                        help='Usar interseção ou união de features')
    args = parser.parse_args()
    run_analysis(args.output_dir, args.corpus1, args.corpus2, args.join)


if __name__ == '__main__':
    main()