from pathlib import Path

import re
import pandas as pd
from tqdm.auto import tqdm
from biberplus.tagger import tag_text, load_config, load_pipeline


# Lazy spaCy loader: avoid importing at module import time so the module
# can be used even if spaCy is not installed. If a caller requests
# `usenlp=True`, we'll try to import and load the model on demand.
nltk_like_nlp = None


# NOTE: variable name is chosen to avoid shadowing potential local vars.
def extract_biber_features_from_folder(
    folder_path_str: str,
    configdict={"n_processes": 4, "function_words": False},
    usenlp=None,
    save_tagged: bool = False,
    output_dir: str = None,
    copy_originals: bool = False,
):
    """
    Processa todos os arquivos .txt em uma pasta, extrai as caracteristicas Biber
    e salva o resultado em um arquivo CSV.

    Args:
        folder_path_str (str): O caminho para a pasta contendo os arquivos de texto.
    """
    corpus_path = Path(folder_path_str).resolve()
    if not corpus_path.is_dir():
        print(f"Erro: A pasta '{corpus_path}' nao foi encontrada.")
        return

    if output_dir:
        base_out = Path(output_dir).resolve()
        base_out.mkdir(parents=True, exist_ok=True)
    else:
        base_out = corpus_path.parent

    csv_name = f"{corpus_path.name}_biberfeatures_rawcount.csv"
    csv_path = base_out / csv_name

    if save_tagged:
        tagged_dir = base_out / f"{corpus_path.name}_tagged"
        tagged_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Corpus : '{corpus_path.name}'")
    print(f"  Origem : {corpus_path}")
    print(f"  Saida  : {base_out}")
    print(f"{'=' * 60}")

    local_nlp = None
    if usenlp:
        print("  -> Carregando pipeline spaCy para tokenizacao...")
        try:
            import spacy

            try:
                local_nlp = spacy.load("en_core_web_trf", exclude=["ner"])
                print("    Pipeline carregado: en_core_web_trf")
            except Exception:
                try:
                    local_nlp = spacy.load("en_core_web_sm", exclude=["ner"])
                    print("    Pipeline carregado (fallback): en_core_web_sm")
                except Exception:
                    print("    Aviso: modelo spaCy nao encontrado; prosseguindo com tokenizacao por regex.")
                    local_nlp = None
            if local_nlp:
                local_nlp.max_length = 2_000_000
        except Exception:
            print("    Aviso: spaCy nao esta instalado no ambiente. Usando tokenizacao por regex.")
            local_nlp = None
    else:
        print("  -> Tokenizacao: regex (usenlp=False)")

    if copy_originals and output_dir:
        print(f"  -> Copiando arquivos originais para '{base_out}/originals/{corpus_path.name}/'...")
        try:
            import shutil

            originals_dir = base_out / "originals"
            originals_dir.mkdir(parents=True, exist_ok=True)
            dest = originals_dir / corpus_path.name
            if dest.exists():
                try:
                    shutil.copytree(corpus_path, dest, dirs_exist_ok=True)
                except TypeError:
                    for src in corpus_path.glob("*"):
                        dst = dest / src.name
                        if src.is_dir():
                            try:
                                shutil.copytree(src, dst)
                            except Exception:
                                pass
                        else:
                            try:
                                dst.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(src, dst)
                            except Exception:
                                pass
            else:
                try:
                    shutil.copytree(corpus_path, dest)
                except Exception:
                    dest.mkdir(parents=True, exist_ok=True)
                    for src in corpus_path.glob("*"):
                        try:
                            if src.is_dir():
                                shutil.copytree(src, dest / src.name)
                            else:
                                shutil.copy2(src, dest / src.name)
                        except Exception:
                            pass
        except Exception:
            pass

    all_records_flat = []
    file_list = list(corpus_path.glob("*.txt"))

    if not file_list:
        print(f"  Aviso: Nenhum arquivo .txt encontrado em '{corpus_path}'.")
        return

    print(f"  -> Extraindo features Biber de {len(file_list)} arquivo(s)...")
    if save_tagged:
        print(f"     Tokens taggeados serao salvos em: {tagged_dir}/")

    for txt_path in tqdm(file_list, desc=f"  Analisando {corpus_path.name}", unit="doc"):
        text = txt_path.read_text(encoding="utf-8", errors="ignore")
        text = re.sub(r"<[^>]*>", "", text)
        filename = txt_path.name

        doc = None
        if local_nlp:
            try:
                doc = local_nlp(text)
            except Exception:
                doc = None

        if doc is not None:
            list_of_words = [token.text for token in doc if token.is_alpha]
        else:
            list_of_words = re.findall(r"\b[A-Za-z]+\b", text)
        list_of_unique_words = list(set(list_of_words))

        n_words = len(list_of_words)
        n_unique_words = len(list_of_unique_words)
        ttr = n_unique_words / n_words if n_words > 0 else 0

        config = load_config()
        config.update(configdict)
        try:
            pipeline = load_pipeline(config)
        except OSError as exc:
            msg = str(exc)
            if "en_core_web_sm" in msg or "[E050]" in msg:
                raise RuntimeError(
                    "spaCy model 'en_core_web_sm' is required but not installed. "
                    "Install it with: python -m spacy download en_core_web_sm"
                ) from exc
            raise

        if usenlp and local_nlp is not None:
            pipeline = local_nlp

        tagged_words = tag_text(text, pipeline=pipeline, config=config)

        tag_counts = pd.Series(sum([word["tags"] for word in tagged_words], [])).value_counts()

        if save_tagged:
            tagged_file = tagged_dir / f"{txt_path.stem}_tagged.tsv"
            try:
                with tagged_file.open("w", encoding="utf-8", newline="") as outfh:
                    outfh.write(f"# filename: {filename}\n")
                    outfh.write("token\ttags\n")
                    for i, wdict in enumerate(tagged_words):
                        token_text = None
                        if isinstance(wdict, dict):
                            token_text = wdict.get("word") or wdict.get("text") or wdict.get("token")
                        if not token_text:
                            token_text = doc[i].text if i < len(doc) else ""
                        tags = wdict.get("tags") if isinstance(wdict, dict) else (wdict if isinstance(wdict, list) else [])
                        safe_token = token_text.replace("\t", " ").replace("\n", " ").replace("\r", "")
                        outfh.write(f"{safe_token}\t{' '.join(tags)}\n")
            except Exception:
                pass

        field_name = filename.split(".")[1] if len(filename.split(".")) > 1 else "unknown"
        section_name = filename.split(".")[3] if len(filename.split(".")) > 3 else "unknown"

        record = {
            "filename": filename,
            "field": field_name,
            "section": section_name,
            "Words": n_words,
            "TTR": ttr,
        }

        for tag, count in tag_counts.items():
            record[f"{tag}"] = count

        all_records_flat.append(record)

    if all_records_flat:
        df = pd.DataFrame(all_records_flat)
        df.to_csv(csv_path, index=False)
        print(f"  + Contagens brutas salvas: '{csv_path.name}' ({len(df)} documentos)")
    else:
        print("  Aviso: Nenhum dado foi processado.")


def normalize_biber_features(csv_path_str: str, decimal_places=None):
    """
    Le um arquivo CSV com contagens brutas de caracteristicas Biber e cria uma nova versao
    com os valores normalizados por 1000 palavras.

    Args:
        csv_path_str (str): O caminho para o arquivo CSV com as contagens brutas.
    """
    csv_path = Path(csv_path_str).resolve()
    if not csv_path.is_file():
        print(f"Erro: O arquivo '{csv_path}' nao foi encontrado.")
        return

    norm_csv_name = csv_path.stem.replace("_rawcount", "") + "_norm1000.csv"
    norm_csv_path = csv_path.parent / norm_csv_name

    print(f"\n{'-' * 60}")
    print(f"  Normalizando: '{csv_path.name}'")
    print("  -> Dividindo cada contagem por numero de palavras x 1000")
    print(f"  -> Saida: '{norm_csv_name}'")

    df = pd.read_csv(csv_path)

    cols_to_normalize = [
        col for col in df.columns if col not in ["filename", "field", "section", "Words", "TTR"]
    ]

    df_norm = df.copy()

    for col in cols_to_normalize:
        df_norm[col] = (df[col] * 1000) / df["Words"]
        if decimal_places is not None:
            df_norm[col] = df_norm[col].round(decimal_places)

    df_norm.to_csv(norm_csv_path, index=False)
    print(f"  + Normalizacao concluida: '{norm_csv_path.name}'")


def biberplus(
    folder_path_str: str,
    configdict={"n_processes": 4, "function_words": False},
    usenlp=None,
    save_tagged: bool = False,
    output_dir: str = None,
    copy_originals: bool = False,
):
    """Alias de alto nivel para a extracao/tagging BiberPlus."""
    return extract_biber_features_from_folder(
        folder_path_str=folder_path_str,
        configdict=configdict,
        usenlp=usenlp,
        save_tagged=save_tagged,
        output_dir=output_dir,
        copy_originals=copy_originals,
    )
