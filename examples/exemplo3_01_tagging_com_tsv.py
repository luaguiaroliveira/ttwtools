from pathlib import Path
from ttwtools.tagging import biberplus, normalize_biber_features


# ─────────────────────────────────────────────────
# CONFIGURAÇÕES — ajuste estas variáveis antes de rodar
# ─────────────────────────────────────────────────

# Pasta de saída onde todos os arquivos gerados serão salvos.
OUTPUT_DIR = 'out_exemplo3'

# Lista de corpora (pastas com arquivos .txt) a processar.
PASTAS = [
    "examples/test_corpora/CorIFAessaysNE_100",
    "examples/test_corpora/essays_bawe_somentetexto_100",
]

# Se True, copia os arquivos originais de cada corpus para OUTPUT_DIR/originals/<corpus>
COPY_ORIGINALS = True

# Se True, usa spaCy para tokenização (requer modelo spaCy instalado no ambiente)
USENLP = False

# ─────────────────────────────────────────────────


def choose_incremental_out(base_dir: Path, base_name: str = 'out') -> Path:
    """Retorna um caminho único para o diretório de saída, incrementando o sufixo se necessário."""
    candidate = base_dir / base_name
    if not candidate.exists():
        return candidate
    i = 1
    while True:
        candidate = base_dir / f"{base_name}_{i}"
        if not candidate.exists():
            return candidate
        i += 1


def run_tagging(output_dir=OUTPUT_DIR, pastas=PASTAS, copy_originals=COPY_ORIGINALS, usenlp=USENLP):
    """
    Processa cada corpus em `pastas`: extrai features Biber, salva arquivos
    taggeados e gera CSVs de contagem bruta e normalizada em `output_dir`.

    Parâmetros
    ----------
    output_dir : str | None
        Pasta de saída. Se None, cria 'out' incremental no diretório atual.
    pastas : list[str]
        Lista de caminhos para as pastas de corpus.
    copy_originals : bool
        Copiar arquivos originais do corpus para output_dir/originals/.
    usenlp : bool
        Usar spaCy para tokenização.
    """
    # ── Passo 1: determinar pasta de saída ─────────────────────────────────
    if output_dir:
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[Passo 1/3] Pasta de saída definida: {out_dir}")
    else:
        out_dir = choose_incremental_out(Path.cwd(), 'out')
        out_dir.mkdir(parents=True, exist_ok=False)
        print(f"[Passo 1/3] Pasta de saída criada automaticamente: {out_dir}")

    # ── Passo 2: processar cada corpus ─────────────────────────────────────
    print(f"\n[Passo 2/3] Processando {len(pastas)} corpus(a)...")
    for i, pasta in enumerate(pastas, start=1):
        print(f"\n  [{i}/{len(pastas)}] Corpus: '{pasta}'")
        print(f"         Extraindo features Biber e salvando tokens taggeados em '{out_dir}/{Path(pasta).name}_tagged/'...")

        biberplus(
            pasta,
            usenlp=usenlp,
            save_tagged=True,
            output_dir=out_dir,
            copy_originals=copy_originals,
        )

        # ── Passo 2b: normalizar por 1000 palavras ─────────────────────────
        pasta_name = Path(pasta).name
        rawcount_csv = out_dir / f"{pasta_name}_biberfeatures_rawcount.csv"
        print(f"         Normalizando contagens por 1000 palavras → '{rawcount_csv.stem.replace('_rawcount','')}_norm1000.csv'...")
        normalize_biber_features(rawcount_csv)

        print(f"  [{i}/{len(pastas)}] '{pasta}' concluído.")

    # ── Passo 3: resumo de arquivos gerados ────────────────────────────────
    print(f"\n[Passo 3/3] Resumo dos arquivos gerados em '{out_dir}':")
    for pasta in pastas:
        pasta_name = Path(pasta).name
        rawcount = out_dir / f"{pasta_name}_biberfeatures_rawcount.csv"
        norm     = out_dir / f"{pasta_name}_biberfeatures_norm1000.csv"
        tagged   = out_dir / f"{pasta_name}_tagged"
        print(f"  Corpus '{pasta_name}':")
        print(f"    Contagens brutas  : {rawcount}")
        print(f"    Norm. por 1000 p. : {norm}")
        print(f"    Tokens taggeados  : {tagged}/")
        if copy_originals:
            print(f"    Cópia original    : {out_dir}/originals/{pasta_name}/")

    return out_dir   # retorna o caminho para uso em scripts encadeados


if __name__ == '__main__':
    run_tagging()
