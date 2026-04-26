from pathlib import Path
import warnings

import numpy as np
import pandas as pd


def pooled_std(group1, group2):
    """Calcula o desvio padrao combinado (pooled standard deviation) para dois grupos."""
    n1 = len(group1)
    n2 = len(group2)

    if n1 < 2 or n2 < 2:
        warnings.warn(
            f"Um dos grupos tem tamanho menor que 2 (n1={n1}, n2={n2}). Pooled std nao pode ser calculado.",
            UserWarning,
        )
        return np.nan

    std1 = np.std(group1, ddof=1)
    std2 = np.std(group2, ddof=1)

    if np.isnan(std1) or np.isnan(std2):
        warnings.warn("Desvio padrao de um ou ambos os grupos e NaN.", UserWarning)
        return np.nan

    numerator = (n1 - 1) * std1**2 + (n2 - 1) * std2**2
    denominator = n1 + n2 - 2

    if denominator <= 0:
        warnings.warn(
            f"Denominador (n1+n2-2 = {denominator}) e zero ou negativo. Pooled std nao pode ser calculado.",
            UserWarning,
        )
        return np.nan

    if numerator < 0:
        warnings.warn(f"Numerador ({numerator}) e negativo. Definindo pooled variance como 0.", UserWarning)
        pooled_variance = 0
    else:
        pooled_variance = numerator / denominator

    return np.sqrt(pooled_variance)


def cohens_d(group1, group2):
    """Calcula o tamanho do efeito (Cohen's D) entre dois grupos."""
    if len(group1) == 0 or len(group2) == 0:
        warnings.warn("Um ou ambos os grupos estao vazios.", UserWarning)
        return np.nan

    mean1 = np.mean(group1)
    mean2 = np.mean(group2)

    std_pooled = pooled_std(group1, group2)

    if std_pooled == 0 or np.isnan(std_pooled):
        warnings.warn("Desvio padrao combinado e zero ou NaN.", UserWarning)
        return np.nan

    return (mean1 - mean2) / std_pooled


def analyze_key_features(corpus1_path: str, corpus2_path: str, min_effect_size: float = 0.0, join: str = "union"):
    """Realiza a analise de key features (KFA) entre dois corpora norm1000.csv."""
    c1 = Path(corpus1_path).name
    c2 = Path(corpus2_path).name
    print(f"\n{'=' * 60}")
    print("  Key Feature Analysis (KFA)")
    print(f"  Corpus 1 : {c1}")
    print(f"  Corpus 2 : {c2}")
    print(f"  Metodo   : {join}  |  effect size minimo: {min_effect_size}")
    print(f"{'=' * 60}")

    print("  -> Lendo arquivos CSV...")
    df1 = pd.read_csv(corpus1_path)
    df2 = pd.read_csv(corpus2_path)
    print(f"     Corpus 1: {len(df1)} documentos, {len(df1.columns)} colunas")
    print(f"     Corpus 2: {len(df2)} documentos, {len(df2.columns)} colunas")

    ignore_cols = ["filename", "field", "section", "Words", "TTR"]
    features_df1 = set(col for col in df1.columns if col not in ignore_cols)
    features_df2 = set(col for col in df2.columns if col not in ignore_cols)

    join = join.lower()
    if join not in ("union", "intersection"):
        raise ValueError("Argumento 'join' invalido. Use 'union' ou 'intersection'.")

    if join == "union":
        feature_union = sorted(list(features_df1.union(features_df2)))
        if not feature_union:
            raise ValueError("Nenhuma feature encontrada nos corpora.")

        for col in feature_union:
            if col not in df1.columns:
                df1[col] = 0
            if col not in df2.columns:
                df2[col] = 0

        features_only_df1 = features_df1 - features_df2
        features_only_df2 = features_df2 - features_df1

        if features_only_df1:
            print(
                f"\n  Features apenas no Corpus 1 (preenchidas com 0 no Corpus 2): {sorted(features_only_df1)}"
            )
        if features_only_df2:
            print(
                f"  Features apenas no Corpus 2 (preenchidas com 0 no Corpus 1): {sorted(features_only_df2)}"
            )

        print(f"\n  -> Calculando Cohen's D para {len(feature_union)} features (uniao)...")
        feature_cols = feature_union
    else:
        feature_inter = sorted(list(features_df1.intersection(features_df2)))
        if not feature_inter:
            raise ValueError("Nenhuma feature em comum encontrada entre os dois corpora.")
        print(f"\n  -> Calculando Cohen's D para {len(feature_inter)} features (intersecao)...")
        feature_cols = feature_inter

    results = []

    for feature in feature_cols:
        values1 = df1[feature].values
        values2 = df2[feature].values

        values1 = np.where(np.isnan(values1), 0.0, values1)
        values2 = np.where(np.isnan(values2), 0.0, values2)

        if len(values1) < 2 or len(values2) < 2:
            print(f"  ! Feature '{feature}' ignorada - dados insuficientes (C1={len(values1)}, C2={len(values2)})")
            continue

        mean1 = np.mean(values1)
        mean2 = np.mean(values2)
        std1 = np.std(values1, ddof=1)
        std2 = np.std(values2, ddof=1)

        effect_size = cohens_d(values1, values2)

        if np.isnan(effect_size):
            print(f"  ! Feature '{feature}' ignorada - Cohen's D indefinido (medias: {mean1:.3f} vs {mean2:.3f})")
            continue

        if abs(effect_size) >= min_effect_size:
            results.append(
                {
                    "Feature": feature,
                    "Mean_Corpus1": mean1,
                    "Mean_Corpus2": mean2,
                    "Std_Corpus1": std1,
                    "Std_Corpus2": std2,
                    "Effect_Size": effect_size,
                    "Difference": mean1 - mean2,
                    "N_Corpus1": len(values1),
                    "N_Corpus2": len(values2),
                }
            )

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values(by="Effect_Size", key=abs, ascending=False)

    n_sig = len(results_df)
    n_total = len(feature_cols)
    print(f"  + KFA concluida: {n_sig}/{n_total} features com |d| >= {min_effect_size}")

    return results_df


def kfa(corpus1_path: str, corpus2_path: str, min_effect_size: float = 0.0, join: str = "union"):
    """Alias de alto nivel para Key Feature Analysis."""
    return analyze_key_features(
        corpus1_path=corpus1_path,
        corpus2_path=corpus2_path,
        min_effect_size=min_effect_size,
        join=join,
    )
