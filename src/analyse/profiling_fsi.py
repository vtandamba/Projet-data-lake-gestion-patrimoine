"""
Profiling BRONZE — Financial Secrecy Index (FSI 2026)
=====================================================
Objectif : ANALYSER les données brutes du FSI avant toute transformation.
On ne modifie rien ici : on observe (dimensions, colonnes, types, valeurs
manquantes, doublons, valeurs distinctes, statistiques de base).

Ce profiling sert à :
- comprendre la structure réelle des données ;
- repérer les problèmes de qualité à corriger en silver ;
- produire les chiffres "avant correction" demandés par le barème.

Entrée : data/bronze/fsi_2026_raw.csv
Sortie : affichage console (rien n'est écrit sur disque).

À placer dans : src/analyse/profiling_fsi.py
Lancer depuis la racine du projet :  python src/analyse/profiling_fsi.py
"""

from pathlib import Path
import pandas as pd

# ------------------------------------------------------------------
# Chemins
# ------------------------------------------------------------------
# Le script est dans src/analyse/ -> parents[2] = racine du projet
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRONZE_FILE = PROJECT_ROOT / "data" / "bronze" / "fsi_2026_raw.csv"


def ligne(titre=""):
    """Affiche une ligne de séparation lisible."""
    print("\n" + "=" * 60)
    if titre:
        print(titre)
        print("=" * 60)


def main():
    ligne("PROFILING BRONZE — FSI 2026")

    # --------------------------------------------------------------
    # Chargement
    # --------------------------------------------------------------
    if not BRONZE_FILE.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {BRONZE_FILE}\n"
            "Lance d'abord le script d'ingestion bronze."
        )

    df = pd.read_csv(BRONZE_FILE)

    # --------------------------------------------------------------
    # 1. Dimensions
    # --------------------------------------------------------------
    ligne("1. DIMENSIONS")
    print(f"Nombre de lignes   : {df.shape[0]}")
    print(f"Nombre de colonnes : {df.shape[1]}")

    # --------------------------------------------------------------
    # 2. Colonnes et types
    # --------------------------------------------------------------
    ligne("2. COLONNES ET TYPES")
    for col in df.columns:
        print(f" - {col:30} {df[col].dtype}")

    # --------------------------------------------------------------
    # 3. Valeurs manquantes
    # --------------------------------------------------------------
    ligne("3. VALEURS MANQUANTES (par colonne)")
    manquantes = df.isna().sum()
    for col, n in manquantes.items():
        pct = 100 * n / len(df)
        marque = "  <-- à vérifier" if n > 0 else ""
        print(f" - {col:30} {n:4} ({pct:.1f} %){marque}")

    # --------------------------------------------------------------
    # 4. Doublons
    # --------------------------------------------------------------
    ligne("4. DOUBLONS")
    nb_doublons = df.duplicated().sum()
    print(f"Lignes entièrement dupliquées : {nb_doublons}")
    # Doublon sur la clé pays (jurisdiction_id) : ne devrait pas exister
    if "jurisdiction_id" in df.columns:
        doublons_id = df["jurisdiction_id"].duplicated().sum()
        print(f"Doublons sur jurisdiction_id  : {doublons_id}")

    # --------------------------------------------------------------
    # 5. Valeurs distinctes par colonne
    # --------------------------------------------------------------
    ligne("5. VALEURS DISTINCTES (par colonne)")
    for col in df.columns:
        print(f" - {col:30} {df[col].nunique()} valeurs distinctes")

    # --------------------------------------------------------------
    # 6. Statistiques sur les colonnes clés
    # --------------------------------------------------------------
    ligne("6. STATISTIQUES — colonnes clés")
    for col in ["index_score", "index_value", "index_share", "rank", "gsw"]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            print(f"\n{col} :")
            print(f"   min    : {s.min()}")
            print(f"   max    : {s.max()}")
            print(f"   moyenne: {s.mean():.2f}")

    # --------------------------------------------------------------
    # 7. Aperçu
    # --------------------------------------------------------------
    ligne("7. APERÇU (5 premières lignes)")
    # On n'affiche que quelques colonnes pour rester lisible
    colonnes_apercu = [
        c for c in
        ["jurisdiction_id", "jurisdiction_name_fr", "index_score", "rank"]
        if c in df.columns
    ]
    print(df[colonnes_apercu].head(5).to_string(index=False))

    ligne("FIN DU PROFILING")


if __name__ == "__main__":
    main()
