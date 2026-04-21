from pathlib import Path
import ttwtools


# Esta parte permite testar o módulo diretamente
print("--- Executando ttwtools.biberplus() em modo de teste ---")

# Localiza a pasta test_corpora relativa a este script
_HERE = Path(__file__).resolve().parent
_TEST_CORPORA = _HERE / 'test_corpora'
_OUT_DIR = _HERE / 'out_exemplo1'

# Lista de pastas para processar
# Adicione aqui as pastas que você quer analisar
pastas_para_processar = [
    str(_TEST_CORPORA / 'subcorpus_introduction_aphd'),
    str(_TEST_CORPORA / 'subcorpus_introduction_articles'),
    # str(_TEST_CORPORA / 'teste_corpus'),
]

_OUT_DIR.mkdir(parents=True, exist_ok=True)

for pasta in pastas_para_processar:
    # Processa os arquivos e gera o CSV com contagens brutas
    ttwtools.biberplus(pasta, usenlp=False, output_dir=_OUT_DIR)

    # Normaliza as características por 1000 palavras
    rawcount_csv = _OUT_DIR / f"{Path(pasta).name}_biberfeatures_rawcount.csv"
    ttwtools.normalize_biber_features(rawcount_csv)

print("\n--- Teste concluído ---")