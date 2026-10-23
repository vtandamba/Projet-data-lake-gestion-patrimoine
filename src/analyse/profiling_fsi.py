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

IMPORTANT (piège pandas) : le code ISO du pays "NA" (Namibie) est lu par
défaut comme une valeur manquante. On neutralise ce comportement avec
na_values / keep_default_na pour que la Namibie ne disparaisse pas.

Entrée : data/bronze/fsi_2026_raw.csv
Sortie : affichage console + rapport écrit dans reports/fsi_profiling.txt

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

# Un seul dossier reports/ à la racine, fichiers nommés <source>_<étape>.txt
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORT_FILE = REPORTS_DIR / "fsi_profiling.txt"

# On accumule toutes les lignes pour les afficher ET les écrire dans le rapport.
_lignes_rapport = []


def sortie(texte=""):
    """Affiche à l'écran et mémorise la ligne pour le rapport."""
    print(texte)
    _lignes_rapport.append(texte)


def titre(t):
    sortie("\n" + "=" * 60)
    sortie(t)
    sortie("=" * 60)


def main():
    titre("PROFILING BRONZE — FSI 2026")

    # --------------------------------------------------------------
    # Chargement
    # --------------------------------------------------------------
    if not BRONZE_FILE.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {BRONZE_FILE}\n"
            "Lance d'abord le script d'ingestion bronze."
        )

    # keep_default_na=False + na_values ciblés :
    #   - "NA" (Namibie) reste la chaîne "NA" et n'est pas pris pour un vide
    #   - les colonnes numériques restent correctement typées
    df = pd.read_csv(
        BRONZE_FILE,
        keep_default_na=False,
        na_values=["", "NaN", "null"],
    )

    # --------------------------------------------------------------
    # 1. Dimensions
    # --------------------------------------------------------------
    titre("1. DIMENSIONS")
    sortie(f"Nombre de lignes   : {df.shape[0]}")
    sortie(f"Nombre de colonnes : {df.shape[1]}")

    # --------------------------------------------------------------
    # 2. Colonnes et types
    # --------------------------------------------------------------
    titre("2. COLONNES ET TYPES")
    for col in df.columns:
        sortie(f" - {col:30} {df[col].dtype}")

    # --------------------------------------------------------------
    # 3. Valeurs manquantes
    # --------------------------------------------------------------
    titre("3. VALEURS MANQUANTES (par colonne)")
    for col, n in df.isna().sum().items():
        pct = 100 * n / len(df)
        marque = "  <-- à vérifier" if n > 0 else ""
        sortie(f" - {col:30} {n:4} ({pct:.1f} %){marque}")

    # --------------------------------------------------------------
    # 4. Doublons
    # --------------------------------------------------------------
    titre("4. DOUBLONS")
    sortie(f"Lignes entièrement dupliquées : {df.duplicated().sum()}")
    if "jurisdiction_id" in df.columns:
        sortie(f"Doublons sur jurisdiction_id  : {df['jurisdiction_id'].duplicated().sum()}")

    # --------------------------------------------------------------
    # 5. Valeurs distinctes par colonne
    # --------------------------------------------------------------
    titre("5. VALEURS DISTINCTES (par colonne)")
    for col in df.columns:
        sortie(f" - {col:30} {df[col].nunique()} valeurs distinctes")

    # --------------------------------------------------------------
    # 6. Statistiques sur les colonnes clés
    # --------------------------------------------------------------
    titre("6. STATISTIQUES — colonnes clés")
    for col in ["index_score", "index_value", "index_share", "rank", "gsw"]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            sortie(f"\n{col} :")
            sortie(f"   min    : {s.min()}")
            sortie(f"   max    : {s.max()}")
            sortie(f"   moyenne: {s.mean():.2f}")

    # --------------------------------------------------------------
    # 7. Aperçu
    # --------------------------------------------------------------
    titre("7. APERÇU (5 premières lignes)")
    colonnes_apercu = [
        c for c in
        ["jurisdiction_id", "jurisdiction_name_fr", "index_score", "rank"]
        if c in df.columns
    ]
    sortie(df[colonnes_apercu].head(5).to_string(index=False))

    titre("FIN DU PROFILING")

    # --------------------------------------------------------------
    # Écriture du rapport
    # --------------------------------------------------------------
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(_lignes_rapport), encoding="utf-8")
    print(f"\n[OK] Rapport enregistré : {REPORT_FILE}")


if __name__ == "__main__":
    main()