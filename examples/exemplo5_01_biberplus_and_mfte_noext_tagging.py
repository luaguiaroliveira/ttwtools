from pathlib import Path
import ttwtools


# ─────────────────────────────────────────────────
# CONFIGURAÇÕES
# ─────────────────────────────────────────────────

OUTPUT_DIR = 'out_exemplo5'

PASTAS = [
    "test_corpora/CorIFAessaysNE_100",
    "test_corpora/essays_bawe_somentetexto_100",
]

COPY_ORIGINALS = True
USENLP = False      # spaCy para BiberPlus
USE_GPU = None      # GPU para MFTE: None = auto-detectar

# MFTE versão não estendida — apenas as features Biber originais
EXTENDED = False

# ─────────────────────────────────────────────────


def choose_incremental_out(base_dir: Path, base_name: str = 'out') -> Path:
    candidate = base_dir / base_name
    if not candidate.exists():
        return candidate
    i = 1
    while True:
        candidate = base_dir / f"{base_name}_{i}"
        if not candidate.exists():
            return candidate
        i += 1


def run_tagging(
    output_dir=OUTPUT_DIR,
    pastas=PASTAS,
    copy_originals=COPY_ORIGINALS,
    usenlp=USENLP,
    use_gpu=USE_GPU,
):
    """
    Processa cada corpus com BiberPlus e com MFTE (não estendido), gerando
    CSVs de contagem bruta e normalizada por 1000 palavras para cada tagger.

    Parâmetros
    ----------
    output_dir : str | None
    pastas : list[str]
    copy_originals : bool
    usenlp : bool — usar spaCy no BiberPlus
    use_gpu : bool | None — GPU para Stanza/MFTE
    """
    if output_dir:
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[Passo 1/4] Pasta de saída definida: {out_dir}")
    else:
        out_dir = choose_incremental_out(Path.cwd(), 'out')
        out_dir.mkdir(parents=True, exist_ok=False)
        print(f"[Passo 1/4] Pasta de saída criada automaticamente: {out_dir}")

    # ── Passo 2: BiberPlus ────────────────────────────────────────────────
    print(f"\n[Passo 2/4] Tagging com BiberPlus ({len(pastas)} corpus(a))...")
    for i, pasta in enumerate(pastas, start=1):
        pasta_name = Path(pasta).name
        print(f"\n  [{i}/{len(pastas)}] BiberPlus → '{pasta_name}'")

        ttwtools.biberplus(
            pasta,
            usenlp=usenlp,
            save_tagged=True,
            output_dir=out_dir,
            copy_originals=copy_originals,
        )

        rawcount_csv = out_dir / f"{pasta_name}_biberfeatures_rawcount.csv"
        ttwtools.normalize_biber_features(rawcount_csv)
        print(f"  [{i}/{len(pastas)}] BiberPlus '{pasta_name}' concluído.")

    # ── Passo 3: MFTE (não estendido) ────────────────────────────────────
    print(f"\n[Passo 3/4] Tagging com MFTE (extended=False) ({len(pastas)} corpus(a))...")
    for i, pasta in enumerate(pastas, start=1):
        pasta_name = Path(pasta).name
        print(f"\n  [{i}/{len(pastas)}] MFTE → '{pasta_name}'")

        ttwtools.mfte(
            pasta,
            use_gpu=use_gpu,
            extended=False,
            save_tagged=True,
            output_dir=out_dir,
            copy_originals=False,   # já copiado pelo BiberPlus acima
        )

        rawcount_csv = out_dir / f"{pasta_name}_mfte_rawcount.csv"
        ttwtools.normalize_mfte_features(rawcount_csv)
        print(f"  [{i}/{len(pastas)}] MFTE '{pasta_name}' concluído.")

    # ── Passo 4: resumo ──────────────────────────────────────────────────
    print(f"\n[Passo 4/4] Resumo dos arquivos gerados em '{out_dir}':")
    for pasta in pastas:
        pasta_name = Path(pasta).name
        print(f"  Corpus '{pasta_name}':")
        print(f"    BiberPlus rawcount : {out_dir / f'{pasta_name}_biberfeatures_rawcount.csv'}")
        print(f"    BiberPlus norm1000 : {out_dir / f'{pasta_name}_biberfeatures_norm1000.csv'}")
        print(f"    MFTE rawcount      : {out_dir / f'{pasta_name}_mfte_rawcount.csv'}")
        print(f"    MFTE norm1000      : {out_dir / f'{pasta_name}_mfte_norm1000.csv'}")
        print(f"    Tokens (BiberPlus) : {out_dir / f'{pasta_name}_tagged'}/")
        if copy_originals:
            print(f"    Cópia original     : {out_dir}/originals/{pasta_name}/")

    return out_dir


if __name__ == '__main__':
    run_tagging()
