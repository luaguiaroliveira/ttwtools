from pathlib import Path
from ttwtools.tagging import biberplus, normalize_biber_features


# Esta parte permite testar o módulo diretamente
print("--- Executando ttwtools.tagging.biberplus() em modo de teste ---")

# Lista de pastas para processar
# Adicione aqui as pastas que você quer analisar
pastas_para_processar = [
    "subcorpus_introduction_aphd",
    "subcorpus_introduction_articles",
    # "examples/test_corpora/teste_corpus"
]

for pasta in pastas_para_processar:
    # Processa os arquivos e gera o CSV com contagens brutas
    #configdict = {'n_processes': 4, 'function_words': False, 'grieve_clarke': False}
    biberplus(pasta, usenlp=True)#configdict=configdict)

    # Normaliza as características por 1000 palavras
    pasta_path = Path(pasta).resolve()
    rawcount_csv = pasta_path.parent / f"{pasta_path.name}_biberfeatures_rawcount.csv"
    normalize_biber_features(rawcount_csv)
    
print("\n--- Teste concluído ---")